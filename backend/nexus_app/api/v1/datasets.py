import io
import csv
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import ExtractedDataset, DatasetRecord
from nexus_app.schemas.dataset import DatasetOut, DatasetRecordOut, DataQualityReportOut, CleanDataRequest
from nexus_app.engine.cleaner import DataCleaner
from nexus_app.engine.quality import DataQualityScorer
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/datasets", tags=["Datasets & Exports"])

@router.get("", response_model=List[DatasetOut])
def list_datasets(
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        Project.user_id == current_user.id
    )
    if project_id:
        query = query.filter(ExtractedDataset.project_id == project_id)
    return query.order_by(ExtractedDataset.created_at.desc()).all()

@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset

@router.get("/{dataset_id}/records")
def get_dataset_records(
    dataset_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=200),
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    query = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id)
    all_records = query.order_by(DatasetRecord.record_index.asc()).all()

    # In-memory search if q specified
    if q and q.strip():
        search_term = q.lower().strip()
        filtered = []
        for r in all_records:
            record_str = json.dumps(r.cleaned_data).lower()
            if search_term in record_str:
                filtered.append(r)
        records_to_paginate = filtered
    else:
        records_to_paginate = all_records

    total = len(records_to_paginate)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_records = records_to_paginate[start_idx:end_idx]

    return {
        "dataset_id": dataset_id,
        "total": total,
        "page": page,
        "per_page": per_page,
        "records": [
            {
                "id": r.id,
                "record_index": r.record_index,
                "source_url": r.source_url,
                "raw_data": r.raw_data,
                "cleaned_data": r.cleaned_data,
                "content_hash": r.content_hash,
                "created_at": r.created_at.isoformat()
            }
            for r in page_records
        ]
    }

@router.get("/{dataset_id}/quality", response_model=DataQualityReportOut)
def get_data_quality_report(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).all()
    cleaned_records = [r.cleaned_data for r in records]

    return DataQualityScorer.evaluate(cleaned_records, dataset_id=dataset_id)

@router.post("/{dataset_id}/clean")
def clean_and_deduplicate_dataset(
    dataset_id: str,
    req: CleanDataRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).all()
    updated_records = []

    for r in records:
        cleaned = DataCleaner.clean_record(r.raw_data, req.cleaner_rules)
        r.cleaned_data = cleaned
        r.content_hash = DataCleaner.compute_content_hash(cleaned, req.deduplication_keys)
        updated_records.append(cleaned)

    # Re-evaluate Quality Score
    quality_rep = DataQualityScorer.evaluate(updated_records, dataset_id=dataset_id)
    dataset.quality_score = quality_rep.overall_score
    db.commit()

    return {
        "message": f"Successfully cleaned {len(records)} records.",
        "new_quality_score": quality_rep.overall_score,
        "grade": quality_rep.grade
    }

@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: str,
    format: str = Query(default="json", pattern="^(json|csv|xlsx|jsonl)$"),
    cleaned_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Exports dataset in CSV, JSON, Excel (.xlsx), or JSONL formats.
    """
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).order_by(DatasetRecord.record_index.asc()).all()
    rows = []
    for r in records:
        row = dict(r.cleaned_data if cleaned_only else r.raw_data)
        row["_source_url"] = r.source_url
        rows.append(row)

    filename_base = f"dataset_{dataset_id[:8]}"

    if format == "json":
        json_bytes = json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8")
        return Response(
            content=json_bytes,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.json"'}
        )

    elif format == "jsonl":
        jsonl_str = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        return Response(
            content=jsonl_str.encode("utf-8"),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.jsonl"'}
        )

    elif format == "csv":
        if not rows:
            return Response(content="", media_type="text/csv")
        output = io.StringIO()
        # Collect all unique headers
        headers = []
        for r in rows:
            for k in r.keys():
                if k not in headers:
                    headers.append(k)

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            # Flatten lists to comma string
            flat_row = {}
            for k, v in r.items():
                if isinstance(v, list):
                    flat_row[k] = "; ".join(str(i) for i in v)
                elif isinstance(v, dict):
                    flat_row[k] = json.dumps(v)
                else:
                    flat_row[k] = v
            writer.writerow(flat_row)

        return Response(
            content=output.getvalue().encode("utf-8"),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.csv"'}
        )

    elif format == "xlsx":
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Extracted Records"

            if rows:
                headers = []
                for r in rows:
                    for k in r.keys():
                        if k not in headers:
                            headers.append(k)
                ws.append(headers)

                for r in rows:
                    row_vals = []
                    for h in headers:
                        v = r.get(h)
                        if isinstance(v, list):
                            row_vals.append("; ".join(str(i) for i in v))
                        elif isinstance(v, dict):
                            row_vals.append(json.dumps(v))
                        else:
                            row_vals.append(str(v) if v is not None else "")
                    ws.append(row_vals)

            output = io.BytesIO()
            wb.save(output)
            output.seek(0)

            return Response(
                content=output.getvalue(),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate Excel file: {e}")
