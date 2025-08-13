# token_utils.py
from itsdangerous import URLSafeTimedSerializer
from app.core.config import settings

serializer = URLSafeTimedSerializer(settings.SECRET_KEY)

def create_invitation_token(email: str, company_id: str):
    return serializer.dumps({"email": email, "company_id": company_id})

def verify_invitation_token(token: str, max_age: int = 172800):  # 48 hours
    return serializer.loads(token, max_age=max_age)
