from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ProjectOut(ProjectBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    configs_count: Optional[int] = 0
    jobs_count: Optional[int] = 0

    class Config:
        from_attributes = True
