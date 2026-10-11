from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class AISchemaFieldProposal(BaseModel):
    field_name: str
    data_type: str  # text, number, url, image_url, date, list
    selector: str
    selector_type: str  # css or xpath
    extract_type: str   # text, attr, html
    attribute_name: Optional[str] = None
    confidence: float
    sample_value: Optional[str] = None
    reasoning: Optional[str] = None

class AISchemaRequest(BaseModel):
    url: Optional[str] = None
    html_snippet: Optional[str] = None
    user_instruction: str  # e.g. "Extract article title, author, publish date, category"

class AISchemaResponse(BaseModel):
    detected_entity_type: str  # e.g. "Article", "E-commerce Product", "Job Posting"
    proposed_fields: List[AISchemaFieldProposal]
    confidence_score: float
    explanation: str
    tokens_used: int = 0
    provider_used: str = "heuristic"
