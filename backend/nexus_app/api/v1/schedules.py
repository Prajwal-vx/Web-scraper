from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import ScrapingConfig
from nexus_app.models.schedule import ScheduledJob
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/schedules", tags=["Scheduled Jobs & Monitoring"])

class ScheduleCreate(BaseModel):
    project_id: str
    config_id: str
    name: str
    interval_minutes: int = 60
    is_active: bool = True

class ScheduleOut(BaseModel):
    id: str
    project_id: str
    config_id: str
    name: str
    interval_minutes: int
    is_active: bool
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

@router.get("", response_model=List[ScheduleOut])
def list_schedules(
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(ScheduledJob).join(Project, ScheduledJob.project_id == Project.id).filter(
        Project.user_id == current_user.id
    )
    if project_id:
        query = query.filter(ScheduledJob.project_id == project_id)
    return query.order_by(ScheduledJob.created_at.desc()).all()

@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    req: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    config = db.query(ScrapingConfig).filter(ScrapingConfig.id == req.config_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="Scraping configuration not found")

    next_run = datetime.utcnow() + timedelta(minutes=req.interval_minutes)

    schedule = ScheduledJob(
        project_id=req.project_id,
        config_id=req.config_id,
        name=req.name,
        interval_minutes=req.interval_minutes,
        is_active=req.is_active,
        next_run_at=next_run
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule

@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    schedule = db.query(ScheduledJob).join(Project, ScheduledJob.project_id == Project.id).filter(
        ScheduledJob.id == schedule_id,
        Project.user_id == current_user.id
    ).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    db.delete(schedule)
    db.commit()
    return None
