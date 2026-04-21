"""
main.py — FastAPI application entry point for MindBridge.

Endpoints:
  POST /api/sessions/new          → create a session
  GET  /api/sessions              → list all sessions
  GET  /api/sessions/{id}/messages → all messages for a session
  POST /api/chat                  → main chat endpoint (RAG + Gemini + crisis)
  GET  /health                    → health check
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import rag
import gemini as gem
import crisis as crs
import db

# ── Lifespan: build RAG index on startup ─────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] Building RAG index …")
    rag.build_index()
    print("[Startup] Ready.")
    yield
    print("[Shutdown] Goodbye.")


app = FastAPI(title="MindBridge API", lifespan=lifespan)

# Allow frontend (file:// or localhost dev server) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend from ../frontend/
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ── Request models ────────────────────────────────────────────────────────

class NewSessionRequest(BaseModel):
    title: str = "New conversation"


class ChatRequest(BaseModel):
    session_id: str
    message: str


# ── Routes ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "rag_chunks": len(rag._chunks)}


@app.post("/api/sessions/new")
async def new_session(req: NewSessionRequest):
    sid = await db.create_session(req.title)
    return {"session_id": sid, "title": req.title}


@app.get("/api/sessions")
async def list_sessions():
    sessions = await db.list_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    msgs = await db.get_messages(session_id)
    return {"messages": msgs}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_msg   = req.message.strip()
    session_id = req.session_id

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # 1. Persist user message
    await db.save_message(session_id, "user", user_msg)

    # 2. Crisis check (keyword layer is synchronous, LLM layer is async)
    #    We run crisis check concurrently with RAG retrieval for speed.
    context_task = asyncio.create_task(
        asyncio.to_thread(rag.retrieve, user_msg)
    )
    crisis_task = asyncio.create_task(
        crs.check_crisis(user_msg, gem)
    )

    context, is_crisis = await asyncio.gather(context_task, crisis_task)

    if is_crisis:
        # Bypass LLM entirely — use pre-written, human-reviewed crisis response
        await db.save_message(session_id, "crisis", crs.CRISIS_RESPONSE, crisis_triggered=True)
        # Auto-title session if first turn
        all_msgs = await db.get_messages(session_id)
        if len(all_msgs) <= 2:
            await db.update_session_title(session_id, "Crisis support session")
        return {
            "response":        crs.CRISIS_RESPONSE,
            "crisis_triggered": True,
            "session_id":      session_id,
        }

    # 3. Retrieve conversation history for context window
    history = await db.get_recent_history(session_id, n=8)
    # Exclude the message we just inserted (it's the last one)
    history = history[:-1]

    # 4. Generate response via Gemini
    try:
        response_text = await gem.generate_response(user_msg, context, history)
    except Exception as e:
        print(f"[Gemini error] {e}")
        response_text = (
            "I'm sorry, I'm having a bit of difficulty right now. "
            "If you need immediate support, please contact iCall at 9152987821. "
            "They're available Monday–Saturday, 8 AM–10 PM."
        )

    # 5. Persist assistant response
    await db.save_message(session_id, "assistant", response_text)

    # 6. Auto-title session from first user message
    all_msgs = await db.get_messages(session_id)
    if len(all_msgs) == 2:   # user + first assistant reply
        title = user_msg[:50] + ("…" if len(user_msg) > 50 else "")
        await db.update_session_title(session_id, title)

    return {
        "response":        response_text,
        "crisis_triggered": False,
        "session_id":      session_id,
    }


# ── Serve index.html at root ──────────────────────────────────────────────

@app.get("/")
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "MindBridge API running. Frontend not mounted."}


@app.get("/chat")
async def serve_chat():
    chat_path = os.path.join(FRONTEND_DIR, "chat.html")
    if os.path.exists(chat_path):
        return FileResponse(chat_path)
    raise HTTPException(status_code=404, detail="Chat page not found")
