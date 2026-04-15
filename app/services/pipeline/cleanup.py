import re

FILLER_PATTERNS = [
    r"\buh\b",
    r"\bumm\b",
    r"\bum\b",
    r"\bahh\b",
    r"\byou know\b",
]

WHISPER_HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "thanks for watching!",
    "please subscribe",
    "like and subscribe",
    "subscribe to my channel",
    "don't forget to subscribe",
    "see you in the next video",
    "see you next time",
    "bye",
    "goodbye",
    "...",
    "thank you",
    "thanks",
}


def _is_hallucination(text: str) -> bool:
    normalised = re.sub(r"[^\w\s]", "", text).strip().lower()
    return normalised in WHISPER_HALLUCINATIONS or text.strip() in WHISPER_HALLUCINATIONS


def clean_transcript(text: str) -> str:
    if not text or _is_hallucination(text):
        return ""
    cleaned = text
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.")
    if _is_hallucination(cleaned):
        return ""
    if cleaned and cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned