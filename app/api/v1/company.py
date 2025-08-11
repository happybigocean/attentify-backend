from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from app.models.user import CompanyCreate, SimpleCompanyOut, CompanyInDB
from bson import ObjectId
from app.db.mongodb import get_database
from app.core.security import get_current_user
from typing import List

router = APIRouter()

def transform_company(company):
    return {
        "id": str(company["_id"]),
        **{k: v for k, v in company.items() if k != "_id"}
    }

#GET /api/v1/company/
@router.get("/", response_model=List[SimpleCompanyOut])
async def list_companies(current_user: dict = Depends(get_current_user), db = Depends(get_database)):
    user_id = current_user["_id"]

    memberships_cursor = db["memberships"].find({
        "user_id": user_id,
        "status": "active"
    })

    company_ids = [m["company_id"] for m in await memberships_cursor.to_list(length=100)]

    if not company_ids:
        return []

    companies_cursor = db["companies"].find({
        "_id": {"$in": company_ids}
    })

    companies = await companies_cursor.to_list(length=100)

    # Convert _id to id
    return [transform_company(company) for company in companies]


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

# /api/v1/company/{company_id}
@router.get("/{company_id}", response_model=CompanyInDB)
async def get_company(
    company_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    if not ObjectId.is_valid(company_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid company ID")

    company = await db["companies"].find_one({"_id": ObjectId(company_id)})

    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    # Optional: check if current_user has access rights to this company
    # if company["created_by"] != current_user["_id"]:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Convert ObjectId fields to str
    company["id"] = str(company["_id"])
    company["created_by"] = str(company["created_by"])

    return CompanyInDB.parse_obj(company)
    


