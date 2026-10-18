"""Build tiktoken's cl100k_base offline cache from pinned gpt-tokenizer data."""
from __future__ import annotations

import hashlib
import pathlib
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = ROOT / ".models/v2/cognee/gpt-tokenizer-4.1.0.tgz"
CACHE = ROOT / ".models/v2/tokenizers"
PACKAGE_SHA256 = "ec0f7e3eea8e4f56b30297af68e4a52629707bdc59530f4a82d81ac03aad4447"
ENCODING_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
ENCODING_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
TIKTOKEN_CACHE_KEY = hashlib.sha1(ENCODING_URL.encode()).hexdigest()


def main() -> None:
    if hashlib.sha256(PACKAGE.read_bytes()).hexdigest() != PACKAGE_SHA256:
        raise SystemExit("gpt-tokenizer package checksum mismatch")
    with tarfile.open(PACKAGE, "r:gz") as archive:
        archive.extractall(ROOT / ".models/v2/cognee/unpacked", filter="data")
    module = ROOT / ".models/v2/cognee/unpacked/package/cjs/bpeRanks/cl100k_base.js"
    build = r"""
const fs = require('fs');
const crypto = require('crypto');
const ranks = require(process.argv[1]).default;
const bytes = ranks.map((item, rank) => {
  const token = typeof item === 'string' ? Buffer.from(item, 'utf8') : Buffer.from(item);
  return token.toString('base64') + ' ' + rank + '\n';
}).join('');
const output = process.argv[2];
fs.writeFileSync(output, bytes);
console.log(crypto.createHash('sha256').update(bytes).digest('hex'));
"""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / TIKTOKEN_CACHE_KEY
    result = subprocess.run(
        ["node", "-e", build, str(module), str(target)],
        check=True,
        text=True,
        capture_output=True,
    )
    actual = result.stdout.strip()
    if actual != ENCODING_SHA256:
        target.unlink(missing_ok=True)
        raise SystemExit(f"derived cl100k_base checksum mismatch: {actual}")
    print(f"Installed offline cl100k_base cache {target} sha256={actual}")


if __name__ == "__main__":
    main()
