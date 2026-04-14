import asyncio
import base64
import json
import logging
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.schemas import AudioChunkPayload, PlaybackInterruptPayload, SessionStartPayload
from app.api.schemas import SessionStopPayload
from app.core.config import get_settings
from app.services.pipeline.audio import SessionAudioBuffer, convert_webm_to_wav, write_bytes
from app.services.pipeline.cleanup import clean_transcript
from app.services.pipeline.storage import ObjectStorage
from app.services.providers.openai_provider import OpenAIProviders

router = APIRouter()
logger = logging.getLogger(__name__)


@dataclass
class LiveSession:
    session_id: str
    websocket: WebSocket
    queue: asyncio.Queue[AudioChunkPayload]
    audio_buffer: SessionAudioBuffer
    processor_task: asyncio.Task | None = None
    active_tts_task: asyncio.Task | None = None
    cancelled: bool = False
    latest_sequence_id: int = 0
    elapsed_window_ms: int = 0
    segment_index: int = 0
    # Sentence carry-forward: text from an incomplete previous segment
    pending_text: str = ""
    held_segment_count: int = 0


class SessionRegistry:
    def __init__(self) -> None:
        self.sessions: dict[str, LiveSession] = {}
        self.settings = get_settings()
        self.providers = OpenAIProviders()
        self.storage: ObjectStorage | None = None

    def ensure_storage(self) -> ObjectStorage:
        if self.storage is None:
            storage = ObjectStorage()
            storage.ensure_bucket()
            self.storage = storage
        return self.storage

    async def start_session(self, payload: SessionStartPayload, websocket: WebSocket) -> LiveSession:
        queue: asyncio.Queue[AudioChunkPayload] = asyncio.Queue(maxsize=self.settings.ingress_queue_cap)
        session = LiveSession(
            session_id=payload.session_id,
            websocket=websocket,
            queue=queue,
            audio_buffer=SessionAudioBuffer(session_id=payload.session_id),
            latest_sequence_id=payload.sequence_id,
        )
        session.processor_task = asyncio.create_task(self._process_session(session))
        self.sessions[payload.session_id] = session
        logger.info("session.started session_id=%s", payload.session_id)
        return session

    async def stop_session(self, session_id: str) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        logger.info("session.stop.requested session_id=%s", session_id)
        if session.processor_task:
            await session.queue.put(None)  # type: ignore[arg-type]
            await session.processor_task
        self.sessions.pop(session_id, None)
        logger.info("session.stopped session_id=%s", session_id)

    async def enqueue_chunk(self, payload: AudioChunkPayload) -> None:
        session = self.sessions.get(payload.session_id)
        if not session:
            return
        session.latest_sequence_id = payload.sequence_id
        logger.info(
            "audio.chunk.received session_id=%s sequence_id=%s duration_ms=%s queue_size=%s",
            payload.session_id,
            payload.sequence_id,
            payload.chunk_duration_ms,
            session.queue.qsize(),
        )
        if session.queue.full():
            await session.websocket.send_json(
                {"event_type": "error", "code": "INGRESS_QUEUE_OVERFLOW", "session_id": payload.session_id}
            )
            await session.websocket.close(code=4000)
            raise RuntimeError("Ingress queue overflow")
        await session.queue.put(payload)

    async def interrupt(self, payload: PlaybackInterruptPayload) -> None:
        session = self.sessions.get(payload.session_id)
        if not session:
            return
        logger.info("playback.interrupt session_id=%s sequence_id=%s", payload.session_id, payload.sequence_id)
        session.cancelled = True
        if session.active_tts_task and not session.active_tts_task.done():
            session.active_tts_task.cancel()

    async def _process_session(self, session: LiveSession) -> None:
        max_duration = self.settings.max_session_duration_seconds
        deadline = asyncio.get_event_loop().time() + max_duration
        try:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.warning(
                        "session.limit_reached session_id=%s max_seconds=%s",
                        session.session_id,
                        max_duration,
                    )
                    await session.websocket.send_json(
                        {
                            "event_type": "session.limit_reached",
                            "session_id": session.session_id,
                            "reason": "MAX_SESSION_DURATION",
                        }
                    )
                    if session.elapsed_window_ms > 0 and len(session.audio_buffer.chunks) > 1:
                        await self._flush_window(session, None, is_final=True)
                    elif session.pending_text:
                        await self._flush_pending(session, None)
                    break

                try:
                    payload = await asyncio.wait_for(session.queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    logger.warning(
                        "session.limit_reached session_id=%s max_seconds=%s",
                        session.session_id,
                        max_duration,
                    )
                    await session.websocket.send_json(
                        {
                            "event_type": "session.limit_reached",
                            "session_id": session.session_id,
                            "reason": "MAX_SESSION_DURATION",
                        }
                    )
                    if session.elapsed_window_ms > 0 and len(session.audio_buffer.chunks) > 1:
                        await self._flush_window(session, None, is_final=True)
                    elif session.pending_text:
                        await self._flush_pending(session, None)
                    break

                if payload is None:
                    if session.elapsed_window_ms > 0 and len(session.audio_buffer.chunks) > 1:
                        await self._flush_window(session, None, is_final=True)
                    elif session.pending_text:
                        await self._flush_pending(session, None)
                    break
                raw_chunk = base64.b64decode(payload.payload_b64)
                session.audio_buffer.add_chunk(raw_chunk)
                session.elapsed_window_ms += payload.chunk_duration_ms

                if not session.audio_buffer.should_flush(session.elapsed_window_ms):
                    continue

                await self._flush_window(session, payload)
                session.elapsed_window_ms = 0
                session.audio_buffer.reset_window()
                session.segment_index += 1
        except Exception:
            logger.exception("session.processing.failed session_id=%s", session.session_id)
            try:
                await session.websocket.send_json(
                    {
                        "event_type": "error",
                        "code": "SEGMENT_PROCESSING_FAILED",
                        "session_id": session.session_id,
                    }
                )
            except Exception:
                logger.exception("session.error.emit.failed session_id=%s", session.session_id)

    async def _flush_window(
        self, session: LiveSession, payload: AudioChunkPayload | None, *, is_final: bool = False
    ) -> None:
        settings = self.settings
        segment_prefix = f"{session.session_id}/segment-{session.segment_index}"
        webm_path = settings.tmp_dir / f"{segment_prefix}.webm"
        wav_path = settings.tmp_dir / f"{segment_prefix}.wav"
        mp3_path = settings.tmp_dir / f"{segment_prefix}.mp3"
        storage = self.ensure_storage()

        assembled = session.audio_buffer.build_window()
        logger.info(
            "segment.flush.start session_id=%s segment_index=%s bytes=%s elapsed_window_ms=%s",
            session.session_id,
            session.segment_index,
            len(assembled),
            session.elapsed_window_ms,
        )
        await session.websocket.send_json(
            {
                "event_type": "session.processing",
                "session_id": session.session_id,
                "segment_index": session.segment_index,
            }
        )
        await write_bytes(webm_path, assembled)
        storage.upload_file(webm_path, f"{segment_prefix}.webm")
        await convert_webm_to_wav(webm_path, wav_path)

        transcript = await self.providers.transcribe_file(wav_path)
        logger.info(
            "segment.transcript session_id=%s segment_index=%s text=%r",
            session.session_id,
            session.segment_index,
            transcript.text,
        )
        cleaned = clean_transcript(transcript.text)
        logger.info(
            "segment.cleaned session_id=%s segment_index=%s text=%r",
            session.session_id,
            session.segment_index,
            cleaned,
        )

        # Combine with any text carried forward from a previous incomplete segment
        if session.pending_text and cleaned:
            combined = f"{session.pending_text} {cleaned}".strip()
        elif session.pending_text:
            combined = session.pending_text
        else:
            combined = cleaned

        if not combined:
            logger.warning(
                "segment.cleaned.empty session_id=%s segment_index=%s",
                session.session_id,
                session.segment_index,
            )
            return

        # Decide whether to translate now or hold for the next segment
        sentence_ended = combined[-1] in ".!?"
        force_flush = is_final or session.held_segment_count >= 2

        if not sentence_ended and not force_flush:
            session.pending_text = combined
            session.held_segment_count += 1
            logger.info(
                "segment.held session_id=%s segment_index=%s held_count=%s pending_text=%r",
                session.session_id,
                session.segment_index,
                session.held_segment_count,
                combined,
            )
            return

        # Ready to translate — reset carry-forward state
        session.pending_text = ""
        session.held_segment_count = 0

        translation = await self.providers.translate_to_hindi(combined, tone="auto")
        logger.info(
            "segment.translation session_id=%s segment_index=%s tone=%s combined_text=%r hindi=%r",
            session.session_id,
            session.segment_index,
            translation.detected_tone,
            combined,
            translation.text,
        )

        async def _synthesize() -> bytes:
            tts_result = await self.providers.synthesize_hindi(translation.text)
            await write_bytes(mp3_path, tts_result.audio_bytes)
            storage.upload_file(mp3_path, f"{segment_prefix}.mp3")
            return tts_result.audio_bytes

        session.cancelled = False
        session.active_tts_task = asyncio.create_task(_synthesize())
        try:
            audio_bytes = await session.active_tts_task
        except asyncio.CancelledError:
            logger.info("tts.cancelled session_id=%s segment_index=%s", session.session_id, session.segment_index)
            session.active_tts_task = None
            return

        if session.cancelled:
            session.active_tts_task = None
            return

        await session.websocket.send_json(
            {
                "event_type": "tts.chunk",
                "session_id": session.session_id,
                "sequence_id": payload.sequence_id if payload else session.latest_sequence_id,
                "audio_b64": base64.b64encode(audio_bytes).decode("utf-8"),
                "format": "mp3",
                "detected_tone": translation.detected_tone,
            }
        )
        logger.info(
            "segment.tts.sent session_id=%s segment_index=%s bytes=%s",
            session.session_id,
            session.segment_index,
            len(audio_bytes),
        )
        await session.websocket.send_json(
            {
                "event_type": "tts.completed",
                "session_id": session.session_id,
                "segment_index": session.segment_index,
            }
        )
        session.active_tts_task = None


    async def _flush_pending(self, session: LiveSession, payload: AudioChunkPayload | None) -> None:
        """Translate and synthesise any text held in pending_text without an audio window."""
        if not session.pending_text:
            return
        combined = session.pending_text
        session.pending_text = ""
        session.held_segment_count = 0
        segment_prefix = f"{session.session_id}/segment-{session.segment_index}-pending"
        mp3_path = self.settings.tmp_dir / f"{segment_prefix}.mp3"
        storage = self.ensure_storage()
        logger.info(
            "segment.pending.flush session_id=%s text=%r",
            session.session_id,
            combined,
        )
        translation = await self.providers.translate_to_hindi(combined, tone="auto")
        logger.info(
            "segment.translation session_id=%s segment_index=%s tone=%s combined_text=%r hindi=%r",
            session.session_id,
            session.segment_index,
            translation.detected_tone,
            combined,
            translation.text,
        )

        async def _synthesize() -> bytes:
            tts_result = await self.providers.synthesize_hindi(translation.text)
            await write_bytes(mp3_path, tts_result.audio_bytes)
            storage.upload_file(mp3_path, f"{segment_prefix}.mp3")
            return tts_result.audio_bytes

        session.cancelled = False
        session.active_tts_task = asyncio.create_task(_synthesize())
        try:
            audio_bytes = await session.active_tts_task
        except asyncio.CancelledError:
            session.active_tts_task = None
            return

        if session.cancelled:
            session.active_tts_task = None
            return

        await session.websocket.send_json(
            {
                "event_type": "tts.chunk",
                "session_id": session.session_id,
                "sequence_id": payload.sequence_id if payload else session.latest_sequence_id,
                "audio_b64": base64.b64encode(audio_bytes).decode("utf-8"),
                "format": "mp3",
                "detected_tone": translation.detected_tone,
            }
        )
        session.active_tts_task = None


registry = SessionRegistry()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("websocket.connected")
    try:
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)
            event_type = payload.get("event_type")

            if event_type == "session.start":
                parsed = SessionStartPayload.model_validate(payload)
                await registry.start_session(parsed, websocket)
                await websocket.send_json({"event_type": "session.started", "session_id": parsed.session_id})
            elif event_type == "audio.chunk":
                parsed = AudioChunkPayload.model_validate(payload)
                await registry.enqueue_chunk(parsed)
                await websocket.send_json(
                    {"event_type": "session.ack", "session_id": parsed.session_id, "sequence_id": parsed.sequence_id}
                )
            elif event_type == "playback.interrupt":
                parsed = PlaybackInterruptPayload.model_validate(payload)
                await registry.interrupt(parsed)
            elif event_type == "session.stop":
                parsed = SessionStopPayload.model_validate(payload)
                await registry.stop_session(parsed.session_id)
                await websocket.send_json({"event_type": "session.completed", "session_id": parsed.session_id})
                break
            else:
                await websocket.send_json({"event_type": "error", "code": "UNSUPPORTED_EVENT"})
    except WebSocketDisconnect:
        logger.info("websocket.disconnected")
