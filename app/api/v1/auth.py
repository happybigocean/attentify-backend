from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from app.models.user import UserCreate
from app.core.security import verify_password, get_password_hash, create_access_token
from bson import ObjectId
from app.db.mongodb import get_database

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
    user_id  = str(result.inserted_id)

    token = create_access_token(data={"sub": user.email, "user_id": user_id })
    
    return {
        "token": token,
        "user": {
            "id": user_id ,
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
        }
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
    token = create_access_token(data={"sub": user["email"], "user_id": user_id})

    return {
        "token": token,
        "user": {
            "id": user_id,  
            "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "email": user["email"],
            "role": user.get("role", "readonly"),
            "status": user.get("status", "active")
        }
    }
