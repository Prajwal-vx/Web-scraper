from typing import List, Dict, Any
from nexus_app.schemas.dataset import DataQualityReportOut, DataQualityMetric
from nexus_app.engine.cleaner import DataCleaner

class DataQualityScorer:
    """
    Computes a transparent, auditable Data Quality Score (0-100%)
    based on Completeness, Type Validity, and Record Uniqueness.
    """

    @classmethod
    def evaluate(
        cls,
        records: List[Dict[str, Any]],
        dataset_id: str = "dataset-001",
        required_fields: List[str] = None
    ) -> DataQualityReportOut:
        total = len(records)
        if total == 0:
            return DataQualityReportOut(
                dataset_id=dataset_id,
                overall_score=0.0,
                grade="F",
                metrics=[],
                total_records=0,
                duplicate_records_count=0,
                missing_required_count=0,
                fields_evaluated=[]
            )

        # 1. Identify all fields
        all_fields = set()
        for r in records:
            all_fields.update(r.keys())
        fields_evaluated = sorted(list(all_fields))
        req_fields = set(required_fields or fields_evaluated)

        # 2. Completeness Check
        total_cells = total * len(fields_evaluated)
        filled_cells = 0
        missing_required = 0

        for r in records:
            for f in fields_evaluated:
                val = r.get(f)
                is_filled = val is not None and val != "" and val != []
                if is_filled:
                    filled_cells += 1
                elif f in req_fields:
                    missing_required += 1

        completeness_ratio = (filled_cells / total_cells) if total_cells > 0 else 0.0

        # 3. Uniqueness Check
        unique_records, duplicate_count = DataCleaner.deduplicate_records(records)
        uniqueness_ratio = (len(unique_records) / total) if total > 0 else 0.0

        # 4. Validity Check (syntactic & type sanity)
        valid_cells = 0
        total_eval_cells = 0
        for r in records:
            for f, v in r.items():
                if v is None or v == "":
                    continue
                total_eval_cells += 1
                val_str = str(v)
                # Check if field hints at URL or date or number
                if "url" in f.lower() or "link" in f.lower() or "href" in f.lower():
                    if val_str.startswith("http://") or val_str.startswith("https://") or val_str.startswith("/"):
                        valid_cells += 1
                elif "date" in f.lower() or "time" in f.lower():
                    if DataCleaner.clean_to_date(val_str) is not None:
                        valid_cells += 1
                elif "price" in f.lower() or "count" in f.lower() or "rating" in f.lower() or "amount" in f.lower():
                    if DataCleaner.clean_to_float(val_str) is not None:
                        valid_cells += 1
                else:
                    # General text field is valid if length > 0
                    valid_cells += 1

        validity_ratio = (valid_cells / total_eval_cells) if total_eval_cells > 0 else 1.0

        # Weights: Completeness 40%, Validity 35%, Uniqueness 25%
        w_completeness = 0.40
        w_validity = 0.35
        w_uniqueness = 0.25

        overall_score = round(
            ((completeness_ratio * w_completeness) +
             (validity_ratio * w_validity) +
             (uniqueness_ratio * w_uniqueness)) * 100,
            1
        )

        grade = "A" if overall_score >= 90 else "B" if overall_score >= 80 else "C" if overall_score >= 70 else "D" if overall_score >= 60 else "F"

        metrics = [
            DataQualityMetric(
                metric_name="Completeness",
                score=round(completeness_ratio * 100, 1),
                weight=w_completeness,
                description="Percentage of populated non-null fields across all records.",
                details={"filled_cells": filled_cells, "total_cells": total_cells, "missing_required": missing_required}
            ),
            DataQualityMetric(
                metric_name="Validity",
                score=round(validity_ratio * 100, 1),
                weight=w_validity,
                description="Data conformity to expected semantic types (dates, URLs, numbers).",
                details={"valid_cells": valid_cells, "evaluated_cells": total_eval_cells}
            ),
            DataQualityMetric(
                metric_name="Uniqueness",
                score=round(uniqueness_ratio * 100, 1),
                weight=w_uniqueness,
                description="Ratio of distinct records to total extracted records.",
                details={"unique_records": len(unique_records), "duplicate_records": duplicate_count}
            ),
        ]

        return DataQualityReportOut(
            dataset_id=dataset_id,
            overall_score=overall_score,
            grade=grade,
            metrics=metrics,
            total_records=total,
            duplicate_records_count=duplicate_count,
            missing_required_count=missing_required,
            fields_evaluated=fields_evaluated
        )
