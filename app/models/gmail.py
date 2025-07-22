from pydantic import BaseModel, EmailStr, Field, GetCoreSchemaHandler
from typing import Optional, Any
from bson import ObjectId
from datetime import datetime
from pydantic_core import core_schema

class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_before_validator_function(
            cls.validate, core_schema.str_schema()
        )

    @classmethod
    def validate(cls, v: Any) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError("Invalid ObjectId")

class GmailAccountBase(BaseModel):
    user_id: PyObjectId = Field(...)
    email: EmailStr
    access_token: str
    refresh_token: str
    token_type: Optional[str] = "Bearer"
    expires_at: datetime
    client_id: str
    client_secret: str
    status: Optional[str] = "connected"
    scope: Optional[str] = None
    token_issued_at: Optional[datetime] = None
    is_primary: Optional[bool] = False
    provider: Optional[str] = "google"
    model_config = {
        "arbitrary_types_allowed": True,
        "json_encoders": {ObjectId: str},
    }

class GmailAccountCreate(GmailAccountBase):
    id: str
    pass

class GmailAccountUpdate(BaseModel):
    access_token: Optional[str]
    refresh_token: Optional[str]
    token_type: Optional[str]
    expires_at: Optional[datetime]
    status: Optional[str]

class GmailAccountInDB(GmailAccountBase):
    id: str
    user_id: str
