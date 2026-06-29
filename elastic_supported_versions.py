#!/usr/bin/env python3
"""
Report Elastic product minor lines that should receive maintenance/security fixes.

Policy implemented from Elastic's Product & Version End of Life Policy:
  * a major release is maintained for the longer of 30 months from its GA or
    18 months from the next major GA;
  * within maintained majors, Elastic maintains the two newest minor releases
    of the current major and the final minor release of the previous major.

By default this script reads GitHub's machine-readable releases APIs and the
Elastic EOL policy page:

    python3 elastic_supported_versions.py
    python3 elastic_supported_versions.py --json
    python3 elastic_supported_versions.py --at 2026-05-06
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable


GITHUB_RELEASES_API_TEMPLATE = "https://api.github.com/repos/{repo}/releases"
ELASTIC_EOL_URL = "https://www.elastic.co/support/eol"
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
DATE_RE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})")
DEFAULT_CA_FILES = (
    # Some packaged Python/OpenSSL builds point at non-standard CA locations.
    # These are common Linux bundle paths we can safely try before asking users
    # to pass --ca-file or fall back to --insecure.
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/ca-bundle.pem",
    "/etc/ssl/cert.pem",
)
DOCKER_HUB_REPLICATION_IMAGES = (
    ("elasticsearch", "elastic/elasticsearch"),
    ("filebeat", "elastic/filebeat"),
    ("kibana", "elastic/kibana"),
    ("logstash", "elastic/logstash"),
    ("metricbeat", "elastic/metricbeat"),
)
DEFAULT_REPLICATION_RULE_PREFIX = "harbor-elastic"
ECK_OPERATOR_REPLICATION_RULE_SUFFIX = "eckoperator"
ECK_OPERATOR_IMAGE = "elastic/eck-operator"
MAIL_RELEASE_MAJORS = (8, 9)


@dataclass(frozen=True)
class ProductConfig:
    name: str
    github_repo: str
    release_page: str
    eol_terms: str


@dataclass(frozen=True)
class Release:
    version: str
    major: int
    minor: int
    patch: int
    published_at: dt.date
    url: str

    @property
    def minor_line(self) -> str:
        return f"{self.major}.{self.minor}.x"


PRODUCTS = (
    ProductConfig(
        name="Elasticsearch",
        github_repo="elastic/elasticsearch",
        release_page="https://github.com/elastic/elasticsearch/releases",
        eol_terms="core_stack",
    ),
    ProductConfig(
        name="Elastic Cloud on Kubernetes",
        github_repo="elastic/cloud-on-k8s",
        release_page="https://github.com/elastic/cloud-on-k8s/releases",
        eol_terms="cloud_on_k8s",
    ),
)


def bundled_ca_file() -> str | None:
    """Return the first known system CA bundle that exists on this host."""
    for path in DEFAULT_CA_FILES:
        if os.path.isfile(path):
            return path
    return None


def fetch_text(
    url: str,
    *,
    accept: str = "text/html",
    insecure: bool = False,
    ca_file: str | None = None,
    bearer_token: str | None = None,
) -> str:
    headers = {
        "Accept": accept,
        "User-Agent": "elastic-maintenance-check/1.0",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    context = None
    if insecure:
        context = ssl._create_unverified_context()
    elif ca_file:
        # Explicit user choice wins over all auto-detected CA paths.
        context = ssl.create_default_context(cafile=ca_file)
    else:
        # Keep normal TLS verification enabled, but use a common system bundle
        # when Python's compiled-in OpenSSL path is missing or incomplete.
        fallback_ca_file = bundled_ca_file()
        if fallback_ca_file:
            context = ssl.create_default_context(cafile=fallback_ca_file)
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset)


def parse_iso_date(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def parse_elastic_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%d-%b-%Y").date()


def add_months(value: dt.date, months: int) -> dt.date:
    """Add calendar months while clamping the day for short target months."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    return dt.date(year, month, min(value.day, days_in_month))


