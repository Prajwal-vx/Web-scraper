from fastapi import APIRouter, Depends, HTTPException
from nexus_app.schemas.ai import AISchemaRequest, AISchemaResponse
from nexus_app.engine.ai_assistant import AIAssistantEngine
from nexus_app.engine.fetcher import SecureFetcher
from nexus_app.security.ssrf import validate_url
from nexus_app.security.auth import get_current_user
from nexus_app.models.user import User

router = APIRouter(prefix="/ai", tags=["AI Extraction Assistant"])

@router.post("/suggest-schema", response_model=AISchemaResponse)
def suggest_schema(
    req: AISchemaRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Accepts natural language extraction instructions and website sample,
    returning structured schema proposals, data types, and deterministic CSS/XPath selectors.
    """
    html_content = req.html_snippet or ""
    base_url = req.url or ""

    if not html_content and req.url:
        try:
            validate_url(req.url)
            fetcher = SecureFetcher()
            res = fetcher.fetch(req.url)
            html_content = res.content
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed retrieving target URL: {e}")

    if not html_content:
        raise HTTPException(status_code=400, detail="Either 'url' or 'html_snippet' must be provided.")

    return AIAssistantEngine.generate_schema(
        html_snippet=html_content,
        instruction=req.user_instruction,
        base_url=base_url
    )
