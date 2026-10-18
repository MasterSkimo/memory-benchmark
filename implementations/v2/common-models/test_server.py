from __future__ import annotations
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from server import EmbeddingsHandler, MODEL_ID
from embedder import LocalEmbedder


def test_local_openai_embeddings_api():
    handler = type("TestHandler", (EmbeddingsHandler,), {"embedder": LocalEmbedder()})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"model": MODEL_ID, "input": ["the contract was signed", "le contrat a été signé"]}).encode()
        request = Request(f"http://127.0.0.1:{server.server_port}/v1/embeddings", data=payload,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        assert result["model"] == MODEL_ID
        assert len(result["data"]) == 2
        assert all(len(row["embedding"]) == 384 for row in result["data"])
        assert result["usage"] == {"prompt_tokens": 9, "total_tokens": 9}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
