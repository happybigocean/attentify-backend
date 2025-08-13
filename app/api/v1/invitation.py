# routers/invitations.py
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from bson import ObjectId
from app.db.mongodb import get_database
from app.models.invitation import InvitationBase
from app.utils.token_utils import create_invitation_token, verify_invitation_token
from app.utils.email_utils import send_invitation_email

router = APIRouter()

#POST /api/v1/invitations/send
@router.post("/send")
async def send_invitation(invite: InvitationBase, db=Depends(get_database)):
    if not ObjectId.is_valid(str(invite.company_id)):
        raise HTTPException(status_code=400, detail="Invalid company ID")
    
    token = create_invitation_token(invite.email, str(invite.company_id))
    invite_link = f"http://localhost:5173/accept-invite?token={token}"

    await db["invitations"].insert_one({
        "email": invite.email,
        "company_id": ObjectId(invite.company_id),
        "role": invite.role,
        "token": token,
        "invited_at": datetime.utcnow(),
        "status": "pending"
    })

    await send_invitation_email(invite.email, invite_link)
    return {"message": "Invitation sent successfully."}

@router.post("/accept")
async def accept_invitation(token: str, db=Depends(get_database)):
    try:
        data = verify_invitation_token(token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    email = data["email"]
    company_id = data["company_id"]

    invitation = await db["invitations"].find_one({"token": token, "status": "pending"})
    if not invitation:
        raise HTTPException(status_code=400, detail="Invitation already used or invalid")

    # Check if user exists
    user = await db["users"].find_one({"email": email})
    if not user:
        # Redirect user to signup in frontend or create placeholder
        raise HTTPException(status_code=404, detail="User not found. Please sign up first.")

    # Add to memberships
    await db["memberships"].insert_one({
        "user_id": user["_id"],
        "company_id": ObjectId(company_id),
        "role": invitation["role"],
        "status": "active",
        "joined_at": datetime.utcnow(),
        "last_used_at": datetime.utcnow()
    })

    # Mark invitation as accepted
    await db["invitations"].update_one(
        {"_id": invitation["_id"]},
        {"$set": {"status": "accepted"}}
    )

    return {"message": "Invitation accepted successfully"}

