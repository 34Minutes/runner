"""Manage container groups: edit, delete, and reorder."""

from __future__ import annotations

from .container_dialog import ContainerDialog
from .group_list_manager import GroupListManagerDialog


class ContainerManagerDialog(GroupListManagerDialog):
    """Edit, delete, and reorder the container groups the user has created."""

    TITLE = "Manage Container Groups"
    DELETE_TITLE = "Delete Container Group"
    EMPTY_TEXT = "No container groups yet. Press Add New… to make one."

    def _saved(self):
        return self._cfg.config.container_groups

    def _editor(self, group):
        return ContainerDialog(self._cfg, group, self)

    def _store_new(self, group) -> None:
        self._cfg.add_container_group(group)

    def _store_edit(self, group) -> None:
        self._cfg.update_container_group(group)

    def _remove(self, group_id: str) -> None:
        self._cfg.remove_container_group(group_id)

    def _reorder(self, ordered_ids: list[str]) -> None:
        self._cfg.reorder_container_groups(ordered_ids)
