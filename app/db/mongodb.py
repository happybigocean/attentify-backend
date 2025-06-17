# app/db/mongodb.py

from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import Request
import os

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "attentify")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Dependency for FastAPI
async def get_database():
    return db
