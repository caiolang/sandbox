# Healthcare Appointment Conversational Agent


This project uses a LangChain conversational agent to help patients manage their appointments. The key design goal is simple: **all appointment actions are blocked until identity verification succeeds**.

This behavior is not left to prompt instructions alone: the **critical policy boundary** is enforced **deterministically** in the **tool layer**, which makes the system easier to test, debug, and evolve across model changes. This is of utmost importance in an evals-first environment.

**This project includes:**
1. A FastAPI backend that exposes a single conversational endpoint (`POST /chat`) for clinic patients to manage appointments.
2. A CLI to easily interact with the backend.
3. Behavioral evals and unit tests that could run on CI.
4. Trace export to a Langfuse instance, [which can be run locally](README.md/#langfuse-tracing).

**Current limitations:**
- In-memory only (no database persistence).
- Mock data for users and appointments.
- Session/auth state is per-process and per-thread.
- No external auth token integration.
- No streaming responses.



## How to run

### Pre-requisites

#### 1️⃣ Dev environment

Be sure to have [`uv` installed](https://docs.astral.sh/uv/getting-started/installation/).

#### 2️⃣ LLM Provider

Any OpenAI-compliant LLM provider is supported. For local testing, I recommend [Groq](https://console.groq.com/) for their fast inference and generous free tiers.

Set these in environment variables or `.env`:

- `OPENAI_API_KEY` (or `GROQ_API_KEY`)
- `OPENAI_BASE_URL` (default: `https://api.groq.com/openai/v1`)
- `OPENAI_MODEL` (default: `llama-3.3-70b-versatile`)

#### 3️⃣ Observability

See [Langfuse Tracing](./README.md#langfuse-tracing).

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

Today, the test suite acts as a lightweight behavioral eval harness for the most important requirements in the prompt:

- Access is denied before verification.
- Verification can be completed progressively across multiple turns.
- A verified patient can list, confirm, cancel, and reschedule.
- The user can move naturally between actions without losing session state.
- A new thread does not inherit another user's verification state.
- Invalid transitions and bad inputs fail safely.

This is intentionally narrower than a full LLM eval program, but it covers the highest-value failure modes first. We focus on evals based on code assertions, which are [cheaper to run and to maintain](https://hamel.dev/blog/posts/evals-faq/#q-should-i-build-automated-evaluators-for-every-failure-mode-i-find).

#### How I would extend evals next

If I were taking this beyond the exercise, the next step would be to add transcript-driven evals on top of the deterministic unit tests:

- **Scenario evals:** a small corpus of multi-turn patient conversations with expected outcomes, such as whether verification was completed, whether a tool was called too early, and whether the final appointment state is correct.
- **Observability-backed review (error analysis)**, using Langfuse traces to cluster recurring failure modes and convert them into new regression cases.
- **LLM Judges** for persistent failure cases that can't be measured with a deterministic code assertion. These would need to be aligned on a dataset annotated by human domain experts.


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
File: `app/clients/chat_cli.py`

- Lightweight terminal client for interactive testing.
- Supports switching thread IDs during the same CLI session.

## End-to-end Request Flow

1. Client calls `POST /chat` with `thread_id` + user message.
2. FastAPI passes message to `invoke_assistant(...)`.
3. Agent runs with LangGraph memory (same `thread_id`), may decide to call tools.
4. Tool executes business logic and auth check against `session_store`.
5. Tool result is returned to the agent, then to API response.

## Design choices

- **Deterministic authorization** lives in session store and is used on tool calls. Prompt text additionally nudges the authorization to be done before attempting any other action, improving UX.
- **Conversation quality** (memory, phrasing, rerouting) lives in agent + model.
- **Mock-first implementation** keeps exercise scope tight while preserving realistic control flow.

## Why this stands out for an evals-focused role

I would highlight three deliberate choices in this implementation:

- **Policy enforcement is below the prompt layer.** The highest-risk requirement in the challenge is preventing appointment access before identity verification. I implemented that as deterministic tool gating, so the safety rule is stable even if the model takes an unexpected path.
  - **The core behavior is already expressed as executable checks.** The current test suite validates the contract that matters most for a conversational agent in healthcare: refusal before verification, progressive identity collection, thread isolation, allowed re-routing after verification, and invalid appointment state transitions.
- **Tracing is built in for transcript-level review.** Langfuse integration makes it straightforward to inspect failures turn by turn, which is the feedback loop you need when moving from hand-written tests to broader conversational evals.

That combination is the main architectural point I would emphasize in an interview: not just that the agent works, but that it is structured to be measurable.

This is the framing I would use for the application: the project is not only a working agent, but a small eval-friendly system where the riskiest behaviors are deterministic, observable, and easy to turn into regressions.

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