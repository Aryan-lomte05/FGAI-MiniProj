"""
crisis.py — Two-layer crisis detection.

Layer 1 (fast): Regex keyword match on explicit crisis phrases.
Layer 2 (Gemini): Score distress level 1-10; flag if >= 7.

The crisis response is fully pre-written — the LLM is NOT used for
crisis responses. This is intentional and safety-critical.
"""

import re

# ── Pre-written crisis response (human-reviewed) ───────────────────────────
CRISIS_RESPONSE = """I hear you, and I'm really glad you're talking to me right now.

What you're feeling is real, and you don't have to carry it alone.

Please reach out to someone who can support you right now:

📞 **iCall (TISS)** — 9152987821
   Monday–Saturday, 8 AM–10 PM | Free, confidential, no judgement

📞 **Vandrevala Foundation** — 1860-2662-345
   Available 24/7, any hour of the day or night

If you are in immediate danger, please call **112** (India emergency) or go to your nearest hospital.

You reached out here — that matters. These counsellors want to hear from you. Will you call one of them?"""

# ── Layer 1: Keyword regex ─────────────────────────────────────────────────
_CRISIS_PATTERNS = re.compile(
    r"\b("
    r"want to die|wanna die|kill myself|end my life|end it all|"
    r"suicide|suicidal|self.harm|self harm|cutting myself|hurt myself|"
    r"no reason to live|not worth living|better off dead|"
    r"don't want to be here|dont want to be here|"
    r"can't go on|cant go on|give up on life|"
    r"overdose|hanging|jump off|methods to die"
    r")\b",
    re.IGNORECASE,
)

def keyword_crisis_check(text: str) -> bool:
    """Return True if the message contains explicit crisis language."""
    return bool(_CRISIS_PATTERNS.search(text))


# ── Layer 2: Gemini distress scoring ──────────────────────────────────────
async def llm_crisis_check(text: str, gemini_client) -> bool:
    """
    Ask Gemini to score distress 1-10.  Returns True if score >= 7.
    Uses a very short, focused prompt — this runs in parallel with the main response.
    Falls back to False on error (keyword layer is the hard safety net).
    """
    try:
        prompt = (
            "You are a mental health safety classifier. "
            "Rate the distress level of the following message on a scale of 1 to 10. "
            "1 = calm/everyday stress. 10 = immediate crisis or suicidal ideation. "
            "Respond with ONLY a single integer and nothing else.\n\n"
            f"Message: {text[:500]}"
        )
        response = await gemini_client.generate_async(prompt, max_tokens=5)
        score_str = response.strip()
        score = int(re.search(r"\d+", score_str).group())
        return score >= 7
    except Exception:
        return False


async def check_crisis(text: str, gemini_client) -> bool:
    """
    Combined check: keyword first (fast path), then LLM if not triggered.
    Returns True if either layer flags the message.
    """
    if keyword_crisis_check(text):
        return True
    return await llm_crisis_check(text, gemini_client)
