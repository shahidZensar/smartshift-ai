from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, Optional, List
from datetime import datetime
from enum import Enum

class ChatMessage(BaseModel):
    """Model for individual chat messages"""
    id: Optional[str] = Field(None, description="Unique message ID")
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)

class QueryRequest(BaseModel):
    """Model for chat query requests"""
    question: str = Field(..., description="User's question or query")
    session_id: Optional[str] = Field(None, description="Session ID for conversation tracking")
    include_context: Optional[bool] = Field(True, description="Include retrieved context in response")
    
    class Config:
        extra = "allow"  # Allow extra fields

class QueryResponse(BaseModel):
    """Model for chat query responses"""
    answer: str = Field(..., description="Generated answer from RAG model")
    session_id: Optional[str] = Field(None, description="Session ID for conversation tracking")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: Optional[List[str]] = Field(None, description="Retrieved document sources")
    follow_up_questions: Optional[List[str]] = Field(None, description="Suggested follow-up questions")

class ChatHistory(BaseModel):
    """Model for chat history"""
    session_id: str = Field(..., description="Session ID")
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# ==================== In-Memory Storage ====================
# In production, use a proper database
chat_sessions: dict = {}

class RoutingDecision(BaseModel):
    action: Literal[
        "ANALYZE_FILE",
        "SEARCH_RAG",
        "DIRECT_ANSWER",
        "CLARIFY",
        "REFUSE"
    ]

class SufficiencyDecision(BaseModel):
    action: Literal["ANSWER", "SEARCH_WEB"]
 
class DeviceLifecycleResponse(BaseModel):
    device: str
    eol_date: Optional[str]
    eos_date: Optional[str]
    replacement_model: Optional[str]
    license_notes: Optional[str]
    data_source: str

class LLMResponse(BaseModel):
    answer: str
    follow_up_questions: List[str]

class SQLResponse(BaseModel):
    query: str
    params: List[str]


# ==================== CONFIG intent ====================

class ConfigStage(str, Enum):
    """Lifecycle of a CONFIG conversation (see CONFIG_INTENT_PLAN.md §6)."""
    DETECT_TYPE = "DETECT_TYPE"
    DISAMBIGUATE = "DISAMBIGUATE"
    COLLECT_FIELDS = "COLLECT_FIELDS"
    RESOLVE_TARGET = "RESOLVE_TARGET"
    CONFIRM_APPROVAL = "CONFIRM_APPROVAL"
    DELIVER = "DELIVER"
    DONE = "DONE"


class ConfigState(BaseModel):
    """Per-session CONFIG slot/lifecycle state, persisted between turns."""
    config_type: Optional[str] = None
    collected: Dict[str, Any] = Field(default_factory=dict)   # field -> value (cumulative)
    missing_fields: List[str] = Field(default_factory=list)
    candidates: List[str] = Field(default_factory=list)        # disambiguation options offered (§8)
    stage: ConfigStage = ConfigStage.DETECT_TYPE
    target_mode: Optional[str] = None                         # "integrated" | "standalone" (future)
    target_device: Optional[Dict[str, Any]] = None
    delivery_mode: str = "manual"                             # "manual" (v1) | "automated" (future)
    approved: bool = False
    attempts: int = 0
    last_executed_signature: Optional[str] = None             # idempotency key (§15)
    last_result: Optional[Dict[str, Any]] = None              # cached delivery payload for idempotent re-send


class ConfigTypeDetection(BaseModel):
    """LLM fallback output for config-type detection (§8)."""
    config_type: Optional[str] = Field(None, description="Best-match config_type, or null if unsure")
    confidence: float = Field(0.0, description="0.0-1.0 confidence in the match")
    candidates: List[str] = Field(default_factory=list, description="Other plausible config_types")


class ConfigFieldExtraction(BaseModel):
    """LLM output for slot extraction (§6 step 3). Only includes fields actually stated."""
    collected: Dict[str, Any] = Field(default_factory=dict, description="field -> value, omit unknowns")


class ConfigConnectionExtraction(BaseModel):
    """LLM output for standalone connection details (§10.2). Omit fields not provided."""
    device_name: Optional[str] = None
    ansible_host: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
