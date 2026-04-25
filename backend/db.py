"""
db.py — MongoDB connection and helper functions.
Uses Motor (async MongoDB driver) for FastAPI compatibility.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB  = os.getenv("MONGODB_DB", "mindbridge")

# Single shared client — created once at startup
_client: AsyncIOMotorClient = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI, tlsAllowInvalidCertificates=True)
    return _client


def get_db():
    return get_client()[MONGODB_DB]


# ── Users ───────────────────────────────────────────────────────────────────────

async def create_user(username: str, password_hash: str) -> str:
    db = get_db()
    result = await db.users.insert_one({
        "username": username,
        "password_hash": password_hash,
        "created_at": datetime.utcnow()
    })
    return str(result.inserted_id)

async def get_user(username: str) -> dict:
    db = get_db()
    return await db.users.find_one({"username": username})

# ── Sessions ──────────────────────────────────────────────────────────────────

async def create_session(username: str, title: str = "New conversation") -> str:
    """Insert a new session document and return its string id."""
    db = get_db()
    result = await db.sessions.insert_one({
        "username":   username,
        "title":      title,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    return str(result.inserted_id)


async def list_sessions(username: str, limit: int = 30) -> list[dict]:
    """Return recent sessions newest-first."""
    db = get_db()
    cursor = db.sessions.find({"username": username}).sort("created_at", -1).limit(limit)
    sessions = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        sessions.append(doc)
    return sessions


async def update_session_title(session_id: str, title: str, username: str = None):
    db = get_db()
    query = {"_id": ObjectId(session_id)}
    if username:
        query["username"] = username
    await db.sessions.update_one(
        query,
        {"$set": {"title": title[:60], "updated_at": datetime.utcnow()}}
    )


# ── Messages ──────────────────────────────────────────────────────────────────

async def save_message(session_id: str, role: str, content: str,
                       crisis_triggered: bool = False) -> str:
    """Persist a single message.  role ∈ {'user', 'assistant', 'crisis'}"""
    db = get_db()
    result = await db.messages.insert_one({
        "session_id":      session_id,
        "role":            role,
        "content":         content,
        "crisis_triggered": crisis_triggered,
        "timestamp":       datetime.utcnow(),
    })
    # Also bump session updated_at
    await db.sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"updated_at": datetime.utcnow()}}
    )
    return str(result.inserted_id)


async def get_messages(session_id: str, username: str = None) -> list[dict]:
    """Return all messages for a session, oldest-first."""
    db = get_db()
    
    if username:
        # Verify session belongs to user
        session = await db.sessions.find_one({"_id": ObjectId(session_id), "username": username})
        if not session:
            return []

    cursor = db.messages.find({"session_id": session_id}).sort("timestamp", 1)
    msgs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        msgs.append(doc)
    return msgs


async def get_recent_history(session_id: str, n: int = 10) -> list[dict]:
    """Return the last n messages as simple {role, content} dicts for prompt building."""
    all_msgs = await get_messages(session_id)
    return [{"role": m["role"], "content": m["content"]} for m in all_msgs[-n:]]
