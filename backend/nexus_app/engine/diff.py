from typing import List, Dict, Any, Optional
from nexus_app.engine.cleaner import DataCleaner

class DatasetDiffer:
    """
    Website Change Radar:
    Compares two datasets (Snapshot A vs Snapshot B) and produces
    record-level and field-level diffs (added, removed, modified).
    """

    @classmethod
    def compare_datasets(
        cls,
        old_records: List[Dict[str, Any]],
        new_records: List[Dict[str, Any]],
        key_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Calculates differences between two dataset record lists.
        """
        # Map by identifier key or content hash
        old_map: Dict[str, Dict[str, Any]] = {}
        for r in old_records:
            ident = DataCleaner.compute_content_hash(r, key_fields)
            old_map[ident] = r

        new_map: Dict[str, Dict[str, Any]] = {}
        for r in new_records:
            ident = DataCleaner.compute_content_hash(r, key_fields)
            new_map[ident] = r

        added_records = []
        removed_records = []
        modified_records = []
        unchanged_count = 0

        # Check for added and modified
        for ident, n_rec in new_map.items():
            if ident not in old_map:
                added_records.append(n_rec)
            else:
                o_rec = old_map[ident]
                # Compare fields
                field_diffs = {}
                all_keys = set(o_rec.keys()).union(set(n_rec.keys()))
                for k in all_keys:
                    old_v = o_rec.get(k)
                    new_v = n_rec.get(k)
                    if old_v != new_v:
                        field_diffs[k] = {"old": old_v, "new": new_v}

                if field_diffs:
                    modified_records.append({
                        "record": n_rec,
                        "changes": field_diffs
                    })
                else:
                    unchanged_count += 1

        # Check for removed
        for ident, o_rec in old_map.items():
            if ident not in new_map:
                removed_records.append(o_rec)

        return {
            "summary": {
                "total_old": len(old_records),
                "total_new": len(new_records),
                "added_count": len(added_records),
                "removed_count": len(removed_records),
                "modified_count": len(modified_records),
                "unchanged_count": unchanged_count,
            },
            "added_records": added_records[:50],  # sample preview
            "removed_records": removed_records[:50],
            "modified_records": modified_records[:50],
        }
