# app/routes/message.py

from fastapi import APIRouter, HTTPException, Depends, Body
from app.services.gmail_service import fetch_all_gmail_accounts
from app.db.mongodb import get_database
from app.models.message import Message, ChatEntry, PyObjectId 
from typing import List
import re
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.services.ai_service import analyze_emails_with_ai
import json

router = APIRouter()

@router.post("/fetch-all")
async def fetch_all(db=Depends(get_database)):
    result = await fetch_all_gmail_accounts(db)
    return {"result": result}

def extract_name(email_str: str) -> str:
    match = re.match(r"^(.*?)\s*<", email_str)
    return match.group(1).strip() if match else email_str

def doc_to_message(doc: dict) -> Message:
    # Clean client_id
    raw_client_id = doc.get("client_id", "")
    cleaned_client_id = extract_name(raw_client_id)

    return Message(
        id=PyObjectId(doc['_id']),
        client_id=cleaned_client_id,
        agent_id=doc.get("agent_id"),
        session_id=doc.get("session_id"),
        started_at=doc.get("started_at"),
        last_updated=doc.get("last_updated"),
        status=doc.get("status", "open"),
        channel=doc.get("channel"),
        title=doc.get("title"),
        ai_summary=doc.get("ai_summary"),
        tags=doc.get("tags", []),
        resolved_by_ai=doc.get("resolved_by_ai", False),
    )

def doc_to_message_detail(doc: dict) -> Message:
    return Message(
        id=doc["_id"],
        client_id=extract_name(doc.get("client_id", "")),
        agent_id=doc.get("agent_id"),
        session_id=doc.get("session_id"),
        started_at=doc.get("started_at"),
        last_updated=doc.get("last_updated"),
        status=doc.get("status", "open"),
        channel=doc.get("channel"),
        title=doc.get("title"),
        ai_summary=doc.get("ai_summary"),
        tags=doc.get("tags", []),
        resolved_by_ai=doc.get("resolved_by_ai", False),
        messages=[]  # or omit this line if optional in schema
    )

@router.get("/", response_model=List[dict])
async def get_messages(db=Depends(get_database)):
    cursor = db["messages"].find({})
    messages = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])  # Convert ObjectId to string

        raw_client_id = doc.get("client_id", "")
        cleaned_client_id = extract_name(raw_client_id)
        doc["client_id"] = cleaned_client_id

        doc.pop("messages", None)  # <- Remove the 'messages' field if it exists

        messages.append(doc)
    return messages

@router.get("/{id}", response_model=dict)
async def get_message(id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid message ID")

    doc = await db["messages"].find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")

    doc["_id"] = str(doc["_id"])  # Convert ObjectId to string
    return doc

@router.post("/analyze_as_list", response_model=list)
async def analyze_email_message_as_list(
    body: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Analyze all email ChatEntry objects in a message and extract order/refund/cancel info as JSON.
    Input: JSON body with { "message_id": str }.
    Output: List of JSON results, one per ChatEntry.
    """
    message_id = body.get("message_id")
    if not message_id or not ObjectId.is_valid(message_id):
        raise HTTPException(status_code=400, detail="Invalid message ID")

    doc = await db["messages"].find_one({"_id": ObjectId(message_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")

    result = await analyze_emails_with_ai(doc)
    order_list = []
    for entry in result:
        try:
            order_info = json.loads(entry["response"])
            if order_info.get("order_id") and order_info.get("status") == 1:
                order_info["shopify_order"] = {}
                order_list.append(order_info)
        except Exception:
            continue

    return order_list

@router.post("/analyze", response_model=dict)
async def analyze_email_message(
    body: dict = Body(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Analyze the last three email ChatEntry objects in a message and extract order/refund/cancel info as JSON.
    Input: JSON body with { "message_id": str }.
    Output: Single JSON result for the combined analysis.
    """
    message_id = body.get("message_id")
    if not message_id or not ObjectId.is_valid(message_id):
        raise HTTPException(status_code=400, detail="Invalid message ID")

    doc = await db["messages"].find_one({"_id": ObjectId(message_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")

    result = await analyze_emails_with_ai(doc)
    # result is now a single dict, not a list

    try:
        order_info = json.loads(result["response"])
        if order_info.get("order_id") and order_info.get("status") == 1:
            order_info["shopify_order"] = {}
            return order_info
    except Exception:
        pass

    return {}  # or return order_info if you want to return whatever the AI gave, even if not a valid order