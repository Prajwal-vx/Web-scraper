import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import CrawlJob, ScrapingConfig, JobLog
from nexus_app.schemas.job import JobCreate, JobOut, JobLogOut, JobRetryAdvisorOut
from nexus_app.tasks.job_runner import runner
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["Jobs & Execution"])

@router.get("", response_model=List[JobOut])
def list_jobs(
    project_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CrawlJob).join(Project, CrawlJob.project_id == Project.id).filter(Project.user_id == current_user.id)
    if project_id:
        query = query.filter(CrawlJob.project_id == project_id)

    jobs = query.order_by(CrawlJob.created_at.desc()).all()
    out = []
    for j in jobs:
        cfg_name = j.config.name if j.config else "Ad-hoc Run"
        item = JobOut.model_validate(j)
        item.config_name = cfg_name
        out.append(item)
    return out

@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_and_start_job(
    req: JobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == req.project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    config_id = req.config_id

    # If ad-hoc URL & selectors provided without config_id, create an inline ScrapingConfig
    if not config_id and req.url:
        inline_config = ScrapingConfig(
            project_id=project.id,
            name=req.name or f"Crawl {req.url}",
            starting_urls=[req.url],
            selectors=req.selectors or [{"name": "title", "selector": "h1, title", "selector_type": "css", "extract_type": "text"}],
            extraction_mode=req.extraction_mode or "http",
            max_pages=req.max_pages or 10,
            crawl_delay=1.0,
            same_domain_only=1
        )
        db.add(inline_config)
        db.commit()
        db.refresh(inline_config)
        config_id = inline_config.id

    job = CrawlJob(
        project_id=project.id,
        config_id=config_id,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Dispatch to background task runner
    runner.submit_job(job.id)

    cfg_name = job.config.name if job.config else "Ad-hoc Run"
    item = JobOut.model_validate(job)
    item.config_name = cfg_name
    return item

@router.get("/{job_id}", response_model=JobOut)
def get_job_details(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(CrawlJob).join(Project, CrawlJob.project_id == Project.id).filter(
        CrawlJob.id == job_id,
        Project.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    item = JobOut.model_validate(job)
    item.config_name = job.config.name if job.config else "Ad-hoc Run"
    return item

@router.post("/{job_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(CrawlJob).join(Project, CrawlJob.project_id == Project.id).filter(
        CrawlJob.id == job_id,
        Project.user_id == current_user.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in ("completed", "failed", "cancelled"):
        return {"message": f"Job is already {job.status}"}

    runner.cancel_job(job_id)
    job.status = "cancelled"
    db.commit()
    return {"message": "Job cancellation initiated successfully."}

@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    old_job = db.query(CrawlJob).join(Project, CrawlJob.project_id == Project.id).filter(
        CrawlJob.id == job_id,
        Project.user_id == current_user.id
    ).first()
    if not old_job:
        raise HTTPException(status_code=404, detail="Job not found")

    new_job = CrawlJob(
        project_id=old_job.project_id,
        config_id=old_job.config_id,
        status="pending",
        retry_count=old_job.retry_count + 1
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    runner.submit_job(new_job.id)

    item = JobOut.model_validate(new_job)
    item.config_name = new_job.config.name if new_job.config else "Ad-hoc Run"
    return item

@router.get("/{job_id}/logs", response_model=List[JobLogOut])
def get_job_logs(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(JobLog).filter(JobLog.job_id == job_id).order_by(JobLog.timestamp.asc()).all()
    return logs

@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Server-Sent Events (SSE) live progress and log stream for job monitoring.
    """
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = runner.get_or_create_queue(job_id)

    async def event_generator():
        # Emit initial state
        init_evt = {"type": "status", "data": {"status": job.status, "records_count": job.records_count}}
        yield f"data: {json.dumps(init_evt)}\n\n"

        while True:
            try:
                # Wait for next event with a timeout for heartbeat
                item = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("data", {}).get("status") in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                # Send SSE keep-alive comment
                yield ": keep-alive\n\n"
            except asyncio.CancelledError:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{job_id}/retry-advisor", response_model=JobRetryAdvisorOut)
def get_job_retry_advisor(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Smart Retry Advisor: Diagnoses failure patterns (rate limit, timeout, empty elements, JS needed)
    and provides safe recommendations.
    """
    job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    actions = []
    reason = job.error_summary or "Unknown error"
    recommended_mode = None

    if job.status == "completed" and job.records_count == 0:
        reason = "Crawl succeeded but no records or matching fields were extracted."
        actions.append("The target website may require JavaScript hydration. Switch Extraction Mode from 'HTTP' to 'Browser' (Playwright).")
        actions.append("Inspect the CSS/XPath selectors using the Visual Selector Builder to ensure the classes match.")
        recommended_mode = "browser"
    elif "403" in reason or "Forbidden" in reason:
        reason = "Server returned 403 Forbidden."
        actions.append("Check the site's robots.txt to ensure your path is allowed.")
        actions.append("Increase crawl delay to respect rate limits.")
    elif "429" in reason or "Rate" in reason:
        reason = "Server returned HTTP 429 Too Many Requests."
        actions.append("Increase crawl delay to at least 3.0 - 5.0 seconds.")
        actions.append("Lower max concurrent pages.")
    elif "Timeout" in reason:
        reason = "Network connection timed out."
        actions.append("Increase request timeout setting.")
        actions.append("Verify target host DNS availability.")
    elif job.status == "completed":
        reason = "Job completed successfully."
        actions.append("No errors detected. Dataset is ready for export or RAG indexing.")

    return JobRetryAdvisorOut(
        job_id=job.id,
        status=job.status,
        primary_failure_reason=reason,
        suggested_actions=actions,
        can_retry=job.status in ("failed", "cancelled", "completed"),
        recommended_mode_switch=recommended_mode
    )
