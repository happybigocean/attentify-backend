from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.models.user import User, UserCreate
from app.db.mongodb import get_database
from sqlalchemy.orm import Session
import uuid

router = APIRouter()

@router.get("/", response_model=List[User])
async def list_users(db: Session = Depends(get_database)):
    cursor = db.users.find()

    users = []
    async for user in cursor:
        user["_id"] = str(user["_id"])  # Convert ObjectId to string

        users.append(user)
    return users

@router.post("/", response_model=User)
def create_user(user: UserCreate, db: Session = Depends(get_database)):
    db_user = User(**user.dict(), id=str(uuid.uuid4()))
    db.users.insert_one(db_user)
    return db_user

    

@router.put("/{user_id}", response_model=User)
def update_user(user_id: str, user: User, db: Session = Depends(get_database)):
    db_user = db.users.find_one({"id": user_id})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    for key, value in user.dict(exclude_unset=True).items():
        setattr(db_user, key, value)
    db.users.replace_one({"id": user_id}, db_user)
    return db_user

@router.delete("/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_database)):
    db_user = db.users.find_one({"id": user_id})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db.users.delete_one({"id": user_id})
    return {"message": "User deleted"}
