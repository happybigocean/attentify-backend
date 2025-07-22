# app/routes/message.py

from fastapi import APIRouter, HTTPException, Depends, Body
from app.services.gmail_service import fetch_all_gmail_accounts, get_gmail_service
from app.db.mongodb import get_database
from app.models.message import Message, ChatEntry, PyObjectId 
from typing import List
import re
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.services.ai_service import analyze_emails_with_ai
import json
from bson import ObjectId
import base64
from email.utils import formatdate, format_datetime
from email.mime.text import MIMEText
from datetime import datetime, timezone
from email.utils import parseaddr
from pymongo import DESCENDING
from app.core.security import get_current_user

router = APIRouter()

@router.post("/fetch-all")
async def fetch_all(db=Depends(get_database), current_user: dict = Depends(get_current_user)):
    result = await fetch_all_gmail_accounts(db, user_id=str(current_user["_id"]))
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
async def get_messages(db=Depends(get_database), current_user: dict = Depends(get_current_user)):
    # Sort by 'last_updated' in descending order
    cursor = db["messages"].find({"user_id": current_user["_id"]}).sort("last_updated", DESCENDING)

    messages = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"]) 
        doc["user_id"] = str(doc["user_id"])
        raw_client_id = doc.get("client_id", "")
        cleaned_client_id = extract_name(raw_client_id)
        doc["client_id"] = cleaned_client_id
        doc.pop("messages", None)  # Remove the 'messages' field if it exists
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
    
    order_info = json.loads(result["response"])
    order_id = str(order_info.get("order_id", ""))
    order_name = order_id if order_id.startswith("#") else "#" + order_id

    db_order = await db["orders"].find_one({"name": order_name})
    if db_order:
        db_order["_id"] = str(db_order["_id"])
        order_info["shopify_order"] = db_order
    else:
        order_info["msg"] = "Order not found"
    return order_info

@router.post("/{id}/reply", response_model=dict)
async def reply_to_message(
    id: str,
    body: dict = Body(...),  # expects: { "content": "the reply text" }
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Reply to a message by adding a new ChatEntry and sending email via Gmail API.
    Input: Message ID (path) and reply content (body).
    Output: Updated message document.
    """
    
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid message ID")
    
    message = await db["messages"].find_one({"_id": ObjectId(id)})
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Find latest client message for threading
    client_message = None
    for msg in reversed(message.get("messages", [])):
        if msg.get("sender") == message.get("client_id"):
            client_message = msg
            break
    if not client_message:
        raise HTTPException(status_code=400, detail="No client message to reply to.")
    
    # Identify Gmail user (agent sending reply)
    agent_id = None
    agent_id = message.get("agent_id")  # agent_id should be the email of the agent

    if not agent_id:
        raise HTTPException(status_code=400, detail="No Gmail user found in participants.")

    _, agent_email = parseaddr(agent_id)
    user_creds = await db["gmail_accounts"].find_one({"email": agent_email})
    if not user_creds:
        raise HTTPException(status_code=400, detail="User Gmail credentials not found.")

    thread_id = message.get("thread_id")
    subject = client_message.get("title", "No Subject")
    original_msg_id = client_message.get("metadata", {}).get("gmail_id")
    to_addr = message.get("client_id")  # recipient (client)

    if original_msg_id and not original_msg_id.startswith("<"):
        original_msg_id = f"<{original_msg_id}>"

    mime_msg = MIMEText(body["content"])
    mime_msg['To'] = to_addr
    mime_msg['From'] = agent_email
    mime_msg['Subject'] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if original_msg_id:
        mime_msg['In-Reply-To'] = original_msg_id
        mime_msg['References'] = original_msg_id
    mime_msg['Date'] = formatdate(localtime=True)

    raw_message = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode()
    
    # Send via Gmail API
    service = get_gmail_service(user_creds)
    sent = service.users().messages().send(
        userId="me",
        body={
            'raw': raw_message,
            'threadId': thread_id
        }
    ).execute()

    # Construct ChatEntry and save to DB
    now = datetime.now(timezone.utc).astimezone()
    reply_entry = {
        "sender": agent_email,
        "recipient": to_addr,
        "content": body["content"],
        "title": subject if subject.lower().startswith("re:") else f"Re: {subject}",
        "timestamp": datetime.utcnow(),
        "message_type": "html",
        "channel": "email",
        "metadata": {
            "gmail_id": sent.get("id"),
            "from": agent_email,
            "to": to_addr,
            "date": format_datetime(now)
        }
    }

    await db["messages"].update_one(
        {"_id": ObjectId(id)},
        {
            "$push": {"messages": reply_entry},
            "$set": {"last_updated": reply_entry["timestamp"]}
        }
    )

    updated_message = await db["messages"].find_one({"_id": ObjectId(id)})

    if '_id' in updated_message:
        updated_message['_id'] = str(updated_message['_id'])
    return updated_message