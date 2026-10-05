import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SCRAPER_DATABASE", str(Path(tempfile.gettempdir()) / "fieldnote-test-bootstrap.db"))
import webapp


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        webapp.DATABASE = Path(self.temp.name) / "test.db"
        webapp.initialize()
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json, {"status": "ok"})

    def test_rejects_invalid_url_and_page_limit(self):
        bad_url = self.client.post("/api/jobs", json={"url": "file:///etc/passwd"})
        self.assertEqual(bad_url.status_code, 400)
        with patch.object(webapp, "validate_url", return_value="https://example.org/"):
            bad_limit = self.client.post("/api/jobs", json={"url": "https://example.org", "max_pages": 1000})
        self.assertEqual(bad_limit.status_code, 400)

    def test_configuration_create_list_update_delete(self):
        with patch.object(webapp, "validate_url", return_value="https://example.org/"):
            created = self.client.post("/api/configurations", json={"url": "https://example.org", "selectors": {"Title": "h1"}})
            self.assertEqual(created.status_code, 201)
            config_id = created.json["id"]
            self.assertEqual(self.client.get("/api/configurations").json[0]["selectors"], {"Title": "h1"})
            updated = self.client.put(f"/api/configurations/{config_id}", json={"url": "https://example.org", "name": "Updated", "max_pages": 3})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.delete(f"/api/configurations/{config_id}").status_code, 204)

    def test_worker_stores_results_and_export(self):
        with webapp.connect() as db:
            cursor = db.execute("INSERT INTO jobs(name,start_url,selectors,status,created_at,pages_requested) VALUES(?,?,?,'Pending',?,1)",
                                ("Test", "https://example.org", "{}", "2026-10-05T00:00:00Z"))
            job_id = cursor.lastrowid
        webapp.cancel_events[job_id] = __import__("threading").Event()
        record = {"title": "Example", "url": "https://example.org", "scraped_at": "2026-10-05T00:00:00Z"}

        def fake_scrape(url, limit, delay, selectors, on_page, cancelled, errors):
            on_page(record, 1)
            return [record]

        with patch.object(webapp, "scrape_all", side_effect=fake_scrape):
            webapp.job_worker(job_id)
        job = self.client.get(f"/api/jobs/{job_id}").json
        result = self.client.get(f"/api/jobs/{job_id}/results").json
        download = self.client.get(f"/api/jobs/{job_id}/export?format=json")
        self.assertEqual(job["status"], "Completed")
        self.assertEqual(result["results"], [record])
        self.assertEqual(download.status_code, 200)


if __name__ == "__main__":
    unittest.main()
