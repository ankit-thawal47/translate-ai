# Technical Approach (POC Build Spec)

## Purpose

This document is the engineer-facing technical handoff for the real-time English-to-Hindi voice translation system.

It defines the expected stack, system boundaries, data ownership, runtime behavior, storage model, and implementation defaults so the system can be built without needing follow-up clarification on core architecture.

## Problem Shape

We are building a real-time voice-to-voice pipeline where:

- the user explicitly starts and stops recording from the UI
- audio streams from the client to the backend over WebSockets
- spoken English is processed into Hindi speech in near real time
- the end user does not see transcript text in the UI
- the end user hears Hindi audio as the main product output

Even though transcript text is not shown to the user, intermediate text still matters internally for debugging, observability, quality control, and replay.

## Decisions Already Made

### 1. Backend Stack Direction

Approved stack:

- Python
- FastAPI
- WebSockets
- Pydantic
- PostgreSQL
- Redis
- Object storage for canonical audio
- OpenAI APIs for STT, translation, and TTS in the POC
- asyncio background tasks for retry/replay in POC v1

### 2. Session Control

We are not using VAD as the primary control mechanism.

The UI will provide explicit:

- `Start`
- `Stop`

That means recording boundaries are user-driven, not speech-detection-driven.

### 3. User Experience Direction

The UI is audio-first.

The user will not be shown:

- raw transcript
- cleaned transcript
- Hindi translation text

The user-facing output is Hindi audio playback.

### 4. Internal Text Artifacts

Even though transcripts are hidden from the UI, the system should still keep internal stage outputs for:

- debugging
- observability
- quality review
- replay and retries
- failure analysis

Important internal artifacts:

- raw ASR transcript
- cleaned English transcript
- Hindi translation text before TTS

### 5. Output Quality Requirement

The final response must not behave like raw speech text.

Internally, before generating TTS, the system should ensure:

- fillers such as `umm`, `uh`, and `ahh` are removed unless meaningful
- punctuation is corrected
- sentence structure is cleaned
- named entities are preserved correctly
- numbers, dates, abbreviations, and times are normalized appropriately
- tone is recognized and respected

### 6. Storage Direction

Local `/tmp` should not be the source of truth for long-running or replayable audio.

The recommended direction is:

- local `/tmp` for transient processing
- durable blob/object storage for canonical raw audio
- Redis for transient coordination
- PostgreSQL as the durable metadata store

### 7. Logging Direction

Application logs should be stored under a dedicated `/logs` directory.

We should add log statements wherever necessary in the code so that:

- session lifecycle can be traced
- websocket activity can be diagnosed
- stage failures are visible
- retries and replay behavior are observable
- latency issues can be investigated

Logging should be treated as part of the implementation standard, not as an afterthought.

## Core Technical Position

This system should be designed as an audio-first product with text-backed internals.

That means:

- audio is the product output
- text is the control and quality layer behind the scenes
- storage and replay should be designed around resilience, not just streaming speed
- latency target from segment close to Hindi audio start: `<= 4.0s` p95

## Why This Matters

Because the product does not expose transcript text to the user, audio quality and correctness become more important.

If the system speaks broken or awkward Hindi, the user has no textual fallback to understand what happened.

So the technical design should favor:

- stable and natural TTS input
- careful cleanup before speech output
- controlled chunking
- strong replay and debugging support

## Technical Response To Key Challenges

### 1. Accents And Fast Speech

- use fixed 5-second STT windows with Whisper batch transcription
- treat each transcription result as a stable segment
- do not emit TTS for empty or clearly corrupted STT results

### 2. Named Entities

- do not depend only on a manual glossary
- use entity-preservation rules, acronym heuristics, and lightweight term detection
- protect detected entities before translation

### 3. Partial Inputs

- translate only completed 5-second STT windows
- do not translate raw websocket micro-chunks directly

### 4. Fillers And Disfluencies

- add a cleanup layer between ASR and translation
- remove low-value fillers such as `uh`, `umm`, and `you know`

### 5. Latency Buildup

- keep the live websocket path lean
- avoid unnecessary queue hops in the hot path
- add per-stage latency logging and bounded segment processing

### 6. Tone Drift

- use a session-level default tone with segment-level refinement
- pass tone explicitly into translation

### 7. Numbers, Dates, Abbreviations

- normalize structured tokens before translation
- use deterministic handling for time, date, number, duration, and acronym forms

### 8. Overlap And Interruptions

- maintain cancellable playback state
- stop or drop stale pending TTS when fresh input makes it outdated

## Implementation Defaults

These defaults should be used unless a later decision explicitly replaces them.

### 1. Primary Database

- `PostgreSQL` is the primary durable database
- store sessions, segments, stage state, transcript artifacts, translation artifacts, errors, and storage references here

