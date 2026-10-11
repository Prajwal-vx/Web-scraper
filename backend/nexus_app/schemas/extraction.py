
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

class SelectorRule(BaseModel):
    name: str
    selector: str
    selector_type: str = "css"  # css, xpath, jsonld, regex
    extract_type: str = "text"   # text, html, attr, regex
    attribute_name: Optional[str] = None  # e.g., 'href', 'src', 'data-id'
    is_multiple: bool = False
    is_required: bool = False
    regex_pattern: Optional[str] = None
    default_value: Optional[str] = None

class CleanerRule(BaseModel):
    field_name: str
    action: str  # trim, strip_html, to_lower, to_upper, to_int, to_float, to_date, normalize_url, regex_replace
    params: Optional[Dict[str, Any]] = None

class ScrapingConfigBase(BaseModel):
    name: str
    starting_urls: List[str]
    selectors: List[SelectorRule]
    extraction_mode: str = "http"  # http, browser
    max_pages: int = Field(default=10, ge=1, le=500)
    max_depth: int = Field(default=2, ge=0, le=10)
    crawl_delay: float = Field(default=1.0, ge=0.1, le=30.0)
    same_domain_only: bool = True
    cleaner_rules: Optional[List[CleanerRule]] = None

class ScrapingConfigCreate(ScrapingConfigBase):
    project_id: str

class ScrapingConfigUpdate(BaseModel):
    name: Optional[str] = None
    starting_urls: Optional[List[str]] = None
    selectors: Optional[List[SelectorRule]] = None
    extraction_mode: Optional[str] = None
    max_pages: Optional[int] = None
    max_depth: Optional[int] = None
    crawl_delay: Optional[float] = None
    same_domain_only: Optional[bool] = None
    cleaner_rules: Optional[List[CleanerRule]] = None

class ScrapingConfigOut(ScrapingConfigBase):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class InspectRequest(BaseModel):
    url: str
    mode: str = "http"  # http or browser

class InspectResponse(BaseModel):
    url: str
    status_code: int
    content_type: str
    title: Optional[str] = None
    html_preview: str
    robots_allowed: bool
    robots_crawl_delay: Optional[float] = None
    sitemaps_found: List[str] = []
    discovered_links: List[str] = []
    meta_tags: Dict[str, str] = {}
    json_ld_schemas: List[Dict[str, Any]] = []

class SelectorTestRequest(BaseModel):
    url: Optional[str] = None
    html: Optional[str] = None
    selectors: List[SelectorRule]

class SelectorTestResult(BaseModel):
    field_name: str
    selector: str
    selector_type: str
    match_count: int
    sample_values: List[Any]
    is_valid: bool
    error_message: Optional[str] = None

class SelectorTestResponse(BaseModel):
    results: List[SelectorTestResult]
    records_preview: List[Dict[str, Any]]
