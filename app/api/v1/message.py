# app/routes/message.py

from fastapi import APIRouter, Depends
from app.services.gmail_service import fetch_all_gmail_accounts
from app.db.mongodb import get_database
from app.models.message import Message, ChatEntry 
from typing import List

router = APIRouter()

@router.post("/fetch-all")
async def fetch_all(db=Depends(get_database)):
    result = await fetch_all_gmail_accounts(db)
    return {"result": result}

# Helper to convert MongoDB document to dict with string _id
def doc_to_message(doc: dict) -> Message:
    # Parse messages list, converting each dict into ChatEntry instance
    messages = []
    for m in doc.get("messages", []):
        messages.append(ChatEntry(**m))

    return Message(
        id=doc["_id"],
        client_id=doc.get("client_id"),
        agent_id=doc.get("agent_id"),
        session_id=doc.get("session_id"),
        started_at=doc.get("started_at"),
        last_updated=doc.get("last_updated"),
        status=doc.get("status", "open"),
        channel=doc.get("channel"),
        title=doc.get("title"),
        messages=messages,
        ai_summary=doc.get("ai_summary"),
        tags=doc.get("tags", []),
        resolved_by_ai=doc.get("resolved_by_ai", False),
    )

@router.get("/", response_model=List[Message])
async def get_messages(db=Depends(get_database)):
    cursor = db["messages"].find({})
    messages = []
    async for doc in cursor:
        messages.append(doc_to_message(doc))
    return messages