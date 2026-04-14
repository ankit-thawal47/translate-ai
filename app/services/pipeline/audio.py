import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SessionAudioBuffer:
    session_id: str
    init_chunk: bytes | None = None
    chunks: list[bytes] = field(default_factory=list)
    bytes_received: int = 0
    window_index: int = 0

    def add_chunk(self, chunk: bytes) -> None:
        if self.init_chunk is None:
            self.init_chunk = chunk
        self.chunks.append(chunk)
        self.bytes_received += len(chunk)

    def should_flush(self, duration_hint_ms: int) -> bool:
        settings = get_settings()
        return duration_hint_ms >= settings.stt_window_seconds * 1000

    def build_window(self) -> bytes:
        if not self.init_chunk:
            return b"".join(self.chunks)
        if not self.chunks:
            return b""
        # MediaRecorder emits a single init/header chunk first; prepend it for each window.
        return self.init_chunk + b"".join(self.chunks[1:])

    def reset_window(self) -> None:
        if self.init_chunk is None:
            self.chunks.clear()
        else:
            self.chunks = [self.init_chunk]
        self.window_index += 1


async def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, payload)


async def convert_webm_to_wav(source_path: Path, destination_path: Path) -> None:
    def _run() -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(destination_path),
            ],
            check=True,
            capture_output=True,
        )

    logger.info("audio.convert.start source=%s destination=%s", source_path, destination_path)
    await asyncio.to_thread(_run)
