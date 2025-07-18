from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from typing import List, Optional
import httpx
from urllib.parse import urlencode
from datetime import datetime, timedelta

from bson import ObjectId
import os

from app.models.gmail import (
    GmailAccountCreate,
    GmailAccountUpdate,
    GmailAccountInDB
)
from app.utils.email_utils import gmail_account_helper

router = APIRouter()

@router.post("/", response_model=GmailAccountInDB)
async def create_gmail_account(account: GmailAccountCreate, request: Request):
    db = request.app.state.db
    existing = await db.gmail_accounts.find_one({"email": account.email})
    if existing:
        raise HTTPException(status_code=400, detail="Gmail account already registered")
    account_dict = account.dict()
    result = await db.gmail_accounts.insert_one(account_dict)
    account_dict["id"] = str(result.inserted_id)
    return account_dict

@router.get("/", response_model=List[GmailAccountInDB])
async def list_gmail_accounts(request: Request):
    db = request.app.state.db
    accounts_cursor = db.gmail_accounts.find()
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
async def google_oauth_login():
    """
    Redirect user to Google OAuth consent page
    """
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # To ensure refresh token returned
    }
    url = GOOGLE_AUTH_URL + "?" + urlencode(params)
    return RedirectResponse(url)

#/api/v1/gmail/oauth/callback
@router.get("/oauth/callback")
async def google_oauth_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    """
    Handle OAuth callback from Google, exchange code for tokens and store account
    """
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Exchange authorization code for tokens
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
        token_data = token_resp.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data.get("error_description", "Failed to get tokens"))

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")  # seconds

    if not access_token or not refresh_token:
        raise HTTPException(status_code=400, detail="Missing access or refresh token")

    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Use access token to get user's email info
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo = userinfo_resp.json()
        email = userinfo.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Failed to retrieve user email from Google")

    # Save or update Gmail account in DB, now including client_id and client_secret
    db = request.app.state.db
    existing = await db.gmail_accounts.find_one({"email": email})
    account_data = {
        "email": email,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "status": "connected",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
    }
    if existing:
        await db.gmail_accounts.update_one({"_id": existing["_id"]}, {"$set": account_data})
    else:
        await db.gmail_accounts.insert_one(account_data)

    redirect_url = f"{FRONTEND_URL}/accounts/gmail"
    return RedirectResponse(url=redirect_url)