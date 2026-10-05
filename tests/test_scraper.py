import csv
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

import scraper


class ScraperTests(unittest.TestCase):
    def test_rejects_private_ip(self):
        with self.assertRaisesRegex(ValueError, "private"):
            scraper.validate_url("http://127.0.0.1/")

    def test_rejects_private_dns_result(self):
        answer = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.2", 80))]
        with patch.object(scraper.socket, "getaddrinfo", return_value=answer):
            with self.assertRaisesRegex(ValueError, "private"):
                scraper.validate_url("https://public.example/")

    def test_extracts_common_fields_and_css_selectors(self):
        soup = BeautifulSoup("""<html><head><title> Catalog </title><meta name="description" content="Items"></head>
        <body><main><h1>Widget</h1><p class="price"> Rs. 20 </p><a href="/item">Item</a>
        <img src="/widget.png" alt="Widget"><script type="application/ld+json">{"@type":"Product"}</script></main></body></html>""", "html.parser")
        row = scraper.extract_page(soup, "https://example.org/catalog", {"Price": ".price"})
        self.assertEqual(row["title"], "Catalog")
        self.assertEqual(row["fields"]["Price"], "Rs. 20")
        self.assertEqual(row["links"], ["https://example.org/item"])
        self.assertEqual(row["images"][0]["url"], "https://example.org/widget.png")
        self.assertEqual(row["metadata"]["description"], "Items")

    def test_bad_css_selector_is_reported(self):
        with self.assertRaisesRegex(ValueError, "Invalid CSS selector"):
            scraper.extract_page(BeautifulSoup("<p>x</p>", "html.parser"), "https://example.org", {"bad": "["})

    def test_query_pagination_increments_page_parameter(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertEqual(scraper.find_next_page_url(soup, "https://example.org/list?page=2&sort=asc"),
                         "https://example.org/list?page=3&sort=asc")

    def test_json_and_csv_exports_accept_structured_records(self):
        row = {"title": "A", "url": "https://example.org", "links": ["https://example.org/a"]}
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "result.json"
            csv_path = Path(directory) / "result.csv"
            scraper.save_json([row], str(json_path))
            scraper.save_csv([row], str(csv_path))
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), [row])
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                csv_row = next(csv.DictReader(stream))
            self.assertEqual(json.loads(csv_row["links"]), row["links"])


if __name__ == "__main__":
    unittest.main()
