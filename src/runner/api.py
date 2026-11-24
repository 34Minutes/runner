"""What programs outside Runner may do to its launchers, groups and containers.

This is the one place the rules live. `runner ctl` sends requests here, through
the running app's private socket or, when Runner is closed, straight to the
config file. Nothing in this module touches Qt.

A request is a JSON object:

    {"op": "launcher.add", "source": "claude", "data": {"name": ..., "command": ...}}
    {"op": "group.update", "source": "claude", "ref": "Release", "data": {...}}
    {"op": "launcher.list", "filter": {"source": "claude"}}

and the reply is {"ok": true, "result": ...} or {"ok": false, "error": "..."}.

The rules, because a launcher is a command Runner will run:

- Every change names its `source`, the program making it. What a source makes
  is stamped with that name, and only the same source can change or delete it
  from outside. Everything made in Runner itself is read-only from outside.
- Nothing here runs a launcher or a group. Running stays with the user.
- A launcher can't be set to run as administrator from outside.
- A group can be given dates, but only the user turns its Schedule switch on.
  A scheduled group, and the command of a launcher one runs, can't be changed
  from outside; the user turns the schedule off first.

Items are found by `ref`: an id, or a name (any case). A name two items share
is an error that lists their ids.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from . import __version__
from .config import (
    SCHEDULE_TIME_FORMAT,
    ConfigManager,
    ContainerGroup,
    ContainerMember,
    Group,
    GroupMember,
    Launcher,
    ScheduleEntry,
)

PROTOCOL = 1
SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,39}$")

LAUNCHER_FIELDS = {
    "name": str,
    "command": str,
    "args": str,
    "working_dir": (str, type(None)),
    "show_in_main": bool,
    "show_console": bool,
}
GROUP_FIELDS = {
    "name": str,
    "launchers": list,
    "show_contents": bool,
    "click_runs": bool,
    "schedule": list,
    "scheduled": bool,
}
CONTAINER_FIELDS = {"name": str, "launchers": list}
REPEAT_FIELDS = ("months", "weeks", "days", "hours", "minutes")
# The interval rollers' ranges, so a repeat set from outside reads the same on them.
REPEAT_LIMITS = {"months": 99, "weeks": 3, "days": 6, "hours": 23, "minutes": 59}
# What a launcher in a scheduled group may not have changed from outside.
RUN_FIELDS = ("command", "args", "working_dir")

KINDS = ("launcher", "group", "container")
VERBS = ("list", "get", "add", "update", "upsert", "delete")
WRITE_VERBS = ("add", "update", "upsert", "delete")


class ApiError(Exception):
    """A request that can't be done, in words for whoever sent it."""


@dataclass
class Outcome:
    reply: dict[str, Any]
    changed: bool = False


def is_write(request: Any) -> bool:
    op = request.get("op", "") if isinstance(request, dict) else ""
    return isinstance(op, str) and op.rpartition(".")[2] in WRITE_VERBS


