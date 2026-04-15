## Plan: Healthcare Agent Backend

Build a minimal but robust FastAPI conversational service around a LangChain agent created with create_agent(), backed by an OpenAI-compatible chat model configuration (Groq-compatible), an in-memory mock patient/appointment store, and strict appointment-action enforcement inside the tool layer. The endpoint remains conversational across turns via LangGraph MemorySaver with a caller-provided thread_id. Memory is scoped to a single thread only in v1; no long-lived user_id is introduced yet. The tools own the hard authorization boundary: listing, confirming, canceling, and rescheduling appointments all refuse to proceed until identity verification succeeds within that thread.

**Steps**
1. Phase 1: Establish the service skeleton. Create the FastAPI entrypoint, request/response schemas, and dependency manifest. The /chat endpoint accepts a user message and a caller-supplied thread_id and returns the assistant reply. The thread_id is the sole session identity in v1; clients must reuse it to continue a conversation. A future user_id can be layered on top later for cross-session memory.
2. Phase 1: Define the conversation state strategy. Use LangGraph MemorySaver with LangChain create_agent() so the agent can preserve collected patient details and prior actions across turns within a thread. No long-term persistence is introduced in v1.
3. Phase 2: Model the mock domain data. Add a small in-memory dataset for patients and appointments. Patient lookup is by exact match on full name, phone number, and date of birth. Each appointment exposes: ID, clinician, specialty, date/time, location, status, and a short list of predefined alternate slots used for rescheduling.
4. Phase 2: Implement the tools. Create five LangChain @tool functions: verify_patient, list_appointments, confirm_appointment, cancel_appointment, and reschedule_appointment. Each appointment tool must check verified state before doing anything and return a user-safe refusal if verification has not succeeded in that thread. Allowed status transitions: scheduled→confirmed, scheduled→canceled, confirmed→canceled, scheduled/confirmed→rescheduled. Canceled appointments are terminal. Appointment actions can be requested by ID or by ordinal reference ("the second one") against the most recent list returned in the same thread.
5. Phase 3: Build the agent orchestration. Instantiate the agent with create_agent(), the OpenAI-compatible model client, all five tools, MemorySaver, and a system prompt that: (a) instructs the assistant to progressively collect missing identity fields across multiple turns rather than demanding all at once; (b) explains to the patient why verification is required before appointment access; (c) refuses appointment operations until verification succeeds; and (d) allows natural rerouting between actions after verification. This step depends on 2 and 4.
6. Phase 3: Store verified state deterministically. Use a lightweight in-memory session registry keyed by thread_id to record successful verification. Tools read from this registry, not from the model's memory, so the authorization decision is always deterministic. This step depends on 2 and 4.
7. Phase 4: Wire the FastAPI endpoint to the agent. The endpoint passes the incoming message to the agent with the thread_id config and returns the latest assistant response. The API surface stays intentionally small in v1. This step depends on 1, 5, and 6.
8. Phase 4: Add defensive behavior. Handle: malformed or ambiguous DOB values; missing identity fields (ask only for what is still missing); unknown patients (explain mismatch, ask to retry, no lockout in v1); invalid or already-terminal appointment IDs; repeated confirm/cancel on the same appointment; reschedule flow where the assistant must show available alternate slots and wait for the patient to choose one before applying the change. This step depends on 4, 5, and 7.
9. Phase 5: Add test coverage. Cover the full target demo flow: (1) appointment action refused before verification; (2) progressive verification across turns; (3) list appointments after verification; (4) confirm one, relist; (5) reschedule another from predefined slots; (6) cancel another; (7) second thread_id starts unverified again. This step depends on 7.
10. Phase 5: Document local setup. Cover required environment variables for the OpenAI-compatible provider (Groq), how to run the FastAPI app, the /chat request/response format, thread_id semantics, and a walkthrough of the full demo scenario.

