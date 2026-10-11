from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from nexus_app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(150), nullable=False, index=True)
    description = Column(Text, nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="projects")
    configs = relationship("ScrapingConfig", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("CrawlJob", back_populates="project", cascade="all, delete-orphan")
    datasets = relationship("ExtractedDataset", back_populates="project", cascade="all, delete-orphan")
    schedules = relationship("ScheduledJob", back_populates="project", cascade="all, delete-orphan")
