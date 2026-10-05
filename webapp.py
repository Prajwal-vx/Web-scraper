"""Small local dashboard and JSON API for durable scraping jobs."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from scraper import scrape_all, validate_url

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("SCRAPER_DATABASE", BASE_DIR / "scraper.db"))
MAX_PAGES = 100
executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scrape")
cancel_events: dict[str, threading.Event] = {}
logger = logging.getLogger("scraper.jobs")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


@contextmanager
def connect():
    db = sqlite3.connect(DATABASE, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, start_url TEXT NOT NULL,
                selectors TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL, created_at TEXT NOT NULL,
                started_at TEXT, completed_at TEXT, pages_requested INTEGER NOT NULL,
                pages_processed INTEGER NOT NULL DEFAULT 0, records_found INTEGER NOT NULL DEFAULT 0,
                errors TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                source_url TEXT NOT NULL, data TEXT NOT NULL, scraped_at TEXT NOT NULL, content_hash TEXT NOT NULL,
                UNIQUE(job_id, content_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_records_job_id ON records(job_id, id);
            CREATE TABLE IF NOT EXISTS configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, start_url TEXT NOT NULL,
                selectors TEXT NOT NULL DEFAULT '{}', max_pages INTEGER NOT NULL DEFAULT 10,
                created_at TEXT NOT NULL
            );
        """)


def validate_selectors(value) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > 20:
        raise ValueError("Selectors must be an object with at most 20 fields")
    for name, selector in value.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Selector field names must be 1 to 100 characters")
        if not isinstance(selector, str) or not selector.strip() or len(selector) > 500:
            raise ValueError("Each CSS selector must be 1 to 500 characters")
    return value


def job_worker(job_id: int) -> None:
    event = cancel_events[job_id]
    with connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        db.execute("UPDATE jobs SET status='Running', started_at=? WHERE id=?", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), job_id))
    errors: list[str] = []
    pages: list[dict] = []

    def save_page(page: dict, processed: int) -> None:
        payload = json.dumps(page, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256((page["url"] + payload).encode("utf-8")).hexdigest()
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO records(job_id, source_url, data, scraped_at, content_hash) VALUES(?,?,?,?,?)",
                       (job_id, page["url"], payload, page["scraped_at"], digest))
            db.execute("UPDATE jobs SET pages_processed=?, records_found=(SELECT COUNT(*) FROM records WHERE job_id=?) WHERE id=?",
                       (processed, job_id, job_id))

    try:
        pages = scrape_all(job["start_url"], job["pages_requested"], (1.0, 2.0),
                            json.loads(job["selectors"]), save_page, event.is_set, errors)
        status = "Cancelled" if event.is_set() else "Partially Completed" if pages and errors else "Completed" if pages else "Failed"
        if not pages and not event.is_set():
            errors.append("No pages could be collected. Check the URL and whether the site permits automated access.")
    except Exception as exc:
        logger.exception("Scrape job %s failed", job_id)
        status = "Cancelled" if event.is_set() else "Failed"
        errors.append(str(exc)[:500])
        if pages and not event.is_set():
            status = "Partially Completed"
    finally:
        with connect() as db:
            db.execute("UPDATE jobs SET status=?, completed_at=?, errors=? WHERE id=?",
                       (status, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), json.dumps(errors), job_id))
        cancel_events.pop(job_id, None)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/jobs")
def create_job():
    body = request.get_json(silent=True) or {}
    try:
        url = validate_url(str(body.get("url", "")))
        max_pages = int(body.get("max_pages", 10))
        selectors = validate_selectors(body.get("selectors", {}))
        if not 1 <= max_pages <= MAX_PAGES:
            raise ValueError(f"Maximum pages must be between 1 and {MAX_PAGES}")
        json.dumps(selectors)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    name = str(body.get("name") or urlparse_host(url))[:120]
    with connect() as db:
        cursor = db.execute("INSERT INTO jobs(name,start_url,selectors,status,created_at,pages_requested) VALUES(?,?,?,'Pending',?,?)",
                            (name, url, json.dumps(selectors), created, max_pages))
        job_id = cursor.lastrowid
    cancel_events[job_id] = threading.Event()
    executor.submit(job_worker, job_id)
    return jsonify({"id": job_id, "status": "Pending"}), 202


def urlparse_host(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).hostname or "Scrape job"


@app.get("/api/jobs")
def list_jobs():
    with connect() as db:
        rows = db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify([dict(row) | {"errors": json.loads(row["errors"])} for row in rows])


