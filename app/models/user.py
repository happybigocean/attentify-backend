from pydantic import BaseModel, EmailStr

class User(BaseModel):
    email: EmailStr

class UserCreate(User):
    password: str

class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str