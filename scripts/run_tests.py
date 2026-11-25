"""Run Runner's tests: one run at a time, and only when something changed.

Usage (from anywhere; it uses the project's own folder):
    .venv/bin/python scripts/run_tests.py            lint and test, unless this code already passed
    .venv/bin/python scripts/run_tests.py --force    lint and test even if it did
    .venv/bin/python scripts/run_tests.py -- -k dial pass the rest to pytest (never skipped)

One run at a time: a second run stops at once and says which one is going.
The lock is held by the running process, so it goes away when that process
ends, however it ends (a crash or a power cut leaves no stale lock).

Only when something changed: after a full run passes, a fingerprint of the
code is saved. The next run with the same fingerprint says so and stops,
passing. The fingerprint covers every file git tracks or would track (not
ignored files) under src/, tests/, and the files listed in FILES, plus the
Python version. A version bump alone doesn't count as a change, so the build
after a release doesn't test the same code again.

Exit codes: 0 passed (or already passed), 1 failed, 75 another run is going.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("src", "tests")
FILES = ("pyproject.toml", "runner.spec", "scripts/run_tests.py")
STATE_DIR = ROOT / ".pytest_cache"  # ignored by git; `pytest --cache-clear` forgets the pass too
LOCK_FILE = STATE_DIR / "runner-tests.lock"
PASS_FILE = STATE_DIR / "runner-tests-passed.json"
EXIT_BUSY = 75
# version = "1.2.3" / __version__ = "1.2.3": a release changes these and nothing else.
VERSION_LINE = re.compile(rb'^(\s*(?:__version__|version)\s*=\s*)"[^"\n]*"', re.MULTILINE)


def _files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
         "--", *FOLDERS, *FILES],
        check=True, capture_output=True,
    ).stdout
    return sorted({p for p in out.decode().split("\0") if p})


def fingerprint() -> str:
    digest = hashlib.sha256()
    digest.update(sys.version.encode())
    for rel in _files():
        path = ROOT / rel
        if not path.is_file():  # deleted but not yet committed
            continue
        digest.update(rel.encode() + b"\0")
        digest.update(VERSION_LINE.sub(rb'\1"*"', path.read_bytes()) + b"\0")
    return digest.hexdigest()


class Busy(Exception):
    pass


def _lock():
    """Hold the lock for as long as the returned file stays open."""
    STATE_DIR.mkdir(exist_ok=True)
    handle = open(LOCK_FILE, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.seek(0)
        holder = handle.read().strip() or "another run"
        handle.close()
        raise Busy(holder) from None
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid {os.getpid()}, started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    handle.flush()
    return handle


def _last_pass() -> str | None:
    try:
        return json.loads(PASS_FILE.read_text())["fingerprint"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _save_pass(print_: str) -> None:
    PASS_FILE.write_text(json.dumps({"fingerprint": print_, "passed": time.strftime("%Y-%m-%d %H:%M:%S")}))


def main(argv: list[str]) -> int:
    force = "--force" in argv or os.environ.get("RUNNER_TESTS_FORCE") == "1"
    pytest_args = argv[argv.index("--") + 1:] if "--" in argv else []
    try:
        lock = _lock()
    except Busy as exc:
        print(f"STOPPED: the tests are already running ({exc}). Only one run at a time.", file=sys.stderr)
        return EXIT_BUSY
    with lock:
        before = fingerprint()
        if not force and not pytest_args and before == _last_pass():
            print("==> Tests already passed for this code; not running them again (--force to run anyway).")
            return 0
        print("==> Lint (ruff)...", flush=True)
        if subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests"], cwd=ROOT).returncode:
            return 1
        print("==> Running tests (some briefly open windows)...", flush=True)
        # --capture=sys lets Qt's own error messages through if a test aborts.
        code = subprocess.run([sys.executable, "-m", "pytest", "-q", "--capture=sys", *pytest_args],
                              cwd=ROOT).returncode
        # Only a full run counts, and only if the code didn't change while it ran.
        if code == 0 and not pytest_args and fingerprint() == before:
            _save_pass(before)
        return 1 if code else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
