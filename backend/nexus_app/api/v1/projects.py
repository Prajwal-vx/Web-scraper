from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from nexus_app.database import get_db
from nexus_app.models.user import User
from nexus_app.models.project import Project
from nexus_app.models.scraping import ScrapingConfig
from nexus_app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from nexus_app.schemas.extraction import ScrapingConfigCreate, ScrapingConfigUpdate, ScrapingConfigOut
from nexus_app.security.auth import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects & Configs"])

@router.get("", response_model=List[ProjectOut])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    results = []
    for p in projects:
        p_out = ProjectOut(
            id=p.id,
            name=p.name,
            description=p.description,
            user_id=p.user_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
            configs_count=len(p.configs),
            jobs_count=len(p.jobs)
        )
        results.append(p_out)
    return results

@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = Project(
        name=project_in.name,
        description=project_in.description,
        user_id=current_user.id
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        user_id=project.user_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        configs_count=0,
        jobs_count=0
    )

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        user_id=project.user_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        configs_count=len(project.configs),
        jobs_count=len(project.jobs)
    )

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return None

# Scraping Configurations
@router.post("/{project_id}/configs", response_model=ScrapingConfigOut, status_code=status.HTTP_201_CREATED)
def create_scraping_config(
    project_id: str,
    config_in: ScrapingConfigBase,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    selectors_data = [s.model_dump() for s in config_in.selectors]
    cleaner_rules_data = [c.model_dump() for c in config_in.cleaner_rules] if config_in.cleaner_rules else []

    config = ScrapingConfig(
        project_id=project_id,
        name=config_in.name,
        starting_urls=config_in.starting_urls,
        selectors=selectors_data,
        extraction_mode=config_in.extraction_mode,
        max_pages=config_in.max_pages,
        max_depth=config_in.max_depth,
        crawl_delay=config_in.crawl_delay,
        same_domain_only=1 if config_in.same_domain_only else 0,
        cleaner_rules=cleaner_rules_data
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config

@router.get("/{project_id}/configs", response_model=List[ScrapingConfigOut])
def list_scraping_configs(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.configs
