"""Configuration persistence for Runner.

Stores launchers and UI settings in a JSON file under the platform user config dir.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import platformdirs

APP_NAME = "Runner"
CONFIG_FILENAME = "config.json"

# Large enough to see on a big display. The old 36×28 arrow was easy to miss.
# A saved arrow smaller than this is raised to it once, then the user's resize sticks.
DEFAULT_TRIGGER_WIDTH = 120
# 2: one show_in_main flag replaced enabled, only_in_groups, and each
# container membership's only_in_container. Version 1 files are converted on load.
CONFIG_VERSION = 2
DEFAULT_TRIGGER_HEIGHT = 96


@dataclass
class Launcher:
    """A single launchable item."""

    id: str
    name: str
    command: str  # exe path, "calc", url, "python script.py", etc.
    args: str = ""  # additional parameters / command line args
    # On the main hover list. Off, it is still in every execute group and
    # container it belongs to. Include in dropdown list, Only in Groups, and
    # Only in Container Group all read and write this one value.
    show_in_main: bool = True
    working_dir: str | None = None
    run_as_admin: bool = False
    show_console: bool = False
    # Set when a program outside Runner made it through `runner ctl`: the name
    # that program gave. Only that program may change or delete it from
    # outside. None for everything made in Runner itself.
    source: str | None = None

    @classmethod
    def new(cls, name: str, command: str, **kwargs: Any) -> Launcher:
        return cls(id=str(uuid4()), name=name, command=command, **kwargs)


@dataclass
class GroupMember:
    """One launcher inside a group, in execution order."""

    launcher_id: str
    concurrent: bool = False


@dataclass
class ScheduleEntry:
    """One date a scheduled group runs on, and how often it repeats from there.

    start is local time, "YYYY-MM-DDTHH:MM". The repeat is the interval
    roller's five values; all zero means it runs once. Months are calendar
    months: from the 31st, a 30-day month uses the 30th.
    """

    id: str
    start: str
    months: int = 0
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0

    @classmethod
    def new(cls, start: datetime) -> ScheduleEntry:
        return cls(id=str(uuid4()), start=start.strftime(SCHEDULE_TIME_FORMAT))

    @property
    def when(self) -> datetime:
        return datetime.strptime(self.start, SCHEDULE_TIME_FORMAT)

    @property
    def repeats(self) -> bool:
        return any((self.months, self.weeks, self.days, self.hours, self.minutes))


SCHEDULE_TIME_FORMAT = "%Y-%m-%dT%H:%M"


@dataclass
class Group:
    """An ordered set of launchers the user can start together."""

    id: str
    name: str
    members: list[GroupMember] = field(default_factory=list)
    # Hover opens this group's launchers only when this is on. Default is collapsed.
    show_contents: bool = False
    # A scheduled group runs on its dates instead of from the Execute Groups
    # list, and shows only in the Schedules list. Turned off, its dates are kept.
    scheduled: bool = False
    schedule: list[ScheduleEntry] = field(default_factory=list)
    # A scheduled group's row in the Schedules list: a click opens it for
    # editing (the default), or runs it now when this is on.
    click_runs: bool = False
    source: str | None = None  # see Launcher.source

    @classmethod
    def new(cls, name: str, members: list[GroupMember] | None = None) -> Group:
        return cls(id=str(uuid4()), name=name, members=list(members or []))


@dataclass
class ContainerMember:
    """One launcher inside a container group."""

    launcher_id: str


@dataclass
class ContainerGroup:
    """A named submenu. Hovering it lists its launchers. It does not run them."""

    id: str
    name: str
    members: list[ContainerMember] = field(default_factory=list)
    source: str | None = None  # see Launcher.source

    @classmethod
    def new(cls, name: str, members: list[ContainerMember] | None = None) -> ContainerGroup:
        return cls(id=str(uuid4()), name=name, members=list(members or []))


class ConfigFormatError(ValueError):
    """The config file is not a JSON object Runner can read at all."""


# Field annotations are strings under `from __future__ import annotations`.
_SCALAR_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "bool": (bool,),
    "int": (int,),
    "str | None": (str, type(None)),
}


def _type_ok(annotation: str, value: Any) -> bool:
    allowed = _SCALAR_TYPES.get(annotation)
    if allowed is None:
        return True
    # bool is a subclass of int. A JSON true must not pass as an int field.
    if annotation == "int" and isinstance(value, bool):
        return False
    return isinstance(value, allowed)


def _from_fields(
    cls,
    data: Any,
    *,
    label: str,
    problems: list[str],
    required: tuple[str, ...] = (),
    skip: tuple[str, ...] = (),
):
    """Build a dataclass from JSON, ignoring keys this version does not know.

    A required field that is missing or has the wrong type drops the whole
    entry and returns None. Any other field with the wrong type falls back to
    its default. Each problem is described in problems.
    """
    if not isinstance(data, dict):
        problems.append(f"{label} is not an object and was skipped.")
        return None
    kwargs: dict[str, Any] = {}
    for item in fields(cls):
        if item.name in skip:
            continue
        if item.name not in data:
            if item.name in required:
                problems.append(f"{label} has no {item.name} and was skipped.")
                return None
            continue
        value = data[item.name]
        if _type_ok(str(item.type), value):
            kwargs[item.name] = value
        elif item.name in required:
            problems.append(f"{label} has an invalid {item.name} and was skipped.")
            return None
        else:
            problems.append(f"{label}: {item.name} had an invalid value and was reset.")
    return cls(**kwargs)


def _members_from(cls, raw: Any, *, label: str, problems: list[str]) -> list:
    if not isinstance(raw, list):
        if raw is not None:
            problems.append(f"{label}: members was not a list and was cleared.")
        return []
    members = []
    seen: set[str] = set()
    for index, entry in enumerate(raw, start=1):
        member = _from_fields(
            cls,
            entry,
            label=f"{label}, member {index}",
            problems=problems,
            required=("launcher_id",),
        )
        if member is None or member.launcher_id in seen:
            continue
        seen.add(member.launcher_id)
        members.append(member)
    return members


def _schedule_from(raw: Any, *, label: str, problems: list[str]) -> list[ScheduleEntry]:
    """A group's dates. One with an unreadable date or a negative repeat is dropped."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        problems.append(f"{label}: schedule was not a list and was cleared.")
        return []
    entries: list[ScheduleEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        where = f"{label}, schedule date {index}"
        entry = _from_fields(ScheduleEntry, item, label=where, problems=problems, required=("id", "start"))
        if entry is None or entry.id in seen:
            continue
        try:
            _ = entry.when
        except ValueError:
            problems.append(f"{where} has an unreadable date and was skipped.")
            continue
        if min(entry.months, entry.weeks, entry.days, entry.hours, entry.minutes) < 0:
            problems.append(f"{where} has a negative repeat and was skipped.")
            continue
        seen.add(entry.id)
        entries.append(entry)
    return entries


def _migrate_main_menu_flags(data: dict[str, Any], launchers: list[Launcher]) -> None:
    """Version 1 kept the main-popup choice in three places. Fold them into show_in_main.

    A launcher was on the main popup only when it was enabled, not Only In
    Groups, and not Only in Container Group in any container. A launcher that
    already has show_in_main is left alone.
    """
    raw_by_id = {
        item["id"]: item
        for item in data.get("launchers", []) or []
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    hidden_by_container: set[str] = set()
    containers = data.get("container_groups", [])
    for group in containers if isinstance(containers, list) else []:
        members = group.get("members", []) if isinstance(group, dict) else []
        for member in members if isinstance(members, list) else []:
            if (
                isinstance(member, dict)
                and member.get("only_in_container") is True
                and isinstance(member.get("launcher_id"), str)
            ):
                hidden_by_container.add(member["launcher_id"])
    for launcher in launchers:
        raw = raw_by_id.get(launcher.id, {})
        if isinstance(raw.get("show_in_main"), bool):
            continue
        launcher.show_in_main = (
            raw.get("enabled", True) is not False
            and raw.get("only_in_groups", False) is not True
            and launcher.id not in hidden_by_container
        )


def _entry_label(kind: str, index: int, entry: Any) -> str:
    name = entry.get("name") if isinstance(entry, dict) else None
    if isinstance(name, str) and name:
        return f"{kind} '{name}'"
    return f"{kind} #{index}"


def _list_of(data: dict[str, Any], key: str, problems: list[str]) -> list:
    raw = data.get(key, [])
    if isinstance(raw, list):
        return raw
    problems.append(f"'{key}' was not a list and was ignored.")
    return []


def _unique_known(ids: list[str], known: set[str]) -> set[str]:
    return {item_id for item_id in ids if item_id in known}


_COPY_SUFFIX = re.compile(r"^(?P<base>.*?)\s*\((?P<n>\d+)\)$")


def duplicate_name(name: str, taken: list[str]) -> str:
    """The name for a copy: the base name and the next free number in brackets.

    "Brave" gives "Brave (1)", then "Brave (2)". Copying "Brave (1)" counts on
    from the same base, so it gives the next free number too, not "Brave (1) (1)".
    """
    match = _COPY_SUFFIX.match(name.strip())
    base = (match.group("base") if match else name).strip() or name.strip()
    highest = 0
    for other in taken:
        found = _COPY_SUFFIX.match(other.strip())
        if found and found.group("base").strip() == base:
            highest = max(highest, int(found.group("n")))
    return f"{base} ({highest + 1})"


def _put(items: list, item) -> None:
    """Append item, or replace the entry with its id."""
    for index, existing in enumerate(items):
        if existing.id == item.id:
            items[index] = item
            return
    items.append(item)


def _insert_after(items: list, index: int, item) -> None:
    items.insert(index + 1 if index >= 0 else len(items), item)


def _copy_member_after(members: list, original_id: str, copy_id: str) -> list:
    """Put the copy straight after the original, with the same flags."""
    result = list(members)
    for index, member in enumerate(result):
        if member.launcher_id == original_id:
            result.insert(index + 1, replace(member, launcher_id=copy_id))
            break
    return result


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
    # dark, bright, or medium. Unknown values display as Dark.
    color_scheme: str = "dark"
    # How solid the arrow and the lists are, from 20 to 100.
    opacity_percent: int = 100
    # How long a list takes to fade after the pointer leaves. 0 is immediate.
    decay_ms: int = 250
    # False until the one-time enlarge below has been saved. Old config files
    # omit this, so they pick up the larger arrow once and then keep any resize.
    applied_visible_trigger_size: bool = False
    # Whether the date dial shows its minute ring. Off, times land on the hour.
    dial_show_minutes: bool = True


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
    version: int = CONFIG_VERSION

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
    def from_dict(cls, data: Any, problems: list[str] | None = None) -> AppConfig:
        """Build a config from parsed JSON.

        Bad entries are skipped, not fatal. Each one is described in problems
        when a list is passed. Raises ConfigFormatError only when data is not
        a JSON object at all.
        """
        if problems is None:
            problems = []
        if not isinstance(data, dict):
            raise ConfigFormatError("The config file does not contain a JSON object.")
        settings = _from_fields(
            Settings, data.get("settings", {}), label="Settings", problems=problems
        ) or Settings()

        launchers: list[Launcher] = []
        launcher_ids: set[str] = set()
        for index, item in enumerate(_list_of(data, "launchers", problems), start=1):
            label = _entry_label("Launcher", index, item)
            launcher = _from_fields(
                Launcher,
                item,
                label=label,
                problems=problems,
                required=("id", "name", "command"),
            )
            if launcher is None:
                continue
            if launcher.id in launcher_ids:
                problems.append(f"{label} repeats an id that is already used and was skipped.")
                continue
            launcher_ids.add(launcher.id)
            launchers.append(launcher)

        groups: list[Group] = []
        group_ids: set[str] = set()
        for index, item in enumerate(_list_of(data, "groups", problems), start=1):
            label = _entry_label("Execute group", index, item)
            if isinstance(item, dict):
                item = {"name": "", **item}
            group = _from_fields(
                Group,
                item,
                label=label,
                problems=problems,
                required=("id",),
                skip=("members", "schedule"),
            )
            if group is None or group.id in group_ids:
                continue
            group_ids.add(group.id)
            group.members = _members_from(
                GroupMember, item.get("members"), label=label, problems=problems
            )
            group.schedule = _schedule_from(item.get("schedule"), label=label, problems=problems)
            groups.append(group)

        container_groups: list[ContainerGroup] = []
        container_ids: set[str] = set()
        for index, item in enumerate(_list_of(data, "container_groups", problems), start=1):
            label = _entry_label("Container group", index, item)
            if isinstance(item, dict):
                item = {"name": "", **item}
            group = _from_fields(
                ContainerGroup,
                item,
                label=label,
                problems=problems,
                required=("id",),
                skip=("members",),
            )
            if group is None or group.id in container_ids:
                continue
            container_ids.add(group.id)
            group.members = _members_from(
                ContainerMember, item.get("members"), label=label, problems=problems
            )
            container_groups.append(group)

        main_order = [
            item for item in _list_of(data, "main_order", problems) if isinstance(item, str)
        ]
        _migrate_main_menu_flags(data, launchers)
        return cls(
            launchers=launchers,
            settings=settings,
            groups=groups,
            container_groups=container_groups,
            main_order=main_order,
            version=CONFIG_VERSION,
        )


def _make_private(path: Path, mode: int) -> None:
    """chmod on macOS and Linux. Windows keeps %APPDATA% private by itself."""
    if sys.platform == "win32":
        return
    with suppress(OSError):
        os.chmod(path, mode)


_LOCK_STATE = threading.local()


@contextmanager
def _config_lock(config_dir: Path):
    """Reentrant per-thread advisory lock serializing config writes across processes."""
    config_dir.mkdir(parents=True, exist_ok=True)
    _make_private(config_dir, 0o700)
    lock_path = (config_dir / ".config.lock").resolve()
    held: dict[Path, int] = getattr(_LOCK_STATE, "held", None)
    if held is None:
        held = {}
        _LOCK_STATE.held = held
    if held.get(lock_path, 0) > 0:
        held[lock_path] += 1
        try:
            yield
        finally:
            held[lock_path] -= 1
        return
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _make_private(lock_path, 0o600)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        held[lock_path] = 1
        try:
            yield
        finally:
            held.pop(lock_path, None)
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


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
        # What the last load had to skip or reset, in words for the user.
        # Empty when the file loaded cleanly.
        self.load_problems: list[str] = []

    @property
    def config(self) -> AppConfig:
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> AppConfig:
        self.load_problems = []
        if not self.config_path.exists():
            self.had_saved_config = False
            cfg = self._create_default()
            self.save(cfg)
            return cfg

        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            problems: list[str] = []
            cfg = AppConfig.from_dict(data, problems)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            # json.JSONDecodeError and ConfigFormatError are ValueErrors.
            # Nothing usable: keep the file aside and start fresh.
            backup = self._backup(move=True)
            where = f" It was moved to {backup}." if backup else ""
            self.load_problems = [
                f"The config file could not be read ({exc}).{where} Runner started with a new config."
            ]
            self.had_saved_config = False
            cfg = self._create_default()
            self.save(cfg)
            return cfg

        self.had_saved_config = True
        if problems:
            # The next save drops what was skipped. Keep the original first.
            backup = self._backup(move=False)
            if backup:
                problems.append(f"The original file was copied to {backup}.")
            self.load_problems = problems
        return cfg

    @contextmanager
    def locked(self):
        """Hold the cross-process config lock across a read-modify-write sequence."""
        with _config_lock(self.config_dir):
            yield

    def save(self, config: AppConfig | None = None) -> None:
        if config is None:
            config = self.config
        with _config_lock(self.config_dir):
            # Unique temp file avoids races with concurrent writers and symlink
            # attacks. mkstemp creates the file with 0o600 on POSIX.
            fd, tmp_name = tempfile.mkstemp(
                dir=self.config_dir, prefix=".config.", suffix=".tmp"
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    _make_private(tmp_path, 0o600)
                    json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.config_path)
            except BaseException:
                with suppress(OSError):
                    tmp_path.unlink(missing_ok=True)
                raise
        self._config = config

    def _create_default(self) -> AppConfig:
        # Will be populated with seed data by the app on first run if empty
        return AppConfig()

    def _backup(self, *, move: bool) -> Path | None:
        """Keep a dated copy of the config file. An earlier backup is never overwritten."""
        if not self.config_path.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.config_path.with_name(f"{self.config_path.stem}.{stamp}.bak.json")
        counter = 1
        while backup.exists():
            backup = self.config_path.with_name(
                f"{self.config_path.stem}.{stamp}-{counter}.bak.json"
            )
            counter += 1
        try:
            if move:
                self.config_path.replace(backup)
            else:
                shutil.copy2(self.config_path, backup)
        except OSError:
            return None
        _make_private(backup, 0o600)
        return backup

    def get_main_view_launchers(self) -> list[Launcher]:
        """Launchers that belong on the main hover list."""
        return [launcher for launcher in self.config.launchers if launcher.show_in_main]

    def reload(self) -> AppConfig:
        """Re-read the file from disk, after an external edit.

        The widgets hold the AppConfig object itself. The new values are copied
        into that same object so every holder sees them, not a stale copy.
        """
        current = self._config
        fresh = self.load()
        if current is None:
            self._config = fresh
            return fresh
        for item in fields(AppConfig):
            setattr(current, item.name, getattr(fresh, item.name))
        # load() may have saved a default config, which points _config at it.
        self._config = current
        return current

    def add_launcher(self, launcher: Launcher) -> None:
        # A screen that duplicated may already have saved this one. Adding it
        # again replaces it in place instead of listing it twice.
        _put(self.config.launchers, launcher)
        self.save()

    def duplicate_launcher(self, launcher_id: str) -> Launcher | None:
        """Save a copy straight after the original, in every list it is in.

        The copy has the next free number in brackets on its name, and is a
        Runner launcher even when the original came from `runner ctl`.
        """
        launchers = self.config.launchers
        index = next((i for i, item in enumerate(launchers) if item.id == launcher_id), -1)
        if index < 0:
            return None
        original = launchers[index]
        copy = replace(
            original,
            id=str(uuid4()),
            name=duplicate_name(original.name, [item.name for item in launchers]),
            source=None,
        )
        _insert_after(launchers, index, copy)
        for group in self.config.groups:
            group.members = _copy_member_after(group.members, original.id, copy.id)
        for group in self.config.container_groups:
            group.members = _copy_member_after(group.members, original.id, copy.id)
        self._order_copy_after("launcher", original.id, copy.id)
        self.save()
        return copy

    def _order_copy_after(self, kind: str, original_id: str, copy_id: str) -> None:
        """Put the copy's main-popup row under the original's, once the user has an order."""
        order = self.config.main_order
        token = f"{kind}:{original_id}"
        if token in order:
            order.insert(order.index(token) + 1, f"{kind}:{copy_id}")

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
        _put(self.config.groups, group)
        self.save()

    def duplicate_group(self, group_id: str) -> Group | None:
        """Save a copy of an execute group or schedule straight after it."""
        groups = self.config.groups
        index = next((i for i, item in enumerate(groups) if item.id == group_id), -1)
        if index < 0:
            return None
        original = groups[index]
        copy = replace(
            original,
            id=str(uuid4()),
            name=duplicate_name(original.name, [item.name for item in groups]),
            members=[replace(member) for member in original.members],
            schedule=[replace(entry, id=str(uuid4())) for entry in original.schedule],
            source=None,
        )
        _insert_after(groups, index, copy)
        self.save()
        return copy

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
        _put(self.config.container_groups, group)
        self.save()

    def duplicate_container_group(self, group_id: str) -> ContainerGroup | None:
        """Save a copy of a container group straight after it."""
        groups = self.config.container_groups
        index = next((i for i, item in enumerate(groups) if item.id == group_id), -1)
        if index < 0:
            return None
        original = groups[index]
        copy = replace(
            original,
            id=str(uuid4()),
            name=duplicate_name(original.name, [item.name for item in groups]),
            members=[replace(member) for member in original.members],
            source=None,
        )
        _insert_after(groups, index, copy)
        self._order_copy_after("container", original.id, copy.id)
        self.save()
        return copy

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
        for launcher in self.config.launchers:
            if launcher.id == launcher_id:
                launcher.show_in_main = shown
                self.save()
                return

    def set_launcher_membership(
        self,
        launcher_id: str,
        container_ids: list[str],
        execute_ids: list[str],
    ) -> None:
        """Put this launcher in exactly these container and execute groups.

        A membership that stays keeps its place and its Concurrent flag.
        """
        container_keep = _unique_known(
            container_ids, {group.id for group in self.config.container_groups}
        )
        execute_keep = _unique_known(
            execute_ids, {group.id for group in self.config.groups}
        )
        for group in self.config.container_groups:
            group.members = _sync_members(
                group.members,
                launcher_id,
                group.id in container_keep,
                lambda: ContainerMember(launcher_id),
            )
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

    def update_settings(self, *, save: bool = True, **kwargs: Any) -> None:
        """Change settings. save=False leaves the write to the caller, for slider drags."""
        for k, v in kwargs.items():
            if hasattr(self.config.settings, k):
                setattr(self.config.settings, k, v)
        if save:
            self.save()