def fetch_releases(
    repo: str,
    max_pages: int = 20,
    *,
    insecure: bool = False,
    ca_file: str | None = None,
    github_token: str | None = None,
) -> list[Release]:
    releases: list[Release] = []
    for page in range(1, max_pages + 1):
        # The HTML releases page is rendered for humans and can omit older
        # entries behind pagination. The API gives stable JSON records instead.
        url = f"{GITHUB_RELEASES_API_TEMPLATE.format(repo=repo)}?per_page=100&page={page}"
        payload = json.loads(
            fetch_text(
                url,
                accept="application/vnd.github+json",
                insecure=insecure,
                ca_file=ca_file,
                bearer_token=github_token,
            )
        )
        if not payload:
            break

        for item in payload:
            match = VERSION_RE.match(item.get("tag_name", ""))
            if not match or item.get("prerelease") or item.get("draft"):
                # Elastic may publish prereleases or drafts; maintenance policy
                # decisions should be based only on stable public releases.
                continue

            major, minor, patch = (int(part) for part in match.groups())
            releases.append(
                Release(
                    version=f"{major}.{minor}.{patch}",
                    major=major,
                    minor=minor,
                    patch=patch,
                    published_at=parse_iso_date(item["published_at"]),
                    url=item["html_url"],
                )
            )

    if not releases:
        raise RuntimeError(f"No stable releases found for {repo} via GitHub releases API")
    return sorted(releases, key=lambda release: (release.major, release.minor, release.patch))


def strip_html_to_text(markup: str) -> str:
    """Convert Elastic's policy page HTML into searchable plain text."""
    text = re.sub(r"(?i)<(br|/p|/tr|/li|/h[1-6])\b[^>]*>", "\n", markup)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text)


def find_core_stack_terms(eol_html: str) -> dict[int, dt.date]:
    """Extract published maintenance end dates for Core Stack major series."""
    text = strip_html_to_text(eol_html)
    terms: dict[int, dt.date] = {}

    # The page has several product families. Elasticsearch belongs to the
    # "Core Stack" rows, so avoid accidentally reading APM agent or retired
    # product dates that use the same x.y.x notation.
    for section_start, section_end in [
        ("Current Versions", "Prior Versions"),
        ("Prior Versions", "Retired Software Products"),
    ]:
        if section_start not in text or section_end not in text:
            continue
        section = text.split(section_start, 1)[1].split(section_end, 1)[0]
        if "Core Stack" not in section:
            continue
        core = section.split("Core Stack", 1)[1].split("Orchestration", 1)[0]
        for series, date_text in re.findall(r"\b(\d+)(?:\.\d+)?\.x\s+" + DATE_RE.pattern, core):
            terms[int(series)] = parse_elastic_date(date_text)

    return terms


def find_cloud_on_k8s_terms(eol_html: str) -> dict[int, dt.date]:
    """Extract published maintenance end dates for Elastic Cloud on Kubernetes."""
    text = strip_html_to_text(eol_html)
    terms: dict[int, dt.date] = {}

    if "Elastic Cloud on Kubernetes" not in text:
        return terms

    # Current versions table: "Elastic Cloud on Kubernetes 3.x 15-Oct-2027 ..."
    for series, date_text in re.findall(
        r"Elastic Cloud on Kubernetes(?:\^\{\d+\})?\s+(\d+)\.x\s+" + DATE_RE.pattern,
        text,
    ):
        terms[int(series)] = parse_elastic_date(date_text)

    # Prior versions table: the first ECK line includes the product name, while
    # older prior lines can follow as plain version rows, e.g. "1.9.x ...".
    prior = text.split("Prior Versions", 1)[1].split("APM Agents", 1)[0] if "Prior Versions" in text else ""
    if "Elastic Cloud on Kubernetes" in prior:
        eck_prior = prior.split("Elastic Cloud on Kubernetes", 1)[1]
        for series, date_text in re.findall(r"\b(\d+)(?:\.\d+)?\.x\s+" + DATE_RE.pattern, eck_prior):
            terms[int(series)] = parse_elastic_date(date_text)

    return terms


def eol_terms_for_product(eol_html: str, product: ProductConfig) -> dict[int, dt.date]:
    if product.eol_terms == "core_stack":
        return find_core_stack_terms(eol_html)
    if product.eol_terms == "cloud_on_k8s":
        return find_cloud_on_k8s_terms(eol_html)
    raise ValueError(f"Unknown EOL term parser: {product.eol_terms}")


def first_release_date(releases: Iterable[Release], major: int) -> dt.date | None:
    major_releases = [release for release in releases if release.major == major]
    # GA normally corresponds to x.0.0. If the API window does not include that
    # tag, use the earliest release we have for that major as a conservative
    # fallback; the EOL page later overrides calculated terms when available.
    zero = [release for release in major_releases if release.minor == 0 and release.patch == 0]
    candidates = zero or major_releases
    return min((release.published_at for release in candidates), default=None)


def calculated_major_terms(releases: list[Release]) -> dict[int, dt.date]:
    terms: dict[int, dt.date] = {}
    majors = sorted({release.major for release in releases})
    for major in majors:
        ga = first_release_date(releases, major)
        if ga is None:
            continue

        # Elastic's base rule: a major is maintained for the later of 30 months
        # from its GA or 18 months from the next major's GA.
        candidates = [add_months(ga, 30)]
        next_ga = first_release_date(releases, major + 1)
        if next_ga:
            candidates.append(add_months(next_ga, 18))
        terms[major] = max(candidates)
    return terms


