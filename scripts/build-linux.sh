#!/bin/bash
set -euo pipefail

# Build a portable Linux x86_64 binary with the shared PyInstaller spec.
# Run this on Linux after: pip install -e ".[dev]"
#
# The frozen file is dist/Runner. It carries its own Python. It still needs
# glibc 2.35 or newer, which is Ubuntu 22.04, Debian 12, Fedora 36, and
# anything newer. A normal desktop already has the graphics libraries Qt uses.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "==> Building Runner for Linux..."
pyinstaller --clean --noconfirm runner.spec

chmod +x dist/Runner
echo
echo "==> Build complete."
ls -lh dist/Runner
echo "Single file: dist/Runner"
echo "Copy it to another x86_64 machine with glibc 2.35 or newer and run it."
