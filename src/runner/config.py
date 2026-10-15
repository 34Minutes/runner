"""Configuration persistence for Runner.

Stores launchers and UI settings in a JSON file under the platform user config dir.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import platformdirs

APP_NAME = "Runner"
CONFIG_FILENAME = "config.json"


@dataclass
class Launcher:
    """A single launchable item shown in the dropdown (when enabled)."""

    id: str
    name: str
    command: str  # exe path, "calc", url, "python script.py", etc.
    args: str = ""  # additional parameters / command line args
    enabled: bool = True
    working_dir: str | None = None
    run_as_admin: bool = False
    show_console: bool = False

    @classmethod
    def new(cls, name: str, command: str, **kwargs: Any) -> Launcher:
        return cls(id=str(uuid4()), name=name, command=command, **kwargs)


@dataclass
class Settings:
    """UI and behavior settings."""

    trigger_width: int = 36
    trigger_height: int = 28
    dropdown_width: int = 220
    hover_delay_ms: int = 120
    animation_duration_ms: int = 180
    position_x: int = 100
    position_y: int = 60
    pinned_open: bool = False
    show_filter_box: bool = True
    launch_at_startup: bool = False  # Windows only; managed via registry Run key


@dataclass
class AppConfig:
    """Root configuration object."""

    launchers: list[Launcher] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": asdict(self.settings),
            "launchers": [asdict(l) for l in self.launchers],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        version = data.get("version", 1)
        settings = Settings(**data.get("settings", {}))
        launchers = [Launcher(**item) for item in data.get("launchers", [])]
        return cls(launchers=launchers, settings=settings, version=version)


class ConfigManager:
    """Handles loading, saving, and providing defaults for AppConfig."""

    def __init__(self) -> None:
        self.config_dir: Path = Path(
            platformdirs.user_config_dir(APP_NAME, appauthor=False)
        )
        self.config_path: Path = self.config_dir / CONFIG_FILENAME
        self._config: AppConfig | None = None

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            cfg = self._create_default()
            self.save(cfg)
            return cfg

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig.from_dict(data)
        except Exception:
            # Corrupt or unreadable -> backup and recreate
            self._backup_corrupt()
            cfg = self._create_default()
            self.save(cfg)
            return cfg

    def save(self, config: AppConfig | None = None) -> None:
        if config is None:
            config = self.config
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        tmp_path.replace(self.config_path)
        self._config = config

    def _create_default(self) -> AppConfig:
        # Will be populated with seed data by the app on first run if empty
        return AppConfig()

    def _backup_corrupt(self) -> None:
        if self.config_path.exists():
            backup = self.config_path.with_suffix(".json.bak")
            try:
                self.config_path.replace(backup)
            except Exception:
                pass

    def get_enabled_launchers(self) -> list[Launcher]:
        return [l for l in self.config.launchers if l.enabled]

    def reload(self) -> AppConfig:
        """Force re-read from disk (useful after external edit)."""
        self._config = None
        return self.config

    def add_launcher(self, launcher: Launcher) -> None:
        self.config.launchers.append(launcher)
        self.save()

    def update_launcher(self, launcher: Launcher) -> None:
        for i, existing in enumerate(self.config.launchers):
            if existing.id == launcher.id:
                self.config.launchers[i] = launcher
                self.save()
                return
        # Not found -> add
        self.add_launcher(launcher)

    def remove_launcher(self, launcher_id: str) -> None:
        self.config.launchers = [
            l for l in self.config.launchers if l.id != launcher_id
        ]
        self.save()

    def reorder_launchers(self, ordered_ids: list[str]) -> None:
        id_to_launcher = {l.id: l for l in self.config.launchers}
        new_order = []
        for lid in ordered_ids:
            if lid in id_to_launcher:
                new_order.append(id_to_launcher.pop(lid))
        new_order.extend(id_to_launcher.values())  # any remaining at end
        self.config.launchers = new_order
        self.save()

    def update_settings(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self.config.settings, k):
                setattr(self.config.settings, k, v)
        self.save()
