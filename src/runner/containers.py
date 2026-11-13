"""Container groups list launchers in a submenu. They do not run them.

A launcher stays on the main hover list when Only in Container Group is off
for every container it belongs to. One container with that switch on hides it
from the main list. It can still be picked for other container groups and for
execute groups, and it still appears in each container submenu it belongs to.
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


def submenu_launchers(group: ContainerGroup, launchers: Sequence[Launcher]) -> list[Launcher]:
    """Enabled members of one container, in the container's order."""
    by_id = {launcher.id: launcher for launcher in launchers}
    found: list[Launcher] = []
    for member in group.members:
        launcher = by_id.get(member.launcher_id)
        if launcher is not None and launcher.enabled:
            found.append(launcher)
    return found
