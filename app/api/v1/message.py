# app/routes/message.py

from fastapi import APIRouter, Depends
from app.services.gmail_service import fetch_all_gmail_accounts
from app.db.mongodb import get_database

router = APIRouter()

@router.post("/fetch-all")
async def fetch_all(db=Depends(get_database)):
    result = await fetch_all_gmail_accounts(db)
    return {"result": result}