def newest_patch_by_minor(releases: list[Release]) -> dict[tuple[int, int], Release]:
    newest: dict[tuple[int, int], Release] = {}
    for release in releases:
        key = (release.major, release.minor)
        # We report minor lines, but point users at the newest patch available
        # within each line because that is the practical upgrade target.
        if key not in newest or release.patch > newest[key].patch:
            newest[key] = release
    return newest


def maintained_lines(releases: list[Release], terms: dict[int, dt.date], at: dt.date) -> list[dict[str, str]]:
    latest_by_minor = newest_patch_by_minor(releases)
    current_major = max(release.major for release in releases)
    previous_major = current_major - 1

    result: list[dict[str, str]] = []

    def add_line(release: Release, reason: str) -> None:
        eom = terms.get(release.major)
        if eom is None or eom < at:
            # The minor-line rule is subject to the major still being inside
            # its maintenance term.
            return
        result.append(
            {
                "minor_line": release.minor_line,
                "latest_release": release.version,
                "released": release.published_at.isoformat(),
                "end_of_maintenance": eom.isoformat(),
                "reason": reason,
                "url": release.url,
            }
        )

    current_minors = sorted(
        {minor for major, minor in latest_by_minor if major == current_major},
        reverse=True,
    )
    # Current major: only the two newest minor lines receive maintenance.
    for minor in current_minors[:2]:
        add_line(
            latest_by_minor[(current_major, minor)],
            "one of the two newest minor releases of the current major",
        )

    previous_minors = sorted({minor for major, minor in latest_by_minor if major == previous_major})
    if previous_minors:
        # Previous major: only the final minor line receives maintenance, and
        # only while that major's maintenance term is still active.
        final_minor = previous_minors[-1]
        add_line(
            latest_by_minor[(previous_major, final_minor)],
            "final minor release of the previous major",
        )

    return result


def build_product_output(
    product: ProductConfig,
    *,
    eol_html: str | None,
    at: dt.date,
    max_pages: int,
    insecure: bool,
    ca_file: str | None,
    github_token: str | None,
    ignore_eol_page: bool,
) -> dict[str, object]:
    releases = fetch_releases(
        product.github_repo,
        max_pages=max_pages,
        insecure=insecure,
        ca_file=ca_file,
        github_token=github_token,
    )
    terms = calculated_major_terms(releases)
    source_notes = [f"GitHub releases API ({product.github_repo})"]

    if not ignore_eol_page and eol_html is not None:
        # Elastic may publish table-specific exceptions or later dates.
        # Prefer those official values over dates inferred from releases.
        terms.update(eol_terms_for_product(eol_html, product))
        source_notes.append("Elastic EOL policy page")

    return {
        "product": product.name,
        "release_page": product.release_page,
        "sources": source_notes,
        "maintained_minor_lines": maintained_lines(releases, terms, at),
    }


def replication_rule_name(prefix: str, suffix: str) -> str:
    return f"{prefix}-{suffix}" if prefix else suffix


def docker_pull_commands(version: str, *, replication_rule_prefix: str) -> list[dict[str, str]]:
    return [
        {
            "replication_rule": replication_rule_name(replication_rule_prefix, suffix),
            "registry": "Docker Hub",
            "image": image,
            "command": f"docker pull {image}:{version}",
        }
        for suffix, image in DOCKER_HUB_REPLICATION_IMAGES
    ]


