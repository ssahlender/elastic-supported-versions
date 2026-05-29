# Elastic Supported Versions Checker

Small Python script and static web page that check Elastic releases and report
which minor version lines should still receive Elastic maintenance/security
updates.

The script implements Elastic's published Product & Version End of Life Policy:

- A major release is maintained for the longer of:
  - 30 months from its GA date.
  - 18 months from the GA date of the next major release.
- Within maintained majors, Elastic maintains:
  - the two newest minor releases of the current major;
  - the final minor release of the previous major.

Currently included products:

- Elasticsearch
- Elastic Cloud on Kubernetes (ECK)

Sources:

- Elastic EOL policy: <https://www.elastic.co/support/eol>
- Elasticsearch releases: <https://github.com/elastic/elasticsearch/releases>
- ECK releases: <https://github.com/elastic/cloud-on-k8s/releases>

## Requirements

- Python 3.10 or newer
- Network access to GitHub and Elastic

No third-party Python packages are required.

## Usage

Run with today's date:

```bash
./elastic_supported_versions.py
```

Evaluate a specific date:

```bash
./elastic_supported_versions.py --at 2026-05-06
```

Emit JSON:

```bash
./elastic_supported_versions.py --json
```

Write JSON for the static web page:

```bash
./elastic_supported_versions.py --output site/data.json
```

Emit a short German mail template for the Harbor replication-rule request:

```bash
./elastic_supported_versions.py --mail-template
```

The template includes Docker pull commands for the maintained Elasticsearch
patch versions and these Docker Hub replication rules:

- `harbor-elastic-elasticsearch`
- `harbor-elastic-filebeat`
- `harbor-elastic-kibana`
- `harbor-elastic-logstash`
- `harbor-elastic-metricbeat`

Use `--replication-rule-prefix` if your Harbor rules use a different prefix:

```bash
./elastic_supported_versions.py --mail-template --replication-rule-prefix my-elastic
```

If the ECK operator rule also needs a specific operator tag, pass it explicitly.
Without this option, the ECK operator image is not included in the mail
template. ECK support status is still included in the normal CLI and web output.

```bash
./elastic_supported_versions.py --mail-template --eck-operator-version 3.1.0
```

Use a specific CA bundle:

```bash
./elastic_supported_versions.py --ca-file /etc/ssl/certs/ca-certificates.crt
```

## TLS Certificates

By default, the script tries Python/OpenSSL's normal certificate configuration.
If that environment points at a missing or incomplete CA store, the script also
tries common Linux CA bundle locations, including:

- `/etc/ssl/certs/ca-certificates.crt`
- `/etc/pki/tls/certs/ca-bundle.crt`
- `/etc/ssl/ca-bundle.pem`
- `/etc/ssl/cert.pem`

If needed, pass `--ca-file` explicitly. The `--insecure` option disables TLS
certificate verification and should only be used as a last-resort test option.

## Example Output

```text
Elastic maintained minor lines on 2026-05-29:

Elasticsearch:
  - 9.4.x (latest 9.4.2, released 2026-05-28, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v9.4.2
  - 9.3.x (latest 9.3.5, released 2026-05-28, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v9.3.5
  - 8.19.x (latest 8.19.16, released 2026-05-28, maintenance through 2027-01-15)
    Reason: final minor release of the previous major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v8.19.16
  Sources: GitHub releases API (elastic/elasticsearch), Elastic EOL policy page

Elastic Cloud on Kubernetes:
  - 3.4.x (latest 3.4.0, released 2026-05-05, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/cloud-on-k8s/releases/tag/v3.4.0
  - 3.3.x (latest 3.3.2, released 2026-04-01, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/cloud-on-k8s/releases/tag/v3.3.2
  - 2.16.x (latest 2.16.1, released 2025-01-21, maintenance through 2027-01-15)
    Reason: final minor release of the previous major
    Release: https://github.com/elastic/cloud-on-k8s/releases/tag/v2.16.1
  Sources: GitHub releases API (elastic/cloud-on-k8s), Elastic EOL policy page
```

## GitHub Pages

This repository includes a static GitHub Pages site in `site/`. GitHub Pages
does not run Python on request, so the included workflow generates
`site/data.json` first and then deploys the static files.

To enable the page:

1. Push this repository to GitHub.
2. Open repository Settings -> Pages.
3. Set Source to GitHub Actions.
4. Run the "Update GitHub Pages" workflow manually once.

After deployment, the site will be available at
<https://ssahlender.github.io/elastic-supported-versions/>.

The workflow also runs daily at 06:00 UTC.
