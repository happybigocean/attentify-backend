from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from app.models.user import User, UserCreate, UserInDB, Token
from app.core.security import verify_password, get_password_hash, create_access_token

router = APIRouter()

#/api/v1/auth/register
@router.post("/register")
async def register(user: UserCreate, request: Request):
    db = request.app.state.db
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)

    user_doc = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role or "user",
        "hashed_password": hashed_password,
        "created_at": datetime.utcnow(),
    }

    await db.users.insert_one(user_doc)

    token = create_access_token(data={"sub": user.email})

    return {
        "token": token,
        "user": {
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "role": user.role or "user"
        }
    }

#/api/v1/auth/login
@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    db = request.app.state.db
    user = await db.users.find_one({"email": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    token = create_access_token(data={"sub": user["email"]})
    
    return {
        "token": token,
        "user": {
            "name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "email": user["email"],
            "role": user.get("role", "user")
        }
    }
