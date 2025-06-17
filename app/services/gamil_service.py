import base64
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.models.message import Message, ChatEntry  # Ensure your model imports are correct
from bson import ObjectId


async def fetch_and_save_gmail(account: dict, db):
    """
    Fetch unread emails from a Gmail account and save them to the messages collection.
    
    account: A dict containing Gmail credentials and metadata (from GmailAccountInDB)
    db: MongoDB database instance
    """
    # Prepare credentials
    creds = Credentials(
        token=account["access_token"],
        refresh_token=account["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    )

    # Refresh token if needed
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    # Build Gmail API service
    service = build("gmail", "v1", credentials=creds)

    # Fetch unread emails
    result = service.users().messages().list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=10).execute()
    messages = result.get("messages", [])

    for msg in messages:
        full_msg = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
        payload = full_msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "")
        date = next((h["value"] for h in headers if h["name"] == "Date"), "")

        # Convert date to datetime object
        try:
            timestamp = datetime.strptime(date[:25], "%a, %d %b %Y %H:%M:%S")
        except Exception:
            timestamp = datetime.utcnow()

        # Get email body
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        # Build chat entry
        chat_entry = ChatEntry(
            sender="client",
            content=body,
            channel="email",
            timestamp=timestamp
        )

        # Find existing message thread
        existing = await db["messages"].find_one({"client_id": sender})

        if existing:
            await db["messages"].update_one(
                {"_id": existing["_id"]},
                {
                    "$push": {"messages": chat_entry.dict()},
                    "$set": {"last_updated": datetime.utcnow()},
                }
            )
        else:
            message_doc = Message(
                client_id=sender,
                agent_id=None,
                channel="email",
                status="open",
                messages=[chat_entry],
                last_updated=datetime.utcnow()
            )
            await db["messages"].insert_one(message_doc.dict(by_alias=True))

    return f"Fetched and stored {len(messages)} messages for {account['email']}"
