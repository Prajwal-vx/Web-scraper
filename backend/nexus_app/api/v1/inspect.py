from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from nexus_app.schemas.extraction import InspectRequest, InspectResponse, SelectorTestRequest, SelectorTestResponse, SelectorTestResult
from nexus_app.security.ssrf import validate_url, SSRFSecurityError
from nexus_app.engine.fetcher import SecureFetcher
from nexus_app.engine.browser import BrowserWorker
from nexus_app.engine.extractor import ExtractorEngine
from nexus_app.security.auth import get_current_user
from nexus_app.models.user import User

router = APIRouter(prefix="/inspect", tags=["Visual Inspector & Selector Tester"])

@router.post("", response_model=InspectResponse)
def inspect_website(
    req: InspectRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Validates URL against SSRF, retrieves content, evaluates robots.txt,
    discovers sitemaps, and extracts page preview and metadata.
    """
    try:
        validate_url(req.url)
    except SSRFSecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    fetcher = SecureFetcher()
    is_allowed, crawl_delay = fetcher.is_url_allowed_by_robots(req.url)
    _, sitemaps = fetcher.get_robots_parser(req.url)

    html_content = ""
    status_code = 200
    content_type = "text/html"

    try:
        if req.mode == "browser":
            worker = BrowserWorker()
            html_content = worker.render_page(req.url)
        else:
            res = fetcher.fetch(req.url)
            status_code = res.status_code
            content_type = res.content_type
            html_content = res.content
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to retrieve target URL: {e}")

    extractor = ExtractorEngine(html_content, base_url=req.url)
    meta = extractor.get_page_metadata()
    json_ld = extractor.get_json_ld()
    links = extractor.get_all_links()

    # Create safe HTML preview snippet (first 10,000 chars)
    html_preview = html_content[:15000]

    return InspectResponse(
        url=req.url,
        status_code=status_code,
        content_type=content_type,
        title=meta.get("title", ""),
        html_preview=html_preview,
        robots_allowed=is_allowed,
        robots_crawl_delay=crawl_delay,
        sitemaps_found=sitemaps[:5],
        discovered_links=links[:50],
        meta_tags={k: v for k, v in meta.items() if k != "title"},
        json_ld_schemas=json_ld[:5]
    )

@router.post("/test-selectors", response_model=SelectorTestResponse)
def test_selectors(
    req: SelectorTestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Tests CSS or XPath selectors against a target URL or provided HTML string,
    returning match counts, sample extracted values, and validation errors.
    """
    html = req.html or ""
    base_url = req.url or ""

    if not html and req.url:
        try:
            validate_url(req.url)
            fetcher = SecureFetcher()
            res = fetcher.fetch(req.url)
            html = res.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL for testing: {e}")

    if not html:
        raise HTTPException(status_code=400, detail="Either 'url' or 'html' must be supplied.")

    extractor = ExtractorEngine(html, base_url=base_url)
    results: List[SelectorTestResult] = []
    record_preview: Dict[str, Any] = {}

    for rule in req.selectors:
        try:
            val = extractor.extract_field(
                selector=rule.selector,
                selector_type=rule.selector_type,
                extract_type=rule.extract_type,
                attribute_name=rule.attribute_name,
                is_multiple=rule.is_multiple,
                regex_pattern=rule.regex_pattern,
                default_value=rule.default_value
            )

            samples = val if isinstance(val, list) else ([val] if val is not None else [])
            match_count = len(samples)

            results.append(SelectorTestResult(
                field_name=rule.name,
                selector=rule.selector,
                selector_type=rule.selector_type,
                match_count=match_count,
                sample_values=samples[:5],
                is_valid=True,
                error_message=None
            ))
            record_preview[rule.name] = val
        except Exception as e:
            results.append(SelectorTestResult(
                field_name=rule.name,
                selector=rule.selector,
                selector_type=rule.selector_type,
                match_count=0,
                sample_values=[],
                is_valid=False,
                error_message=str(e)
            ))

    return SelectorTestResponse(
        results=results,
        records_preview=[record_preview] if record_preview else []
    )
