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

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from elevenlabs.client import ElevenLabs
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
    language: str = "English"


class TTSRequest(BaseModel):
    text: str

# ── Auth Config ────────────────────────────────────────────────────────
security = HTTPBearer()

def get_password_hash(password: str):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, os.getenv("JWT_SECRET", "supersecret"), algorithm="HS256")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "supersecret"), algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

class AuthRequest(BaseModel):
    username: str
    password: str

# ── Routes ────────────────────────────────────────────────────────────────

@app.post("/api/auth/register")
async def register(req: AuthRequest):
    existing = await db.get_user(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed = get_password_hash(req.password)
    await db.create_user(req.username, hashed)
    return {"message": "User registered successfully"}

@app.post("/api/auth/login")
async def login(req: AuthRequest):
    user = await db.get_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token({"sub": req.username})
    return {"access_token": token, "token_type": "bearer", "username": req.username}


@app.get("/health")
async def health():
    return {"status": "ok", "rag_chunks": len(rag._chunks)}


@app.post("/api/sessions/new")
async def new_session(req: NewSessionRequest, current_user: str = Depends(get_current_user)):
    sid = await db.create_session(current_user, req.title)
    return {"session_id": sid, "title": req.title}


@app.get("/api/sessions")
async def list_sessions(current_user: str = Depends(get_current_user)):
    sessions = await db.list_sessions(current_user)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str, current_user: str = Depends(get_current_user)):
    msgs = await db.get_messages(session_id, current_user)
    return {"messages": msgs}


@app.post("/api/chat")
async def chat(req: ChatRequest, current_user: str = Depends(get_current_user)):
    user_msg   = req.message.strip()
    session_id = req.session_id

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # 1. Persist user message
    await db.save_message(session_id, "user", user_msg)

    # 2. Retrieve conversation history early for context window
    history = await db.get_recent_history(session_id, n=8)
    history = history[:-1]

    # 3. Parallel Tasks (RAG, Crisis, Emotion)
    context_task = asyncio.create_task(
        asyncio.to_thread(rag.retrieve, user_msg)
    )
    crisis_task = asyncio.create_task(
        crs.check_crisis(user_msg, gem)
    )
    emotion_task = asyncio.create_task(
        gem.analyze_emotion(user_msg, history)
    )

    context, is_crisis, emotion = await asyncio.gather(context_task, crisis_task, emotion_task)

    if is_crisis:
        # Bypass LLM entirely — use pre-written, human-reviewed crisis response
        await db.save_message(session_id, "crisis", crs.CRISIS_RESPONSE, crisis_triggered=True)
        # Auto-title session if first turn
        all_msgs = await db.get_messages(session_id)
        if len(all_msgs) <= 2:
            await db.update_session_title(session_id, "Crisis support session", current_user)
        return {
            "response":        crs.CRISIS_RESPONSE,
            "crisis_triggered": True,
            "session_id":      session_id,
            "emotion":         emotion
        }

    # 4. Generate response via Gemini
    try:
        response_text = await gem.generate_response(user_msg, context, history, req.language, emotion)
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
        await db.update_session_title(session_id, title, current_user)

    return {
        "response":        response_text,
        "crisis_triggered": False,
        "session_id":      session_id,
        "emotion":         emotion
    }


@app.post("/api/tts")
def text_to_speech(req: TTSRequest):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")
        
    client = ElevenLabs(api_key=api_key)
    
    try:
        audio_stream = client.text_to_speech.convert(
            voice_id="EXAVITQu4vr4xnSDxMaL", # Sarah voice ID (Available on free tier)
            text=req.text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        return StreamingResponse(audio_stream, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stt")
def speech_to_text(file: UploadFile = File(...)):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")
        
    client = ElevenLabs(api_key=api_key)
    try:
        response = client.speech_to_text.convert(
            file=file.file,
            model_id="scribe_v1"
        )
        return {"text": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