### 2. Audio Storage

- canonical raw audio must be stored in object storage
- local temp storage is for active processing only
- raw audio should be written in segmentable form so failed stages can be replayed without rerunning the full session

### 3. Temp Storage

- use a project-local temp directory such as `./tmp` in development
- use per-session temp subdirectories
- temp files must be safe to delete after upload or stage completion

### 4. Logs

- store logs under `./logs` in development
- make the log directory configurable for deployment
- add log statements in websocket lifecycle, session lifecycle, storage, STT, cleanup, translation, TTS, retries, and failures

### 5. Segment Model

- process audio as bounded segments rather than one unbroken session blob
- use fixed `5s` windows in POC v1
- translation and TTS should operate on completed windows, not raw micro-chunks

### 6. Tone Model

- use `neutral-professional` as the default tone
- allow segment-level refinement, but keep tone sticky across the session

### 7. Runtime Split

- websocket ingestion and live orchestration stay in the FastAPI app path
- use in-process asyncio tasks for replay/retries in POC v1
- do not introduce Celery in POC v1

### 8. POC Deployment Mode

- the POC must run locally
- the architecture should still be production-shaped and horizontally extensible
- local runtime may use local PostgreSQL, local Redis, local `./tmp`, local `./logs`, and optionally local object storage emulation or a configured remote bucket
- external STT, translation, and TTS calls should use OpenAI API keys for now

## System Components

### 1. FastAPI App

Responsibilities:

- websocket connection management
- session start and stop handling
- audio frame ingestion
- live session state coordination
- dispatch to downstream processing
- client-facing status and error signaling

### 2. STT Layer

Responsibilities:

- consume streamed audio segments
- produce raw transcript output
- output one transcript result per completed STT window

### 3. Cleanup And Normalization Layer

Responsibilities:

- remove fillers and disfluencies
- normalize punctuation and sentence boundaries
- preserve entities, acronyms, and technical terms
- normalize numbers, dates, times, durations, and abbreviations
- produce cleaned transcript text for downstream use

### 4. Translation Layer

Responsibilities:

- translate cleaned English transcript into natural Hindi
- preserve protected entities
- apply tone policy
- produce Hindi text suitable for speech, not just display

### 5. TTS Layer

Responsibilities:

- synthesize Hindi speech from translated text for completed STT windows
- return audio suitable for immediate playback
- support cancellation of pending playback units

### 6. Persistence Layer

Responsibilities:

- persist session metadata in PostgreSQL
- persist canonical audio in object storage
- persist transient coordination state in Redis
- persist retryable job state and errors

## Directory Conventions

- `./tmp` for transient audio chunks and worker-local processing files
- `./logs` for application logs in development
- both paths should be configurable by environment variables

## Provider Defaults For POC

- STT: OpenAI speech-to-text API
- Translation: OpenAI text model
- TTS: OpenAI text-to-speech API

Provider integrations must be abstracted behind service interfaces from the first implementation so they can be replaced later without changing websocket, persistence, or orchestration code.

## WebSocket Contract

Use a message-oriented protocol with explicit event types.

Minimum inbound events:

- `session.start`
- `audio.chunk`
- `session.stop`
- `playback.interrupt`

Minimum outbound events:

- `session.started`
- `session.ack`
- `session.processing`
- `tts.chunk`
- `tts.completed`
- `session.completed`
- `error`

Each event should include:

- `session_id`
- `sequence_id`
- `timestamp`
- `event_type`

`audio.chunk` should also include:

- audio payload
- audio format metadata
- chunk duration or frame count

Audio format defaults for POC:

- client capture format: `audio/webm;codecs=opus` via `MediaRecorder`
- STT handoff format: `wav` (`pcm_s16le`, `16k`, mono) after backend conversion
- TTS output format: `mp3` by default

WebM container rule:

- cache and persist the session init/header bytes from the first WebM chunk
- every assembled STT window must prepend session init/header bytes before decode/convert
- never transcode mid-session chunk slices as standalone files without init/header

Interrupt signal path:

- client sends `playback.interrupt`
- backend marks active playback segments cancelled
- backend cancels in-flight TTS task/request for the active segment
- backend suppresses late chunks from cancelled tasks using session/segment cancellation checks

Backpressure policy:

- per-session ingress queue cap: `10` chunks
- on overflow: emit `error` with `code=INGRESS_QUEUE_OVERFLOW` and close websocket
- do not silently drop old or new chunks

## Processing Flow

