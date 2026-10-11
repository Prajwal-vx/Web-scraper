from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class DatasetRecordOut(BaseModel):
    id: str
    record_index: int
    source_url: str
    raw_data: Dict[str, Any]
    cleaned_data: Dict[str, Any]
    content_hash: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DatasetOut(BaseModel):
    id: str
    job_id: str
    project_id: str
    name: str
    schema_json: Optional[Dict[str, Any]] = None
    total_records: int
    quality_score: float
    created_at: datetime

    class Config:
        from_attributes = True
        protected_namespaces = ()

class DataQualityMetric(BaseModel):
    metric_name: str
    score: float
    weight: float
    description: str
    details: Dict[str, Any]

class DataQualityReportOut(BaseModel):
    dataset_id: str
    overall_score: float
    grade: str  # A, B, C, D, F
    metrics: List[DataQualityMetric]
    total_records: int
    duplicate_records_count: int
    missing_required_count: int
    fields_evaluated: List[str]

class CleanDataRequest(BaseModel):
    cleaner_rules: List[Dict[str, Any]]
    deduplication_keys: Optional[List[str]] = None
