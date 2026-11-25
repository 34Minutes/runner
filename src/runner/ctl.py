"""`runner ctl`: add, change and remove launchers, groups and containers from outside Runner.

It sends one request to the running Runner over its private socket (see
runner.instance and runner.api) and prints the answer. When Runner isn't
running it makes the change in the config file itself, with the same rules.

    runner ctl launcher add --name "Build & deploy" --command ./scripts/build-mac.sh \\
        --args --deploy --cwd ~/Projects/runner
    runner ctl group upsert --name Release --launcher "Build & deploy"
    runner ctl launcher list --mine --json
    runner ctl raw '{"op": "group.get", "ref": "Release"}'

`runner ctl guide` prints ctl_guide.md, the full guide written for LLMs.

Every change is made in the name of a source (--as, default "cli"). Only that
source can change or delete what it made, and nothing made in Runner itself
can be changed from here. Nothing here runs a launcher: running stays with you.

Exit status: 0 done, 1 Runner refused it (the reason is printed),
2 the command line was wrong, 3 Runner is running but did not answer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .api import KINDS, REPEAT_FIELDS, RunnerApi
from .config import SCHEDULE_TIME_FORMAT
from .instance import REQUEST_TIMEOUT_MS, SINGLE_INSTANCE_SERVER

EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_NO_ANSWER = 0, 1, 2, 3
DEFAULT_SOURCE = "cli"
_EVERY = re.compile(r"(\d+)\s*(months?|mo|weeks?|w|days?|d|hours?|h|minutes?|mins?|m)\b", re.I)
_EVERY_UNIT = {"mo": "months", "w": "weeks", "d": "days", "h": "hours", "m": "minutes", "min": "minutes"}


class NoAnswer(Exception):
    """Runner took the connection but sent nothing back."""


def guide_text() -> str:
    """The guide for LLMs and scripts, shipped beside this module."""
    return Path(__file__).with_name("ctl_guide.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ transport


def send(request: dict[str, Any], *, timeout_ms: int = REQUEST_TIMEOUT_MS) -> tuple[dict[str, Any], bool]:
    """(reply, True) from the running Runner, or (reply, False) done on the config file.

    Raises NoAnswer when Runner is running but does not answer, for example an
    older version that only knows "show yourself".
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtNetwork import QLocalSocket

    if QCoreApplication.instance() is None:
        _app = QCoreApplication([])  # noqa: F841 - Qt networking wants one
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if not socket.waitForConnected(500):
        err = socket.error()
        socket.abort()
        if err in (
            QLocalSocket.LocalSocketError.ServerNotFoundError,
            QLocalSocket.LocalSocketError.ConnectionRefusedError,
        ):
            return _offline(request), False
        raise NoAnswer(
            "Runner is running but did not accept the connection in time. "
            "Close any open Runner window and try again."
        )
    socket.write(json.dumps(request).encode("utf-8") + b"\n")
    socket.waitForBytesWritten(timeout_ms)
    data = bytearray()
    while b"\n" not in data:
        if not socket.waitForReadyRead(timeout_ms):
            data += bytes(socket.readAll().data())
            break
        data += bytes(socket.readAll().data())
    socket.abort()
    line = bytes(data).split(b"\n", 1)[0].strip()
    if not line:
        raise NoAnswer(
            "Runner is running but did not answer. It may be a version from before "
            "`runner ctl` existed: update it, or quit it and try again."
        )
    try:
        return json.loads(line.decode("utf-8")), True
    except (UnicodeDecodeError, ValueError):
        raise NoAnswer("Runner answered with something that is not JSON.") from None


def _offline(request: dict[str, Any]) -> dict[str, Any]:
    from .config import ConfigManager

    cfg = ConfigManager()
    with cfg.locked():
        return RunnerApi(cfg).handle(request)


# ------------------------------------------------------------------ command line


class _AppendMember(argparse.Action):
    """--launcher and --concurrent both add to one ordered list of members."""

    def __call__(self, parser, namespace, value, option_string=None):
        members = list(getattr(namespace, "members", None) or [])
        members.append({"ref": value, "concurrent": option_string == "--concurrent"})
        namespace.members = members


def _flag_pair(parser: argparse.ArgumentParser, name: str, help_on: str, help_off: str) -> None:
    dest = name.replace("-", "_")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{name}", dest=dest, action="store_true", default=None, help=help_on)
    group.add_argument(f"--no-{name}", dest=dest, action="store_false", help=help_off)


def _launcher_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--name", help="what the launcher is called")
    parser.add_argument("--command", help="the program, script, file or URL to open")
    parser.add_argument("--args", help="arguments for the command, as one string")
    parser.add_argument("--cwd", help="folder to start in (empty: the default)")
    _flag_pair(parser, "show-in-main", "show it on the main list (the default for new ones)",
               "keep it off the main list; it still runs in its groups")
    _flag_pair(parser, "show-console", "show a console window (Windows)", "no console window")