def version_key(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.match(version)
    if not match:
        raise ValueError(f"Invalid release version: {version}")
    return tuple(int(part) for part in match.groups())


def latest_mail_release_lines(
    maintained_minor_lines: list[object],
    *,
    majors: tuple[int, ...] = MAIL_RELEASE_MAJORS,
) -> list[dict[str, str]]:
    latest_by_major: dict[int, dict[str, str]] = {}

    for line in maintained_minor_lines:
        if not isinstance(line, dict):
            continue
        version = str(line["latest_release"])
        major, minor, patch = version_key(version)
        if major not in majors:
            continue
        current = latest_by_major.get(major)
        if current is None or (major, minor, patch) > version_key(str(current["latest_release"])):
            latest_by_major[major] = {str(key): str(value) for key, value in line.items()}

    return [
        latest_by_major[major]
        for major in sorted(latest_by_major, reverse=True)
    ]


def render_mail_template(
    output: dict[str, object],
    *,
    eck_operator_version: str | None = None,
    replication_rule_prefix: str = DEFAULT_REPLICATION_RULE_PREFIX,
) -> str:
    lines = output["maintained_minor_lines"]
    if not isinstance(lines, list):
        raise ValueError("maintained_minor_lines must be a list")
    mail_lines = latest_mail_release_lines(lines)

    message: list[str] = [
        "Subject: Harbor Replication Rules fuer Elastic Stack aktualisieren",
        "",
        "Hallo zusammen,",
        "",
        "koennt ihr bitte die Harbor Replication Rules fuer die neuesten supporteten Elastic Stack Versionen aktualisieren?",
        "",
        f"Stand: {output['evaluated_at']}",
        "",
        "Rules:",
    ]

    for suffix, image in DOCKER_HUB_REPLICATION_IMAGES:
        message.append(f"- {replication_rule_name(replication_rule_prefix, suffix)} (Docker Hub, {image})")

    if eck_operator_version:
        eck_rule = replication_rule_name(replication_rule_prefix, ECK_OPERATOR_REPLICATION_RULE_SUFFIX)
        message.append(f"- {eck_rule} (Docker Hub, {ECK_OPERATOR_IMAGE})")

    message.extend(["", "Docker Pulls:"])
    if eck_operator_version:
        message.extend(
            [
                f"docker pull {ECK_OPERATOR_IMAGE}:{eck_operator_version}  # {eck_rule}",
            ]
        )
    for line in mail_lines:
        version = str(line["latest_release"])
        message.extend(
            [
                "",
                f"{line['minor_line']} aktueller Patch: {version}",
            ]
        )
        for command in docker_pull_commands(version, replication_rule_prefix=replication_rule_prefix):
            message.append(f"{command['command']}  # {command['replication_rule']}")

    message.extend(
        [
            "",
            "Danke",
        ]
    )
    return "\n".join(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show Elastic product versions that should receive maintenance/security updates.",
    )
    parser.add_argument("--at", default=dt.date.today().isoformat(), help="evaluation date, YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--mail-template",
        action="store_true",
        help="emit a mail template for Harbor replication-rule requests",
    )
    parser.add_argument(
        "--eck-operator-version",
        help="include an ECK operator docker pull command with this explicit operator version",
    )
    parser.add_argument(
        "--replication-rule-prefix",
        default=DEFAULT_REPLICATION_RULE_PREFIX,
        help=(
            "Harbor replication rule prefix used in mail templates "
            f"(default: {DEFAULT_REPLICATION_RULE_PREFIX})"
        ),
    )
    parser.add_argument(
        "--output",
        help="write JSON output to this path; implies --json for the file content",
    )
    parser.add_argument(
        "--ignore-eol-page",
        action="store_true",
        help="calculate maintenance windows from GitHub release dates only",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification; intended only for restricted test environments",
    )
    parser.add_argument(
        "--ca-file",
        help="CA bundle to use for TLS verification, e.g. /etc/ssl/certs/ca-certificates.crt",
    )
    parser.add_argument("--max-pages", type=int, default=20, help="GitHub releases API pages to scan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    at = dt.date.fromisoformat(args.at)

    try:
        eol_html = None
        if not args.ignore_eol_page:
            eol_html = fetch_text(ELASTIC_EOL_URL, insecure=args.insecure, ca_file=args.ca_file)
        products = [
            build_product_output(
                product,
                eol_html=eol_html,
                at=at,
                max_pages=args.max_pages,
                insecure=args.insecure,
                ca_file=args.ca_file,
                github_token=os.environ.get("GITHUB_TOKEN"),
                ignore_eol_page=args.ignore_eol_page,
            )
            for product in PRODUCTS
        ]
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = {
        "evaluated_at": at.isoformat(),
        "products": products,
        # Keep these legacy fields for older static pages or scripts that only
        # know about the original Elasticsearch-only output format.
        "product": products[0]["product"],
        "sources": products[0]["sources"],
        "maintained_minor_lines": products[0]["maintained_minor_lines"],
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.json:
            print(f"Wrote {output_path}")
            return 0

    if args.mail_template:
        print(
            render_mail_template(
                output,
                eck_operator_version=args.eck_operator_version,
                replication_rule_prefix=args.replication_rule_prefix,
            )
        )
        return 0

    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0

    print(f"Elastic maintained minor lines on {at.isoformat()}:")
    for product in products:
        product_lines = product["maintained_minor_lines"]
        print(f"\n{product['product']}:")
        if not product_lines:
            print("  No maintained lines found.")
            continue
        for line in product_lines:
            print(
                "  - {minor_line} (latest {latest_release}, released {released}, "
                "maintenance through {end_of_maintenance})".format(**line)
            )
            print(f"    Reason: {line['reason']}")
            print(f"    Release: {line['url']}")
        print(f"  Sources: {', '.join(product['sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
