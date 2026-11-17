"""Pytest configuration for Runner Qt tests."""

import pytest

# qt_api is set in pyproject.toml [tool.pytest.ini_options].


@pytest.fixture(scope="session")
def qapp_args():
    # Extra args for QApplication in tests if needed (e.g. for offscreen)
    return []


@pytest.fixture(autouse=True)
def _never_touch_the_real_config(tmp_path_factory, monkeypatch):
    """Point every ConfigManager at a throwaway folder.

    A test that builds ConfigManager() without its own redirect would
    otherwise read and overwrite the user's real config.json. Tests that set
    their own folder still do; this only replaces the default.
    """
    folder = tmp_path_factory.mktemp("runner-config")
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(folder),
    )