def _group_fields(parser: argparse.ArgumentParser, kind: str) -> None:
    parser.add_argument("--name", help=f"what the {kind} is called")
    member_help = "a launcher's name or id, in order; repeat for more"
    parser.add_argument("--launcher", action=_AppendMember, metavar="REF", help=member_help)
    parser.add_argument("--clear-launchers", action="store_true", help="leave it with no launchers")
    if kind == "container":
        return
    parser.add_argument("--concurrent", action=_AppendMember, metavar="REF",
                        help="like --launcher, but starts together with the one before it")
    _flag_pair(parser, "show-contents", "hovering it lists its launchers", "hovering does not")
    _flag_pair(parser, "click-runs", "once you schedule it, clicking it in Schedules runs it",
               "once you schedule it, clicking it opens it to edit")
    parser.add_argument("--date", action="append", metavar="WHEN",
                        help='a date it runs on, like "2026-11-25 09:00" or "25 Nov 9am"; repeat for more. '
                             "Only you can turn its Schedule switch on, in Runner")
    parser.add_argument("--every", action="append", metavar="INTERVAL",
                        help='how often the --date before it repeats, like "1 week" or "1d 12h"')
    parser.add_argument("--clear-dates", action="store_true", help="remove all its dates")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="runner ctl",
        description="Add, change and remove Runner's launchers, groups and containers from outside it.",
        epilog="New here? Run `runner ctl guide` first. Items are found by id or name. Changes are made "
               "as --as (default cli); only that source can change or delete them later, and items made "
               "in Runner can't be changed here.",
    )
    parser.add_argument("--as", dest="source", default=DEFAULT_SOURCE, metavar="SOURCE",
                        help="the name to make changes as, such as claude (default: cli)")
    parser.add_argument("--json", action="store_true", help="print Runner's full JSON reply")
    kinds = parser.add_subparsers(dest="kind", required=True, metavar="{guide,launcher,group,container,ping,raw}")
    kinds.add_parser("guide", help="print the full guide: rules, fields, examples (read this first)")
    kinds.add_parser("ping", help="check Runner answers, and its version")
    raw = kinds.add_parser("raw", help="send one JSON request as it is (see runner ctl guide)")
    raw.add_argument("request", help="the request, or - to read it from stdin")

    for kind in KINDS:
        sub = kinds.add_parser(kind, help=f"{kind}s").add_subparsers(dest="verb", required=True)
        listing = sub.add_parser("list", help=f"list {kind}s")
        listing.add_argument("--mine", action="store_true", help="only the ones --as made")
        listing.add_argument("--source", dest="filter_source", help="only the ones this source made")
        sub.add_parser("get", help=f"show one {kind}").add_argument("ref", help="its id or name")
        sub.add_parser("delete", help=f"delete a {kind} you made").add_argument("ref", help="its id or name")
        for verb, text in (("add", "add a new one"), ("update", "change one you made"),
                           ("upsert", "change yours with this --name, or add it")):
            p = sub.add_parser(verb, help=text)
            if verb == "update":
                p.add_argument("ref", help="its id or name")
            if kind == "launcher":
                _launcher_fields(p)
            else:
                _group_fields(p, kind)
            p.add_argument("--data", metavar="JSON", help="more fields as a JSON object, merged in last")
    _anywhere(parser)
    return parser


