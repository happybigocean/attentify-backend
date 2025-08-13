# models/invitation.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Literal
from bson import ObjectId
from app.utils.bson import PyObjectId

class InvitationBase(BaseModel):
    email: EmailStr
    company_id: PyObjectId
    role: Literal["company_owner", "store_owner", "agent", "readonly"]

class InvitationInDB(InvitationBase):
    id: PyObjectId
    token: str
    invited_at: datetime
    status: Literal["pending", "accepted", "expired"] = "pending"

    class Config:
        json_encoders = {ObjectId: str}
