from fastapi import APIRouter, Depends, HTTPException
from typing import List
from pymongo.collection import Collection
from app.models.user import User, UserBase, UserCreate
from app.db.mongodb import get_database
from datetime import datetime
import uuid
from bson import ObjectId

router = APIRouter()

@router.get("/")
async def list_users(db: Collection = Depends(get_database)):
    cursor = db.users.find()
    users = []
    async for user in cursor:
        user["_id"] = str(user["_id"])  # ObjectId to str
        user["id"] = user["_id"]
        users.append(user)
    return users

@router.post("/")
async def create_user(user: UserBase, db: Collection = Depends(get_database)):
    # Check if the email already exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    now = datetime.utcnow()
    db_user = {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "status": user.status,
        "team_id": user.team_id,
        "created_at": now,
        "updated_at": now,
        "last_login": None
    }
    result = await db.users.insert_one(db_user)
    # Fetch the newly created user document (ensure _id is included)
    created_user = await db.users.find_one({"_id": result.inserted_id})
    # Convert ObjectId to string for both _id and id fields
    created_user["_id"] = str(created_user["_id"])
    created_user["id"] = created_user["_id"]
    # Optionally, serialize datetime fields to ISO strings
    if created_user.get("created_at"):
        created_user["created_at"] = created_user["created_at"].isoformat()
    if created_user.get("updated_at"):
        created_user["updated_at"] = created_user["updated_at"].isoformat()
    return created_user


@router.put("/{user_id}")
async def update_user(user_id: str, user: UserBase, db: Collection = Depends(get_database)):
    from bson import ObjectId
    from fastapi import HTTPException
    from datetime import datetime

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    db_user = await db.users.find_one({"_id": oid})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    update_data = {k: v for k, v in user.dict(exclude_unset=True).items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    await db.users.update_one({"_id": oid}, {"$set": update_data})
    updated_user = await db.users.find_one({"_id": oid})
    # Convert ObjectId to str
    updated_user["_id"] = str(updated_user["_id"])
    # Add "id" as alias for compatibility
    updated_user["id"] = updated_user["_id"]
    return updated_user

@router.delete("/{user_id}")
async def delete_user(user_id: str, db: Collection = Depends(get_database)):
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id format")
    db_user = await db.users.find_one({"_id": oid})
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.delete_one({"_id": oid})
    return {"message": "User deleted"}