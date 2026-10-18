"""Minimal local OpenAI-compatible embeddings endpoint for SDK adapters."""
from __future__ import annotations
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from typing import Any
from embedder import LocalEmbedder

MODEL_ID = "codex-public-dev-bilingual-mean-embedding"


class EmbeddingsHandler(BaseHTTPRequestHandler):
    server_version = "LocalEmbeddingServer/1.0"
    embedder: LocalEmbedder

    def _json(self, status: int, body: dict[str, Any]):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok", "model": MODEL_ID, "dimension": self.embedder.dimension})
        elif self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "local"}]})
        else:
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self):
        if self.path != "/v1/embeddings":
            self._json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8_000_000:
                raise ValueError("request body size is invalid")
            body = json.loads(self.rfile.read(length))
            texts = body.get("input")
            if isinstance(texts, str): texts = [texts]
            if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
                raise ValueError("input must be a string or nonempty string list")
            model = body.get("model", MODEL_ID)
            if model != MODEL_ID:
                raise ValueError(f"unknown model: {model}")
            vectors = self.embedder.encode(texts)
            token_count = sum(self.embedder.token_count(text) for text in texts)
            self._json(200, {
                "object": "list",
                "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
                "model": MODEL_ID,
                "usage": {"prompt_tokens": token_count, "total_tokens": token_count},
            })
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": {"message": str(exc), "type": "invalid_request_error"}})


def serve(host: str = "127.0.0.1", port: int = 8765):
    if not ip_address(host).is_loopback:
        raise ValueError("The local embedding server may bind only to loopback")
    handler = type("BoundEmbeddingsHandler", (EmbeddingsHandler,), {"embedder": LocalEmbedder()})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"{MODEL_ID} listening on http://{host}:{server.server_port}/v1/embeddings", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.host, args.port)
