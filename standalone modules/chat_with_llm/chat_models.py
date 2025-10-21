"""
Chat Service Data Models
========================

Pydantic models for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ModelInfo(BaseModel):
    """Information about an available model"""
    name: str
    size: int
    modified_at: str
    digest: Optional[str] = None


class ChatMessage(BaseModel):
    """Single chat message"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str


class InitChatRequest(BaseModel):
    """Request to initialize a chat session"""
    model: str = Field(..., description="Model name to use")
    conversation_id: Optional[str] = Field(None, description="Resume existing conversation")


class InitChatResponse(BaseModel):
    """Response for chat initialization"""
    conversation_id: str
    model: str
    status: str
    message: str


class SendMessageRequest(BaseModel):
    """Request to send a message"""
    conversation_id: str
    message: str
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class SendMessageResponse(BaseModel):
    """Response with AI message"""
    conversation_id: str
    message: ChatMessage
    model: str


class ConversationInfo(BaseModel):
    """Conversation metadata"""
    conversation_id: str
    model: str
    created_at: str
    updated_at: str
    message_count: int


class ConversationHistory(BaseModel):
    """Full conversation history"""
    conversation_id: str
    model: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


class HealthResponse(BaseModel):
    """Service health check response"""
    status: str
    ollama_connected: bool
    version: str
    active_conversations: int


class WebSocketMessage(BaseModel):
    """WebSocket message format"""
    action: str  # 'init', 'message', 'exit'
    model: Optional[str] = None
    conversation_id: Optional[str] = None
    message: Optional[str] = None
    temperature: Optional[float] = 0.7