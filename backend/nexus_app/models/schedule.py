from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from nexus_app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class ScheduledJob(Base):
    __tablename__ = "scheduled_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(String(36), ForeignKey("scraping_configs.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    cron_expression = Column(String(50), nullable=True)  # e.g. "0 */6 * * *"
    interval_minutes = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)
    next_run_at = Column(DateTime, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="schedules")
    config = relationship("ScrapingConfig")

class MonitoringSnapshot(Base):
    __tablename__ = "monitoring_snapshots"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(String(36), ForeignKey("scraping_configs.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(String(36), ForeignKey("extracted_datasets.id", ondelete="CASCADE"), nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    total_records = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class ChangeEvent(Base):
    __tablename__ = "change_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    old_snapshot_id = Column(String(36), ForeignKey("monitoring_snapshots.id", ondelete="CASCADE"), nullable=False)
    new_snapshot_id = Column(String(36), ForeignKey("monitoring_snapshots.id", ondelete="CASCADE"), nullable=False)
    added_count = Column(Integer, default=0)
    removed_count = Column(Integer, default=0)
    modified_count = Column(Integer, default=0)
    diff_details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
