import time
import threading
from datetime import datetime, timedelta
import logging

from nexus_app.database import SessionLocal
from nexus_app.models.schedule import ScheduledJob
from nexus_app.models.scraping import CrawlJob
from nexus_app.tasks.job_runner import runner

logger = logging.getLogger("nexus.tasks.scheduler")

class SchedulerDaemon:
    """
    Lightweight background scheduler daemon checking for recurring jobs
    based on configured minute intervals.
    """

    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval_seconds = check_interval_seconds
        self.running = False
        self.thread: threading.Thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Scheduler daemon started.")

    def stop(self):
        self.running = False

    def _run_loop(self):
        while self.running:
            try:
                self._check_and_trigger()
            except Exception as e:
                logger.error(f"Error in scheduler tick: {e}")
            time.sleep(self.check_interval_seconds)

    def _check_and_trigger(self):
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            active_schedules = db.query(ScheduledJob).filter(
                ScheduledJob.is_active == True,
                (ScheduledJob.next_run_at == None) | (ScheduledJob.next_run_at <= now)
            ).all()

            for sched in active_schedules:
                # Trigger job
                new_job = CrawlJob(
                    project_id=sched.project_id,
                    config_id=sched.config_id,
                    status="pending"
                )
                db.add(new_job)
                db.flush()

                # Schedule next run
                sched.last_run_at = now
                interval_mins = sched.interval_minutes or 60
                sched.next_run_at = now + timedelta(minutes=interval_mins)
                db.commit()

                # Submit to background runner
                runner.submit_job(new_job.id)
                logger.info(f"Triggered scheduled job {new_job.id} for config {sched.config_id}")
        finally:
            db.close()

scheduler = SchedulerDaemon()
