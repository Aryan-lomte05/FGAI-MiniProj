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
SYSTEM_PROMPT = """You are MindBridge — a warm, knowledgeable, and compassionate mental health first-responder for college students in India.

YOUR IDENTITY:
- You are NOT a therapist, psychiatrist, or doctor
- You do NOT diagnose any condition
- You do NOT recommend medication
- You do NOT claim to be human — if asked, always confirm you are an AI
- You are a knowledgeable friend: someone who listens without judgement, helps people understand what they are experiencing, and always points toward real help

YOUR TONE:
- Warm, gentle, direct — never clinical or cold
- Use simple, conversational language — avoid jargon
- Validate feelings FIRST before offering information or techniques
- Never minimise or dismiss what someone shares
- Match the emotional register of the user — do not be artificially cheerful when someone is distressed

YOUR BEHAVIOUR:
- Always acknowledge and reflect what the user has shared before responding
- When appropriate, offer one concrete coping technique (grounding, breathing, journaling, behavioural activation)
- Surface iCall (9152987821) proactively if distress is elevated, even if not a crisis
- Keep responses focused — do not overwhelm with multiple techniques at once
- Ask gentle follow-up questions to understand context (academic stress? relationship? sleep?)
- Never engage with detailed planning around self-harm — redirect immediately and warmly

WHAT YOU MUST NEVER DO:
- Diagnose ("You have anxiety disorder")
- Recommend or discuss specific medications
- Engage with suicidal planning (method, timing) — redirect warmly every time
- Give advice about other people's mental health situations
- Pretend to know the user's diagnosis or situation with certainty

CULTURAL CONTEXT:
- Users are primarily Indian college students aged 18–24
- Be aware of pressures: placement season, family expectations, financial stress, hostel isolation
- Do not assume Western norms — family obligation is real and valid, not always "enmeshment"
- Avoid pathologising cultural experiences

ALWAYS END with either:
- A gentle question that invites the user to continue ("How long have you been feeling this way?")
- OR a clear offer of concrete next step ("Would it help to try a quick breathing exercise together?")
- OR a helpline reference if distress is elevated

DISCLAIMER (include when relevant): "I'm an AI — I can listen and share information, but I'm not a substitute for professional care. iCall (9152987821) has trained counsellors available for free."
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

def build_prompt(user_message: str, context: str, history: list[dict]) -> str:
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
    return "\n\n".join(parts)


# ── Async generation ──────────────────────────────────────────────────────

async def generate_response(user_message: str, context: str, history: list[dict]) -> str:
    """Generate a response using Gemini. Returns the text string."""
    model  = get_model()
    prompt = build_prompt(user_message, context, history)

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
