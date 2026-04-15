from __future__ import annotations

import argparse
import json
import uuid
from urllib import error, request

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


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
    table = Table(title="Commands", header_style="bold cyan")
    table.add_column("Command", style="bold")
    table.add_column("Description")
    table.add_row("/help", "Show commands")
    table.add_row("/thread", "Show current thread_id")
    table.add_row("/thread <id>", "Switch to a new thread_id")
    table.add_row("/new", "Generate and switch to a random thread_id")
    table.add_row("/exit", "Exit the chat")
    console.print(table)


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

    console.print(
        Panel.fit(
            f"[bold]Healthcare Agent CLI[/bold]\n"
            f"[cyan]Endpoint:[/cyan] {endpoint}\n"
            f"[cyan]Thread:[/cyan] {thread_id}\n"
            f"[dim]Type /help for commands.[/dim]",
            border_style="blue",
            title="Session",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold yellow]Bye.[/bold yellow]")
            return 0

        if not user_input:
            continue

        if user_input == "/exit":
            console.print("[bold yellow]Bye.[/bold yellow]")
            return 0

        if user_input == "/help":
            print_help()
            continue

        if user_input == "/thread":
            console.print(f"[cyan]Current thread_id:[/cyan] [bold]{thread_id}[/bold]")
            continue

        if user_input.startswith("/thread "):
            next_thread = user_input.split(" ", 1)[1].strip()
            if not next_thread:
                console.print("[red]Please provide a thread id after /thread[/red]")
                continue
            thread_id = next_thread
            console.print(f"[green]Switched to thread_id:[/green] [bold]{thread_id}[/bold]")
            continue

        if user_input == "/new":
            thread_id = f"demo-{uuid.uuid4().hex[:8]}"
            console.print(f"[green]Switched to new thread_id:[/green] [bold]{thread_id}[/bold]")
            continue

        try:
            data = post_chat(endpoint=endpoint, thread_id=thread_id, message=user_input)
            reply = data.get("reply", "(no reply field in response)")
            console.print(
                Panel(
                    reply,
                    title="[bold magenta]Assistant[/bold magenta]",
                    border_style="magenta",
                )
            )
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            console.print(
                Panel(
                    f"HTTP {exc.code}: {body}",
                    title="[bold red]HTTP Error[/bold red]",
                    border_style="red",
                )
            )
        except error.URLError as exc:
            console.print(
                Panel(
                    f"Connection error: {exc.reason}\n"
                    "Make sure the FastAPI server is running and endpoint is correct.",
                    title="[bold red]Connection Error[/bold red]",
                    border_style="red",
                )
            )
        except json.JSONDecodeError:
            console.print("[red]Received a non-JSON response from server.[/red]")


if __name__ == "__main__":
    raise SystemExit(main())
