"""Schedules: execute groups that run on dates instead of from the Execute Groups list."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from runner.config import AppConfig, ConfigManager, Group, GroupMember, Launcher, ScheduleEntry
from runner.schedule import (
    parse_when,
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


def test_the_click_switch_shows_only_for_a_schedule_and_is_saved(qapp, qtbot, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    dialog = GroupDialog(cfg)
    qtbot.addWidget(dialog)
    dialog.show()
    assert dialog.click_runs_switch.isHidden()
    dialog.schedule_switch.setChecked(True)
    assert dialog.click_runs_switch.isVisible()
    assert dialog.click_runs_switch.isChecked() is False  # a click opens it, by default
    dialog.click_runs_switch.setChecked(True)
    dialog._name_edit.setText("Nightly")
    dialog.accept()
    group = dialog.result_group
    assert group.click_runs is True

    again = GroupDialog(cfg, group)
    qtbot.addWidget(again)
    again.show()
    assert again.click_runs_switch.isVisible() and again.click_runs_switch.isChecked()


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


def test_typed_dates_are_read_with_the_rest_from_the_dial():
    base = datetime(2026, 11, 24, 9, 30)
    assert parse_when("Tuesday 24 November 2026 · 09:30", base) == base
    assert parse_when("5 March 2027 18:05", base) == datetime(2027, 3, 5, 18, 5)
    assert parse_when("24/12/2026 7pm", base) == datetime(2026, 12, 24, 19, 0)
    assert parse_when("2027-01-02 8:15", base) == datetime(2027, 1, 2, 8, 15)
    assert parse_when("14:45", base) == datetime(2026, 11, 24, 14, 45)
    assert parse_when("dec 3rd at 7.15am", base) == datetime(2026, 12, 3, 7, 15)
    for bad in ("", "fish", "31 Feb", "25:00", "13pm"):
        with pytest.raises(ValueError):
            parse_when(bad, base)


def _settle(dial) -> None:
    for _ in range(400):
        if not any(ring.moving() for ring in dial.rings):
            return
        dial._last_tick = dial._clock.elapsed() - 16
        dial._tick()


def _stepped(qtbot, when, ring_name, steps):
    """The dial's date after stepping one ring, as the wheel or arrow keys do."""
    from runner.ui.date_dial import MetalDial

    dial = MetalDial(when, first_year=2026)
    qtbot.addWidget(dial)
    ring = getattr(dial, ring_name)
    for _ in range(abs(steps)):
        ring.carries = True
        ring.step_by(1 if steps > 0 else -1)
    _settle(dial)
    return dial.value()


@pytest.mark.parametrize(
    ("when", "ring", "steps", "expected"),
    [
        (datetime(2026, 11, 28, 23, 0), "hour", 1, datetime(2026, 11, 29, 0, 0)),
        (datetime(2026, 11, 29, 0, 0), "hour", -1, datetime(2026, 11, 28, 23, 0)),
        (datetime(2026, 11, 30, 23, 0), "hour", 1, datetime(2026, 12, 1, 0, 0)),
        (datetime(2026, 12, 1, 0, 0), "hour", -1, datetime(2026, 11, 30, 23, 0)),
        (datetime(2026, 12, 31, 23, 0), "hour", 1, datetime(2027, 1, 1, 0, 0)),
        (datetime(2027, 1, 1, 0, 0), "hour", -1, datetime(2026, 12, 31, 23, 0)),
        (datetime(2026, 12, 31, 23, 59), "minute", 1, datetime(2027, 1, 1, 0, 0)),
        (datetime(2026, 11, 28, 22, 0), "hour", 5, datetime(2026, 11, 29, 3, 0)),
        (datetime(2026, 12, 31, 9, 0), "day", 2, datetime(2027, 1, 2, 9, 0)),
        (datetime(2028, 3, 1, 9, 0), "day", -1, datetime(2028, 2, 29, 9, 0)),
        (datetime(2027, 3, 2, 9, 0), "day", -3, datetime(2027, 2, 27, 9, 0)),
        (datetime(2026, 12, 5, 9, 0), "month", 1, datetime(2027, 1, 5, 9, 0)),
        (datetime(2027, 1, 5, 9, 0), "month", -1, datetime(2026, 12, 5, 9, 0)),
    ],
)
def test_a_ring_turned_past_its_end_carries_into_the_next(qapp, qtbot, when, ring, steps, expected):
    assert _stepped(qtbot, when, ring, steps) == expected


@pytest.mark.parametrize(
    ("when", "ring", "steps"),
    [
        (datetime(2037, 12, 31, 23, 0), "hour", 1),
        (datetime(2037, 12, 5, 9, 0), "month", 1),
        (datetime(2026, 1, 1, 0, 0), "hour", -1),
        (datetime(2026, 1, 1, 9, 0), "day", -1),
    ],
)
def test_carrying_stops_at_the_year_rings_ends(qapp, qtbot, when, ring, steps):
    # Twelve years, 2026 to 2037: going off either end would wrap to the other.
    assert _stepped(qtbot, when, ring, steps) == when


