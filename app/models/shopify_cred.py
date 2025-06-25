from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class ShopifyCredBase(BaseModel):
    shop_url: str
    access_token: str
    status: Optional[str] = "connected"
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()
