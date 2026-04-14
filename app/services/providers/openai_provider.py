import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.providers.base import STTProvider, TTSProvider, TTSResult, TranscriptResult
from app.services.providers.base import TranslationProvider, TranslationResult

logger = logging.getLogger(__name__)


class OpenAIProviders(STTProvider, TranslationProvider, TTSProvider):
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
                        "TONE DETECTION & EMOTIONAL INTENSITY:\n"
                        "- Detect the emotional register from word choice, punctuation, and intensity.\n"
                        "- ANGRY/FRUSTRATED (profanity, exclamations, aggressive phrasing):\n"
                        "    Use strong Hindi expressions that carry the same weight.\n"
                        "    'Are you fucking kidding me?' → 'क्या बकवास कर रहे हो तुम?'\n"
                        "    'What the hell is wrong with you?' → 'तुम्हें क्या हो गया है यार?'\n"
                        "    Preserve raised intensity — do NOT soften angry speech into polite Hindi.\n"
                        "- FORMAL (professional, structured, polite):\n"
                        "    आप-form. 'Can we schedule a meeting?' → 'क्या हम एक मीटिंग तय कर सकते हैं?'\n"
                        "- CASUAL (relaxed, friendly, informal):\n"
                        "    तुम-form. 'What are you up to?' → 'क्या कर रहे हो?'\n"
                        "- EXCITED (enthusiasm, high energy):\n"
                        "    Reflect energy with appropriate Hindi exclamations.\n"
                        "- DISTRESSED (worried, sad, upset):\n"
                        "    Softer, empathetic phrasing.\n"
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
        detected_tone = "unknown"
        translation_text = raw
        try:
            parsed = json.loads(raw)
            translation_text = parsed.get("translation", raw).strip()
            detected_tone = parsed.get("tone", "unknown")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("translation.json.parse_failed raw=%r — using raw output as translation", raw)

        result = TranslationResult(text=translation_text, model=self.translation_model, detected_tone=detected_tone)
        logger.info(
            "translation.request.success model=%s detected_tone=%s text_length=%s",
            self.translation_model,
            detected_tone,
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