class RunnerApi:
    def __init__(self, cfg: ConfigManager) -> None:
        self.cfg = cfg

    # ------------------------------------------------------------ entry

    def handle(self, request: Any) -> dict[str, Any]:
        return self.execute(request).reply

    def execute(self, request: Any) -> Outcome:
        try:
            result, changed = self._dispatch(request)
        except ApiError as problem:
            return Outcome({"ok": False, "error": str(problem)})
        return Outcome({"ok": True, "result": result}, changed)

    def _dispatch(self, request: Any) -> tuple[Any, bool]:
        if not isinstance(request, dict):
            raise ApiError("A request is a JSON object.")
        op = request.get("op")
        if op == "ping":
            return {"app": "Runner", "version": __version__, "protocol": PROTOCOL}, False
        if not isinstance(op, str) or op.count(".") != 1:
            raise ApiError(f"Unknown op {op!r}. Try launcher.list, group.add, container.delete, ...")
        kind, verb = op.split(".")
        if kind not in KINDS or verb not in VERBS:
            raise ApiError(f"Unknown op {op!r}. Kinds: {', '.join(KINDS)}. Verbs: {', '.join(VERBS)}.")
        if verb == "list":
            return self._list(kind, request.get("filter") or {}), False
        if verb == "get":
            return self._describe(kind, self._find(kind, request.get("ref"))), False
        source = _source(request.get("source"))
        data = request.get("data") or {}
        if verb == "add":
            return self._add(kind, source, data), True
        if verb == "delete":
            return self._delete(kind, source, request.get("ref")), True
        if verb == "update":
            item = self._find(kind, request.get("ref"))
            return self._update(kind, source, item, data), True
        # upsert: update this source's item with that name, or add it.
        name = data.get("name") if isinstance(data, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ApiError("upsert needs data.name: it finds the item by name.")
        mine = [item for item in self._items(kind) if item.source == source and _same(item.name, name)]
        if len(mine) > 1:
            raise ApiError(f"{source} has {len(mine)} {kind}s named {name!r}: {_ids(mine)}. Use update with an id.")
        if mine:
            return self._update(kind, source, mine[0], data), True
        return self._add(kind, source, data), True

    # ------------------------------------------------------------ reading

    def _items(self, kind: str) -> list:
        config = self.cfg.config
        return {"launcher": config.launchers, "group": config.groups, "container": config.container_groups}[kind]

    def _find(self, kind: str, ref: Any, items: list | None = None):
        if not isinstance(ref, str) or not ref.strip():
            raise ApiError(f"Say which {kind}: give its id or name as ref.")
        items = self._items(kind) if items is None else items
        for item in items:
            if item.id == ref:
                return item
        named = [item for item in items if _same(item.name, ref)]
        if len(named) > 1:
            raise ApiError(f"{len(named)} {kind}s are named {ref!r}: {_ids(named)}. Use the id.")
        if not named:
            raise ApiError(f"No {kind} has the id or name {ref!r}.")
        return named[0]

    def _list(self, kind: str, filters: Any) -> list[dict[str, Any]]:
        if not isinstance(filters, dict):
            raise ApiError("filter is a JSON object, for example {\"source\": \"claude\"}.")
        items = self._items(kind)
        if "source" in filters:
            items = [item for item in items if item.source == filters["source"]]
        return [self._describe(kind, item) for item in items]

    def _describe(self, kind: str, item) -> dict[str, Any]:
        if kind == "launcher":
            out = asdict(item)
            out["groups"] = [g.name for g in self.cfg.config.groups if _has(g, item.id)]
            out["containers"] = [c.name for c in self.cfg.config.container_groups if _has(c, item.id)]
            return out
        names = {launcher.id: launcher.name for launcher in self.cfg.config.launchers}
        out: dict[str, Any] = {"id": item.id, "name": item.name, "source": item.source}
        if kind == "group":
            out["launchers"] = [
                {"id": m.launcher_id, "name": names.get(m.launcher_id, "?"), "concurrent": m.concurrent}
                for m in item.members
            ]
            out["show_contents"] = item.show_contents
            out["scheduled"] = item.scheduled
            out["click_runs"] = item.click_runs
            out["schedule"] = [
                {"start": e.start, **{unit: getattr(e, unit) for unit in REPEAT_FIELDS if getattr(e, unit)}}
                for e in item.schedule
            ]
        else:
            out["launchers"] = [{"id": m.launcher_id, "name": names.get(m.launcher_id, "?")} for m in item.members]
        return out

    # ------------------------------------------------------------ writing

    def _add(self, kind: str, source: str, data: Any):
        data = _fields(kind, data)
        name = data.get("name", "")
        if not isinstance(name, str) or not name.strip():
            raise ApiError(f"A new {kind} needs a name.")
        if kind == "launcher":
            command = data.get("command", "")
            if not command.strip():
                raise ApiError("A new launcher needs a command.")
            launcher = Launcher.new(name.strip(), command.strip(), source=source)
            self._apply_launcher(launcher, data)
            self.cfg.add_launcher(launcher)
            return self._describe(kind, launcher)
        if kind == "group":
            group = Group.new(name.strip())
            group.source = source
            self._apply_group(group, data)
            self.cfg.add_group(group)
            return self._describe(kind, group)
        container = ContainerGroup.new(name.strip())
        container.source = source
        self._apply_container(container, data)
        self.cfg.add_container_group(container)
        return self._describe(kind, container)

    def _update(self, kind: str, source: str, item, data: Any):
        data = _fields(kind, data)
        self._check_owner(kind, source, item)
        if "name" in data and not data["name"].strip():
            raise ApiError("A name can't be empty.")
        if kind == "launcher":
            changing_run = [key for key in RUN_FIELDS if key in data and data[key] != getattr(item, key)]
            scheduled = [g.name for g in self.cfg.config.groups if g.scheduled and _has(g, item.id)]
            if changing_run and scheduled:
                raise ApiError(
                    f"{item.name!r} runs on a schedule ({', '.join(scheduled)}), so its "
                    f"{', '.join(changing_run)} can't be changed from outside Runner. "
                    "Turn that schedule's Schedule switch off in Runner first."
                )
            if "command" in data and not data["command"].strip():
                raise ApiError("A command can't be empty.")
            self._apply_launcher(item, data)
            self.cfg.update_launcher(item)
        elif kind == "group":
            if item.scheduled:
                raise ApiError(
                    f"{item.name!r} is scheduled, so it can't be changed from outside Runner. "
                    "Turn its Schedule switch off in Runner first."
                )
            self._apply_group(item, data)
            self.cfg.update_group(item)
        else:
            self._apply_container(item, data)
            self.cfg.update_container_group(item)
        return self._describe(kind, item)

    def _delete(self, kind: str, source: str, ref: Any):
        item = self._find(kind, ref)
        self._check_owner(kind, source, item)
        if kind == "launcher":
            self.cfg.remove_launcher(item.id)
        elif kind == "group":
            self.cfg.remove_group(item.id)
        else:
            self.cfg.remove_container_group(item.id)
        return {"id": item.id, "name": item.name, "deleted": True}

    def _check_owner(self, kind: str, source: str, item) -> None:
        if item.source is None:
            raise ApiError(
                f"{item.name!r} was made in Runner, so it can't be changed from outside. "
                f"Add a {kind} of your own instead."
            )
        if item.source != source:
            raise ApiError(f"{item.name!r} belongs to {item.source!r}, not {source!r}.")

    def _apply_launcher(self, launcher: Launcher, data: dict[str, Any]) -> None:
        for key, value in data.items():
            setattr(launcher, key, value.strip() if key in ("name", "command") else value)
        if launcher.working_dir is not None and not launcher.working_dir.strip():
            launcher.working_dir = None

    def _members(self, refs: list) -> list[tuple[str, bool]]:
        out: list[tuple[str, bool]] = []
        for ref in refs:
            concurrent = False
            if isinstance(ref, dict):
                extra = set(ref) - {"ref", "concurrent"}
                if extra:
                    raise ApiError(f"A group's launcher takes ref and concurrent, not {', '.join(sorted(extra))}.")
                concurrent = ref.get("concurrent", False)
                if not isinstance(concurrent, bool):
                    raise ApiError("concurrent is true or false.")
                ref = ref.get("ref")
            launcher = self._find("launcher", ref)
            if any(launcher.id == seen for seen, _ in out):
                raise ApiError(f"{launcher.name!r} is listed twice.")
            out.append((launcher.id, concurrent))
        return out

    def _apply_group(self, group: Group, data: dict[str, Any]) -> None:
        if data.get("scheduled"):
            raise ApiError(
                "Only you can turn a group's Schedule switch on, in Runner. "
                "Give it dates with schedule and leave scheduled off."
            )
        if "name" in data:
            group.name = data["name"].strip()
        if "launchers" in data:
            group.members = [GroupMember(lid, concurrent=c) for lid, c in self._members(data["launchers"])]
        if "show_contents" in data:
            group.show_contents = data["show_contents"]
        if "click_runs" in data:
            group.click_runs = data["click_runs"]
        if "schedule" in data:
            group.schedule = [_schedule_entry(raw) for raw in data["schedule"]]

    def _apply_container(self, container: ContainerGroup, data: dict[str, Any]) -> None:
        if "name" in data:
            container.name = data["name"].strip()
        if "launchers" in data:
            members = self._members(data["launchers"])
            if any(concurrent for _, concurrent in members):
                raise ApiError("A container only lists launchers; concurrent is for groups.")
            container.members = [ContainerMember(lid) for lid, _ in members]


# ---------------------------------------------------------------- helpers


def _source(value: Any) -> str:
    if not isinstance(value, str) or not SOURCE_PATTERN.match(value):
        raise ApiError(
            "Every change needs a source: a short name for the program making it, "
            "such as \"claude\" (letters, digits, space, . _ -; up to 40)."
        )
    return value


def _fields(kind: str, data: Any) -> dict[str, Any]:
    allowed = {"launcher": LAUNCHER_FIELDS, "group": GROUP_FIELDS, "container": CONTAINER_FIELDS}[kind]
    if not isinstance(data, dict):
        raise ApiError("data is a JSON object.")
    if kind == "launcher" and "run_as_admin" in data:
        raise ApiError("run_as_admin can't be set from outside Runner. Turn it on in the launcher's own screen.")
    for key, value in data.items():
        if key not in allowed:
            raise ApiError(f"A {kind} has no field {key!r}. Fields: {', '.join(allowed)}.")
        expected = allowed[key]
        if not isinstance(value, expected) or (expected is not bool and isinstance(value, bool)):
            raise ApiError(f"{key} has the wrong type ({type(value).__name__}).")
    return data


def _schedule_entry(raw: Any) -> ScheduleEntry:
    if not isinstance(raw, dict) or not isinstance(raw.get("start"), str):
        raise ApiError('A schedule date is {"start": "YYYY-MM-DDTHH:MM", "weeks": 1, ...}.')
    extra = set(raw) - {"start", *REPEAT_FIELDS}
    if extra:
        raise ApiError(f"A schedule date has no {', '.join(sorted(extra))}. Repeats: {', '.join(REPEAT_FIELDS)}.")
    try:
        when = datetime.strptime(raw["start"], SCHEDULE_TIME_FORMAT)
    except ValueError:
        raise ApiError(f"{raw['start']!r} is not a date like 2026-11-24T09:30.") from None
    entry = ScheduleEntry.new(when)
    for unit in REPEAT_FIELDS:
        value = raw.get(unit, 0)
        top = REPEAT_LIMITS[unit]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= top:
            raise ApiError(f"{unit} is a whole number from 0 to {top} (more carries into the next unit).")
        setattr(entry, unit, value)
    return entry


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


def _has(group, launcher_id: str) -> bool:
    return any(member.launcher_id == launcher_id for member in group.members)


def _ids(items: list) -> str:
    return ", ".join(item.id for item in items)
