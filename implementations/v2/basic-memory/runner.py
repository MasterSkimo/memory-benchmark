"""Run the MCP server with Basic Memory state isolated in this candidate directory."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import sys


def main() -> int:
    bwrap = shutil.which("bwrap")
    if not bwrap:
        print("BLOCKED: bubblewrap is required for candidate-local Basic Memory state", file=sys.stderr)
        return 2
    candidate = Path(__file__).resolve().parent
    runtime = candidate / "v2env" / "home" / ".basic-memory"
    runtime.mkdir(parents=True, exist_ok=True)
    config_target = Path.home() / ".basic-memory"
    command = [bwrap, "--ro-bind", "/", "/", "--tmpfs", str(Path.home()),
        "--dir", str(config_target), "--bind", str(runtime), str(config_target),
        "--dev", "/dev", "--proc", "/proc", "--bind", str(candidate), str(candidate),
        "--bind", str(Path(__file__).resolve().parents[3]), str(Path(__file__).resolve().parents[3]),
        "--chdir", str(candidate), "--", sys.executable, "server.py", *sys.argv[1:]]
    return os.spawnve(os.P_WAIT, bwrap, command, os.environ.copy())

if __name__ == "__main__":
    raise SystemExit(main())
