# Healthcare Conversational Agent

FastAPI backend for a conversational clinic assistant that uses LangChain `create_agent()` and tool-gated appointment actions.

## Features

- Conversational `/chat` endpoint with thread-based memory (`thread_id`)
- Progressive identity verification (full name + phone + DOB)
- Strict authorization at tool layer for:
  - listing appointments
  - confirming appointments
  - canceling appointments
  - rescheduling appointments
- Natural rerouting across actions once verified
- In-memory mock patient and appointment data

## Requirements

- Python 3.12+
- `uv`
- Model credentials (Groq/OpenAI-compatible)

## Setup

```bash
uv sync
```

Set env vars:

```bash
export OPENAI_API_KEY="your_key"    # or GROQ_API_KEY
export OPENAI_BASE_URL="https://api.groq.com/openai/v1"
export OPENAI_MODEL="llama-3.3-70b-versatile"
```

You can also put these in a local `.env` file. The app loads `.env` automatically at startup.

## Run

```bash
uv run fastapi dev main.py
```

## API

`POST /chat`

Request:

```json
{
  "thread_id": "patient-session-1",
  "message": "Hi, can you list my appointments?"
}
```

Response:

```json
{
  "thread_id": "patient-session-1",
  "reply": "Before I can access appointments..."
}
```

Use the same `thread_id` across turns so the assistant retains context in that conversation.

## Test

```bash
uv run pytest
```

The tests validate tool-layer enforcement, progressive verification, appointment status transitions, ordinal references, repeat cancel behavior, and thread isolation.

## Interactive CLI

After starting the API server, open a second terminal and run:

```bash
uv run python scripts/chat_cli.py
```

Optional flags:

```bash
uv run python scripts/chat_cli.py --endpoint http://127.0.0.1:8000/chat --thread-id demo-1
```

CLI commands:

- `/help` shows commands
- `/thread` shows current thread ID
- `/thread <id>` switches threads
- `/new` creates a fresh random thread ID
- `/exit` quits

Using `/new` or switching thread IDs is the easiest way to manually verify that a new conversation starts unverified.
