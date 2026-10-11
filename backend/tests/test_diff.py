import unittest
from nexus_app.engine.diff import DatasetDiffer

class TestDatasetDiffer(unittest.TestCase):
    def test_change_radar_diff(self):
        old_records = [
            {"id": "1", "title": "Old Article", "status": "draft"},
            {"id": "2", "title": "Permanent Article", "status": "published"}
        ]
        new_records = [
            {"id": "2", "title": "Permanent Article", "status": "archived"},  # modified
            {"id": "3", "title": "Brand New Article", "status": "published"}   # added
            # id: 1 removed
        ]

        diff = DatasetDiffer.compare_datasets(old_records, new_records, key_fields=["id"])
        summary = diff["summary"]

        self.assertEqual(summary["total_old"], 2)
        self.assertEqual(summary["total_new"], 2)
        self.assertEqual(summary["added_count"], 1)
        self.assertEqual(summary["removed_count"], 1)
        self.assertEqual(summary["modified_count"], 1)

        # Verify field change details
        mod = diff["modified_records"][0]
        self.assertIn("status", mod["changes"])
        self.assertEqual(mod["changes"]["status"]["old"], "published")
        self.assertEqual(mod["changes"]["status"]["new"], "archived")

if __name__ == "__main__":
    unittest.main()
