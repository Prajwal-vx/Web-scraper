import json
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from typing import List

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import ExtractedDataset, DatasetRecord
from nexus_app.models.rag import RAGPipeline, RAGChunk
from nexus_app.schemas.rag import RAGPipelineCreate, RAGPipelineOut, RAGChunkOut, RAGQueryRequest, RAGQueryResponse
from nexus_app.engine.rag import RAGPipelineEngine
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/rag", tags=["Scrape-to-RAG Pipeline"])

@router.post("/pipelines", response_model=RAGPipelineOut, status_code=status.HTTP_201_CREATED)
def create_rag_pipeline(
    req: RAGPipelineCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ingests an extracted dataset, chunks textual fields with configurable sliding window,
    and indexes them with source URLs and provenance metadata.
    """
    dataset = db.query(ExtractedDataset).join(Project, ExtractedDataset.project_id == Project.id).filter(
        ExtractedDataset.id == req.dataset_id,
        Project.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    pipeline = RAGPipeline(
        project_id=req.project_id,
        dataset_id=req.dataset_id,
        name=req.name,
        chunk_size=req.chunk_size,
        chunk_overlap=req.chunk_overlap
    )
    db.add(pipeline)
    db.flush()

    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == req.dataset_id).all()
    chunk_count = 0

    for r in records:
        chunks = RAGPipelineEngine.process_record_for_rag(
            record_id=r.id,
            source_url=r.source_url,
            data=r.cleaned_data,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap
        )
        for c in chunks:
            chunk_rec = RAGChunk(
                pipeline_id=pipeline.id,
                source_url=c["source_url"],
                record_id=c["record_id"],
                chunk_index=c["chunk_index"],
                text_content=c["text_content"],
                metadata_json=c["metadata"],
                content_hash=c["content_hash"]
            )
            db.add(chunk_rec)
            chunk_count += 1

    pipeline.total_chunks = chunk_count
    db.commit()
    db.refresh(pipeline)
    return pipeline

@router.post("/pipelines/{pipeline_id}/query", response_model=RAGQueryResponse)
def query_rag_pipeline(
    pipeline_id: str,
    req: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Performs source-linked semantic similarity retrieval against indexed chunks.
    """
    pipeline = db.query(RAGPipeline).join(Project, RAGPipeline.project_id == Project.id).filter(
        RAGPipeline.id == pipeline_id,
        Project.user_id == current_user.id
    ).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="RAG Pipeline not found")

    db_chunks = db.query(RAGChunk).filter(RAGChunk.pipeline_id == pipeline_id).all()
    chunk_dicts = [
        {
            "id": c.id,
            "source_url": c.source_url,
            "chunk_index": c.chunk_index,
            "text_content": c.text_content,
            "metadata_json": c.metadata_json
        }
        for c in db_chunks
    ]

    matches = RAGPipelineEngine.query_chunks(chunk_dicts, req.query, top_k=req.top_k)
    results = [
        RAGChunkOut(
            id=m["id"],
            source_url=m["source_url"],
            chunk_index=m["chunk_index"],
            text_content=m["text_content"],
            metadata_json=m.get("metadata_json"),
            similarity_score=m.get("similarity_score")
        )
        for m in matches
    ]

    return RAGQueryResponse(
        query=req.query,
        matches=results,
        total_matches=len(results)
    )

@router.get("/pipelines/{pipeline_id}/export")
def export_rag_jsonl(
    pipeline_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Exports chunked corpus as JSONL with source metadata, ready for Vector DB bulk upload.
    """
    pipeline = db.query(RAGPipeline).join(Project, RAGPipeline.project_id == Project.id).filter(
        RAGPipeline.id == pipeline_id,
        Project.user_id == current_user.id
    ).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="RAG Pipeline not found")

    chunks = db.query(RAGChunk).filter(RAGChunk.pipeline_id == pipeline_id).all()
    lines = []
    for c in chunks:
        doc = {
            "id": c.id,
            "text": c.text_content,
            "metadata": {
                "source_url": c.source_url,
                "chunk_index": c.chunk_index,
                "pipeline_id": pipeline.id,
                "content_hash": c.content_hash,
            }
        }
        lines.append(json.dumps(doc, ensure_ascii=False))

    return Response(
        content="\n".join(lines).encode("utf-8"),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="rag_{pipeline_id[:8]}.jsonl"'}
    )
