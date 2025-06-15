from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from app.models.user import User, UserCreate, UserInDB, Token
from app.core.security import verify_password, get_password_hash, create_access_token

router = APIRouter()

#/api/v1/auth/register
@router.post("/register", response_model=Token)
async def register(user: UserCreate, request: Request):
    db = request.app.state.db
    existing = await db.users.find_one({"email": user.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    await db.users.insert_one({
        "email": user.email,
        "hashed_password": hashed_password,
        "created_at": datetime.utcnow(),
    })
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

#/api/v1/auth/login
@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), request: Request = None):
    db = request.app.state.db
    user = await db.users.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    print("found success")
    access_token = create_access_token(data={"sub": user["email"]})
    print(access_token)
    return {"access_token": access_token, "token_type": "bearer"}