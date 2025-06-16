from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class GmailAccountBase(BaseModel):
    email: EmailStr
    access_token: str
    refresh_token: str
    token_type: Optional[str] = "Bearer"
    expires_at: datetime
    status: Optional[str] = "connected"

class GmailAccountCreate(GmailAccountBase):
    pass

class GmailAccountUpdate(BaseModel):
    access_token: Optional[str]
    refresh_token: Optional[str]
    token_type: Optional[str]
    expires_at: Optional[datetime]
    status: Optional[str]

class GmailAccountInDB(GmailAccountBase):
    id: str
