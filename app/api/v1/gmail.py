from fastapi import APIRouter, Request, HTTPException, Response, Depends
from fastapi.responses import RedirectResponse
from typing import List, Optional
import httpx
from urllib.parse import urlencode
from datetime import datetime, timedelta
from app.core.security import get_current_user
from bson import ObjectId
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.cloud import pubsub_v1
from app.core.config import settings
import asyncio
import json
import base64
from app.db.mongodb import get_database
from app.services.gmail_service import get_gmail_service

from app.models.gmail import (
    GmailAccountCreate,
    GmailAccountUpdate,
    GmailAccountInDB
)

router = APIRouter()

def gmail_account_helper(account: dict) -> dict:
    return {
        "id": str(account["_id"]),
        "user_id": str(account["user_id"]),
        "email": account["email"],
        "access_token": account["access_token"],
        "refresh_token": account["refresh_token"],
        "token_type": account.get("token_type", "Bearer"),
        "expires_at": account["expires_at"],
        "client_id": account["client_id"],
        "client_secret": account["client_secret"],
        "status": account.get("status", "connected"),
        "scope": account.get("scope"),
        "token_issued_at": account.get("token_issued_at"),
        "is_primary": account.get("is_primary", False),
        "provider": account.get("provider", "google"),
        "history_id":  account.get("history_id", "")
    }

