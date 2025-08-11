from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal, List
from datetime import datetime
from bson import ObjectId
from app.utils.bson import PyObjectId

# -------------------
# User
# -------------------
class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True
        arbitrary_types_allowed = True

class UserPublic(BaseModel):
    id: PyObjectId = Field(alias="_id")
    email: str
    first_name: str
    last_name: str

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# -------------------
# Company
# -------------------
class CompanyBase(BaseModel):
    name: str
    site_url: str
    email: EmailStr

class CompanyCreate(CompanyBase):
    pass

class CompanyInDB(CompanyBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_by: PyObjectId
    created_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True
        arbitrary_types_allowed = True

class SimpleCompanyOut(BaseModel):
    id: str
    name: str

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True
        arbitrary_types_allowed = True

class UpdateCompanyRequest(BaseModel):
    company_id: str = Field(..., description="MongoDB ObjectId of the company")
    name: Optional[str] = None
    site_url: Optional[str] = None
    email: Optional[EmailStr] = None

# -------------------
# Membership
# -------------------
class MembershipBase(BaseModel):
    role: Literal["company_owner", "store_owner", "agent", "readonly"]
    status: Literal["active", "invited", "suspended"] = "active"

class MembershipCreate(MembershipBase):
    user_id: PyObjectId
    company_id: PyObjectId


class MembershipInDB(MembershipCreate):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    joined_at: datetime
    last_used_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
        allow_population_by_field_name = True
        arbitrary_types_allowed = True

class MembershipPublic(MembershipInDB):
    user: Optional[UserPublic]
    company: Optional[CompanyInDB]
