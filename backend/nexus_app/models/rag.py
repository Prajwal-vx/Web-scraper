from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from nexus_app.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class RAGPipeline(Base):
    __tablename__ = "rag_pipelines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    dataset_id = Column(String(36), ForeignKey("extracted_datasets.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=50)
    total_chunks = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    chunks = relationship("RAGChunk", back_populates="pipeline", cascade="all, delete-orphan")

class RAGChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    pipeline_id = Column(String(36), ForeignKey("rag_pipelines.id", ondelete="CASCADE"), nullable=False, index=True)
    source_url = Column(String(2048), nullable=False)
    record_id = Column(String(36), nullable=True)
    chunk_index = Column(Integer, default=0)
    text_content = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    embedding_vector = Column(JSON, nullable=True)  # List[float]
    content_hash = Column(String(64), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pipeline = relationship("RAGPipeline", back_populates="chunks")