@router.post("/", response_model=GmailAccountInDB)
async def create_gmail_account(account: GmailAccountCreate, request: Request):
    db = request.app.state.db
    existing = await db.gmail_accounts.find_one({"email": account.email})
    if existing:
        raise HTTPException(status_code=400, detail="Gmail account already registered")

    # Ensure user_id is a valid ObjectId
    try:
        account_dict = account.dict()
        account_dict["user_id"] = ObjectId(account.user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    result = await db.gmail_accounts.insert_one(account_dict)
    account_dict["id"] = str(result.inserted_id)
    return gmail_account_helper(account_dict)

@router.get("/", response_model=List)
async def list_gmail_accounts(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    db = request.app.state.db
    
    accounts_cursor = db.gmail_accounts.find({"user_id": current_user["_id"]})
    accounts = []
    async for account in accounts_cursor:
        accounts.append(gmail_account_helper(account))

    return accounts

@router.get("/{account_id}", response_model=GmailAccountInDB)
async def get_gmail_account(account_id: str, request: Request):
    db = request.app.state.db
    account = await db.gmail_accounts.find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=404, detail="Gmail account not found")
    return gmail_account_helper(account)

@router.put("/{account_id}", response_model=GmailAccountInDB)
async def update_gmail_account(account_id: str, update: GmailAccountUpdate, request: Request):
    db = request.app.state.db
    update_data = {k: v for k, v in update.dict().items() if v is not None}

    if "user_id" in update_data:
        try:
            update_data["user_id"] = ObjectId(update_data["user_id"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid user_id format")

    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided for update")

    result = await db.gmail_accounts.update_one({"_id": ObjectId(account_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Gmail account not found")

    account = await db.gmail_accounts.find_one({"_id": ObjectId(account_id)})
    return gmail_account_helper(account)

@router.delete("/{account_id}", status_code=204)
async def delete_gmail_account(account_id: str, request: Request):
    db = request.app.state.db
    result = await db.gmail_accounts.delete_one({"_id": ObjectId(account_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Gmail account not found")
    return None

# Environment variables for Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email"

#/api/v1/gmail/oauth/login
@router.get("/oauth/login")
async def google_oauth_login(user_id: str):
    """
    Starts the OAuth flow by redirecting to Google with the user's ID in state
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id format")

    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=email%20profile%20https://www.googleapis.com/auth/gmail.readonly%20https://www.googleapis.com/auth/gmail.send%20https://www.googleapis.com/auth/userinfo.email"
        f"&state={user_id}"  # ✅ Attach user_id here
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url=auth_url)

#/api/v1/gmail/oauth/callback
@router.get("/oauth/callback")
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None,
):
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if not state or not ObjectId.is_valid(state):
        raise HTTPException(status_code=400, detail="Missing or invalid user_id (state)")

    user_id = ObjectId(state)

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            token_data = token_resp.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid token response from Google")

        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", "Failed to get tokens"))

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access token")

    expires_at = datetime.utcnow() + timedelta(seconds=expires_in or 3600)

    # Get user info
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo = userinfo_resp.json()
        email = userinfo.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Failed to retrieve user email")

    # Build credentials
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"]
    )

    # Call Gmail API in threadpool (avoid blocking)
    def watch_gmail():
        gmail = build("gmail", "v1", credentials=creds)
        watch_request = {
            "labelIds": ["INBOX"],
            "topicName": f"projects/{settings.PUBSUB_PROJECT}/topics/{settings.PUBSUB_TOPIC}",
        }
        return gmail.users().watch(userId="me", body=watch_request).execute()

    loop = asyncio.get_running_loop()
    watch_response = await loop.run_in_executor(None, watch_gmail)

    history_id = watch_response["historyId"]

    # ✅ Ensure Pub/Sub subscription exists
    def ensure_subscription():
        subscriber = pubsub_v1.SubscriberClient()
        topic_path = subscriber.topic_path(settings.PUBSUB_PROJECT, settings.PUBSUB_TOPIC)
        subscription_path = subscriber.subscription_path(settings.PUBSUB_PROJECT, settings.PUBSUB_SUBSCRIPTION)

        try:
            subscriber.get_subscription(request={"subscription": subscription_path})
        except Exception:
            subscriber.create_subscription(
                request={"name": subscription_path, "topic": topic_path}
            )
        return subscription_path

    subscription_path = await loop.run_in_executor(None, ensure_subscription)

    # Save/update Gmail account
    db = request.app.state.db
    existing = await db.gmail_accounts.find_one({"email": email, "user_id": user_id})

    account_data = {
        "email": email,
        "user_id": user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "status": "connected",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "token_issued_at": datetime.utcnow(),
        "provider": "google",
        "history_id": history_id,
        "subscription": subscription_path,  # ✅ store subscription
    }

    if existing:
        await db.gmail_accounts.update_one({"_id": existing["_id"]}, {"$set": account_data})
    else:
        await db.gmail_accounts.insert_one(account_data)

    return RedirectResponse(url=f"{FRONTEND_URL}/accounts/gmail")

# gmail realtime updates workflow
@router.post("/pubsub/push") 
async def pubsub_push(request: Request, db = Depends(get_database)):
    body = await request.json()
    message = body.get("message")

    if not message or "data" not in message:
        return Response(status_code=400)
    
    # Decode Pub/Sub base64 payload
    data = json.loads(base64.b64decode(message["data"]).decode("utf-8"))
    email_address = data.get("emailAddress")
    history_id = data.get("historyId")

    print(f"Gmail change detected: {email_address}, historyId: {history_id}")

    account = db["gmail_accounts"].find_one({"email": email_address})

    if not account:
        print(f"No account store for {email_address}")
        return Response(status_code=200)

    # Connect Gmail API
    gmail = get_gmail_service(account)

    # Fetch history since last known historyId
    last_history_id = account.get("history_id")
    if last_history_id:
        results = gmail.users().history().list(
            userId = "me",
            startHistoryId = last_history_id
        ).execute()

        history = results.get("history", [])
        for record  in history:
            if "messagesAdded" in record:
                for added in record["messaged=Added"]:
                    msg_id = added["message"]["id"]
                    msg = gmail.users().messages().get(
                        userId = "me",
                        id = msg_id,
                        format = "metadata" 
                    ).execute()
                    print(f"New message for {email_address}: {msg.get('snippet')}")

    # Update stored historyId
    account["history_id"] = history_id

    return Response(status_code=200)


