"""Manage execute groups: edit, delete, and reorder."""

from __future__ import annotations

from .group_dialog import GroupDialog
from .group_list_manager import GroupListManagerDialog


class GroupManagerDialog(GroupListManagerDialog):
    """Edit, delete, and reorder the execute groups the user has created."""

    TITLE = "Manage Execute Groups"
    DELETE_TITLE = "Delete Execute Group"

    def _saved(self):
        return self._cfg.config.groups

    def _editor(self, group):
        return GroupDialog(self._cfg, group, self)

    def _store_new(self, group) -> None:
        self._cfg.add_group(group)

    def _store_edit(self, group) -> None:
        self._cfg.update_group(group)

    def _remove(self, group_id: str) -> None:
        self._cfg.remove_group(group_id)

    def _reorder(self, ordered_ids: list[str]) -> None:
        self._cfg.reorder_groups(ordered_ids)
