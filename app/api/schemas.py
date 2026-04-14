from typing import Literal

from pydantic import BaseModel


class SessionStartPayload(BaseModel):
    event_type: Literal["session.start"]
    session_id: str
    sequence_id: int
    timestamp: str


class AudioChunkPayload(BaseModel):
    event_type: Literal["audio.chunk"]
    session_id: str
    sequence_id: int
    timestamp: str
    payload_b64: str
    mime_type: str = "audio/webm;codecs=opus"
    chunk_duration_ms: int


class SessionStopPayload(BaseModel):
    event_type: Literal["session.stop"]
    session_id: str
    sequence_id: int
    timestamp: str


class PlaybackInterruptPayload(BaseModel):
    event_type: Literal["playback.interrupt"]
    session_id: str
    sequence_id: int
    timestamp: str

