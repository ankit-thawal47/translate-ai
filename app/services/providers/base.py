from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class TranscriptResult:
    text: str
    model: str


@dataclass(slots=True)
class TranslationResult:
    text: str
    model: str
    detected_tone: str = "unknown"


@dataclass(slots=True)
class TTSResult:
    audio_bytes: bytes
    format: str
    model: str


class STTProvider:
    async def transcribe_file(self, audio_path: Path) -> TranscriptResult:  # pragma: no cover - interface
        raise NotImplementedError


class TranslationProvider:
    async def translate_to_hindi(self, text: str, tone: str) -> TranslationResult:  # pragma: no cover
        raise NotImplementedError


class TTSProvider:
    async def synthesize_hindi(self, text: str) -> TTSResult:  # pragma: no cover - interface
        raise NotImplementedError

