import json

import vscode_learning


def test_exchange_metadata_does_not_capture_content_by_default(monkeypatch):
    monkeypatch.setattr(vscode_learning, "CAPTURE_CONTENT", False)

    event = vscode_learning.build_exchange_event(
        "/api/chat",
        json.dumps({"model": "llama3:latest", "messages": [{"content": "secret"}]}).encode(),
        b'{"message":{"content":"answer"}}\n',
        200,
    )

    assert event["model"] == "llama3:latest"
    assert "input" not in event
    assert "output" not in event


def test_exchange_content_can_be_enabled(monkeypatch):
    monkeypatch.setattr(vscode_learning, "CAPTURE_CONTENT", True)

    event = vscode_learning.build_exchange_event(
        "/api/chat",
        json.dumps({"model": "llama3:latest", "messages": [{"content": "task"}]}).encode(),
        b'{"message":{"content":"answer"}}\n',
        200,
    )

    assert event["input"] == [{"content": "task"}]
    assert event["output"] == "answer"