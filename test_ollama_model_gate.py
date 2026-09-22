from pathlib import Path

from ollama_model_gate import OllamaModelGate


class FakeModel:
    def __init__(self, name: str):
        self.name = name
        self.model = name


class FakeClient:
    def __init__(self, loaded: list[str], installed: list[str]):
        self.loaded = loaded
        self.installed = installed

    def ps(self):
        return type("ProcessResponse", (), {"models": [FakeModel(name) for name in self.loaded]})()

    def list(self):
        return type("ListResponse", (), {"models": [FakeModel(name) for name in self.installed]})()


def test_existing_requested_model_does_not_prompt(tmp_path: Path):
    gate = OllamaModelGate(FakeClient(["llama3:latest"], ["llama3:latest"]), tmp_path / "lock")

    assert gate.select_model("llama3:latest") == "llama3:latest"


def test_different_loaded_model_prompts_and_returns_selection(tmp_path: Path, monkeypatch):
    gate = OllamaModelGate(
        FakeClient(["llama3:latest"], ["llama3:latest", "qwen2.5-coder:1.5b"]),
        tmp_path / "lock",
    )
    monkeypatch.setattr("builtins.input", lambda _: "2")

    assert gate.select_model("qwen2.5-coder:1.5b") == "qwen2.5-coder:1.5b"


def test_routes_coding_and_high_token_tasks_to_available_tiers(tmp_path: Path):
    gate = OllamaModelGate(
        FakeClient(
            [],
            ["llama3:latest", "qwen3-coder:30b", "qwen3.6:27b"],
        ),
        tmp_path / "lock",
    )

    assert gate.route_model("Fix this Python test failure") == ("qwen3-coder:30b", "coding")
    assert gate.route_model("Perform a thorough high token architecture analysis") == (
        "qwen3.6:27b",
        "high_token",
    )


def test_model_profile_rates_speed_quality_and_role(tmp_path: Path):
    gate = OllamaModelGate(FakeClient([], []), tmp_path / "lock")

    assert gate.profile("qwen2.5-coder:1.5b") == {
        "size": "small",
        "speed": 5,
        "quality": 2,
        "role": "fast coding",
    }
    assert gate.profile("nomic-embed-text:latest")["role"] == "embeddings only"