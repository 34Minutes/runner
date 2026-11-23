"""Manage execute groups and schedules: edit, delete, and reorder.

Both are execute groups in the config. Manage Execute Groups lists the ones
run by hand, and Manage Schedules the ones that run on dates.
"""

from __future__ import annotations

from .group_dialog import GroupDialog
from .group_list_manager import GroupListManagerDialog


class GroupManagerDialog(GroupListManagerDialog):
    """Edit, delete, and reorder the execute groups the user has created."""

    TITLE = "Manage Execute Groups"
    DELETE_TITLE = "Delete Execute Group"
    EMPTY_TEXT = "No execute groups yet. Press Add New… to make one."

    SCHEDULED = False

    def _saved(self):
        return [group for group in self._cfg.config.groups if bool(group.scheduled) == self.SCHEDULED]

    def _editor(self, group):
        return GroupDialog(self._cfg, group, self, scheduled=self.SCHEDULED)

    def _store_new(self, group) -> None:
        self._cfg.add_group(group)

    def _store_edit(self, group) -> None:
        self._cfg.update_group(group)

    def _remove(self, group_id: str) -> None:
        self._cfg.remove_group(group_id)

    def _reorder(self, ordered_ids: list[str]) -> None:
        self._cfg.reorder_groups(ordered_ids)


class ScheduleManagerDialog(GroupManagerDialog):
    """Edit, delete, and reorder the scheduled execute groups."""

    TITLE = "Manage Schedules"
    DELETE_TITLE = "Delete Schedule"
    EMPTY_TEXT = "No schedules yet. Press Add New… to make one."
    SCHEDULED = True
