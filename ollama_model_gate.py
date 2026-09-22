"""Serialize local Ollama model selection for Strands agents."""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import ollama


TOKEN_PATH = Path.home() / ".ollama" / "proxy-token"


def proxy_headers() -> dict[str, str]:
    """Return the local proxy authorization header when configured."""
    if TOKEN_PATH.exists():
        return {"Authorization": f"Bearer {TOKEN_PATH.read_text().strip()}"}
    return {}


MODEL_PREFERENCES = {
    "fast": ("qwen2.5-coder:1.5b", "llama3:latest"),
    "coding": ("qwen3-coder:30b", "qwen2.5-coder:1.5b", "llama3:latest"),
    "high_token": ("qwen3.6:27b", "qwen3.8:latest", "llama3.1:8b", "llama3:latest"),
}

MODEL_PROFILES = {
    "qwen2.5-coder:1.5b": {"size": "small", "speed": 5, "quality": 2, "role": "fast coding"},
    "llama2:latest": {"size": "medium", "speed": 4, "quality": 2, "role": "general chat"},
    "llama3.1:8b": {"size": "medium", "speed": 3, "quality": 3, "role": "general chat"},
    "llama3:latest": {"size": "medium", "speed": 3, "quality": 3, "role": "general chat"},
    "nomic-embed-text:latest": {"size": "small", "speed": 5, "quality": 1, "role": "embeddings only"},
    "qwen3-coder:30b": {"size": "large", "speed": 2, "quality": 5, "role": "advanced coding"},
    "qwen3.6:27b": {"size": "large", "speed": 2, "quality": 5, "role": "deep reasoning"},
    "qwen3.8:latest": {"size": "large", "speed": 1, "quality": 5, "role": "deep reasoning"},
}


class OllamaModelGate:
    """Coordinate model selection across local agent processes."""

    def __init__(self, client: Any | None = None, lock_path: Path | None = None):
        self.client = client or ollama.Client(
            host="http://127.0.0.1:11434",
            headers=proxy_headers(),
        )
        self.lock_path = lock_path or Path.home() / ".ollama" / "agent-model-selection.lock"
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _selection_lock(self) -> Iterator[None]:
        with self.lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def installed_models(self) -> list[str]:
        return sorted(model.model for model in self.client.list().models)

    def loaded_models(self) -> list[str]:
        return sorted(model.name for model in self.client.ps().models)

    def status(self) -> dict[str, Any]:
        loaded = self.loaded_models()
        return {
            "loaded_models": loaded,
            "installed_models": self.installed_models(),
            "max_loaded_models": int(os.environ.get("OLLAMA_MAX_LOADED_MODELS", "1")),
        }

    def profile(self, model_name: str) -> dict[str, Any]:
        """Return estimated speed, quality, and intended role for a model."""
        return MODEL_PROFILES.get(
            model_name,
                {"size": "medium", "speed": 3, "quality": 3, "role": "general purpose"},
        )

    def route_model(self, task: str, preferred_model: str | None = None) -> tuple[str, str]:
        """Choose a locally installed model tier for a task."""
        installed = set(self.installed_models())
        if preferred_model and preferred_model in installed:
            return preferred_model, "explicit model selection"

        task_lower = task.lower()
        is_coding = any(
            marker in task_lower
            for marker in ("code", "python", "typescript", "bug", "test", "refactor", "debug")
        )
        is_high_token = len(task.split()) >= 1200 or any(
            marker in task_lower
            for marker in ("long context", "high token", "deep analysis", "architecture", "thorough")
        )
        tier = "high_token" if is_high_token else "coding" if is_coding else "fast"
        for candidate in MODEL_PREFERENCES[tier]:
            if candidate in installed:
                return candidate, tier
        raise RuntimeError(f"No installed Ollama model is available for the {tier} tier.")

    def select_model(self, requested_model: str, prompt_on_conflict: bool = True) -> str:
        """Return the model selected by the user for the next agent run."""
        with self._selection_lock():
            loaded = self.loaded_models()
            if not prompt_on_conflict or not loaded or requested_model in loaded:
                return requested_model

            choices = list(dict.fromkeys(loaded + [requested_model] + self.installed_models()))
            print("\nAnother local agent is using an Ollama model.")
            print("Select the model this agent should use:")
            for index, model_name in enumerate(choices, start=1):
                marker = " (currently loaded)" if model_name in loaded else ""
                requested = " (requested)" if model_name == requested_model else ""
                print(f"  {index}. {model_name}{marker}{requested}")

            while True:
                try:
                    answer = input(f"Choice [1-{len(choices)}]: ").strip()
                except EOFError as error:
                    raise RuntimeError(
                        "Model selection requires an interactive terminal. "
                        "Run the agent from a terminal and choose a model."
                    ) from error
                try:
                    selection = choices[int(answer) - 1]
                except (ValueError, IndexError):
                    print("Enter the number of one model from the list.")
                    continue
                print(f"Selected Ollama model: {selection}")
                return selection