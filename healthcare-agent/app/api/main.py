from fastapi import FastAPI, HTTPException

from app.agent.runtime import invoke_assistant
from app.api.schemas import ChatRequest, ChatResponse


app = FastAPI(title="Healthcare Conversational Agent")


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        reply = invoke_assistant(payload.thread_id, payload.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(thread_id=payload.thread_id, reply=reply)
