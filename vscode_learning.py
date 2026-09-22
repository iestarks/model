"""Capture VS Code model exchanges and turn them into Strands lessons."""

from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEARNING_LOG_PATH = Path(
    os.environ.get("OLLAMA_LEARNING_LOG", str(Path.home() / ".ollama" / "vscode-learning.jsonl"))
)
LESSONS_PATH = Path(
    os.environ.get("OLLAMA_LESSONS_FILE", str(Path.home() / ".ollama" / "strands-lessons.jsonl"))
)
CAPTURE_CONTENT = os.environ.get("OLLAMA_LEARNING_CAPTURE_CONTENT", "0").lower() in {
    "1",
    "true",
    "yes",
}

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="strands-learning")
_write_lock = threading.Lock()


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _response_text(body: bytes) -> str:
    parts: list[str] = []
    for line in body.splitlines():
        payload = _json_object(line)
        if isinstance(payload.get("response"), str):
            parts.append(payload["response"])
        message = payload.get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            parts.append(message["content"])
    return "".join(parts)


def build_exchange_event(
    path: str,
    request_body: bytes | None,
    response_body: bytes,
    status: int,
) -> dict[str, Any]:
    request = _json_object(request_body or b"")
    event: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "status": status,
        "model": request.get("model"),
    }
    if CAPTURE_CONTENT:
        event["input"] = request.get("messages") or request.get("prompt") or request.get("input")
        event["output"] = _response_text(response_body)
    return event


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=True) + "\n")


def _learn(event: dict[str, Any]) -> None:
    if "input" not in event or not event.get("input"):
        return
    try:
        from strands import Agent
        from strands.models.ollama import OllamaModel

        model_id = os.environ.get("STRANDS_LEARNING_MODEL") or event.get("model")
        if not model_id:
            return
        upstream = (
            f"http://{os.environ.get('OLLAMA_UPSTREAM_HOST', '127.0.0.1')}"
            f":{os.environ.get('OLLAMA_UPSTREAM_PORT', '11435')}"
        )
        agent = Agent(
            name="VSCodeLearningObserver",
            model=OllamaModel(host=upstream, model_id=model_id),
            system_prompt=(
                "You are a passive learning observer. Extract concise, reusable lessons "
                "about solving the user's task from the exchange. Do not claim facts not "
                "supported by the exchange. Return a short lesson only; never execute actions."
            ),
        )
        lesson = str(agent(json.dumps(event, ensure_ascii=True)))
        _append_jsonl(
            LESSONS_PATH,
            {"captured_at": event["captured_at"], "model": model_id, "lesson": lesson},
        )
    except Exception as error:
        _append_jsonl(
            LESSONS_PATH,
            {"captured_at": event["captured_at"], "error": str(error)},
        )


def record_exchange(
    path: str,
    request_body: bytes | None,
    response_body: bytes,
    status: int,
) -> None:
    """Record a VS Code exchange and asynchronously derive a Strands lesson."""
    event = build_exchange_event(path, request_body, response_body, status)
    _append_jsonl(LEARNING_LOG_PATH, event)
    if CAPTURE_CONTENT:
        _executor.submit(_learn, event)