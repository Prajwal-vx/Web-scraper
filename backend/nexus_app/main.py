import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from nexus_app.config import settings
from nexus_app.database import engine, Base
import nexus_app.models  # Ensure all models are registered with Base.metadata
from nexus_app.api.v1 import api_v1_router
from nexus_app.tasks.scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables if not exist
    Base.metadata.create_all(bind=engine)
    scheduler.start()
    yield
    # Shutdown
    scheduler.stop()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-Oriented AI-Powered Web Scraping & Data Intelligence Platform",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_v1_router)

# Mount frontend / static directory if present
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

index_html_path = os.path.join(static_dir, "index.html")

@app.get("/", include_in_schema=False)
def serve_dashboard():
    if os.path.isfile(index_html_path):
        return FileResponse(index_html_path)
    return {
        "message": f"Welcome to {settings.APP_NAME} API. Visit /docs for OpenAPI documentation.",
        "status": "operational"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
