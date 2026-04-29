"""
Query schemas — Pydantic models for API request/response.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


class OutputFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    PLAIN = "plain"


class SourceCitation(BaseModel):
    """Citation for a piece of retrieved information"""
    agent_name: str
    source_type: str            # "document", "database", "confluence", "web"
    source_identifier: str      # File path, URL, table name, page title
    relevance_score: float = 0.0
    excerpt: Optional[str] = None


class QueryRequest(BaseModel):
    """Incoming query from user"""
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    output_format: OutputFormat = OutputFormat.MARKDOWN
    target_agents: Optional[List[str]] = None
    max_sources: int = Field(default=5, ge=1, le=10)


class QueryResponse(BaseModel):
    """Final response to user"""
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    answer: str
    confidence: float = 0.0
    sources: List[SourceCitation] = []
    agents_used: List[str] = []
    execution_time_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
