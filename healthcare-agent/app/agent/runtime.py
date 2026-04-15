from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

from app.session.store import bind_thread
from app.tools.appointment_tools import ALL_TOOLS

load_dotenv()
try:
    from langfuse.langchain import CallbackHandler

    langfuse_handler = CallbackHandler()
except Exception:
    langfuse_handler = None


SYSTEM_PROMPT = """You are a clinic virtual assistant.

Rules:
1. Before using any appointment management action, verify identity with full name, phone number, and date of birth.
2. Collect missing identity details progressively over multiple turns. Do not ask for fields already provided.
3. Explain briefly why verification is required before accessing appointments.
4. After successful verification, help with listing, confirming, canceling, and rescheduling appointments.
5. Allow natural routing and re-routing between tasks in any order once verified.
6. Keep responses concise, clear, and patient-friendly.
"""


def _build_model() -> ChatOpenAI:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing OPENAI_API_KEY (or GROQ_API_KEY). "
            "Set it to call the model for /chat."
        )

    model_name = os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")
    return ChatOpenAI(model=model_name, api_key=api_key, base_url=base_url, temperature=0)


checkpointer = MemorySaver()
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=_build_model(),
            tools=ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
        )
    return _agent


def _message_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    return str(content)


def _build_invoke_config(thread_id: str) -> dict[str, Any]:
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 10,
        "metadata": {"thread_id": thread_id},
    }

    if langfuse_handler is not None:
        config["callbacks"] = [langfuse_handler]
        config["metadata"]["langfuse_session_id"] = thread_id

    return config


def invoke_assistant(thread_id: str, user_message: str) -> str:
    config = _build_invoke_config(thread_id)
    with bind_thread(thread_id):
        result = _get_agent().invoke(
            {"messages": [{"role": "user", "content": user_message}]},
            config=config,
        )

    messages = result.get("messages", [])
    if not messages:
        return "I wasn't able to produce a response. Please try again."
    return _message_to_text(messages[-1].content)


def get_graph():
    return _get_agent()
