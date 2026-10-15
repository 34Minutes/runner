"""Bootstrap script for PyInstaller bundling.

This allows the packaged app to use the proper package imports
instead of running main.py directly (which breaks relative imports).

Used only for building the standalone app.
"""

from runner.main import main

if __name__ == "__main__":
    raise SystemExit(main())
