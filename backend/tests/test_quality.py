import unittest
from nexus_app.engine.quality import DataQualityScorer

class TestDataQualityScorer(unittest.TestCase):
    def test_quality_scorer_complete_dataset(self):
        records = [
            {"title": "Title 1", "author": "Alice", "url": "https://example.com/1", "date": "2026-10-11"},
            {"title": "Title 2", "author": "Bob", "url": "https://example.com/2", "date": "2026-10-12"},
            {"title": "Title 3", "author": "Charlie", "url": "https://example.com/3", "date": "2026-10-13"},
        ]
        report = DataQualityScorer.evaluate(records, dataset_id="ds-test")
        self.assertGreaterEqual(report.overall_score, 90.0)
        self.assertEqual(report.grade, "A")
        self.assertEqual(report.duplicate_records_count, 0)
        self.assertEqual(report.missing_required_count, 0)

    def test_quality_scorer_penalizes_duplicates_and_empty_cells(self):
        records = [
            {"title": "Duplicate", "author": "", "url": ""},
            {"title": "Duplicate", "author": "", "url": ""},
        ]
        report = DataQualityScorer.evaluate(records, dataset_id="ds-poor")
        self.assertLess(report.overall_score, 70.0)
        self.assertEqual(report.duplicate_records_count, 1)

if __name__ == "__main__":
    unittest.main()
