from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class RAGPipelineCreate(BaseModel):
    project_id: str
    dataset_id: str
    name: str
    chunk_size: int = 500
    chunk_overlap: int = 50

class RAGPipelineOut(BaseModel):
    id: str
    project_id: str
    dataset_id: str
    name: str
    chunk_size: int
    chunk_overlap: int
    total_chunks: int
    created_at: datetime

    class Config:
        from_attributes = True

class RAGChunkOut(BaseModel):
    id: str
    source_url: str
    chunk_index: int
    text_content: str
    metadata_json: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5

class RAGQueryResponse(BaseModel):
    query: str
    matches: List[RAGChunkOut]
    total_matches: int
