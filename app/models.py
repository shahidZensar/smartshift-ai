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
    form_values: Optional[dict] = Field(None, description="Structured CONFIG form submission: field -> value")

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
    # LLM pre-flight cache (keyed by a signature of collected) to avoid re-calling.
    preflight_sig: Optional[str] = None
    preflight_ok: bool = True
    preflight_issues: List[str] = Field(default_factory=list)
    preflight_warnings: List[str] = Field(default_factory=list)
    # Dynamic form: LLM-built copy is generated once and cached here (title/description
    # + per-field heading/description/example). `initial_extracted` gates the one-time
    # combined extract+build LLM call.
    initial_extracted: bool = False
    form_cache: Optional[Dict[str, Any]] = None
    target_mode: Optional[str] = None                         # "integrated" | "standalone" (future)
    target_device: Optional[Dict[str, Any]] = None
    target_filling: bool = False                              # collecting connection fields missing from inventory
    delivery_mode: str = "manual"                             # "manual" (v1) | "automated" (future)
    approved: bool = False
    attempts: int = 0
    last_executed_signature: Optional[str] = None             # idempotency key (§15)
    last_result: Optional[Dict[str, Any]] = None              # cached delivery payload for idempotent re-send


class ConfigTypeDetection(BaseModel):
    """LLM output for the CONFIG semantic gate + type detection.

    `route` is the semantic intent gate verdict (consumed in config_service): it decides
    whether a real configuration ACTION exists BEFORE any config-type mapping. It is
    returned by the SAME existing detect_type call (no extra LLM round-trip). The other
    fields are only meaningful when route == 'CONFIG_ACTION'."""
    route: str = Field("CONFIG_ACTION", description="CONFIG_ACTION | DEVICE_REFERENCE | UNKNOWN | NOT_CONFIG")
    config_type: Optional[str] = Field(None, description="Best-match config_type (only for CONFIG_ACTION), else null")
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


class ConfigFormFieldCopy(BaseModel):
    """LLM-authored presentation copy for one form field (grounded to a registry name)."""
    name: str
    heading: str = ""
    description: str = ""
    example: Optional[str] = None


class ConfigFormBuild(BaseModel):
    """Combined LLM output: form copy + any values extracted from the opening message."""
    title: str = ""
    description: str = ""
    fields: List[ConfigFormFieldCopy] = Field(default_factory=list)
    extracted: Dict[str, Any] = Field(default_factory=dict)


class ConfigPreflight(BaseModel):
    """LLM pre-flight validation of collected values against the target playbook.

    `ok` is False only when there is a BLOCKING problem (a mandatory property the
    playbook needs is missing or implausible). `warnings` are non-blocking cautions
    surfaced at the approval gate."""
    ok: bool = True
    issues: List[str] = Field(default_factory=list, description="Blocking problems, user-facing")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking cautions")
