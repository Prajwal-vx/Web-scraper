import os
import psutil
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from nexus_app.database import get_db
from nexus_app.config import settings

router = APIRouter(tags=["Health & Status"])

@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    mem = psutil.virtual_memory() if hasattr(psutil, "virtual_memory") else None

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "memory_percent": mem.percent if mem else "unknown",
        "playwright_enabled": settings.PLAYWRIGHT_ENABLED,
        "ai_provider": settings.AI_PROVIDER
    }
