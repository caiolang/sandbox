# Healthcare Appointment Conversational Agent


This project uses a LangChain conversational agent to help patients manage their appointments. The key design goal is simple: **all appointment actions are blocked until identity verification succeeds**.

This project has:
1. A FastAPI backend that exposes a single conversational endpoint (`POST /chat`) for clinic patients to manage appointments.
2. A CLI to easily interact with the backend.
3. Simple evals and unit tests that could run on CI.
4. Trace export to a Langfuse instance, [which could be run locally](README.md/#langfuse-tracing).


## How to run


### Configuration

Set these in environment variables or `.env`:

- `OPENAI_API_KEY` (or `GROQ_API_KEY`)
- `OPENAI_BASE_URL` (default: `https://api.groq.com/openai/v1`)
- `OPENAI_MODEL` (default: `llama-3.3-70b-versatile`)

Be sure to have [`uv` installed](https://docs.astral.sh/uv/getting-started/installation/).

### Backend

Run this to start the FastAPI server:

```bash
uv sync
uv run fastapi dev main.py
```

### Interactive CLI

In another terminal:

```bash
uv run python -m app.clients.chat_cli
```

Useful CLI commands:

- `/help`: Show commands
- `/thread`: Show current thread_id
- `/thread <id>`: Switch to a new thread_id
- `/new`: Generate and switch to a random thread_id
- `/exit`: Exit the chat

### Tests

```bash
uv run pytest
```



## Project Layers at a Glance

```text
app/
├── [agent] Agent Runtime (LangChain)
│    > agent/runtime.py
│
├── [api] API Layer (FastAPI + Schemas)
│    > api/main.py
│    > api/schemas.py
│
├── [clients] Client Layer (CLI)
│    > clients/chat_cli.py
│
├── [domain] Domain Layer (Mock data)
│    > domain/mock_data.py
│
├── [session] Session/Auth layer
│    > session/store.py
│
└── [tools] Tool Layer (Actions + Gating)
     > tools/appointment_tools.py


tests/
└── Testing Layer (Evals + Unit tests)
     > test_chat_flow.py

```


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

- **Deterministic authorization** lives in session store and is used on tool cals. Prompt text additionally nudges the authorization to be done before attempting any other action, improving UX.
- **Conversation quality** (memory, phrasing, rerouting) lives in agent + model.
- **Mock-first implementation** keeps exercise scope tight while preserving realistic control flow.

## Langfuse Tracing

For local debugging, I've used [Langfuse](https://langfuse.com/self-hosting/deployment/docker-compose#get-started).

The simplest way to do so is to clone the Langfuse repo somewhere, and using `docker compose`, [as shown here](https://langfuse.com/self-hosting/deployment/docker-compose#get-started).

  git clone https://github.com/langfuse/langfuse.git
  cd langfuse
  docker compose up

Then access `http://localhost:3000/`, sign up, create an org and copy the env vars. Then, add these app env vars to `healthcare-agent/.env`:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=http://localhost:3000
```

The backend initializes `langfuse.langchain.CallbackHandler` and attaches it to each agent invocation, so `/chat` requests are traced automatically.

## Current limitations (intentional for this experiment)

- In-memory only (no database persistence).
- Mock data for users and appointments.
- Session/auth state is per-process and per-thread.
- No external auth token integration.
- No streaming responses.
