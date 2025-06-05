from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pymongo import MongoClient
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

client = MongoClient("mongodb://localhost:27017/")
db = client["mydb"]
users = db["users"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI()

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401, detail="Could not validate credentials"
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        user = users.find_one({"username": username})
        if not user:
            raise credentials_exception
        return user
    except JWTError:
        raise credentials_exception

def require_role(role: str):
    def role_checker(user=Depends(get_current_user)):
        if user.get("role") != role:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return user
    return role_checker

@app.post("/register")
def register(username: str, password: str, role: str = "user"):
    if users.find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed = get_password_hash(password)
    users.insert_one({"username": username, "hashed_password": hashed, "role": role})
    return {"msg": "User created"}

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = users.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = create_access_token({"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
def me(current_user=Depends(get_current_user)):
    return {"username": current_user["username"], "role": current_user["role"]}

@app.get("/admin")
def admin_only(user=Depends(require_role("admin"))):
    return {"msg": f"Hello, {user['username']}! You are an admin."}