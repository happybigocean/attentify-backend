#app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
import os

# CORS origins
origins = os.getenv("ORIGINS", "http://localhost:5173").split(",")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "attentify")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        mongo_client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        # Try to ping the server to check connection
        await mongo_client.admin.command("ping")
        print("✅ Connected to MongoDB")
        app.state.mongo_client = mongo_client
        app.state.db = mongo_client[DB_NAME]
    except Exception as e:
        print("❌ Failed to connect to MongoDB:", e)
        raise e  # Optional: prevent app from starting if DB fails

    yield  # App runs

    print("🔌 Closing MongoDB connection")
    mongo_client.close()

app = FastAPI(title="Attentify APP", lifespan=lifespan)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from app.api.v1 import auth
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
#app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
#app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["Inbox"])
#app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])
#app.include_router(templates.router, prefix="/api/v1/templates", tags=["Templates"])
#app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["Webhooks"])
#app.include_router(shopify.router, prefix="/api/v1/shopify", tags=["Shopify"])
#app.include_router(twilio.router, prefix="/api/v1/twilio", tags=["Twilio"])
#app.include_router(gmail.router, prefix="/api/v1/gmail", tags=["Gmail"])
#app.include_router(stripe.router, prefix="/api/v1/stripe", tags=["Stripe"])

@app.get("/")
def read_root():
    return {"status": "ok"}

@app.get("/health")
def health_check():
    return {"status": "ok"}