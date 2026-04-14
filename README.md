# BridgeAI POC

BridgeAI is a local-first POC for audio-first English-to-Hindi voice translation.

The current repo includes:

- a FastAPI backend with websocket ingestion
- a minimal React/Vite frontend
- local infrastructure config for PostgreSQL, Redis, and MinIO
- OpenAI-backed STT, translation, and TTS provider adapters

## Prerequisites

Install these locally:

- `Python 3.12+`
- `uv`
- `Node.js 22+`
- `npm`
- `Docker`
- `ffmpeg`

## Environment Setup

Create a local env file from the example:

```bash
cp .env.example .env
```

Set at minimum:

- `OPENAI_API_KEY`

The local defaults for PostgreSQL, Redis, MinIO, temp, and logs already match the included Docker setup.

## Start Local Dependencies

Run PostgreSQL, Redis, and MinIO:

```bash
docker compose -f infra/docker-compose.yml up -d
```

MinIO console will be available at:

- `http://localhost:9001`

Default MinIO credentials:

- user: `minioadmin`
- password: `minioadmin`

## Start The Backend

Install Python dependencies:

```bash
uv sync
```

Run the API server:

```bash
./scripts/run_backend.sh
```

The backend will start on:

- `http://localhost:8000`

Health check:

```bash
curl http://localhost:8000/health
```

## Start The Frontend

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

Run the frontend:

```bash
./scripts/run_frontend.sh
```

The frontend will start on:

- `http://localhost:5173`

## How To Use

1. Open `http://localhost:5173`
2. Click `Start`
3. Speak in English
4. Wait for Hindi audio playback
5. Click `Stop` to end the session
6. Click `Interrupt` if you want to cancel in-flight playback

## Run Tests

Backend tests:

```bash
uv run pytest
```

Frontend production build check:

```bash
cd frontend
npm run build
cd ..
```

## Current POC Limitations

- DB models exist, but full persistence wiring is not complete yet
- Alembic migrations are not added yet
- Health endpoint is basic and does not yet verify dependency reachability
- Live OpenAI audio flow depends on valid API credentials and running local services
- The UI is intentionally minimal and does not show transcript or translated text

## Important Files

- [tech_approach.md](/Users/ankit/personal-workspace/bridgeAI/tech_approach.md)
- [tasks.md](/Users/ankit/personal-workspace/bridgeAI/tasks.md)
- [idea.md](/Users/ankit/personal-workspace/bridgeAI/idea.md)
