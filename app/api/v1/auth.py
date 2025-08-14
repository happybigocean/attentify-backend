from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from app.models.user import UserCreate
from app.core.security import verify_password, get_password_hash, create_access_token
from app.db.mongodb import get_database
from app.utils.token_utils import verify_invitation_token
from bson import ObjectId

router = APIRouter()

VALID_ROLES = {"admin", "store_owner", "agent", "readonly"}

# /api/v1/auth/register
@router.post("/register")
async def register(user: UserCreate, db=Depends(get_database)):
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()

    user_doc = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "hashed_password": hashed_password,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)

    # If invitation token is provided, handle it
    if user.invitation_token:
        try:
            data = verify_invitation_token(user.invitation_token)
            company_id = data["company_id"]
            role = data["role"]

            if role not in VALID_ROLES:
                raise HTTPException(status_code=400, detail="Invalid role in invitation token")

            # Add user to memberships
            await db.memberships.insert_one({
                "user_id": result.inserted_id,
                "company_id": ObjectId(company_id),
                "role": role,
                "status": "active",
                "joined_at": now,
                "last_used_at": now
            })

            token = create_access_token(data={
                "sub": user.email,
                "user_id": user_id,
                "company_id": str(company_id),
                "role": role
            })

            company = await db.companies.find_one({"_id": ObjectId(company_id)})

            company_list = []
            if company:
                company_list.append({
                    "id": str(company["_id"]),
                    "name": company.get("name", "")
                })

            return {
                "token": token,
                "user": {
                    "id": user_id,
                    "name": f"{user.first_name} {user.last_name}".strip(),
                    "email": user.email,
                    "company_id": str(company_id),
                    "role": role,
                    "companies": company_list
                },
                "redirect_url": "/dashboard"
            }

        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    token = create_access_token(data={"sub": user.email, "user_id": user_id})

    return {
        "token": token,
        "user": {
            "id": user_id,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email,
        },
        "redirect_url": "/register-company"
    }

# /api/v1/auth/login
@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_database)):
    user = await db.users.find_one({"email": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if user.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended. Contact admin.")

    await db.users.update_one(
        {"email": user["email"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )

    user_id = str(user["_id"])  # Convert ObjectId to string

    if user.get("role") == "admin":
        user_id = user_id
        token = create_access_token(data={
            "sub": user["email"],
            "user_id": user_id,
            "role": "admin"
        })

        return {
            "token": token,
            "user": {
                "id": user_id,  
                "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                "email": user["email"],
                "role": "admin"
            }
        }
        
    memberships_cursor = db.memberships.find({
        "user_id": user["_id"],
        "status": "active"
    }).sort("last_used_at", -1)

    memberships = await memberships_cursor.to_list(length=None)

    if not memberships:
        raise HTTPException(status_code=403, detail="No active company membership found")
    
    selected_membership = memberships[0]
    company_id = selected_membership["company_id"]
    role = selected_membership.get("role", "readonly")

    await db.memberships.update_one(
        {"_id": selected_membership["_id"]},
        {"$set": {"last_used_at": datetime.utcnow()}}
    )

    # === Fetch Company Info ===
    company_ids = [m["company_id"] for m in memberships]
    companies_cursor = db.companies.find({"_id": {"$in": company_ids}})
    companies_map = {str(c["_id"]): c async for c in companies_cursor}

    company_list = []
    for m in memberships:
        cid = str(m["company_id"])
        company = companies_map.get(cid)
        if company:
            company_list.append({
                "id": cid,
                "name": company.get("name", "")
            })
    
    token = create_access_token(data={
        "sub": user["email"],
        "user_id": user_id,
        "company_id": str(company_id),
        "role": role
    })

    return {
        "token": token,
        "user": {
            "id": user_id,  
            "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "email": user["email"],
            "company_id": str(company_id),
            "role": role,
            "companies": company_list
        }
    }
