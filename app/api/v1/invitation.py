# routers/invitations.py
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
from bson import ObjectId
from app.db.mongodb import get_database
from app.models.invitation import InvitationBase, InvitationDetails, AcceptInvitationRequest
from app.utils.token_utils import create_invitation_token, verify_invitation_token
from app.utils.email_utils import send_invitation_email
from jose import jwt, JWTError
from app.core.config import settings
from fastapi.responses import RedirectResponse

router = APIRouter()

#POST /api/v1/invitations/send
@router.post("/send")
async def send_invitation(invite: InvitationBase, db=Depends(get_database)):
    if not ObjectId.is_valid(str(invite.company_id)):
        raise HTTPException(status_code=400, detail="Invalid company ID")
    
    token = create_invitation_token(invite.email, str(invite.company_id), invite.role)
    invite_link = f"{settings.FRONTEND_URL}/accept-invite?token={token}"

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
async def accept_invitation(
    payload: AcceptInvitationRequest,
    db=Depends(get_database)
):
    try:
        data = verify_invitation_token(payload.token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation token")

    email = data["email"]
    company_id = data["company_id"]

    invitation = await db["invitations"].find_one({"token": payload.token, "status": "pending"})
    if not invitation:
        raise HTTPException(status_code=400, detail="Invitation already used or invalid")

    # Check if user exists
    user = await db["users"].find_one({"email": email})
    if not user:
        # Frontend can redirect to signup page if user doesn't exist
        return {"redirect_url": f"/signup?token={payload.token}"}

    # Add user to memberships
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

    return {"redirect_url": f"/login"}

# GET endpoint
@router.get("/{token}", response_model=InvitationDetails)
def get_invitation(token: str):
    payload = verify_invitation_token(token)

    return InvitationDetails(
        email=payload["email"],
        company_id=payload["company_id"],
        role=payload["role"],
        expires_at=datetime.utcnow() + timedelta(seconds=172800)  # optional
    )