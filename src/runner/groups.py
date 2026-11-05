"""Order and run a group of launchers.

A group is an ordered list of launchers. Consecutive members marked concurrent
start in the same step. Every other member is its own step, so it starts on
its own, after the previous step.

Example: item 1 unmarked, items 2-5 concurrent, items 6-10 unmarked.

    [1] then [2, 3, 4, 5] together, then [6], [7], [8], [9], [10]

Steps are separated by GROUP_STEP_GAP_MS. Members inside one step start
immediately, in list order. Disabled launchers and missing ids are skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .config import Group, Launcher

# Long enough that sequential apps are visibly one after another, short enough
# that a group of ten still finishes opening quickly.
GROUP_STEP_GAP_MS = 300


def display_order(base_ids: Sequence[str], selected_ids: Sequence[str]) -> list[str]:
    """Selected rows first, in click or drag order. The rest keep main-view order."""
    base = list(base_ids)
    known = set(base)
    selected = [item_id for item_id in selected_ids if item_id in known]
    selected_set = set(selected)
    return selected + [item_id for item_id in base if item_id not in selected_set]


def select_member(base_ids: Sequence[str], selected_ids: Sequence[str], launcher_id: str) -> list[str]:
    """Append a newly chosen launcher. A second click leaves the order alone."""
    if launcher_id not in set(base_ids) or launcher_id in selected_ids:
        return list(selected_ids)
    return list(selected_ids) + [launcher_id]


def unselect_member(selected_ids: Sequence[str], launcher_id: str) -> list[str]:
    return [item_id for item_id in selected_ids if item_id != launcher_id]


def selected_order_after_drag(visual_ids: Sequence[str], selected_ids: Sequence[str]) -> list[str]:
    """Checked rows keep the order they landed in. Unchecked rows are ignored."""
    selected_set = set(selected_ids)
    return [item_id for item_id in visual_ids if item_id in selected_set]


def execution_steps(group: Group, launchers: Sequence[Launcher]) -> list[list[Launcher]]:
    """Split a group into start steps. See the module docstring."""
    by_id = {launcher.id: launcher for launcher in launchers}
    steps: list[list[Launcher]] = []
    batch: list[Launcher] = []

    def flush() -> None:
        nonlocal batch
        if batch:
            steps.append(batch)
            batch = []

    for member in group.members:
        launcher = by_id.get(member.launcher_id)
        if launcher is None or not launcher.enabled:
            continue
        if member.concurrent:
            batch.append(launcher)
        else:
            flush()
            steps.append([launcher])
    flush()
    return steps


def run_group_steps(
    steps: Sequence[Sequence[Launcher]],
    launch_one: Callable[[Launcher], None],
    schedule: Callable[[int, Callable[[], None]], None],
    gap_ms: int = GROUP_STEP_GAP_MS,
    on_error: Callable[[Launcher, Exception], None] | None = None,
    on_finished: Callable[[], None] | None = None,
) -> None:
    """Run each step, then wait gap_ms before the next one."""

    def run_from(index: int) -> None:
        if index >= len(steps):
            if on_finished is not None:
                on_finished()
            return
        for launcher in steps[index]:
            try:
                launch_one(launcher)
            except Exception as exc:
                if on_error is not None:
                    on_error(launcher, exc)
        if index + 1 < len(steps):
            schedule(gap_ms, lambda index=index: run_from(index + 1))
        elif on_finished is not None:
            on_finished()

    run_from(0)