def _anywhere(parser: argparse.ArgumentParser) -> None:
    """--as and --json work after the command too, where people (and LLMs) often put them."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                if not any(isinstance(a, argparse._SubParsersAction) for a in sub._actions):
                    sub.add_argument("--as", dest="source", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
                    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                                     help=argparse.SUPPRESS)
                _anywhere(sub)


def parse_every(text: str) -> dict[str, int]:
    """'1 week', '1d 12h', '2 months' -> {'weeks': 1} and so on."""
    out: dict[str, int] = {}
    rest = text
    for match in _EVERY.finditer(text):
        word = match.group(2).lower()
        unit = next((u for u in REPEAT_FIELDS if word in (u, u[:-1])), None)
        unit = unit or _EVERY_UNIT.get(word) or _EVERY_UNIT.get(word.rstrip("s"))
        out[unit] = out.get(unit, 0) + int(match.group(1))
        rest = rest.replace(match.group(0), "", 1)
    if not out or rest.strip(" ,and"):
        raise ValueError(f"Can't read {text!r} as an interval. Try \"1 week\" or \"1d 12h\".")
    return out


def _pair_dates(argv: list[str]) -> list[tuple[str, str | None]]:
    """[(date, every or None)] in the order they were typed."""
    pairs: list[list[Any]] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        key, _, inline = arg.partition("=")
        if key in ("--date", "--every"):
            value = inline if inline else (argv[i + 1] if i + 1 < len(argv) else "")
            i += 1 if inline else 2
            if key == "--date":
                pairs.append([value, None])
            elif not pairs or pairs[-1][1] is not None:
                raise ValueError("Each --every follows the --date it belongs to.")
            else:
                pairs[-1][1] = value
            continue
        i += 1
    return [(date, every) for date, every in pairs]


def request_for(args: argparse.Namespace, argv: list[str]) -> dict[str, Any]:
    if args.kind == "ping":
        return {"op": "ping"}
    if args.kind == "raw":
        text = sys.stdin.read() if args.request == "-" else args.request
        request = json.loads(text)
        if isinstance(request, dict) and "source" not in request:
            request["source"] = args.source
        return request
    op = f"{args.kind}.{args.verb}"
    if args.verb == "list":
        source = args.source if args.mine else args.filter_source
        return {"op": op, "filter": {"source": source} if source else {}}
    request: dict[str, Any] = {"op": op, "source": args.source}
    if args.verb in ("get", "delete", "update"):
        request["ref"] = args.ref
    if args.verb in ("get", "delete"):
        return request
    data: dict[str, Any] = {}
    if args.kind == "launcher":
        for key in ("name", "command", "args"):
            if getattr(args, key) is not None:
                data[key] = getattr(args, key)
        if args.cwd is not None:
            data["working_dir"] = args.cwd or None
        for key in ("show_in_main", "show_console"):
            if getattr(args, key) is not None:
                data[key] = getattr(args, key)
    else:
        if args.name is not None:
            data["name"] = args.name
        members = getattr(args, "members", None)
        if args.clear_launchers:
            data["launchers"] = []
        elif members:
            data["launchers"] = members if args.kind == "group" else [m["ref"] for m in members]
        if args.kind == "group":
            for key in ("show_contents", "click_runs"):
                if getattr(args, key) is not None:
                    data[key] = getattr(args, key)
            if args.clear_dates:
                data["schedule"] = []
            elif args.date:
                from .schedule import parse_when

                now = datetime.now().replace(second=0, microsecond=0)
                schedule = []
                for date, every in _pair_dates(argv):
                    entry: dict[str, Any] = {"start": parse_when(date, now).strftime(SCHEDULE_TIME_FORMAT)}
                    if every:
                        entry.update(parse_every(every))
                    schedule.append(entry)
                data["schedule"] = schedule
    if args.data:
        extra = json.loads(args.data)
        if not isinstance(extra, dict):
            raise ValueError("--data is a JSON object.")
        data.update(extra)
    request["data"] = data
    return request


# ------------------------------------------------------------------ output


def _line(kind: str, item: dict[str, Any]) -> str:
    mark = f"  [{item['source']}]" if item.get("source") else ""
    if kind == "launcher":
        command = " ".join(part for part in (item["command"], item.get("args") or "") if part)
        return f"{item['name']}  ->  {command}{mark}  ({item['id']})"
    names = ", ".join(("+ " if m.get("concurrent") else "") + m["name"] for m in item["launchers"]) or "no launchers"
    extra = ""
    if kind == "group":
        if item["scheduled"]:
            extra = "  scheduled"
        elif item["schedule"]:
            extra = f"  {len(item['schedule'])} date(s), not scheduled"
    return f"{item['name']}: {names}{extra}{mark}  ({item['id']})"


def describe(request: dict[str, Any], reply: dict[str, Any]) -> str:
    result = reply.get("result")
    op = request.get("op", "")
    kind, _, verb = op.partition(".")
    if op == "ping":
        return f"Runner {result['version']} is answering."
    if kind not in KINDS:
        return json.dumps(result, indent=2, ensure_ascii=False)
    if verb == "list":
        return "\n".join(_line(kind, item) for item in result) or f"No {kind}s."
    if verb == "delete":
        return f"Deleted {kind} {result['name']!r}."
    if verb == "get":
        return json.dumps(result, indent=2, ensure_ascii=False)
    done = {"add": "Added", "update": "Updated", "upsert": "Saved"}[verb]
    return f"{done} {kind}: {_line(kind, result)}"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code == 0 else EXIT_USAGE
    if args.kind == "guide":
        print(guide_text())
        return EXIT_OK
    try:
        request = request_for(args, argv)
    except ValueError as problem:
        print(f"runner ctl: {problem}", file=sys.stderr)
        return EXIT_USAGE
    try:
        reply, live = send(request)
    except NoAnswer as problem:
        print(f"runner ctl: {problem}", file=sys.stderr)
        return EXIT_NO_ANSWER
    if not live and request.get("op") == "ping":
        print("Runner isn't running.", file=sys.stderr)
        return EXIT_REFUSED
    if not live:
        print("runner ctl: Runner isn't running, so the config file was used directly.", file=sys.stderr)
    if args.json:
        print(json.dumps(reply, indent=2, ensure_ascii=False))
    elif reply.get("ok"):
        print(describe(request, reply))
    else:
        print(f"runner ctl: {reply.get('error', 'Runner refused that.')}", file=sys.stderr)
    return EXIT_OK if reply.get("ok") else EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
