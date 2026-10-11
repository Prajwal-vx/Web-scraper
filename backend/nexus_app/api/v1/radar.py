from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import ExtractedDataset, DatasetRecord
from nexus_app.engine.diff import DatasetDiffer
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/radar", tags=["Website Change Radar & Diff Viewer"])

class DiffRequest(BaseModel):
    old_dataset_id: str
    new_dataset_id: str
    key_fields: Optional[List[str]] = None

@router.post("/diff")
def compare_datasets(
    req: DiffRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compares two extraction snapshots, identifying newly added,
    removed, and field-level modified records.
    """
    old_dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == req.old_dataset_id,
        Project.user_id == current_user.id
    ).first()
    new_dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == req.new_dataset_id,
        Project.user_id == current_user.id
    ).first()

    if not old_dataset or not new_dataset:
        raise HTTPException(status_code=404, detail="One or both datasets could not be found.")

    old_records = [r.cleaned_data for r in db.query(DatasetRecord).filter(DatasetRecord.dataset_id == req.old_dataset_id).all()]
    new_records = [r.cleaned_data for r in db.query(DatasetRecord).filter(DatasetRecord.dataset_id == req.new_dataset_id).all()]

    diff_report = DatasetDiffer.compare_datasets(old_records, new_records, key_fields=req.key_fields)
    return {
        "old_dataset_id": req.old_dataset_id,
        "new_dataset_id": req.new_dataset_id,
        "diff": diff_report
    }
