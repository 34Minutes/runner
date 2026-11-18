#!/bin/bash
set -euo pipefail

# Build Runner for Linux x86_64: dist/Runner, one portable file.
#
# Usage, from any folder:
#   ./scripts/build-linux.sh               lint, test, then build
#   ./scripts/build-linux.sh --skip-tests  build without the lint check and tests
#
# First time, from the repo root:
#   python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
#
# The project's .venv is used when it exists, otherwise python3 on PATH (as on
# GitHub Actions). The file carries its own Python but needs the glibc of the
# machine that built it, or newer. Build on Ubuntu 22.04 (glibc 2.35), as the
# GitHub workflow does, for Ubuntu 22.04, Debian 12, Fedora 36, and later.

RUN_TESTS=1
for arg in "$@"; do
  case "$arg" in
    --skip-tests) RUN_TESTS=0 ;;
    -h|--help)
      sed -n '4,16p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PY="$PROJECT_ROOT/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

VERSION="$("$PY" scripts/check_version.py)"
GLIBC="$(getconf GNU_LIBC_VERSION 2>/dev/null || echo "glibc unknown")"

echo "==> Runner $VERSION"
echo "==> Python: $PY ($("$PY" --version 2>&1))"
echo "==> Building against $GLIBC"

if [ "$RUN_TESTS" -eq 1 ]; then
  echo "==> Lint (ruff)..."
  "$PY" -m ruff check src tests
  echo "==> Running tests (some briefly open windows)..."
  # --capture=sys lets Qt's own error messages through if Qt aborts.
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    "$PY" -m pytest -q --capture=sys
  elif command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a "$PY" -m pytest -q --capture=sys
  else
    echo "ERROR: the tests need a display. Install xvfb, or use --skip-tests." >&2
    exit 1
  fi
fi

echo "==> Building..."
"$PY" -m PyInstaller --clean --noconfirm runner.spec

if [ ! -f dist/Runner ]; then
  echo "ERROR: the build finished but dist/Runner is missing." >&2
  exit 1
fi
chmod +x dist/Runner

echo
echo "==> Built Runner $VERSION"
ls -lh dist/Runner
echo "    One portable file for x86_64 Linux with $GLIBC or newer."
