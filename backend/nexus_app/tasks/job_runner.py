import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor
import logging

from nexus_app.database import SessionLocal
from nexus_app.models.scraping import CrawlJob, JobLog, ExtractedDataset, DatasetRecord, ScrapingConfig
from nexus_app.engine.crawler import CrawlerCoordinator
from nexus_app.engine.cleaner import DataCleaner
from nexus_app.engine.quality import DataQualityScorer
from nexus_app.config import settings

logger = logging.getLogger("nexus.tasks.runner")

class JobRunner:
    """
    Background job execution manager with bounded concurrency,
    event streaming queues, and cancellation support.
    """

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cancelled_jobs: Set[str] = set()
        self.job_event_queues: Dict[str, asyncio.Queue] = {}

    def get_or_create_queue(self, job_id: str) -> asyncio.Queue:
        if job_id not in self.job_event_queues:
            self.job_event_queues[job_id] = asyncio.Queue()
        return self.job_event_queues[job_id]

    def emit_event(self, job_id: str, event_type: str, data: Dict[str, Any]):
        q = self.job_event_queues.get(job_id)
        if q:
            try:
                # Put into queue without blocking
                q.put_nowait({"type": event_type, "data": data, "timestamp": datetime.utcnow().isoformat()})
            except Exception:
                pass

    def cancel_job(self, job_id: str) -> bool:
        self.cancelled_jobs.add(job_id)
        self.emit_event(job_id, "status", {"status": "cancelled", "message": "Cancellation requested."})
        return True

    def submit_job(self, job_id: str):
        """Dispatches job to thread pool executor."""
        self.executor.submit(self._execute_job, job_id)

    def _execute_job(self, job_id: str):
        db = SessionLocal()
        start_time = time.time()
        try:
            job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
            if not job:
                logger.error(f"Job {job_id} not found in database.")
                return

            config = db.query(ScrapingConfig).filter(ScrapingConfig.id == job.config_id).first() if job.config_id else None

            # Mark running
            job.status = "running"
            job.started_at = datetime.utcnow()
            db.commit()

            self.emit_event(job_id, "status", {"status": "running"})

            def log_callback(level: str, msg: str):
                try:
                    db_log = JobLog(job_id=job_id, level=level, message=msg, timestamp=datetime.utcnow())
                    db.add(db_log)
                    db.commit()
                    self.emit_event(job_id, "log", {"level": level, "message": msg})
                except Exception as e:
                    logger.debug(f"Error persisting log: {e}")

            def progress_callback(curr: int, total: int):
                self.emit_event(job_id, "progress", {"current": curr, "total": total, "percent": round((curr / total) * 100, 1) if total > 0 else 0})

            def should_cancel() -> bool:
                return job_id in self.cancelled_jobs

            # Extract parameters
            starting_urls = config.starting_urls if config else []
            selectors = config.selectors if config else []
            extraction_mode = config.extraction_mode if config else "http"
            max_pages = config.max_pages if config else 10
            max_depth = config.max_depth if config else 2
            crawl_delay = config.crawl_delay if config else 1.0
            cleaner_rules = config.cleaner_rules if config else []

            coordinator = CrawlerCoordinator(
                starting_urls=starting_urls,
                selectors=selectors,
                extraction_mode=extraction_mode,
                max_pages=max_pages,
                max_depth=max_depth,
                crawl_delay=crawl_delay,
                log_callback=log_callback,
                progress_callback=progress_callback
            )

            results = coordinator.run_crawl(should_cancel=should_cancel)

            elapsed = round(time.time() - start_time, 2)
            job.duration_seconds = elapsed
            job.pages_scraped = len(coordinator.visited_urls)
            job.finished_at = datetime.utcnow()

            if should_cancel():
                job.status = "cancelled"
                db.commit()
                self.emit_event(job_id, "status", {"status": "cancelled"})
                return

            # Process & Store Results
            valid_results = [r for r in results if r.data]
            error_count = len([r for r in results if r.error])
            job.errors_count = error_count

            # Create Dataset
            dataset_name = f"Dataset - {config.name if config else 'Ad-hoc'} ({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})"
            schema_json = {"selectors": selectors, "fields": [s.get("name") for s in selectors]}
            dataset = ExtractedDataset(
                job_id=job_id,
                project_id=job.project_id,
                name=dataset_name,
                schema_json=schema_json,
                total_records=len(valid_results),
            )
            db.add(dataset)
            db.flush()

            raw_records_for_scoring = []

            for idx, item in enumerate(valid_results):
                cleaned_data = DataCleaner.clean_record(item.data, cleaner_rules)
                c_hash = DataCleaner.compute_content_hash(cleaned_data)
                rec = DatasetRecord(
                    dataset_id=dataset.id,
                    record_index=idx,
                    source_url=item.url,
                    raw_data=item.data,
                    cleaned_data=cleaned_data,
                    content_hash=c_hash
                )
                db.add(rec)
                raw_records_for_scoring.append(cleaned_data)

            # Calculate Quality Score
            quality_report = DataQualityScorer.evaluate(raw_records_for_scoring, dataset_id=dataset.id)
            dataset.quality_score = quality_report.overall_score
            job.quality_score = quality_report.overall_score
            job.records_count = len(valid_results)
            job.status = "completed"

            db.commit()
            self.emit_event(job_id, "status", {"status": "completed", "records_count": len(valid_results), "quality_score": quality_report.overall_score})

        except Exception as e:
            logger.exception(f"Fatal error executing job {job_id}: {e}")
            try:
                job = db.query(CrawlJob).filter(CrawlJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_summary = str(e)
                    job.finished_at = datetime.utcnow()
                    job.duration_seconds = round(time.time() - start_time, 2)
                    db.commit()
                self.emit_event(job_id, "status", {"status": "failed", "error": str(e)})
            except Exception:
                pass
        finally:
            self.cancelled_jobs.discard(job_id)
            db.close()

runner = JobRunner(max_workers=settings.DEFAULT_MAX_CONCURRENT_JOBS)