def test_dragging_the_hour_ring_past_midnight_carries(qapp, qtbot):
    from runner.ui.date_dial import MetalDial

    dial = MetalDial(datetime(2026, 11, 30, 22, 0), first_year=2026)
    qtbot.addWidget(dial)
    dial._grab = dial.hour
    dial.hour.carries = True
    for _ in range(30):  # three hours, a tenth of a notch at a time
        dial.hour.rotation -= dial.hour.step / 10
        dial._sync()
    dial._grab = None
    dial.hour.target = dial.hour.rotation_for(dial.hour.index_at(dial.hour.rotation))
    _settle(dial)
    assert dial.value() == datetime(2026, 12, 1, 1, 0)


def test_selecting_mid_turn_settles_the_carry_first(qapp, qtbot):
    from runner.ui.date_dial import MetalDial

    dial = MetalDial(datetime(2026, 12, 31, 23, 0), first_year=2026)
    qtbot.addWidget(dial)
    chosen = []
    dial.selected.connect(chosen.append)
    dial.hour.carries = True
    dial.hour.step_by(1)
    dial._select()
    assert chosen == [datetime(2027, 1, 1, 0, 0)]


def test_spinning_to_a_date_carries_nothing(qapp, qtbot):
    from runner.ui.date_dial import MetalDial

    dial = MetalDial(datetime(2028, 6, 2, 21, 10), first_year=2026)
    qtbot.addWidget(dial)
    dial.spin_to(datetime(2026, 11, 24, 8, 41))
    _settle(dial)
    assert dial.value() == datetime(2026, 11, 24, 8, 41)


def test_the_dial_opens_on_the_dates_own_year(qapp, qtbot):
    # It used to open on the first year it lists, so a 2027 date read as 2026.
    from runner.ui.date_dial import MetalDial

    dial = MetalDial(datetime(2027, 3, 1, 9, 0), first_year=2026)
    qtbot.addWidget(dial)
    assert dial.value() == datetime(2027, 3, 1, 9, 0)


def test_typing_a_date_spins_the_dial_there(qapp, qtbot):
    dialog = DatePickerDialog(datetime(2026, 11, 24, 9, 30), now=lambda: datetime(2026, 11, 24, 8))
    qtbot.addWidget(dialog)
    dialog.type_date("5 March 2027 18:05")
    assert any(ring.moving() for ring in dialog.dial.rings)  # it turns, not jumps
    _settle(dialog.dial)
    assert dialog.dial.value() == datetime(2027, 3, 5, 18, 5)
    assert dialog.readout.text() == "Friday 5 March 2027 · 18:05"
    assert not dialog.problem.isVisibleTo(dialog)

    dialog.type_date("31 Feb")
    assert dialog.problem.isVisibleTo(dialog) and "no day 31" in dialog.problem.text()
    dialog.type_date("1 Jan 2050")
    assert dialog.problem.text() == "Choose a year from 2026 to 2037."
    assert dialog.dial.value() == datetime(2027, 3, 5, 18, 5)


def test_now_spins_back_to_the_current_time(qapp, qtbot):
    now = datetime(2026, 11, 24, 8, 41)
    dialog = DatePickerDialog(datetime(2028, 6, 2, 21, 10), now=lambda: now)
    qtbot.addWidget(dialog)
    dialog.now_action.trigger()
    assert any(ring.moving() for ring in dialog.dial.rings)
    _settle(dialog.dial)
    assert dialog.dial.value() == now


def test_the_minutes_action_hides_the_minute_ring(qapp, qtbot):
    dialog = DatePickerDialog(datetime(2026, 11, 24, 9, 0), show_minutes=False)
    qtbot.addWidget(dialog)
    seen = []
    dialog.minutes_toggled.connect(seen.append)
    assert not dialog.minutes_action.isChecked() and dialog.dial.minute not in dialog.dial.rings
    dialog.minutes_action.setChecked(True)
    assert dialog.dial.minute in dialog.dial.rings and seen == [True]
    dialog.minutes_action.setChecked(False)
    assert dialog.dial.value().minute == 0 and seen == [True, False]
    # Typing minutes brings the ring back so they are kept.
    dialog.type_date("10:20")
    assert dialog.minutes_action.isChecked()
    # A date with minutes opens with the ring shown, whatever the setting.
    other = DatePickerDialog(datetime(2026, 11, 24, 9, 30), show_minutes=False)
    qtbot.addWidget(other)
    assert other.minutes_action.isChecked()


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


def test_a_schedule_set_to_run_on_click_runs_instead_of_opening(qapp, qtbot, monkeypatch, tmp_path):
    ctl, _by_hand, timed = _controller(qapp, monkeypatch, tmp_path)
    timed.click_runs = True
    ctl.trigger.show()
    opened, started = [], []
    monkeypatch.setattr(ctl, "show_group_dialog", lambda group=None, **_: opened.append(group))
    monkeypatch.setattr(ctl, "_start_group", lambda group, notice: started.append(group.name))
    try:
        ctl.trigger.request_schedules.emit()
        row = ctl.schedule_list._launch_buttons()[0]
        assert "Click to run it now" in ctl._schedule_row_tooltip(row.launcher)
        row.click()
        assert started == ["Timed"] and opened == []
        # Right-click Edit still opens it.
        ctl.schedule_list.edit_requested.emit(row.launcher)
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
