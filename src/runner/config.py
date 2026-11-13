"""Configuration persistence for Runner.

Stores launchers and UI settings in a JSON file under the platform user config dir.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from uuid import uuid4

import platformdirs

APP_NAME = "Runner"
CONFIG_FILENAME = "config.json"

# Large enough to see on a big display. The old 36×28 arrow was easy to miss.
# A saved arrow smaller than this is raised to it once, then the user's resize sticks.
DEFAULT_TRIGGER_WIDTH = 120
DEFAULT_TRIGGER_HEIGHT = 96


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
    # Hidden from the hover list. It still runs inside any group it belongs to.
    only_in_groups: bool = False

    @classmethod
    def new(cls, name: str, command: str, **kwargs: Any) -> Launcher:
        return cls(id=str(uuid4()), name=name, command=command, **kwargs)


@dataclass
class GroupMember:
    """One launcher inside a group, in execution order."""

    launcher_id: str
    concurrent: bool = False


@dataclass
class Group:
    """An ordered set of launchers the user can start together."""

    id: str
    name: str
    members: list[GroupMember] = field(default_factory=list)

    @classmethod
    def new(cls, name: str, members: list[GroupMember] | None = None) -> Group:
        return cls(id=str(uuid4()), name=name, members=list(members or []))


@dataclass
class ContainerMember:
    """One launcher inside a container group.

    only_in_container matches the launcher's main-popup choice. It is on
    when Include in dropdown list is off, and off when that switch is on.
    """

    launcher_id: str
    only_in_container: bool = False


@dataclass
class ContainerGroup:
    """A named submenu. Hovering it lists its launchers. It does not run them."""

    id: str
    name: str
    members: list[ContainerMember] = field(default_factory=list)

    @classmethod
    def new(cls, name: str, members: list[ContainerMember] | None = None) -> ContainerGroup:
        return cls(id=str(uuid4()), name=name, members=list(members or []))


def _from_fields(cls, data: dict[str, Any]):
    """Build a dataclass from JSON, ignoring keys this version does not know."""
    known = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in data.items() if key in known})


def _unique_known(ids: list[str], known: set[str]) -> set[str]:
    return {item_id for item_id in ids if item_id in known}


def _sync_members(members: list, launcher_id: str, keep: bool, make_member):
    """Drop or append this launcher. An existing row stays put, flags included."""
    existing = next((member for member in members if member.launcher_id == launcher_id), None)
    if keep:
        if existing is not None:
            return list(members)
        return [*members, make_member()]
    if existing is None:
        return list(members)
    return [member for member in members if member.launcher_id != launcher_id]


@dataclass
class Settings:
    """UI and behavior settings."""

    trigger_width: int = DEFAULT_TRIGGER_WIDTH
    trigger_height: int = DEFAULT_TRIGGER_HEIGHT
    dropdown_width: int = 220
    hover_delay_ms: int = 120
    animation_duration_ms: int = 180
    position_x: int = 100
    position_y: int = 60
    pinned_open: bool = False
    show_filter_box: bool = True
    launch_at_startup: bool = False  # Windows only; managed via registry Run key
    # Flashing border on each launch. The resize bubble is first-run only.
    show_startup_greeting: bool = True
    # When true, hovering the arrow shows the groups list beside the launchers.
    show_groups: bool = False
    # False until the one-time enlarge below has been saved. Old config files
    # omit this, so they pick up the larger arrow once and then keep any resize.
    applied_visible_trigger_size: bool = False


@dataclass
class AppConfig:
    """Root configuration object."""

    launchers: list[Launcher] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    container_groups: list[ContainerGroup] = field(default_factory=list)
    # Mixed order of the main popup. Tokens are "container:<id>" and "launcher:<id>".
    # Empty means containers first, then launchers, which is the order before any drag.
    main_order: list[str] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": asdict(self.settings),
            "launchers": [asdict(l) for l in self.launchers],
            "groups": [asdict(group) for group in self.groups],
            "container_groups": [asdict(group) for group in self.container_groups],
            "main_order": list(self.main_order),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        version = data.get("version", 1)
        settings = _from_fields(Settings, data.get("settings", {}))
        launchers = [_from_fields(Launcher, item) for item in data.get("launchers", [])]
        groups = []
        for item in data.get("groups", []):
            members = [_from_fields(GroupMember, member) for member in item.get("members", [])]
            groups.append(Group(id=item["id"], name=item.get("name", ""), members=members))
        container_groups = []
        for item in data.get("container_groups", []):
            members = [
                _from_fields(ContainerMember, member) for member in item.get("members", [])
            ]
            container_groups.append(
                ContainerGroup(id=item["id"], name=item.get("name", ""), members=members)
            )
        main_order = [item for item in data.get("main_order", []) if isinstance(item, str)]
        return cls(
            launchers=launchers,
            settings=settings,
            groups=groups,
            container_groups=container_groups,
            main_order=main_order,
            version=version,
        )


class ConfigManager:
    """Handles loading, saving, and providing defaults for AppConfig."""

    def __init__(self) -> None:
        self.config_dir: Path = Path(
            platformdirs.user_config_dir(APP_NAME, appauthor=False)
        )
        self.config_path: Path = self.config_dir / CONFIG_FILENAME
        self._config: AppConfig | None = None
        # True when this process loaded a config file that was already on disk.
        self.had_saved_config = False

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            self.had_saved_config = False
            cfg = self._create_default()
            self.save(cfg)
            return cfg

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.had_saved_config = True
            return AppConfig.from_dict(data)
        except Exception:
            # Corrupt or unreadable -> backup and recreate
            self._backup_corrupt()
            self.had_saved_config = False
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

    def get_main_view_launchers(self) -> list[Launcher]:
        """Enabled launchers that belong on the main hover list."""
        from .containers import shown_in_main_menu

        return [
            launcher
            for launcher in self.config.launchers
            if shown_in_main_menu(launcher, self.config.container_groups)
        ]

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
        for group in self.config.groups:
            group.members = [
                member for member in group.members if member.launcher_id != launcher_id
            ]
        for group in self.config.container_groups:
            group.members = [
                member for member in group.members if member.launcher_id != launcher_id
            ]
        self.save()

    def add_group(self, group: Group) -> None:
        self.config.groups.append(group)
        self.save()

    def update_group(self, group: Group) -> None:
        for index, existing in enumerate(self.config.groups):
            if existing.id == group.id:
                self.config.groups[index] = group
                self.save()
                return
        self.add_group(group)

    def remove_group(self, group_id: str) -> None:
        self.config.groups = [group for group in self.config.groups if group.id != group_id]
        self.save()

    def reorder_groups(self, ordered_ids: list[str]) -> None:
        by_id = {group.id: group for group in self.config.groups}
        new_order = []
        for group_id in ordered_ids:
            if group_id in by_id:
                new_order.append(by_id.pop(group_id))
        new_order.extend(by_id.values())
        self.config.groups = new_order
        self.save()

    def add_container_group(self, group: ContainerGroup) -> None:
        self.config.container_groups.append(group)
        self.save()

    def update_container_group(self, group: ContainerGroup) -> None:
        for index, existing in enumerate(self.config.container_groups):
            if existing.id == group.id:
                self.config.container_groups[index] = group
                self.save()
                return
        self.add_container_group(group)

    def remove_container_group(self, group_id: str) -> None:
        self.config.container_groups = [
            group for group in self.config.container_groups if group.id != group_id
        ]
        self.save()

    def reorder_container_members(self, group_id: str, ordered_ids: list[str]) -> None:
        from .moves import reorder_members

        for group in self.config.container_groups:
            if group.id == group_id:
                group.members = reorder_members(group.members, ordered_ids)
                self.save()
                return

    def reorder_group_members(self, group_id: str, ordered_ids: list[str]) -> None:
        from .moves import reorder_members

        for group in self.config.groups:
            if group.id == group_id:
                group.members = reorder_members(group.members, ordered_ids)
                self.save()
                return

    def apply_main_row_order(self, visible_tokens: list[str]) -> None:
        from .moves import apply_visible_row_order

        apply_visible_row_order(self.config, visible_tokens)
        self.save()

    def move_launcher(
        self,
        launcher_id: str,
        source_key: str,
        dest_key: str,
        dest_index: int,
        dest_visible_ids: list[str] | None = None,
    ) -> bool:
        from .moves import move_launcher

        moved = move_launcher(
            self.config,
            launcher_id,
            source_key,
            dest_key,
            dest_index,
            dest_visible_ids,
        )
        if moved:
            self.save()
        return moved

    def reorder_container_groups(self, ordered_ids: list[str]) -> None:
        by_id = {group.id: group for group in self.config.container_groups}
        new_order = []
        for group_id in ordered_ids:
            if group_id in by_id:
                new_order.append(by_id.pop(group_id))
        new_order.extend(by_id.values())
        self.config.container_groups = new_order
        self.save()

    def set_shown_in_main_menu(self, launcher_id: str, shown: bool) -> None:
        """Save the one main-popup choice for this launcher."""
        from .containers import set_shown_in_main_menu

        for launcher in self.config.launchers:
            if launcher.id != launcher_id:
                continue
            set_shown_in_main_menu(launcher, self.config.container_groups, shown)
            self.save()
            return

    def set_launcher_membership(
        self,
        launcher_id: str,
        container_ids: list[str],
        execute_ids: list[str],
        *,
        hidden_from_main: bool | None = None,
    ) -> None:
        """Put this launcher in exactly these container and execute groups.

        A membership that stays keeps its Concurrent flag. When
        hidden_from_main is set, every container membership uses that value.
        Otherwise an existing Only in Container Group flag is kept, and a new
        container membership starts off.
        """
        container_keep = _unique_known(
            container_ids, {group.id for group in self.config.container_groups}
        )
        execute_keep = _unique_known(
            execute_ids, {group.id for group in self.config.groups}
        )
        hide = bool(hidden_from_main)
        for group in self.config.container_groups:
            group.members = _sync_members(
                group.members,
                launcher_id,
                group.id in container_keep,
                lambda: ContainerMember(launcher_id, only_in_container=hide),
            )
        if hidden_from_main is not None:
            for group in self.config.container_groups:
                for member in group.members:
                    if member.launcher_id == launcher_id:
                        member.only_in_container = hide
        for group in self.config.groups:
            group.members = _sync_members(
                group.members,
                launcher_id,
                group.id in execute_keep,
                lambda: GroupMember(launcher_id, concurrent=False),
            )
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
