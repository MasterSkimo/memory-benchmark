"""Shared public-input hashing; no questions, answers or grader imports."""
import hashlib
from pathlib import Path


def corpus_digest(root):
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*.md')):
        if path.is_symlink():
            raise ValueError('symlink in frozen corpus')
        digest.update(path.relative_to(root).as_posix().encode('utf-8'))
        digest.update(b'\x00')
        digest.update(path.read_bytes())
        digest.update(b'\x00')
    return digest.hexdigest()
