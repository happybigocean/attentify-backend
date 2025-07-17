from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime

# Shared base user fields
class UserBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    role: Literal["admin", "store_owner", "agent", "readonly"] = "readonly"
    status: Literal["active", "invited", "suspended"] = "invited"
    team_id: Optional[str] = None  # For grouping users by store
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

# For user creation (includes password)
class UserCreate(UserBase):
    password: str

# Internal DB model (stores hashed password)
class UserInDB(UserBase):
    hashed_password: str

# Public-facing model (without sensitive data)
class User(UserBase):
    pass

# Token model for auth
class Token(BaseModel):
    access_token: str
    token_type: str
