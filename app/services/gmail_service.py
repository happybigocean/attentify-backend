import base64
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.models.message import Message, MessageCreate, ChatEntry  # Ensure your model imports are correct
from bson import ObjectId
import logging
import requests

async def fetch_and_save_gmail(account: dict, db):
    creds = Credentials(
        token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logging.error(f"Failed to refresh token for {account['email']}: {e}")
            return f"Token refresh failed for {account['email']}"

    # Optional: Verify actual granted scopes
    try:
        token_info = requests.get(
            f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={creds.token}"
        ).json()
        if "https://www.googleapis.com/auth/gmail.readonly" not in token_info.get("scope", ""):
            return f"Insufficient permissions: 'gmail.readonly' not in token scopes for {account['email']}"
    except Exception as e:
        logging.warning(f"Token scope check failed: {e}")

    try:
        service = build("gmail", "v1", credentials=creds)

        result = service.users().messages().list(
            userId="me",
            maxResults=10
        ).execute()

        messages = result.get("messages", [])
        stored_count = 0

        for msg in messages:
            gmail_id = msg["id"]

            # Skip if already stored
            existing = await db["messages"].find_one({
                "messages.metadata.gmail_id": gmail_id
            })
            if existing:
                continue

            full_msg = service.users().messages().get(
                userId="me", id=gmail_id, format="full"
            ).execute()

            payload = full_msg.get("payload", {})
            headers = payload.get("headers", [])

            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "")
            date = next((h["value"] for h in headers if h["name"] == "Date"), "")

            try:
                timestamp = datetime.strptime(date[:25], "%a, %d %b %Y %H:%M:%S")
            except Exception:
                timestamp = datetime.utcnow()

            # Extract plain text body
            body = ""
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        data = part["body"].get("data", "")
                        if data:
                            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                            break
            else:
                data = payload.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

            chat_entry = ChatEntry(
                sender="client",
                content=body,
                title=subject,
                channel="email",
                timestamp=timestamp,
                metadata={"gmail_id": gmail_id}
            )

            # Store or update message thread
            existing_thread = await db["messages"].find_one({"client_id": sender})
            if existing_thread:
                await db["messages"].update_one(
                    {"_id": existing_thread["_id"]},
                    {
                        "$push": {"messages": chat_entry.dict()},
                        "$set": {
                            "last_updated": datetime.utcnow(),
                            "title": subject
                        },
                    }
                )
            else:
                message_doc = MessageCreate(
                    client_id=sender,
                    agent_id=None,
                    channel="email",
                    status="open",
                    title=subject,
                    messages=[chat_entry],
                    last_updated=datetime.utcnow()
                )
                await db["messages"].insert_one(message_doc.dict(by_alias=True))

            stored_count += 1

        return f"Fetched and stored {stored_count} new messages for {account['email']}"

    except Exception as e:
        logging.exception(f"Error fetching emails for {account['email']}: {str(e)}")
        return f"Failed to fetch emails for {account['email']} due to an error."
    
async def fetch_all_gmail_accounts(db):
    cursor = db["gmail_accounts"].find({})
    results = []
    async for cred in cursor:
        try:
            token_data = {
                "email": cred["email"],  # <-- include email here
                "access_token": cred["access_token"],
                "refresh_token": cred["refresh_token"],
                "client_id": cred["client_id"],
                "client_secret": cred["client_secret"]
            }

            result = await fetch_and_save_gmail(token_data, db)  # now only 2 args
            results.append({cred["email"]: result})
        except Exception as e:
            results.append({cred["email"]: f"Error: {str(e)}"})

    return results