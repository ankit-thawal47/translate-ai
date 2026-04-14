# translate.ai POC Implementation Tasks

This checklist maps directly to `tech_approach.md`.  
Scope is POC v1 only.

## Phase 0: Project Setup

- [ ] `T0.1` Initialize backend project structure (`app/`, `tests/`, `scripts/`, `config/`).
- [ ] `T0.2` Initialize frontend project (`React + Vite + TypeScript`) with single-screen layout.
- [ ] `T0.3` Add environment config loader for: OpenAI key, Postgres URL, Redis URL, MinIO settings, `TMP_DIR`, `LOG_DIR`.
- [ ] `T0.4` Add local run scripts for backend, frontend, and dependency services.
- [ ] `T0.5` Create `./tmp` and `./logs` directory bootstrap on app startup.

Acceptance:

- [ ] Backend and frontend boot locally.
- [ ] Missing required env vars fail fast with clear error.

## Phase 1: Local Infrastructure

- [ ] `T1.1` Create local service setup for PostgreSQL, Redis, MinIO.
- [ ] `T1.2` Create MinIO bucket bootstrap on startup (idempotent).
- [ ] `T1.3` Add health endpoints for API + dependency connectivity.

Acceptance:

- [ ] Health check verifies DB, Redis, MinIO connectivity.

## Phase 2: Database Layer

- [ ] `T2.1` Create schema migration for `sessions`.
- [ ] `T2.2` Create schema migration for `segments`.
- [ ] `T2.3` Create schema migration for `segment_artifacts`.
- [ ] `T2.4` Create schema migration for `segment_stage_runs`.
- [ ] `T2.5` Create schema migration for `session_events`.
- [ ] `T2.6` Create schema migration for `protected_terms`.
- [ ] `T2.7` Add indexes: `(session_id, status)` and `(segment_id, stage_name, status)`.
- [ ] `T2.8` Seed `protected_terms` with 20-30 day-1 terms.

Acceptance:

- [ ] Migrations run cleanly on empty database.
- [ ] Seed script is idempotent.

## Phase 3: Provider Interfaces

- [ ] `T3.1` Define STT adapter interface.
- [ ] `T3.2` Define translation adapter interface.
- [ ] `T3.3` Define TTS adapter interface.
- [ ] `T3.4` Implement OpenAI STT adapter (Whisper batch mode).
- [ ] `T3.5` Implement OpenAI translation adapter.
- [ ] `T3.6` Implement OpenAI TTS adapter.

Acceptance:

- [ ] Adapters are swappable by configuration without API-layer changes.

## Phase 4: WebSocket Session Lifecycle

- [ ] `T4.1` Implement websocket event protocol for `session.start`, `audio.chunk`, `session.stop`, `playback.interrupt`.
- [ ] `T4.2` Implement outbound events: `session.started`, `session.ack`, `session.processing`, `tts.chunk`, `tts.completed`, `session.completed`, `error`.
- [ ] `T4.3` Add per-session controller task ownership model.
- [ ] `T4.4` Add sequence validation and session state transitions.

Acceptance:

- [ ] Session starts, accepts chunks, and closes cleanly on stop.
- [ ] Invalid sequence/order emits structured `error`.

## Phase 5: Audio Ingestion, Windowing, and Backpressure

- [ ] `T5.1` Implement per-session chunk ingress queue with hard cap `10`.
- [ ] `T5.2` On overflow emit `error` code `INGRESS_QUEUE_OVERFLOW` and close websocket.
- [ ] `T5.3` Capture and persist WebM session init/header from first chunk.
- [ ] `T5.4` Assemble fixed `5s` STT windows by prepending session init/header.
- [ ] `T5.5` Convert assembled window to WAV (`16k`, mono PCM) for STT.

Acceptance:

- [ ] No silent chunk drops.
- [ ] Mid-session windows decode correctly using prepended header rule.

## Phase 6: Pipeline Processing

