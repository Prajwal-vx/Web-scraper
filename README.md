# Fieldnote Web Scraper

A local web dashboard and command-line tool for collecting structured data from public HTML pages. It uses one polite HTTP request at a time per job, checks `robots.txt`, limits response size and job length, and stores job history in SQLite.

## Features

- Start and monitor background jobs from a responsive local dashboard.
- Extract page title, text, headings, links, images, metadata, and JSON-LD.
- Add named CSS selectors for page-specific fields.
- Follow common next-page links on the same host with a bounded page limit.
- Search and page through stored results; export JSON or CSV.
- Save and reuse scrape configurations; cancel, retry, and delete jobs.
- Record job-level failures without exposing internal tracebacks in the UI.
- Keep the original CLI and CSV, JSON, and SQLite output formats.

## Architecture

`scraper.py` contains URL validation, bounded HTTP fetching, HTML extraction, pagination, and CLI exporters. `webapp.py` provides the local Flask API, SQLite persistence, and a small thread-backed job runner. The dashboard is `templates/index.html`. Scraped pages and job state are stored in `scraper.db` by default.

## Requirements and installation

Python 3.10 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SCRAPER_DATABASE` | `./scraper.db` | SQLite database path |
| `PORT` | `5000` | Local dashboard port |

There are no application secrets. The dashboard binds to `127.0.0.1` and has no authentication; do not expose it to a network.

## Run the dashboard

```powershell
python webapp.py
```

Open `http://127.0.0.1:5000`. Jobs are capped at 100 pages, responses at 5 MB, and the worker pool at two concurrent jobs. Requests wait at least one second between pages. The scraper checks the site's `robots.txt` and will not follow pagination links to another host.

## Command line

```powershell
python scraper.py --url https://example.org --max-pages 5 --output-format json
python scraper.py --url https://example.org --output-format csv --output-file results.csv
```

`--max-pages 0` means unlimited for the CLI; set an explicit limit for responsible use.

## API

- `POST /api/jobs` — create a job (`url`, optional `name`, `max_pages`, and `selectors` object).
- `GET /api/jobs` and `GET /api/jobs/{id}` — list job history or inspect progress.
- `POST /api/jobs/{id}/cancel` — request cancellation.
- `POST /api/jobs/{id}/retry` — rerun a job with its saved settings.
- `DELETE /api/jobs/{id}` — remove a completed job and its results.
- `GET /api/jobs/{id}/results?page=1&per_page=25&q=term` — search and page through records.
- `GET /api/jobs/{id}/export?format=json|csv` — download results.
- `GET`, `POST /api/configurations`; `PUT`, `DELETE /api/configurations/{id}` — manage saved settings.
- `GET /api/health` — local health check.

Example:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:5000/api/jobs `
  -ContentType 'application/json' `
  -Body '{"url":"https://example.org","max_pages":3,"selectors":{"Heading":"h1"}}'
```

## Database setup

The application creates its SQLite tables and indexes on first run. SQLite foreign keys and cascading result deletion are enabled. Back up `scraper.db` like any other local data file.

## Development and tests

```powershell
python -m unittest discover -s tests -v
```

The tests cover URL safety, extraction, CSV/JSON export, and the local API. No separate database service or migration tool is needed for the current single-user deployment.

## Security and limitations

URLs are restricted to HTTP and HTTPS, credentials in URLs are rejected, DNS results must be public, and redirects are validated before following. HTML is treated as data and displayed with text escaping. Job sizes and response sizes are bounded in the dashboard. Keep the service on loopback.

This version handles static HTML over HTTP. It does not run JavaScript, log in to sites, evade access controls, schedule jobs, or provide user accounts. Sitemap ingestion, multiple starting URLs, Excel export, and job pause are not included. Sites that require a JavaScript browser should be marked unsupported until an isolated, resource-limited browser worker is added.

## Troubleshooting

- **Host could not be resolved:** check the spelling and DNS availability.
- **Local/private network targets are not allowed:** the app blocks non-public address ranges to prevent server-side request forgery.
- **robots.txt disallows the page:** choose a page the site permits automated clients to fetch.
- **No pages could be collected:** inspect the URL and whether the server serves HTML to automated clients.
- **Need a clean local history:** stop the app and back up or remove the configured SQLite database.
