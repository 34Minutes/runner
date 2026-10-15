"""Allow running the package directly: python -m runner"""

from .main import main

if __name__ == "__main__":
    raise SystemExit(main())
