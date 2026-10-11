from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class JobCreate(BaseModel):
    project_id: str
    config_id: Optional[str] = None
    # Ad-hoc config if not pointing to saved config
    url: Optional[str] = None
    name: Optional[str] = None
    selectors: Optional[List[Dict[str, Any]]] = None
    max_pages: Optional[int] = 10
    extraction_mode: Optional[str] = "http"

class JobLogOut(BaseModel):
    id: str
    job_id: str
    level: str
    message: str
    timestamp: datetime
    metadata_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class JobOut(BaseModel):
    id: str
    project_id: str
    config_id: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    pages_scraped: int
    records_count: int
    errors_count: int
    error_summary: Optional[str] = None
    duration_seconds: float
    retry_count: int
    quality_score: Optional[float] = None
    created_at: datetime
    config_name: Optional[str] = None

    class Config:
        from_attributes = True

class JobRetryAdvisorOut(BaseModel):
    job_id: str
    status: str
    primary_failure_reason: Optional[str] = None
    suggested_actions: List[str] = []
    can_retry: bool = True
    recommended_mode_switch: Optional[str] = None  # e.g., "browser" if JS rendered
