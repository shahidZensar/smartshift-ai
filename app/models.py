from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import datetime

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