- [ ] `T6.1` Run Whisper batch transcription per completed `5s` window.
- [ ] `T6.2` Implement transcript cleanup: filler removal, punctuation normalization.
- [ ] `T6.3` Implement protected-term preservation in cleanup/translation path.
- [ ] `T6.4` Run translation to Hindi on cleaned transcript.
- [ ] `T6.5` Run TTS on translated Hindi text and stream audio chunks to client.
- [ ] `T6.6` Use fixed tone `neutral-professional` (no tone inference call).

Acceptance:

- [ ] Raw ASR text never goes directly to TTS.
- [ ] Protected terms survive translation path correctly.

## Phase 7: Interrupt and Cancellation

- [ ] `T7.1` Implement `playback.interrupt` handling at session level.
- [ ] `T7.2` Mark active segment cancelled and stop forwarding pending TTS chunks.
- [ ] `T7.3` Cancel in-flight TTS request/task immediately.
- [ ] `T7.4` Suppress late chunks from cancelled task using cancellation checks.

Acceptance:

- [ ] Interrupt stops playback quickly and prevents stale audio emission.

## Phase 8: Persistence and Replay

- [ ] `T8.1` Persist session and segment records across all stages.
- [ ] `T8.2` Persist artifacts: raw transcript, cleaned transcript, Hindi translation, optional TTS URI.
- [ ] `T8.3` Persist per-stage runs with status, latency, attempt, errors.
- [ ] `T8.4` Persist append-only `session_events`.
- [ ] `T8.5` Implement segment-scoped replay from last successful stage.
- [ ] `T8.6` Add asyncio background retry/replay worker for failed segments.

Acceptance:

- [ ] Replay restarts from failed segment/stage, not full session.

## Phase 9: Logging and Observability

- [ ] `T9.1` Add structured logs for websocket connect/disconnect.
- [ ] `T9.2` Add structured logs for session start/stop and chunk ingest.
- [ ] `T9.3` Add stage logs for STT/cleanup/translation/TTS start/success/failure/latency.
- [ ] `T9.4` Add logs for retry, replay, cancellation, and MinIO errors.
- [ ] `T9.5` Write logs to configurable directory (default `./logs`).

Acceptance:

- [ ] A single session has traceable end-to-end logs with session and segment IDs.

## Phase 10: Frontend (Minimal UI)

- [ ] `T10.1` Build single-screen UI with only Start, Stop, and status indicator.
- [ ] `T10.2` Capture mic audio using `MediaRecorder` (`audio/webm;codecs=opus`).
- [ ] `T10.3` Stream chunks over websocket with required metadata.
- [ ] `T10.4` Play returned Hindi TTS audio stream.
- [ ] `T10.5` Handle error states and reconnect policy for POC.

Acceptance:

- [ ] UI has no transcript panel, history, waveform, or advanced controls.
- [ ] Status states shown: `idle`, `listening`, `processing`, `speaking`, `interrupted`, `completed`, `error`.

## Phase 11: Testing

- [ ] `T11.1` Unit tests for queue, window assembly, header prepend, and conversion helpers.
- [ ] `T11.2` Unit tests for cleanup and protected-term handling.
- [ ] `T11.3` Adapter-mocked integration tests for STT -> translate -> TTS pipeline.
- [ ] `T11.4` Add 3-4 deterministic golden tests with fixed fixtures/artifacts.
- [ ] `T11.5` Add one optional live OpenAI smoke test marked slow/manual.

Acceptance:

- [ ] Default test suite is deterministic and does not call live APIs.

## Phase 12: Done Criteria

- [ ] End-to-end local demo works using PostgreSQL + Redis + MinIO + OpenAI APIs.
- [ ] Segment model is fixed `5s` windowing with no silent chunk loss.
- [ ] Interrupt cancels in-flight TTS and prevents stale playback.
- [ ] Replay works at segment/stage level.
- [ ] p95 latency from segment close to Hindi audio start is measured and reported against `<= 4.0s` target.
