"""Run scheduled execute groups when their dates come round.

One timer waits for the soonest run, and never longer than a minute, so a
change to the clock or a wake from sleep is noticed soon. Each time it fires,
every scheduled group with a run since the last check is started once.

Missed runs are skipped. Runs before Runner started are never looked at, and
a run noticed more than GRACE after it fell due, such as on waking from
sleep, is passed over and the schedule carries on from the next one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer

from .config import Group
from .schedule import due_between, group_next_run

GRACE = timedelta(minutes=2)
MAX_WAIT_MS = 60_000


class Scheduler(QObject):
    def __init__(
        self,
        groups: Callable[[], list[Group]],
        run: Callable[[Group], None],
        *,
        now: Callable[[], datetime] = datetime.now,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._groups = groups
        self._run = run
        self._now = now
        self._since: datetime | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self.check)

    def start(self) -> None:
        """Begin watching from now. Anything due before this is not run."""
        self._since = self._now()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()
        self._since = None

    def is_waiting(self) -> bool:
        return self._timer.isActive()

    def wait_ms(self) -> int:
        return self._timer.remainingTime() if self._timer.isActive() else -1

    def _scheduled(self) -> list[Group]:
        return [group for group in self._groups() if group.scheduled and group.schedule]

    def refresh(self) -> None:
        """Wait for the soonest run. Call after any schedule changes."""
        if self._since is None:
            return
        runs = [run for run in (group_next_run(group, self._since) for group in self._scheduled()) if run]
        if not runs:
            self._timer.stop()
            return
        wait = (min(runs) - self._now()).total_seconds() * 1000
        self._timer.start(int(max(0, min(wait, MAX_WAIT_MS))))

    def check(self) -> None:
        """Start each group with a run since the last check, then wait for the next."""
        if self._since is None:
            return
        now = self._now()
        since, self._since = self._since, now
        for group in self._scheduled():
            due = [run for run in (due_between(entry, since, now) for entry in group.schedule) if run]
            if due and now - max(due) <= GRACE:
                self._run(group)
        self.refresh()
