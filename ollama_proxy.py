"""Authenticated localhost reverse proxy for Ollama."""

from __future__ import annotations

import http.client
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from vscode_learning import record_exchange


PUBLIC_HOST = os.environ.get("OLLAMA_PROXY_HOST", "127.0.0.1")
PUBLIC_PORT = int(os.environ.get("OLLAMA_PROXY_PORT", "11434"))
UPSTREAM_HOST = os.environ.get("OLLAMA_UPSTREAM_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("OLLAMA_UPSTREAM_PORT", "11435"))
TOKEN_PATH = Path(
    os.environ.get("OLLAMA_PROXY_TOKEN_FILE", str(Path.home() / ".ollama" / "proxy-token"))
)


def load_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not TOKEN_PATH.exists():
        TOKEN_PATH.write_text(secrets.token_urlsafe(32) + "\n")
        TOKEN_PATH.chmod(0o600)
    return TOKEN_PATH.read_text().strip()


class OllamaProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _authorized(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {load_token()}"

    def _proxy(self) -> None:
        if not self._authorized():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        body = None
        if self.headers.get("Content-Length"):
            body = self.rfile.read(int(self.headers["Content-Length"]))
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        headers["Host"] = f"{UPSTREAM_HOST}:{UPSTREAM_PORT}"
        connection = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=600)
        connection._http_vsn = 10
        connection._http_vsn_str = "HTTP/1.0"
        response_status = 502
        response_chunks: list[bytes] = []
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            response_status = response.status
            payload_length = response.getheader("Content-Length")
            self.close_connection = payload_length is None
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in {"connection", "keep-alive", "transfer-encoding"}:
                    self.send_header(key, value)
            if payload_length is not None:
                self.send_header("Content-Length", payload_length)
            else:
                self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                response_chunks.append(chunk)
                self.wfile.write(chunk)
                self.wfile.flush()
        except (ConnectionError, OSError) as error:
            self.send_error(502, f"Ollama upstream unavailable: {error}")
        finally:
            record_exchange(self.path, body, b"".join(response_chunks), response_status)
            connection.close()

    def do_GET(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def log_message(self, format: str, *args: object) -> None:
        print(f"ollama-proxy: {format % args}", flush=True)


def main() -> None:
    load_token()
    server = ThreadingHTTPServer((PUBLIC_HOST, PUBLIC_PORT), OllamaProxyHandler)
    print(
        f"Authenticated Ollama proxy listening on {PUBLIC_HOST}:{PUBLIC_PORT}; "
        f"upstream {UPSTREAM_HOST}:{UPSTREAM_PORT}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()