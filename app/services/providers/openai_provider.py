import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.providers.base import (
    NormalizationProvider, NormalizationResult,
    STTProvider, TTSProvider, TTSResult, TranscriptResult,
    TranslationProvider, TranslationResult,
)

logger = logging.getLogger(__name__)


class OpenAIProviders(STTProvider, NormalizationProvider, TranslationProvider, TTSProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.stt_model = "whisper-1"
        self.translation_model = "gpt-4.1-mini"
        self.tts_model = "gpt-4o-mini-tts"
        self.tts_voice = "nova"

    async def transcribe_file(self, audio_path: Path) -> TranscriptResult:
        logger.info("stt.request.start model=%s path=%s", self.stt_model, audio_path)
        with audio_path.open("rb") as audio_file:
            response = await self.client.audio.transcriptions.create(
                model=self.stt_model,
                file=audio_file,
            )
        result = TranscriptResult(text=response.text.strip(), model=self.stt_model)
        logger.info("stt.request.success model=%s text_length=%s", self.stt_model, len(result.text))
        return result

    async def normalize_for_translation(self, text: str) -> NormalizationResult:
        logger.info("normalize.request.start model=%s text_length=%s", self.translation_model, len(text))
        response = await self.client.responses.create(
            model=self.translation_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a text normalization engine that prepares English speech transcripts "
                        "for translation into Hindi.\n"
                        "Return a JSON object with exactly two keys: 'normalized_text' and 'tone'.\n"
                        "Output ONLY the JSON. No markdown, no explanation.\n"
                        "\n"
                        "TONE — classify the speaker's emotional register:\n"
                        "  formal     — professional, structured, polite\n"
                        "  casual     — relaxed, friendly, conversational\n"
                        "  angry      — frustrated, aggressive, uses profanity or strong language\n"
                        "  excited    — enthusiastic, high energy, celebratory\n"
                        "  distressed — worried, sad, upset, pleading\n"
                        "Pick the single best match.\n"
                        "\n"
                        "NORMALIZED TEXT — same language (English), same content, but:\n"
                        "\n"
                        "1. IDENTIFIER DIGIT SEQUENCES (phone numbers, PINs, OTPs, account numbers,\n"
                        "   reference IDs, ZIP/postal codes, order numbers):\n"
                        "   → Spell each digit as an English word.\n"
                        "   '9403430000' → 'nine four zero three four three zero zero zero zero'\n"
                        "   'PIN is 4821' → 'PIN is four eight two one'\n"
                        "   'OTP 739201' → 'OTP seven three nine two zero one'\n"
                        "\n"
                        "2. EXPANDABLE ABBREVIATIONS (things a translator might misread):\n"
                        "   ETA → 'estimated time of arrival'\n"
                        "   ASAP → 'as soon as possible'\n"
                        "   FYI → 'for your information'\n"
                        "   EOD → 'end of day'\n"
                        "   OOO → 'out of office'\n"
                        "   WFH → 'work from home'\n"
                        "   TBD → 'to be decided'\n"
                        "   DOB → 'date of birth'\n"
                        "   Keep technical acronyms as-is: API, URL, SDK, UI, GPS, ID, etc.\n"
                        "\n"
                        "3. TIMES, DATES, QUANTITIES — leave exactly as-is.\n"
                        "   '5 PM', 'March 15', '400 people', '2026' — do not change.\n"
                        "\n"
                        "4. EMOJIS — replace each emoji with its English meaning as a word or short phrase.\n"
                        "   🔥 → 'fire', ❤️ → 'love', 👍 → 'okay', 😂 → 'laughing', 🙏 → 'please'\n"
                        "   Remove emojis that add no meaning (decorative repetition, etc.).\n"
                        "\n"
                        "5. EVERYTHING ELSE — leave exactly as-is.\n"
                        "   Do not rewrite, fix grammar, or add/remove content.\n"
                        "\n"
                        "EXAMPLES:\n"
                        '{"tone":"formal","normalized_text":"Can we move the meeting to 5 PM tomorrow?"}\n'
                        '{"tone":"angry","normalized_text":"Are you kidding me? You have to present right now."}\n'
                        '{"tone":"casual","normalized_text":"My phone number is nine four zero three four three."}'
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        raw = response.output_text.strip()
        normalized_text = text
        detected_tone = "neutral"
        try:
            parsed = json.loads(raw)
            normalized_text = parsed.get("normalized_text", text).strip()
            detected_tone = parsed.get("tone", "neutral")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("normalize.json.parse_failed raw=%r — using original text", raw)

        logger.info(
            "normalize.request.success model=%s tone=%s original=%r normalized=%r",
            self.translation_model, detected_tone, text, normalized_text,
        )
        return NormalizationResult(text=normalized_text, model=self.translation_model, detected_tone=detected_tone)

    async def translate_to_hindi(self, text: str, tone: str) -> TranslationResult:
        logger.info(
            "translation.request.start model=%s text_length=%s",
            self.translation_model,
            len(text),
        )
        response = await self.client.responses.create(
            model=self.translation_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a speech translation engine.\n"
                        "Input: English text transcribed from live speech via ASR.\n"
                        "Output: JSON with exactly two keys: 'tone' and 'translation'.\n"
                        "  tone        — one of: formal | casual | angry | excited | distressed\n"
                        "  translation — Hindi text ready for text-to-speech, spoken aloud verbatim.\n"
                        "Output ONLY the JSON object. No markdown, no explanation.\n"
                        "\n"
                        "STRICT TRANSLATION RULES:\n"
                        "- Hindi only in 'translation'. No English words, no digits, no markdown.\n"
                        "- Never add content not present in the input.\n"
                        "\n"
                        f"TONE: {tone}\n"
                        "Apply this tone throughout the translation:\n"
                        "- formal     → आप-form, polished phrasing. "
                        "'Can we schedule a meeting?' → 'क्या हम एक मीटिंग तय कर सकते हैं?'\n"
                        "- casual     → तुम-form, relaxed. 'What are you up to?' → 'क्या कर रहे हो?'\n"
                        "- angry      → strong, direct Hindi. Preserve intensity — do NOT soften. "
                        "'Are you kidding me?' → 'क्या बकवास कर रहे हो तुम?'\n"
                        "- excited    → energetic Hindi with exclamations where natural.\n"
                        "- distressed → softer, empathetic phrasing.\n"
                        "- neutral    → formal as default.\n"
                        "\n"
                        "NUMBERS:\n"
                        "- Counting/listed (1, 2, 3) → एक, दो, तीन. Never merge digits.\n"
                        "- Times: '5 PM' → 'शाम पाँच बजे', '9 AM' → 'सुबह नौ बजे'.\n"
                        "- Dates: 'March 15' → 'पंद्रह मार्च'.\n"
                        "- Integers in sentences → Hindi words: '3 points' → 'तीन बातें'.\n"
                        "\n"
                        "NAMED ENTITIES:\n"
                        "- Transliterate: 'Google Meet' → 'गूगल मीट', 'Zoom' → 'ज़ूम'.\n"
                        "- Acronyms: API → 'एपीआई', ETA → 'ईटीए'.\n"
                        "\n"
                        "PARTIAL INPUT:\n"
                        "- Translate only what is present. Do not complete or invent.\n"
                        "\n"
                        "EXAMPLES:\n"
                        '{"tone":"formal","translation":"क्या हम मीटिंग को कल शाम पाँच बजे कर सकते हैं?"}\n'
                        '{"tone":"angry","translation":"क्या बकवास कर रहे हो तुम? चार सौ लोगों के सामने अभी प्रेजेंटेशन देनी है।"}'
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        raw = response.output_text.strip()
        translation_text = raw
        try:
            parsed = json.loads(raw)
            translation_text = parsed.get("translation", raw).strip()
        except (json.JSONDecodeError, AttributeError):
            logger.warning("translation.json.parse_failed raw=%r — using raw output", raw)
        result = TranslationResult(text=translation_text, model=self.translation_model, detected_tone=tone)
        logger.info(
            "translation.request.success model=%s tone=%s text_length=%s",
            self.translation_model,
            tone,
            len(result.text),
        )
        return result

    async def synthesize_hindi(self, text: str) -> TTSResult:
        logger.info("tts.request.start model=%s voice=%s text_length=%s", self.tts_model, self.tts_voice, len(text))
        response = await self.client.audio.speech.create(
            model=self.tts_model,
            voice=self.tts_voice,
            input=text,
            response_format="mp3",
        )
        audio_bytes = await response.aread()
        result = TTSResult(audio_bytes=audio_bytes, format="mp3", model=self.tts_model)
        logger.info("tts.request.success model=%s bytes=%s", self.tts_model, len(result.audio_bytes))
        return result
