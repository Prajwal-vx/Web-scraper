from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from nexus_app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class ScrapingConfig(Base):
    __tablename__ = "scraping_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    starting_urls = Column(JSON, nullable=False)  # List[str]
    selectors = Column(JSON, nullable=False)      # List[Dict[str, Any]]
    extraction_mode = Column(String(50), default="http")  # "http" or "browser"
    max_pages = Column(Integer, default=10)
    max_depth = Column(Integer, default=2)
    crawl_delay = Column(Float, default=1.0)
    same_domain_only = Column(Integer, default=1)  # 1 for True, 0 for False
    cleaner_rules = Column(JSON, nullable=True)   # Dict of field cleaning actions
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="configs")
    jobs = relationship("CrawlJob", back_populates="config", cascade="all, delete-orphan")

class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(String(36), ForeignKey("scraping_configs.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="pending", index=True)  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    pages_scraped = Column(Integer, default=0)
    records_count = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    duration_seconds = Column(Float, default=0.0)
    retry_count = Column(Integer, default=0)
    quality_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="jobs")
    config = relationship("ScrapingConfig", back_populates="jobs")
    logs = relationship("JobLog", back_populates="job", cascade="all, delete-orphan")
    dataset = relationship("ExtractedDataset", back_populates="job", uselist=False, cascade="all, delete-orphan")

class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(String(20), default="INFO")
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    job = relationship("CrawlJob", back_populates="logs")

class ExtractedDataset(Base):
    __tablename__ = "extracted_datasets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    schema_json = Column(JSON, nullable=True)
    total_records = Column(Integer, default=0)
    quality_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("CrawlJob", back_populates="dataset")
    project = relationship("Project", back_populates="datasets")
    records = relationship("DatasetRecord", back_populates="dataset", cascade="all, delete-orphan")

class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    dataset_id = Column(String(36), ForeignKey("extracted_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    record_index = Column(Integer, default=0)
    source_url = Column(String(2048), nullable=False)
    raw_data = Column(JSON, nullable=False)
    cleaned_data = Column(JSON, nullable=False)
    content_hash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("ExtractedDataset", back_populates="records")
