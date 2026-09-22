# Local Ollama Models

This directory contains the local Ollama model gate, Strands integration, and authenticated proxy used by VS Code and local agents.

## Architecture

```text
VS Code / local clients
        |
        | bearer token required
        v
127.0.0.1:11434  authenticated proxy
        |
        v
127.0.0.1:11435  Ollama
```

Only one Ollama model is allowed to remain loaded at a time. The proxy protects the public Ollama endpoint from unauthenticated local requests. It does not provide per-application identity: another same-user process that can read the token can authenticate.

## VS Code setup

The VS Code provider is stored in:

`~/Library/Application Support/Code/User/chatLanguageModels.json`

The provider uses vendor `ollama-models`, URL `http://127.0.0.1:11434`, and an `Authorization` header. To recreate the token/header configuration:

```sh
cd /Users/wolfpacker/development/model
$HOME/.venv/bin/python setup_ollama_proxy.py
```

After changing this file, run **Developer: Reload Window** in VS Code. The local models should then appear in the model picker. The configured chat models are:

- `qwen2.5-coder:1.5b`
- `llama2:latest`
- `llama3.1:8b`
- `llama3:latest`
- `qwen3-coder:30b`
- `qwen3.6:27b`
- `qwen3.8:latest`

The embedding model `nomic-embed-text:latest` is installed but is not exposed as a chat model.

## Strands learning observer

The proxy records every authorized VS Code exchange as metadata in
`~/.ollama/vscode-learning.jsonl`. By default it does not store prompt or response content.
To let a background Strands observer extract lessons from exchanges, enable content capture
before starting or restarting the proxy:

```sh
export OLLAMA_LEARNING_CAPTURE_CONTENT=1
export STRANDS_LEARNING_MODEL=qwen3-coder:30b
```

Lessons are written to `~/.ollama/strands-lessons.jsonl`. The observer calls the Ollama
upstream directly on port `11435`, so its own request is not fed back through the proxy.
Content capture may include sensitive prompts and responses; disable it by unsetting the
environment variable or setting it to `0`.

## Service management

LaunchAgent files:

- `~/Library/LaunchAgents/com.wolfpacker.ollama-proxy.plist`
- `~/Library/LaunchAgents/sh.brew.ollama.plist`

Check both services and ports:

```sh
launchctl print gui/$(id -u)/com.wolfpacker.ollama | rg 'state =|pid ='
launchctl print gui/$(id -u)/sh.brew.ollama | rg 'state =|pid =|OLLAMA_HOST|OLLAMA_MAX_LOADED_MODELS'
lsof -nP -iTCP:11434 -iTCP:11435 -sTCP:LISTEN
```

Expected listeners:

- Proxy: `127.0.0.1:11434`
- Ollama: `127.0.0.1:11435`

If Ollama is restarted by Homebrew and returns to port `11434`, reload the LaunchAgent plist directly:

```sh
launchctl bootout gui/$(id -u)/sh.brew.ollama 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/sh.brew.ollama.plist"
```

## Authentication checks

The token is stored with owner-only permissions at:

`~/.ollama/proxy-token`

Do not commit or paste its contents. Test the proxy without printing the token:

```sh
curl -i http://127.0.0.1:11434/api/tags

$HOME/.venv/bin/python - <<'PY'
import json
from pathlib import Path
from urllib.request import Request, urlopen

token = (Path.home() / ".ollama" / "proxy-token").read_text().strip()
request = Request(
    "http://127.0.0.1:11434/api/tags",
    headers={"Authorization": f"Bearer {token}"},
)
with urlopen(request, timeout=10) as response:
    payload = json.load(response)
print(f"status=200 models={len(payload['models'])}")
PY
```

The first request should return `401`; the authorized request should return `status=200`.

## Source files

- `ollama_proxy.py`: authenticated reverse proxy and response forwarding.
- `vscode_learning.py`: exchange journal and asynchronous Strands learning observer.
- `setup_ollama_proxy.py`: creates the token and updates the VS Code provider header.
- `ollama_model_gate.py`: model discovery, routing, locking, status, and proxy client headers.
- `local_agent.py`: small Strands agent example using the model gate.
- `demo_model_coordination.py`: model-coordination demonstration.
- `test_ollama_model_gate.py`: model-gate tests.

The main Strands entry point is one directory above this folder:

`/Users/wolfpacker/development/strands_agent.py`

It also uses the proxy token and model gate.

## Validation

```sh
cd /Users/wolfpacker/development/model
$HOME/.venv/bin/python -m py_compile \
  ollama_proxy.py setup_ollama_proxy.py ollama_model_gate.py local_agent.py
$HOME/.venv/bin/python -m pytest -q test_ollama_model_gate.py
```

The one-model limit is configured in the Ollama LaunchAgent and in the shell profile:

`~/.zshrc`
