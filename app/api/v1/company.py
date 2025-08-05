from fastapi import APIRouter, Depends
from datetime import datetime
from app.models.user import CompanyCreate
from bson import ObjectId
from app.db.mongodb import get_database
from app.core.security import get_current_user

router = APIRouter()

# /api/v1/compnany/create
@router.post("/create")
async def create_company(company: CompanyCreate, current_user: dict = Depends(get_current_user), db=Depends(get_database)):
    now = datetime.utcnow()
    company_doc = {
        "name": company.name,
        "site_url": company.site_url,
        "created_by": ObjectId(current_user["_id"]),
        "created_at": datetime.utcnow(),
    }
    
    result = await db.companies.insert_one(company_doc)
    company_id = result.inserted_id

    # Create membership for the current user
    membership_doc = {
        "user_id": current_user["_id"],
        "company_id": company_id,
        "role": "company_owner",
        "status": "active",
        "joined_at": now,
        "last_used_at": now,
    }

    await db.memberships.insert_one(membership_doc)

    return {
        "company_id": str(company_id),
        "membership": {
            "role": "company_owner",
            "status": "active"
        }
    }