1. Client sends `session.start`.
2. Backend creates session state and storage context.
3. Client streams `audio.chunk` messages over websocket.
4. Backend appends audio to temp storage and uploads canonical audio segments to object storage.
5. Backend assembles fixed STT windows from chunk stream, prepending the session WebM init/header for each window.
6. Backend converts assembled window to WAV (`16k` mono PCM) for Whisper batch transcription.
7. Backend runs STT on bounded segments.
8. Backend cleans and normalizes transcript output.
9. Backend translates completed-window transcript segments into Hindi.
10. Backend sends finalized Hindi text to TTS.
11. Backend streams Hindi audio chunks back to the client.
12. Client sends `session.stop`.
13. Backend flushes remaining segments, completes pending work, and closes the session cleanly.

## Data Ownership

- `PostgreSQL`: sessions, segments, stage states, artifacts, errors, metrics references
- `Redis`: transient locks, active session state, broker responsibilities, short-lived coordination
- `Object storage`: canonical raw audio and optional retained output artifacts
- `./tmp`: non-canonical working files only

## Database Schema Outline

The database should be normalized enough for traceability and replay, but not overdesigned for the POC.

### 1. `sessions`

Purpose:

- one row per recording session

Suggested fields:

- `id`
- `client_session_id`
- `status`
- `source_language`
- `target_language`
- `default_tone`
- `started_at`
- `stopped_at`
- `completed_at`
- `last_sequence_id`
- `raw_audio_storage_uri`
- `metadata_json`
- `created_at`
- `updated_at`

### 2. `segments`

Purpose:

- ordered processing units within a session

Suggested fields:

- `id`
- `session_id`
- `segment_index`
- `sequence_start`
- `sequence_end`
- `audio_start_ms`
- `audio_end_ms`
- `status`
- `processing_state`
- `audio_storage_uri`
- `created_at`
- `updated_at`

### 3. `segment_artifacts`

Purpose:

- store stage outputs and references per segment

Suggested fields:

- `id`
- `session_id`
- `segment_id`
- `artifact_type`
- `artifact_text`
- `artifact_storage_uri`
- `model_name`
- `tone`
- `version`
- `created_at`

Expected `artifact_type` values:

- `raw_transcript`
- `cleaned_transcript`
- `translation_hi`
- `tts_audio`

### 4. `segment_stage_runs`

Purpose:

- stage-level execution, status, latency, and retry tracking

Suggested fields:

- `id`
- `session_id`
- `segment_id`
- `stage_name`
- `provider_name`
- `status`
- `attempt_number`
- `started_at`
- `completed_at`
- `latency_ms`
- `error_code`
- `error_message`
- `input_ref`
- `output_ref`
- `created_at`

Expected `stage_name` values:

- `audio_persist`
- `stt`
- `cleanup`
- `translation`
- `tts`
- `playback`

### 5. `session_events`

Purpose:

- append-only audit/debug timeline for major lifecycle events

Suggested fields:

- `id`
- `session_id`
- `segment_id`
- `event_type`
- `sequence_id`
- `payload_json`
- `created_at`

### 6. `protected_terms`

Purpose:

- optional seed data for term handling without requiring a full glossary strategy

Suggested fields:

- `id`
- `term`
- `term_type`
- `preserve_as_is`
- `target_rendering`
- `notes`
- `is_active`
- `created_at`
- `updated_at`

This table is required in POC v1 with a seeded list of 20-30 terms (brands, acronyms, and common technical entities).

## Database Design Rules

- use UUID primary keys
- index `session_id`, `segment_id`, `segment_index`, `stage_name`, and `status`
- add compound index `(session_id, status)`
- add compound index `(segment_id, stage_name, status)`
- keep `session_events` append-only
- do not store large binary audio blobs in PostgreSQL
- store blob URIs in PostgreSQL and keep audio in object storage
- keep artifacts versionable so regeneration does not overwrite prior outputs silently

## Persistence Requirements

Persist enough state to replay from the last successful stage.

Minimum persisted records:

- session record
- segment records with ordering and timestamps
- raw transcript artifact
- cleaned transcript artifact
- Hindi translation artifact
- TTS artifact reference if retained
- per-stage status and error metadata

## Failure And Retry Rules

- retries must be segment-scoped where possible
- replay should restart from the last successful stage, not always from raw session start
- stale pending TTS should be dropped if the conversation has advanced
- failed segments must record enough context for postmortem debugging

## Fixed Build Decisions

These decisions are fixed for the POC implementation and should not be treated as open.

### 1. Provider Strategy

- implement provider interfaces from day one
- wire only OpenAI-backed providers in the POC
- keep STT, translation, and TTS clients isolated behind adapters

### 2. Audio Retention

- canonical raw audio is stored in object storage
- successful-session raw audio retention default: `7 days`
- failed-session raw audio retention default: `14 days`
- local temp files should be deleted after upload and stage completion
- orphaned temp files older than `24 hours` should be cleaned automatically

### 3. Segment Finalization

- use fixed `5s` STT windows in POC v1
- finalize each segment at window close and process sequentially
- do not add transcript-stability heuristics in POC v1