**Relevant files**
- `/Users/caio/workspace/sandbox/healthcare-agent/main.py` — FastAPI app, /chat endpoint, dependency wiring, and thread_id handoff into the agent.
- `/Users/caio/workspace/sandbox/healthcare-agent/agent.py` — create_agent() construction, system prompt, model configuration, MemorySaver setup, and invocation helper.
- `/Users/caio/workspace/sandbox/healthcare-agent/tools.py` — LangChain @tool functions: verify_patient, list_appointments, confirm_appointment, cancel_appointment, reschedule_appointment; all with strict tool-layer authorization checks.
- `/Users/caio/workspace/sandbox/healthcare-agent/mock_data.py` — mock patient and appointment records plus deterministic lookup helpers.
- `/Users/caio/workspace/sandbox/healthcare-agent/session_store.py` — recommended lightweight verification/session registry keyed by thread_id to support deterministic tool gating.
- `/Users/caio/workspace/sandbox/healthcare-agent/schemas.py` — Pydantic request/response models for the API layer.
- `/Users/caio/workspace/sandbox/healthcare-agent/pyproject.toml` — managed by uv; dependencies include FastAPI, Uvicorn, LangChain, LangGraph, langchain-openai (for Groq-compatible client), and pytest.
- `/Users/caio/workspace/sandbox/healthcare-agent/README.md` — setup, environment variables, run instructions, and example requests.
- `/Users/caio/workspace/sandbox/healthcare-agent/tests/test_chat_flow.py` — end-to-end conversation-path tests or endpoint-level tests.

**Verification**

Target demo scenario (must work end-to-end):
1. Patient opens a new thread and asks to see their appointments — assistant refuses, explains why verification is needed, and asks for missing identity fields progressively.
2. Patient provides name only — assistant acknowledges and asks for the remaining fields.
3. Patient provides phone and DOB — assistant runs verify_patient, confirms identity, and offers to help with appointments.
4. Patient asks to list appointments — assistant calls list_appointments and presents ID, clinician, specialty, date/time, location, status for each.
5. Patient confirms one appointment by ID or ordinal ("the first one") — status changes to confirmed; assistant acknowledges.
6. Patient asks to list again — updated statuses shown.
7. Patient asks to reschedule another appointment — assistant calls reschedule_appointment which returns predefined alternate slots; assistant presents the options and waits for selection; patient selects; status updates to rescheduled.
8. Patient cancels a third appointment — status changes to canceled; repeat cancel attempt is handled with a clear message.
9. Patient starts a second thread_id — all appointment actions refused again until re-verification.
10. Automated tests cover: pre-verification refusal, progressive collection, successful verification, each appointment action, ordinal reference resolution, terminal-state guard, and new-thread isolation.

**Decisions**
- Model: OpenAI-compatible client; Groq as the target provider via environment variable configuration.
- Data: mock in-memory store only; no database in v1.
- Enforcement: appointment tools enforce authorization themselves; system prompt is a guide, not the security boundary.
- Verification: progressive collection across turns; exact match on full name + phone + DOB; no retry lockout in v1.
- Reschedule: predefined alternate slots per appointment; assistant presents options and waits for patient selection.
- Action reference: tools accept appointment ID or ordinal index into the most recent list returned in the thread.
- Status transitions: scheduled→confirmed, scheduled→canceled, confirmed→canceled, scheduled/confirmed→rescheduled; canceled is terminal.
- Memory: MemorySaver for conversation history; separate session registry for verified state, both scoped to thread_id.
- Session identity: thread_id only in v1; user_id reserved for a future cross-session memory layer.
- Scope in: single /chat endpoint, mock data, progressive verification, list/confirm/cancel/reschedule, natural rerouting, tests, README.
- Scope out: database, auth tokens, frontend, streaming, multi-agent coordination, long-term memory.

**Further Considerations**
1. Ordinal reference resolution ("the second one") should be handled inside the tool by storing the last list result in the session registry alongside verified state, so the model does not need to re-pass raw appointment data on every follow-up message.
2. Verified state lives only in the session registry in v1; if explainability is needed later, the tool response can also inject a short summary into the conversation transcript.
3. Multi-agent coordination is deliberately out of scope for v1. If the exercise evaluator requires it, a thin planner/router agent can be added on top of the existing tools later without restructuring the tool layer.
4. user_id and cross-session memory are a natural next step once the single-session flow is solid. The session registry is designed to be replaced with a persistent store (e.g. Redis, DB) keyed on user_id without changing the tool signatures.
