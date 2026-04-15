# Healthcare Appointment Conversational Agent

A FastAPI backend that exposes a single conversational endpoint (`POST /chat`) for clinic patients to manage appointments.

The key design goal is simple: **all appointment actions are blocked until identity verification succeeds**.

## What this service does

- Verifies a patient progressively with 3 fields: full name, phone number, date of birth.
- After verification, allows conversational appointment actions:
  - list
  - confirm
  - cancel
  - reschedule
- Supports natural re-routing (for example: list -> confirm -> list -> reschedule).
- Maintains conversation continuity per `thread_id`.

## Core Bricks (Architecture)

### 1) API Layer (FastAPI)
Files: `app/api/main.py`, `main.py`

- Exposes `POST /chat`.
- Accepts `{ thread_id, message }`.
- Delegates to the agent runtime and returns `{ thread_id, reply }`.

### 2) Agent Runtime (LangChain create_agent)
File: `app/agent/runtime.py`

- Uses `create_agent()` with:
  - a chat model (OpenAI-compatible, Groq-ready)
  - tool set from `app/tools/appointment_tools.py`
  - In-mem `MemorySaver` checkpointer for per-thread conversational memory
- Loads env variables from `.env` using `python-dotenv`.
- Invokes agent with `thread_id` and a recursion limit.

### 3) Authorization Session Store (Deterministic gate)
File: `app/session/store.py`

- In-memory registry keyed by `thread_id`.
- Stores verification and context fields:
  - `verified_patient_id`
  - collected identity fields
  - last listed appointment IDs (used for ordinal references like "the second one")
- This store is the **source of truth for auth checks**.

### 4) Domain Data (Mock records)
File: `app/domain/mock_data.py`

- In-memory patients and appointments.
- Identity normalization helpers:
  - name normalization
  - phone normalization
  - DOB parsing (`YYYY-MM-DD`, `MM/DD/YYYY`, etc.)
- Appointment reset helper for tests.

### 5) Tool Layer (Business rules + hard gating)
File: `app/tools/appointment_tools.py`

Tools exposed to the agent:

- `verify_patient`
- `list_appointments`
- `confirm_appointment`
- `cancel_appointment`
- `reschedule_appointment`

Important behavior:

- `list/confirm/cancel/reschedule` all call a verification guard first.
- Confirm/cancel/reschedule can resolve appointment by:
  - explicit ID (`APT-1001`)
  - ordinal reference (`first`, `second`, `3`, etc.) from the latest listed appointments.
- Handles invalid references and terminal status behavior (for example, canceled cannot be reconfirmed).

### 6) Contracts and Testing
Files: `app/api/schemas.py`, `tests/test_chat_flow.py`

- `schemas.py` defines request/response models.
- Tests verify key flow:
  - action refusal before verification
  - progressive verification across turns
  - list/confirm/reschedule/cancel transitions
  - repeated cancel messaging
  - thread isolation (new thread starts unverified)

### 7) Manual Interaction Client
Files: `app/clients/chat_cli.py`, `scripts/chat_cli.py`

- Lightweight terminal client for interactive testing.
- Supports switching thread IDs during the same CLI session.

## End-to-end Request Flow

1. Client calls `POST /chat` with `thread_id` + user message.
2. FastAPI passes message to `invoke_assistant(...)`.
3. Agent runs with LangGraph memory (same `thread_id`), may decide to call tools.
4. Tool executes business logic and auth check against `session_store`.
5. Tool result is returned to the agent, then to API response.

## Design choices (why this shape)

- **Deterministic authorization** lives in tools/session store, not in prompt text.
- **Conversation quality** (memory, phrasing, rerouting) lives in agent + model.
- **Mock-first implementation** keeps exercise scope tight while preserving realistic control flow.

## Configuration

Set these in environment variables or `.env`:

- `OPENAI_API_KEY` (or `GROQ_API_KEY`)
- `OPENAI_BASE_URL` (default: `https://api.groq.com/openai/v1`)
- `OPENAI_MODEL` (default: `llama-3.3-70b-versatile`)

## Run

```bash
uv sync
uv run fastapi dev main.py
```

## Interactive CLI

In another terminal:

```bash
uv run python scripts/chat_cli.py
```

Useful commands:

- `/help`
- `/thread`
- `/thread <id>`
- `/new`
- `/exit`

## Tests

```bash
uv run pytest
```

## LangSmith Studio (Local Dev UI)

This repo includes `langgraph.json` configured for Studio and local Agent Server.

1. Add to `.env`:

```bash
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=healthcare-agent-local
LANGSMITH_TRACING=true
```

If you want Studio without sending traces to LangSmith, set:

```bash
LANGSMITH_TRACING=false
```

2. Install/update deps:

```bash
uv sync
```

3. Run local Agent Server:

```bash
uv run langgraph dev
```

4. Open Studio:

`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`

## Local Langfuse (Docker Compose)

This repo includes a reproducible local Langfuse stack:

- Compose file: `infra/langfuse/docker-compose.yml`
- Env template: `infra/langfuse/.env.example`

1. Prepare Langfuse infra env:

```bash
cp infra/langfuse/.env.example infra/langfuse/.env
```

Then replace all placeholder secrets in `infra/langfuse/.env`.

2. Start local Langfuse:

```bash
docker compose --env-file infra/langfuse/.env -f infra/langfuse/docker-compose.yml up -d
```

3. Open UI:

`http://localhost:3000`

4. Create a Langfuse project and copy keys, then add these to your app `.env`:

```bash
LANGFUSE_BASE_URL=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

5. Start FastAPI app and chat as usual:

```bash
uv run fastapi dev main.py
uv run python scripts/chat_cli.py
```

When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, `/chat` requests are traced to Langfuse automatically.

## Current limitations (intentional for v1)

- In-memory only (no database persistence).
- Session/auth state is per-process and per-thread.
- No external auth token integration.
- No streaming responses.
