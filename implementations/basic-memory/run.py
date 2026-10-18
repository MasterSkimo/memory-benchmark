"""Run Basic Memory code with candidate-local storage mounted at its normal config path.

Basic Memory 0.13.1 hardcodes HOME/.basic-memory and offers no config-root selector.
This launcher leaves HOME unchanged and maps only that directory to candidate-local
storage using bubblewrap. The repository remains writable for candidate artifacts.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python implementations/basic-memory/run.py COMMAND [ARG ...]", file=sys.stderr)
        return 2
    bwrap = shutil.which("bwrap")
    if not bwrap:
        print("BLOCKED: bubblewrap (bwrap) is required for candidate-local Basic Memory config storage", file=sys.stderr)
        return 2
    repo = Path(__file__).resolve().parents[2]
    candidate = Path(__file__).resolve().parent
    runtime = candidate / "runtime-home" / ".basic-memory"
    runtime.mkdir(parents=True, exist_ok=True)
    config_target = Path.home() / ".basic-memory"
    argv = [
        bwrap,
        "--ro-bind", "/", "/",
        "--tmpfs", str(Path.home()),
        "--dir", str(config_target),
        "--bind", str(runtime), str(config_target),
        "--dev", "/dev",
        "--proc", "/proc",
        "--bind", str(repo), str(repo),
        "--chdir", str(repo),
        "--", *sys.argv[1:],
    ]
    return subprocess.run(argv, env=os.environ.copy(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
