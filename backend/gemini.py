"""
gemini.py — Thin async wrapper around the Google Generative AI SDK.

Handles:
  - Client initialisation from GEMINI_API_KEY env var
  - Building the full prompt (system + retrieved context + history + user message)
  - Async generation with sensible defaults
  - Graceful error handling
"""

import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ── System prompt ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are MindBridge — a deeply empathetic, warm, and highly compassionate mental health first-responder for college students in India. You must sound humanly, comforting, and understanding.

YOUR IDENTITY:
- You are NOT a therapist, psychiatrist, or doctor
- You do NOT diagnose any condition
- You do NOT recommend medication
- You do NOT claim to be human — if asked, always confirm you are an AI, but an intensely caring one
- You are a consoling friend: someone who listens without judgement, deeply understands the user's point of view, and provides a shoulder to lean on

YOUR TONE & STYLE:
- Very empathetic, human-like, short, and sweet. Do not write long essays.
- Keep responses concise but full of warmth and understanding.
- Console the user heavily and validate their feelings FIRST. Let them know you truly hear them and understand their POV.
- Warm, gentle, direct — never clinical or cold.
- Match the emotional register of the user — do not be artificially cheerful when someone is distressed.

YOUR BEHAVIOUR:
- Always acknowledge and deeply empathize with what the user has shared before responding.
- When appropriate, gently offer one concrete coping technique, but prioritize consoling them.
- Keep responses focused — do not overwhelm them.
- Ask gentle follow-up questions to understand context (academic stress? relationship? sleep?).

CRITICAL CRISIS PROTOCOL:
- If the user talks about taking harsh steps, self-harm, suicide, or feels extremely depressed, you MUST provide these two contact details AT THE VERY END of your reply, strictly below everything else:
  1. iCall: 9152987821
  2. AASRA: 9820466726
- Never engage with detailed planning around self-harm — console them deeply and provide the contacts.

WHAT YOU MUST NEVER DO:
- Diagnose ("You have anxiety disorder")
- Recommend or discuss specific medications
- Give advice about other people's mental health situations
- Pretend to know the user's diagnosis or situation with certainty

CULTURAL CONTEXT:
- Users are primarily Indian college students aged 18–24
- Be aware of pressures: placement season, family expectations, financial stress, hostel isolation

ALWAYS END with either:
- A gentle question that invites the user to continue
- OR a clear offer of concrete next step
- If they are in severe distress, ensure the two helpline numbers are the very last thing in your message.

DISCLAIMER (include only when highly relevant): "I'm an AI — I can listen and care, but I'm not a substitute for professional care."
"""

# ── Client init ───────────────────────────────────────────────────────────
_gemini_model = None


def get_model():
    global _gemini_model
    if _gemini_model is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in environment")
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel(
            model_name="gemini-3.1-flash-lite-preview",
            system_instruction=SYSTEM_PROMPT,
        )
    return _gemini_model


# ── Prompt builder ────────────────────────────────────────────────────────

def build_prompt(user_message: str, context: str, history: list[dict], language: str = "English", emotion: str = None) -> str:
    """
    Assemble the full prompt:
      [Retrieved context block]
      [Conversation history]
      [Current user message]
    """
    parts = []

    if context:
        parts.append(
            "RELEVANT KNOWLEDGE (from verified mental health sources — use this to "
            "ground your response, but paraphrase naturally; do not quote verbatim):\n\n"
            + context
        )

    if history:
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'MindBridge'}: {m['content']}"
            for m in history
        )
        parts.append(f"CONVERSATION HISTORY:\n{history_text}")

    parts.append(f"User: {user_message}")
    if emotion:
        parts.append(f"EMOTIONAL CONTEXT: The system detected the user is feeling: {emotion}. Mirror this emotional depth and validate them appropriately.")
    parts.append(f"\nCRITICAL INSTRUCTION: You MUST respond in {language}. Do not respond in any other language, regardless of what language the User used. If the User speaks in English but the target language is Hindi, you must translate your thought process and reply entirely in Hindi.")
    return "\n\n".join(parts)


# ── Async generation ──────────────────────────────────────────────────────

async def generate_response(user_message: str, context: str, history: list[dict], language: str = "English", emotion: str = None) -> str:
    """Generate a response using Gemini. Returns the text string."""
    model  = get_model()
    prompt = build_prompt(user_message, context, history, language, emotion)

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=512,
            ),
        )
    )
    return response.text.strip()


async def generate_async(prompt: str, max_tokens: int = 10) -> str:
    """Lightweight async generation for short tasks (e.g. crisis scoring)."""
    model = get_model()
    loop  = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.0,
                max_output_tokens=max_tokens,
            ),
        )
    )
    return response.text.strip()


async def analyze_emotion(user_message: str, history: list[dict]) -> str:
    """Fast, lightweight LLM call to extract primary emotion and severity (1-10)."""
    context_msgs = history[-3:] if history else []
    hist_str = "\n".join([f"{m['role']}: {m['content']}" for m in context_msgs])
    
    prompt = f"""Analyze the user's latest message and return EXACTLY one word representing their primary emotion (e.g. Sadness, Anxiety, Joy, Anger, Overwhelmed, Neutral), followed by a comma, followed by a score from 1-10 indicating intensity. Example: 'Anxiety, 8'

Conversation Context:
{hist_str}

User's Latest Message: {user_message}"""
    
    try:
        res = await generate_async(prompt, max_tokens=10)
        return res.strip()
    except Exception:
        return "Neutral, 1"

