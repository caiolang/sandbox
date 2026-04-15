from __future__ import annotations

import argparse
import json
import uuid
from urllib import error, request


def post_chat(endpoint: str, thread_id: str, message: str) -> dict:
    payload = json.dumps({"thread_id": thread_id, "message": message}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def print_help() -> None:
    print("Commands:")
    print("  /help                 Show commands")
    print("  /thread               Show current thread_id")
    print("  /thread <id>          Switch to a new thread_id")
    print("  /new                  Generate and switch to a random thread_id")
    print("  /exit                 Exit the chat")


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive CLI for Healthcare Agent /chat endpoint")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8000/chat",
        help="Chat endpoint URL",
    )
    parser.add_argument(
        "--thread-id",
        default="demo-cli-1",
        help="Initial thread_id to use",
    )
    args = parser.parse_args()

    endpoint = args.endpoint
    thread_id = args.thread_id

    print("Healthcare Agent CLI")
    print(f"Endpoint: {endpoint}")
    print(f"Thread:   {thread_id}")
    print("Type /help for commands.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not user_input:
            continue

        if user_input == "/exit":
            print("Bye.")
            return 0

        if user_input == "/help":
            print_help()
            continue

        if user_input == "/thread":
            print(f"Current thread_id: {thread_id}")
            continue

        if user_input.startswith("/thread "):
            next_thread = user_input.split(" ", 1)[1].strip()
            if not next_thread:
                print("Please provide a thread id after /thread")
                continue
            thread_id = next_thread
            print(f"Switched to thread_id: {thread_id}")
            continue

        if user_input == "/new":
            thread_id = f"demo-{uuid.uuid4().hex[:8]}"
            print(f"Switched to new thread_id: {thread_id}")
            continue

        try:
            data = post_chat(endpoint=endpoint, thread_id=thread_id, message=user_input)
            reply = data.get("reply", "(no reply field in response)")
            print(f"Assistant: {reply}\n")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP {exc.code}: {body}\n")
        except error.URLError as exc:
            print(f"Connection error: {exc.reason}")
            print("Make sure the FastAPI server is running and endpoint is correct.\n")
        except json.JSONDecodeError:
            print("Received a non-JSON response from server.\n")


if __name__ == "__main__":
    raise SystemExit(main())
