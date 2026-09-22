"""Configure local clients to use the authenticated Ollama proxy."""

from __future__ import annotations

import json
from pathlib import Path

from ollama_proxy import TOKEN_PATH, load_token


USER_DATA = Path.home() / "Library/Application Support/Code/User/chatLanguageModels.json"


def main() -> None:
    token = load_token()
    config = json.loads(USER_DATA.read_text())
    for provider in config:
        if provider.get("vendor") == "ollama-models":
            provider["url"] = "http://127.0.0.1:11434"
            provider["headers"] = {"Authorization": f"Bearer {token}"}
    USER_DATA.write_text(json.dumps(config, indent=2) + "\n")
    TOKEN_PATH.chmod(0o600)
    print("Configured the VS Code Ollama provider with the local proxy token.")


if __name__ == "__main__":
    main()