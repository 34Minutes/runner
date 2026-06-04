"""Allow running the package directly: python -m script_runner"""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
