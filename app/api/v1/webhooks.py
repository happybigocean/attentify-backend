from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
from bson import ObjectId

router = APIRouter()

from motor.motor_asyncio import AsyncIOMotorClient
import os
from app.models.message import Message, ChatEntry
from app.db.mongodb import get_database

db = get_database()
messages_col = db["messages"]

router.post("/twilio/sms", response_class=PlainTextResponse)
async def twilio_sms_webhook(
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(...),
    SmsSid: str = Form(...),
    SmsMessageSid: str = Form(None),
):
    thread_id = From  # Or customize: e.g. f"{From}:{To}"

    # Try to find the existing thread
    doc = await messages_col.find_one({"thread_id": thread_id, "channel": "sms"})
    now = datetime.utcnow()

    chat_entry = ChatEntry(
        sender=From,
        recipient=To,
        content=Body,
        title=None,
        timestamp=now,
        channel="sms",
        message_type="text",
        metadata={
            "MessageSid": MessageSid,
            "SmsSid": SmsSid,
            "SmsMessageSid": SmsMessageSid
        }
    )

    if doc:
        # Update thread: add new entry, update last_updated
        await messages_col.update_one(
            {"_id": doc["_id"]},
            {
                "$push": {"messages": chat_entry.dict()},
                "$set": {"last_updated": now}
            }
        )
    else:
        # New thread
        msg_obj = Message(
            thread_id=thread_id,
            participants=[From, To],
            client_id=From,
            channel="sms",
            status="open",
            started_at=now,
            last_updated=now,
            messages=[chat_entry],
        )
        await messages_col.insert_one(msg_obj.dict(by_alias=True))

    # Respond with TwiML
    return "<Response/>"