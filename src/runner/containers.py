"""Container groups list launchers in a submenu. They do not run them.

Whether a launcher is on the main hover list is one choice. Include in
dropdown list, Only In Groups, and Only in Container Group all write that
choice. The last one written is the one that sticks. Off the main list, the
launcher still runs inside an execute group and still appears in each
container submenu it belongs to.
"""

from __future__ import annotations

from collections.abc import Sequence

from .config import ContainerGroup, Launcher


def shown_in_main_menu(launcher: Launcher, container_groups: Sequence[ContainerGroup]) -> bool:
    """True when this launcher belongs in the first popup."""
    if not launcher.enabled or launcher.only_in_groups:
        return False
    for group in container_groups:
        for member in group.members:
            if member.launcher_id == launcher.id and member.only_in_container:
                return False
    return True


def set_shown_in_main_menu(
    launcher: Launcher,
    container_groups: Sequence[ContainerGroup],
    shown: bool,
) -> None:
    """Write the one main-popup choice onto the launcher and every container.

    shown True turns Include in dropdown list on and turns Only In Groups and
    Only in Container Group off. shown False does the opposite. A launcher
    that was fully disabled stays disabled until it is shown again.
    """
    if shown:
        launcher.enabled = True
    launcher.only_in_groups = not shown
    for group in container_groups:
        for member in group.members:
            if member.launcher_id == launcher.id:
                member.only_in_container = not shown


def submenu_launchers(group: ContainerGroup, launchers: Sequence[Launcher]) -> list[Launcher]:
    """Enabled members of one container, in the container's order."""
    by_id = {launcher.id: launcher for launcher in launchers}
    found: list[Launcher] = []
    for member in group.members:
        launcher = by_id.get(member.launcher_id)
        if launcher is not None and launcher.enabled:
            found.append(launcher)
    return found
