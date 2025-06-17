# app/models/message.py

from pydantic import BaseModel, Field
from typing import List, Literal, Optional
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
    sender: Literal["client", "agent", "system", "ai"]
    content: str
    title: Optional[str] = None  # <-- Added title here
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    channel: Optional[Literal["chat", "sms", "email", "voice"]]
    message_type: Optional[Literal["text", "file", "voice", "system"]] = "text"
    metadata: Optional[dict] = {}

class Message(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

    client_id: str                     # e.g. email or phone
    agent_id: Optional[str]           # null if AI or not assigned
    session_id: Optional[str] = None  # optional session tag
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    status: Literal["open", "closed", "pending"] = "open"
    channel: Literal["chat", "sms", "email", "voice"]

    title: Optional[str] 
    
    messages: List[ChatEntry] = []    # all history between client and agent

    ai_summary: Optional[str] = None
    tags: Optional[List[str]] = []
    resolved_by_ai: bool = False

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}