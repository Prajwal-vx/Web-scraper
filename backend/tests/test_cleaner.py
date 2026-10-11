import unittest
from nexus_app.engine.cleaner import DataCleaner

class TestDataCleaner(unittest.TestCase):
    def test_text_trim_and_strip_html(self):
        dirty = "   <div>Hello \n\t  World!   </div> "
        cleaned = DataCleaner.clean_strip_html(dirty)
        self.assertEqual(cleaned, "Hello World!")

    def test_numeric_conversion(self):
        price_str = "  $ 1,499.95 USD "
        f_val = DataCleaner.clean_to_float(price_str)
        self.assertEqual(f_val, 1499.95)

        int_str = "340 items in stock"
        i_val = DataCleaner.clean_to_int(int_str)
        self.assertEqual(i_val, 340)

    def test_date_conversion(self):
        raw_date = "October 11, 2026"
        iso_date = DataCleaner.clean_to_date(raw_date)
        self.assertEqual(iso_date, "2026-10-11")

    def test_url_normalization(self):
        dirty_url = "HTTPS://EXAMPLE.COM/articles/page1/?utm_source=test#anchor"
        norm_url = DataCleaner.clean_normalize_url(dirty_url)
        self.assertEqual(norm_url, "https://example.com/articles/page1?utm_source=test")

    def test_deduplication(self):
        records = [
            {"id": "A", "title": "Article One", "author": "John"},
            {"id": "A", "title": "Article One", "author": "John"},
            {"id": "B", "title": "Article Two", "author": "Jane"},
        ]
        unique, dups = DataCleaner.deduplicate_records(records, dedup_keys=["id"])
        self.assertEqual(len(unique), 2)
        self.assertEqual(dups, 1)

if __name__ == "__main__":
    unittest.main()