### 4. Replay Boundary

- replay is segment-scoped
- replay restarts from the last successful stage for the failed segment
- do not rerun the full session unless session metadata or canonical audio is corrupted

### 5. Tone Handling

- do not run a separate tone-inference call in POC v1
- use fixed session default tone: `neutral-professional`
- tone remains internal for the POC and is not required in the UI

### 6. UI Scope

- show only start/stop and status states in the POC
- required states: `idle`, `listening`, `processing`, `speaking`, `interrupted`, `completed`, `error`
- do not show transcripts or translated text to the end user
- do not add history, waveform visualization, advanced settings, or analytics panels in POC v1
- keep a single-screen flow with minimal controls and clear state indication

## Logging Requirements

Add structured log statements at minimum for:

- websocket connect and disconnect
- session start and stop
- chunk receive and chunk persist
- STT start, success, latency, failure
- cleanup/normalization start and failure
- translation start, success, latency, failure
- TTS start, success, latency, failure
- retry, replay, and cancellation events
- object storage upload/download failures

## Testing Strategy

- default automated tests must mock provider adapters (STT, translation, TTS) at interface boundaries
- include 3-4 deterministic golden pipeline tests over fixed audio fixtures and expected stage artifacts
- keep one optional live smoke test for OpenAI providers marked as slow/manual
- do not run live API calls in default CI test suites

## Local-First But Scalable Runtime

- the POC must run on a single local machine
- the code structure must still separate API, orchestration, persistence, and provider clients
- use environment-based configuration for storage paths, Redis, PostgreSQL, and provider keys
- do not hardcode local-only assumptions into the service boundaries
- keep object storage behind an adapter so local emulation and cloud buckets both work

## Quality Rules

- raw ASR output must never go directly to TTS
- remove low-value fillers before translation
- preserve named entities and acronyms through translation
- normalize punctuation and structured tokens before TTS
- use fixed neutral-professional tone in POC v1

## Local Dev Runbook

Required local services:

- PostgreSQL
- Redis
- MinIO (S3-compatible object storage)

Required environment configuration:

- OpenAI API key for STT, translation, and TTS
- PostgreSQL connection URL
- Redis connection URL
- MinIO endpoint, access key, secret key, and bucket
- local paths for `./tmp` and `./logs`

## UI Minimum States

- idle
- listening
- processing
- speaking
- interrupted
- completed
- error

## Remaining Decisions Still Open

Only these items remain open for later refinement. They should not block the first implementation.

- exact OpenAI model choices for STT, translation, and TTS
- whether to retain generated TTS audio artifacts beyond debugging needs
- whether a future UI version should surface internal tone classification

## Working Architecture Principles

These are the current principles that should guide future design decisions:

- Explicit session start/stop is the recording control model
- WebSockets are the audio transport mechanism
- The user experience is audio-first, not transcript-first
- Internal text stages are still required even if hidden from the UI
- Raw transcript must never be treated as final speech output
- Cleanup and normalization are mandatory before TTS
- Local disk is temporary working storage, not durable truth
- Replayability matters because long sessions can fail mid-pipeline
- Logs should be written consistently so runtime behavior can be traced and debugged

## Practical Implication

The system should be treated as two parallel layers:

### Product Layer

- stream user audio in
- generate Hindi speech out
- keep the UI simple

### Reliability Layer

- store audio durably
- checkpoint intermediate stages
- preserve internal text artifacts
- support retries and replay
- expose enough telemetry to debug failures

## Engineer Execution Summary

Build the POC as a local-first, production-shaped system using FastAPI, WebSockets, PostgreSQL, Redis, asyncio background tasks, object storage, and OpenAI provider adapters.

Treat audio as the primary user output, text as an internal control layer, object storage as the canonical audio store, PostgreSQL as the source of truth for metadata, Redis as transient coordination, and `./tmp` plus `./logs` as local runtime directories.

Implement the pipeline with fixed 5-second STT windows, segment-scoped persistence, replay-from-last-successful-stage behavior, transcript cleanup before translation, translated text to TTS, and structured logging across every stage.

## Junior Engineer Build Order

Implement in this exact order:

1. Build websocket session lifecycle: `session.start`, `audio.chunk`, `session.stop`, `playback.interrupt`.
2. Implement ingestion queue with cap `10`; on overflow emit `INGRESS_QUEUE_OVERFLOW` and close connection.
3. Implement WebM window assembly with session header prepended to each 5-second window.
4. Add Whisper batch transcription for each completed window after WAV conversion.
5. Add cleanup + protected term handling + translation.
6. Add TTS generation and playback chunk streaming with in-flight cancellation on interrupt.
7. Persist sessions/segments/artifacts/stage-runs and add structured logs for all stages.
8. Add adapter-mocked tests first, then one optional slow live smoke test.
