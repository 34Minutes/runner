"""Pytest configuration for Script Runner Qt tests."""

import pytest

# qt_api already set in pyproject.toml [tool.pytest.ini_options]
# Use: pytest --no-qt or pytest-qt will handle QApplication etc.

@pytest.fixture(scope="session")
def qapp_args():
    # Extra args for QApplication in tests if needed (e.g. for offscreen)
    return []
