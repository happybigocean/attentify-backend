from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from app.models.user import UserCreate, Token
from app.core.security import verify_password, get_password_hash, create_access_token
from bson import ObjectId

router = APIRouter()

VALID_ROLES = {"admin", "store_owner", "agent", "readonly"}

# /api/v1/auth/register
@router.post("/register")
async def register(user: UserCreate, request: Request):
    db = request.app.state.db
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    role = user.role if user.role in VALID_ROLES else "readonly"
    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()

    user_doc = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": role,
        "status": "active",
        "hashed_password": hashed_password,
        "team_id": None,
        "created_at": now,
        "updated_at": now,
        "last_login": now,
    }

    result = await db.users.insert_one(user_doc)  # Capture insert result

    inserted_user_id = str(result.inserted_id)
    token = create_access_token(data={"sub": user["email"], "user_id": inserted_user_id})
    return {
        "token": token,
        "user": {
            "id": inserted_user_id,  
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "role": role,
            "status": "active"
        }
    }

# /api/v1/auth/login
@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    db = request.app.state.db
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
