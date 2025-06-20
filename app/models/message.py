from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

class ChatEntry(BaseModel):
    sender: str  # Now stores the actual sender (email, phone number, etc.)
    recipient: Optional[str] = None  # For email/SMS
    content: str
    title: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    channel: Optional[Literal["chat", "sms", "email", "voice"]] = None
    message_type: Optional[Literal["text", "html", "file", "voice", "system"]] = "text"
    metadata: Optional[Dict[str, Any]] = {}

class Message(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

    # Conversation/thread grouping key, e.g., Gmail threadId, SMS conversation ID, chat session ID
    thread_id: Optional[str] = None

    # Participants
    participants: List[str] = []  # All unique senders/recipients in the thread

    # For compatibility with old logic, keep these if needed:
    client_id: Optional[str] = None  # e.g. email or phone for chat initiator
    agent_id: Optional[str] = None
    session_id: Optional[str] = None

    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["open", "closed", "pending"] = "open"
    channel: Literal["chat", "sms", "email", "voice"]
    title: Optional[str] = None

    messages: List[ChatEntry] = []
    ai_summary: Optional[str] = None
    tags: Optional[List[str]] = []
    resolved_by_ai: bool = False

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}