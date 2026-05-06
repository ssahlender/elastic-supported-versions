# Elastic Supported Versions Checker

Small Python script that checks Elasticsearch releases and reports which minor
version lines should still receive Elastic maintenance/security updates.

The script implements Elastic's published Product & Version End of Life Policy:

- A major release is maintained for the longer of:
  - 30 months from its GA date.
  - 18 months from the GA date of the next major release.
- Within maintained majors, Elastic maintains:
  - the two newest minor releases of the current major;
  - the final minor release of the previous major.

Sources:

- Elastic EOL policy: <https://www.elastic.co/support/eol>
- Elasticsearch releases: <https://github.com/elastic/elasticsearch/releases>

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
Elasticsearch maintained minor lines on 2026-05-06:
  - 9.4.x (latest 9.4.0, released 2026-05-05, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v9.4.0
  - 9.3.x (latest 9.3.4, released 2026-04-30, maintenance through 2027-10-15)
    Reason: one of the two newest minor releases of the current major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v9.3.4
  - 8.19.x (latest 8.19.15, released 2026-04-30, maintenance through 2027-01-15)
    Reason: final minor release of the previous major
    Release: https://github.com/elastic/elasticsearch/releases/tag/v8.19.15
Sources: GitHub releases API, Elastic EOL policy page
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
