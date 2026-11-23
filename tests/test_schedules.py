"""Schedules: execute groups that run on dates instead of from the Execute Groups list."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel, QPushButton

from runner.config import AppConfig, ConfigManager, Group, GroupMember, Launcher, ScheduleEntry
from runner.schedule import (
    NO_REPEAT,
    add_months,
    describe_repeat,
    due_between,
    format_when,
    next_run,
)
from runner.scheduler import GRACE, MAX_WAIT_MS, Scheduler
from runner.ui.group_dialog import SCHEDULE_NOTE, GroupDialog
from runner.ui.group_manager import GroupManagerDialog, ScheduleManagerDialog
from runner.ui.schedule_editor import ScheduleEditor
from runner.ui.schedule_pickers import (
    DatePickerDialog,
    IntervalPickerDialog,
    apply_total,
    entry_total,
    next_quarter_hour,
)


def _entry(when: datetime, **repeat) -> ScheduleEntry:
    entry = ScheduleEntry.new(when)
    for name, value in repeat.items():
        setattr(entry, name, value)
    return entry


# ------------------------------------------------------------------ the maths


def test_a_month_later_keeps_the_day_or_uses_the_last_one():
    assert add_months(datetime(2026, 1, 31, 9), 1) == datetime(2026, 2, 28, 9)
    assert add_months(datetime(2028, 1, 31, 9), 1) == datetime(2028, 2, 29, 9)
    assert add_months(datetime(2026, 11, 15, 9), 3) == datetime(2027, 2, 15, 9)


def test_monthly_from_the_31st_goes_back_to_the_31st_after_a_short_month():
    entry = _entry(datetime(2026, 1, 31, 9), months=1)
    assert next_run(entry, datetime(2026, 2, 1)) == datetime(2026, 2, 28, 9)
    assert next_run(entry, datetime(2026, 2, 28, 9)) == datetime(2026, 3, 31, 9)


def test_weekly_counts_forward_from_the_date_picked():
    entry = _entry(datetime(2026, 11, 24, 9), weeks=1)
    assert next_run(entry, datetime(2026, 11, 20)) == datetime(2026, 11, 24, 9)
    assert next_run(entry, datetime(2026, 11, 24, 9)) == datetime(2026, 12, 1, 9)
    far = next_run(entry, datetime(2029, 6, 1))
    assert far.weekday() == datetime(2026, 11, 24).weekday() and far.hour == 9


def test_a_date_that_does_not_repeat_runs_once():
    entry = _entry(datetime(2026, 11, 24, 9))
    assert next_run(entry, datetime(2026, 11, 24, 8, 59)) == datetime(2026, 11, 24, 9)
    assert next_run(entry, datetime(2026, 11, 24, 9)) is None


def test_mixed_repeats_add_calendar_months_and_exact_time():
    entry = _entry(datetime(2026, 1, 31, 8), months=1, days=1, hours=2)
    assert next_run(entry, datetime(2026, 1, 31, 8)) == datetime(2026, 3, 1, 10)  # 28 Feb + 1 day 2 h


def test_repeats_read_as_a_sentence():
    assert describe_repeat(_entry(datetime(2026, 1, 1))) == NO_REPEAT == "Does not repeat"
    assert describe_repeat(_entry(datetime(2026, 1, 1), weeks=1)) == "Every 1 week"
    assert describe_repeat(_entry(datetime(2026, 1, 1), days=1, hours=12)) == "Every 1 day and 12 hours"
    assert describe_repeat(_entry(datetime(2026, 1, 1), months=2, weeks=1, minutes=30)) == (
        "Every 2 months, 1 week and 30 minutes"
    )


def test_dates_read_the_same_on_every_platform():
    assert format_when(datetime(2026, 11, 3, 9, 5)) == "Tue 3 Nov 2026 · 09:05"


def test_the_latest_run_in_a_window_is_found():
    entry = _entry(datetime(2026, 11, 22, 8), minutes=15)
    assert due_between(entry, datetime(2026, 11, 22, 9, 1), datetime(2026, 11, 22, 9, 40)) == datetime(
        2026, 11, 22, 9, 30
    )
    assert due_between(entry, datetime(2026, 11, 22, 9, 31), datetime(2026, 11, 22, 9, 40)) is None


# ------------------------------------------------------------------ config


def test_schedules_save_and_load_and_old_files_still_load():
    group = Group.new("Morning", [GroupMember("a")])
    group.scheduled = True
    group.schedule = [_entry(datetime(2026, 11, 24, 9), weeks=1)]
    loaded = AppConfig.from_dict(AppConfig(groups=[group]).to_dict())
    assert loaded.groups[0].scheduled is True
    assert loaded.groups[0].schedule[0].start == "2026-11-24T09:00"
    assert loaded.groups[0].schedule[0].weeks == 1

    old = {"groups": [{"id": "g", "name": "Old", "members": []}]}
    assert AppConfig.from_dict(old).groups[0].scheduled is False
    assert AppConfig.from_dict(old).groups[0].schedule == []


def test_a_bad_schedule_date_is_reported_and_dropped():
    data = {"groups": [{"id": "g", "name": "G", "scheduled": True, "schedule": [
        {"id": "1", "start": "2026-11-24T09:00"},
        {"id": "2", "start": "next tuesday"},
        {"id": "3", "start": "2026-11-24T09:00", "days": -1},
    ]}]}
    problems: list[str] = []
    group = AppConfig.from_dict(data, problems).groups[0]
    assert [entry.id for entry in group.schedule] == ["1"]
    assert len(problems) == 2


# ------------------------------------------------------------------ the scheduler


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _scheduled(*entries: ScheduleEntry, name: str = "Morning") -> Group:
    group = Group.new(name)
    group.scheduled = True
    group.schedule = list(entries)
    return group


def test_the_scheduler_runs_a_group_when_its_date_comes(qapp):
    clock = _Clock(datetime(2026, 11, 24, 8, 59))
    group = _scheduled(_entry(datetime(2026, 11, 24, 9), days=1))
    ran: list[str] = []
    scheduler = Scheduler(lambda: [group], lambda g: ran.append(g.name), now=clock)
    scheduler.start()
    assert scheduler.is_waiting()
    assert 0 < scheduler.wait_ms() <= MAX_WAIT_MS
    clock.now = datetime(2026, 11, 24, 9, 0, 1)
    scheduler.check()
    assert ran == ["Morning"]
    clock.now = datetime(2026, 11, 24, 9, 0, 30)
    scheduler.check()
    assert ran == ["Morning"]  # once per run
    clock.now = datetime(2026, 11, 25, 9, 0, 2)
    scheduler.check()
    assert ran == ["Morning", "Morning"]


def test_runs_missed_while_runner_was_closed_are_skipped(qapp):
    clock = _Clock(datetime(2026, 11, 24, 12))
    group = _scheduled(_entry(datetime(2026, 11, 24, 9)), _entry(datetime(2026, 11, 20, 9), days=1))
    ran: list[str] = []
    scheduler = Scheduler(lambda: [group], lambda g: ran.append(g.name), now=clock)
    scheduler.start()
    scheduler.check()
    assert ran == []
    clock.now = datetime(2026, 11, 25, 9, 0, 5)  # the daily one still runs on time
    scheduler.check()
    assert ran == ["Morning"]


def test_a_run_missed_while_asleep_is_skipped_and_the_schedule_carries_on(qapp):
    clock = _Clock(datetime(2026, 11, 24, 8))
    group = _scheduled(_entry(datetime(2026, 11, 24, 9), hours=1))
    ran: list[datetime] = []
    scheduler = Scheduler(lambda: [group], lambda g: ran.append(clock.now), now=clock)
    scheduler.start()
    clock.now = datetime(2026, 11, 24, 10, 30)  # woke long after 09:00 and 10:00
    scheduler.check()
    assert ran == []
    clock.now = datetime(2026, 11, 24, 11, 0) + GRACE / 2
    scheduler.check()
    assert len(ran) == 1


def test_an_execute_group_that_is_not_scheduled_never_runs(qapp):
    clock = _Clock(datetime(2026, 11, 24, 8, 59))
    group = _scheduled(_entry(datetime(2026, 11, 24, 9)))
    group.scheduled = False
    ran: list[str] = []
    scheduler = Scheduler(lambda: [group], lambda g: ran.append(g.name), now=clock)
    scheduler.start()
    assert not scheduler.is_waiting()
    clock.now = datetime(2026, 11, 24, 9, 0, 1)
    scheduler.check()
    assert ran == []


# ------------------------------------------------------------------ the schedule area


def _editor(qtbot, entries, now):
    editor = ScheduleEditor(entries, now=lambda: now)
    qtbot.addWidget(editor)
    return editor


def test_dates_are_listed_by_their_next_run(qtbot):
    now = datetime(2026, 11, 22, 12)
    later = _entry(datetime(2026, 12, 5, 8))
    sooner = _entry(datetime(2026, 11, 25, 14, 30))
    weekly = _entry(datetime(2026, 11, 2, 9), weeks=1)  # next: Mon 23 Nov
    over = _entry(datetime(2026, 11, 1, 9))
    editor = _editor(qtbot, [later, over, sooner, weekly], now)
    assert editor.ordered_ids() == [weekly.id, sooner.id, later.id, over.id]
    texts = editor.row_texts()
    assert texts[0] == ("Mon 23 Nov 2026 · 09:00", "Every 1 week")
    assert texts[-1] == ("Sun 1 Nov 2026 · 09:00  (done)", "Does not repeat")


def test_a_new_date_stays_on_top_until_the_dialog_is_reopened(qtbot):
    now = datetime(2026, 11, 22, 12)
    sooner = _entry(datetime(2026, 11, 25, 14, 30))
    editor = _editor(qtbot, [sooner], now)
    editor.pick_date = lambda when: datetime(2027, 3, 1, 7, 15)
    editor.add_date()
    new_id = editor.ordered_ids()[0]
    assert new_id != sooner.id
    assert editor.row_texts()[0] == ("Mon 1 Mar 2027 · 07:15", "Does not repeat")
    reopened = _editor(qtbot, editor.entries(), now)
    assert reopened.ordered_ids() == [sooner.id, new_id]


def test_the_repeat_button_shows_what_the_rollers_chose(qtbot):
    now = datetime(2026, 11, 22, 12)
    entry = _entry(datetime(2026, 11, 25, 14, 30))
    editor = _editor(qtbot, [entry], now)
    chosen = {}

    def pick(total):
        chosen["was"] = total
        probe = _entry(datetime(2026, 1, 1), days=1, hours=12)
        return entry_total(probe)

    editor.pick_interval = pick
    editor.change_repeat(entry.id)
    assert chosen["was"] == 0
    assert editor.row_texts()[0][1] == "Every 1 day and 12 hours"
    assert editor.entries()[0].days == 1 and editor.entries()[0].hours == 12


def test_closing_a_picker_without_choosing_changes_nothing(qtbot):
    now = datetime(2026, 11, 22, 12)
    entry = _entry(datetime(2026, 11, 25, 14, 30), weeks=1)
    editor = _editor(qtbot, [entry], now)
    editor.pick_date = lambda when: None
    editor.pick_interval = lambda total: None
    editor.add_date()
    editor.change_date(entry.id)
    editor.change_repeat(entry.id)
    assert [(e.start, e.weeks) for e in editor.entries()] == [(entry.start, 1)]


def test_the_cross_removes_a_date(qtbot):
    now = datetime(2026, 11, 22, 12)
    keep, drop = _entry(datetime(2026, 11, 25, 9)), _entry(datetime(2026, 11, 26, 9))
    editor = _editor(qtbot, [keep, drop], now)
    crosses = [b for b in editor.findChildren(QPushButton) if b.objectName() == "scheduleRemove"]
    assert len(crosses) == 2 and all(b.text() == "×" for b in crosses)
    editor.remove(drop.id)
    assert editor.ordered_ids() == [keep.id]


def test_turned_off_the_dates_are_greyed_and_plus_is_gone(qtbot):
    editor = _editor(qtbot, [_entry(datetime(2026, 11, 25, 9))], datetime(2026, 11, 22, 12))
    editor.show()
    editor.set_active(False)
    assert editor.add_button.isHidden()
    assert not editor._rows_host.isEnabled()
    assert len(editor.entries()) == 1
    editor.set_active(True)
    assert editor.add_button.isVisible()
    assert editor._rows_host.isEnabled()


# ------------------------------------------------------------------ the dialog


def _cfg(tmp_path, monkeypatch) -> ConfigManager:
    monkeypatch.setattr("runner.config.platformdirs.user_config_dir", lambda *a, **k: str(tmp_path))
    cfg = ConfigManager()
    cfg.config.launchers = [Launcher.new("Alpha", "a")]
    return cfg


def test_the_schedule_switch_and_note_are_on_the_execute_group_screen(qapp, qtbot, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    dialog = GroupDialog(cfg)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.windowTitle() == "Add Execute Group"
    assert dialog.schedule_switch.text() == "Schedule"
    assert dialog.schedule_switch.isChecked() is False
    assert SCHEDULE_NOTE == "Scheduled items will not appear in the launcher menu."
    assert SCHEDULE_NOTE in [label.text() for label in dialog.findChildren(QLabel)]
    assert dialog.schedule_editor.add_button.isHidden()
    dialog.schedule_switch.setChecked(True)
    assert dialog.schedule_editor.add_button.isVisible()


def test_add_new_schedule_starts_with_the_switch_on_and_saves_dates(qapp, qtbot, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    dialog = GroupDialog(cfg, scheduled=True)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Add Schedule"
    assert dialog.schedule_switch.isChecked() is True
    dialog._name_edit.setText("Backups")
    dialog.schedule_editor.pick_date = lambda when: datetime(2026, 11, 24, 9)
    dialog.schedule_editor.add_date()
    dialog.accept()
    group = dialog.result_group
    assert group.scheduled is True
    assert [entry.start for entry in group.schedule] == ["2026-11-24T09:00"]


def test_turning_a_schedule_back_into_an_execute_group_keeps_its_dates(qapp, qtbot, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    group = _scheduled(_entry(datetime(2026, 11, 24, 9)))
    cfg.config.groups = [group]
    dialog = GroupDialog(cfg, group)
    qtbot.addWidget(dialog)
    dialog.schedule_switch.setChecked(False)
    dialog.accept()
    assert group.scheduled is False
    assert len(group.schedule) == 1


def test_each_manager_lists_only_its_own_kind(qapp, qtbot, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    by_hand, timed = Group.new("By hand"), _scheduled(_entry(datetime(2026, 11, 24, 9)), name="Timed")
    cfg.config.groups = [by_hand, timed]
    groups, schedules = GroupManagerDialog(cfg), ScheduleManagerDialog(cfg)
    qtbot.addWidget(groups)
    qtbot.addWidget(schedules)
    assert [g.name for g in groups._groups] == ["By hand"]
    assert [g.name for g in schedules._groups] == ["Timed"]
    assert schedules.windowTitle() == "Manage Schedules"


# ------------------------------------------------------------------ the pickers


def test_pressing_the_dial_centre_chooses_the_date(qapp, qtbot):
    dialog = DatePickerDialog(datetime(2026, 11, 24, 9, 30))
    qtbot.addWidget(dialog)
    dialog.dial._select()
    assert dialog.chosen == datetime(2026, 11, 24, 9, 30)
    assert dialog.result() == dialog.DialogCode.Accepted


def test_the_full_date_under_the_dial_follows_the_rings(qapp, qtbot):
    dialog = DatePickerDialog(datetime(2026, 11, 24, 9, 30))
    qtbot.addWidget(dialog)
    assert dialog.readout.text() == "Tuesday 24 November 2026 · 09:30"
    dialog.dial.set_value(datetime(2027, 3, 5, 18, 5))
    assert dialog.readout.text() == "Friday 5 March 2027 · 18:05"


def test_the_select_key_and_dont_repeat_choose_the_interval(qapp, qtbot):
    entry = _entry(datetime(2026, 1, 1), weeks=1, hours=6)
    dialog = IntervalPickerDialog(entry_total(entry))
    qtbot.addWidget(dialog)
    dialog.roller.select()
    copy = _entry(datetime(2026, 1, 1))
    apply_total(copy, dialog.chosen)
    assert (copy.weeks, copy.hours) == (1, 6)

    again = IntervalPickerDialog(entry_total(entry))
    qtbot.addWidget(again)
    again.no_repeat.click()
    assert again.chosen == 0


def test_a_new_date_starts_at_the_next_quarter_hour():
    assert next_quarter_hour(datetime(2026, 11, 22, 9, 7, 30)) == datetime(2026, 11, 22, 9, 15)
    assert next_quarter_hour(datetime(2026, 11, 22, 9, 45)) == datetime(2026, 11, 22, 10, 0)


# ------------------------------------------------------------------ in the app


def _controller(qapp, monkeypatch, tmp_path):
    from runner.controller import RunnerController

    cfg = _cfg(tmp_path, monkeypatch)
    by_hand = Group.new("By hand", [GroupMember(cfg.config.launchers[0].id)])
    soon = datetime.now() + timedelta(days=2)
    timed = _scheduled(_entry(soon.replace(second=0, microsecond=0)), name="Timed")
    cfg.config.groups = [by_hand, timed]
    cfg.config.settings.position_x, cfg.config.settings.position_y = 300, 120
    monkeypatch.setattr("runner.controller.create_tray", lambda **_: MagicMock())
    ctl = RunnerController(qapp, cfg)
    ctl.greeting.dismiss_for_session()
    return ctl, by_hand, timed


def _close(ctl) -> None:
    ctl.scheduler.stop()
    for panel in ctl._all_lists():
        panel.force_hide()
    ctl.trigger.hide()


def test_a_scheduled_group_shows_only_in_the_schedules_list(qapp, qtbot, monkeypatch, tmp_path):
    ctl, by_hand, timed = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    try:
        ctl.trigger.request_groups.emit()
        assert [b.launcher.id for b in ctl.group_panel._launch_buttons()] == [by_hand.id]

        ctl.trigger.request_schedules.emit()
        listing = ctl.schedule_list
        assert listing.isVisible() and not ctl.group_panel.isVisible() and not ctl.dropdown.isVisible()
        assert listing._heading.text() == "Schedules"
        rows = listing._launch_buttons()
        assert [b.launcher.id for b in rows] == [timed.id]
        assert rows[0].launcher.name.startswith("Timed  ·  next ")
    finally:
        _close(ctl)


def test_clicking_a_schedule_opens_it_for_editing(qapp, qtbot, monkeypatch, tmp_path):
    ctl, _by_hand, timed = _controller(qapp, monkeypatch, tmp_path)
    ctl.trigger.show()
    opened = []
    monkeypatch.setattr(ctl, "show_group_dialog", lambda group=None, **_: opened.append(group))
    try:
        ctl.trigger.request_schedules.emit()
        ctl.schedule_list._launch_buttons()[0].click()
        assert opened == [timed]
    finally:
        _close(ctl)


def test_the_scheduler_runs_the_group_through_the_app(qapp, qtbot, monkeypatch, tmp_path):
    ctl, _by_hand, timed = _controller(qapp, monkeypatch, tmp_path)
    started = []
    monkeypatch.setattr(ctl, "_start_group", lambda group, notice: started.append((group.name, notice)))
    try:
        ctl._run_scheduled(timed)
        assert started == [("Timed", "Scheduled run")]
    finally:
        _close(ctl)