@app.get("/api/jobs/<int:job_id>")
def get_job(job_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404
    result = dict(row)
    result["errors"] = json.loads(result["errors"])
    return jsonify(result)


@app.post("/api/jobs/<int:job_id>/cancel")
def cancel_job(job_id: int):
    event = cancel_events.get(job_id)
    if event:
        event.set()
        return jsonify({"status": "cancellation requested"}), 202
    return jsonify({"error": "Job is not running"}), 409


@app.post("/api/jobs/<int:job_id>/retry")
def retry_job(job_id: int):
    with connect() as db:
        previous = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not previous:
        return jsonify({"error": "Job not found"}), 404
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with connect() as db:
        cursor = db.execute("INSERT INTO jobs(name,start_url,selectors,status,created_at,pages_requested) VALUES(?,?,?,'Pending',?,?)",
                            (previous["name"] + " (retry)", previous["start_url"], previous["selectors"], created, previous["pages_requested"]))
        new_id = cursor.lastrowid
    cancel_events[new_id] = threading.Event()
    executor.submit(job_worker, new_id)
    return jsonify({"id": new_id, "status": "Pending"}), 202


@app.delete("/api/jobs/<int:job_id>")
def delete_job(job_id: int):
    if job_id in cancel_events:
        return jsonify({"error": "Cancel the job before deleting it"}), 409
    with connect() as db:
        cursor = db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return ("", 204) if cursor.rowcount else (jsonify({"error": "Job not found"}), 404)


@app.get("/api/jobs/<int:job_id>/results")
def results(job_id: int):
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    search = request.args.get("q", "")[:200]
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            return jsonify({"error": "Job not found"}), 404
        total = db.execute("SELECT COUNT(*) FROM records WHERE job_id=? AND data LIKE ?", (job_id, f"%{search}%")).fetchone()[0]
        rows = db.execute("SELECT data FROM records WHERE job_id=? AND data LIKE ? ORDER BY id LIMIT ? OFFSET ?",
                          (job_id, f"%{search}%", per_page, (page - 1) * per_page)).fetchall()
    return jsonify({"total": total, "page": page, "per_page": per_page, "results": [json.loads(row["data"]) for row in rows]})


@app.get("/api/jobs/<int:job_id>/export")
def export(job_id: int):
    kind = request.args.get("format", "json").lower()
    if kind not in {"json", "csv"}:
        return jsonify({"error": "Format must be json or csv"}), 400
    with connect() as db:
        if not db.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
            return jsonify({"error": "Job not found"}), 404
        records = [json.loads(row[0]) for row in db.execute("SELECT data FROM records WHERE job_id=? ORDER BY id", (job_id,))]
    if kind == "json":
        return Response(json.dumps(records, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=job-{job_id}.json"})
    output = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in records for key in row))
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in record.items()})
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=job-{job_id}.csv"})


@app.route("/api/configurations", methods=["GET", "POST"])
def configurations():
    if request.method == "GET":
        with connect() as db:
            rows = db.execute("SELECT * FROM configurations ORDER BY id DESC").fetchall()
        return jsonify([dict(row) | {"selectors": json.loads(row["selectors"])} for row in rows])
    body = request.get_json(silent=True) or {}
    try:
        url = validate_url(str(body.get("url", "")))
        selectors = validate_selectors(body.get("selectors", {}))
        limit = int(body.get("max_pages", 10))
        if not 1 <= limit <= MAX_PAGES:
            raise ValueError("Page limit must be between 1 and 100")
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    with connect() as db:
        cursor = db.execute("INSERT INTO configurations(name,start_url,selectors,max_pages,created_at) VALUES(?,?,?,?,?)",
                            (str(body.get("name") or urlparse_host(url))[:120], url, json.dumps(selectors), limit,
                             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    return jsonify({"id": cursor.lastrowid}), 201


@app.put("/api/configurations/<int:config_id>")
def update_configuration(config_id: int):
    body = request.get_json(silent=True) or {}
    try:
        url = validate_url(str(body.get("url", "")))
        selectors = validate_selectors(body.get("selectors", {}))
        limit = int(body.get("max_pages", 10))
        if not 1 <= limit <= MAX_PAGES:
            raise ValueError("Page limit must be between 1 and 100")
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400
    with connect() as db:
        cursor = db.execute("UPDATE configurations SET name=?,start_url=?,selectors=?,max_pages=? WHERE id=?",
                            (str(body.get("name") or urlparse_host(url))[:120], url, json.dumps(selectors), limit, config_id))
    return jsonify({"id": config_id}) if cursor.rowcount else (jsonify({"error": "Configuration not found"}), 404)


@app.delete("/api/configurations/<int:config_id>")
def delete_configuration(config_id: int):
    with connect() as db:
        cursor = db.execute("DELETE FROM configurations WHERE id=?", (config_id,))
    return ("", 204) if cursor.rowcount else (jsonify({"error": "Configuration not found"}), 404)


initialize()

if __name__ == "__main__":
    # Local only: this app has no account system and must not be exposed publicly.
    with connect() as db:
        db.execute("UPDATE jobs SET status='Failed', completed_at=?, errors=? WHERE status IN ('Pending','Running')",
                   (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), json.dumps(["Worker stopped before the job finished; retry this job."])))
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
