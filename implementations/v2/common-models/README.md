# Shared V2 local multilingual encoder

`LocalEmbedder.encode(texts) -> list[list[float]]` returns 384-dimensional L2-normalized vectors. Weights are loaded from `.models/v2/trained-multilingual/checkpoint.pt` and SHA-256 checked against its manifest; inference is CPU-only and never downloads anything.

This is a genuinely trained, small neural baseline built because the permitted proxy blocks the official FastEmbed/Hugging Face pretrained distribution. It is not a pretrained sentence model. The vocab and learned token embeddings are trained on 40 authored public English/French development pairs with symmetric in-batch contrastive loss. See `dev-pairs.jsonl`, `train.py`, and `results/v2/models/manifest.json` for the frozen recipe, checkpoint hash and public integration check. Its tiny data and word-token OOV behavior limit generalization; do not interpret results as representative pretrained-model quality.

Install exact pins from `requirements.lock` (PyTorch CPU wheels from the official PyTorch CPU index), then run `python train.py`. The local ignored checkpoint is generated deterministically from the fixed seed and public pairs.

For SDKs in separate virtual environments, run `python server.py --host 127.0.0.1 --port 8765`; use base URL `http://127.0.0.1:8765/v1`, model ID `codex-public-dev-bilingual-mean-embedding`, and request `POST /embeddings`. This small OpenAI-compatible endpoint runs the same verified local checkpoint and reports the encoder's actual Unicode-word token count. It rejects non-loopback bind addresses and performs no external calls.
