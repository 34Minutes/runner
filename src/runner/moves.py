"""Move a launcher between the main popup, a container group, and an execute group.

Dragging inside one menu only reorders that menu. Dragging onto a different
menu takes the launcher out of the source menu and inserts it in the destination.
A launcher that leaves the main popup is hidden from it. A launcher dropped on
the main popup is shown there. That choice is the same one Include in dropdown
list writes, so every container membership agrees.
"""

from __future__ import annotations

from .config import AppConfig, ContainerMember, GroupMember, Launcher
from .containers import set_shown_in_main_menu, shown_in_main_menu

MAIN = "main"


def merge_visible_order(entries: list[tuple[str, bool]], visible_ids: list[str]) -> list[str]:
    """Reorder the flagged rows and leave every other row where it is.

    entries is (id, in_play) in the current order. visible_ids is the new
    top-to-bottom order of the in-play rows. Disabled launchers, and enabled
    ones hidden by the filter, stay in their slots.
    """
    in_play = {eid for eid, flagged in entries if flagged}
    queue = [vid for vid in visible_ids if vid in in_play]
    pending = iter(queue)
    merged: list[str] = []
    for eid, flagged in entries:
        if flagged and eid in in_play:
            merged.append(next(pending))
        else:
            merged.append(eid)
    return merged


def launcher_token(launcher_id: str) -> str:
    return f"launcher:{launcher_id}"


def container_token(group_id: str) -> str:
    return f"container:{group_id}"


def split_menu_key(key: str) -> tuple[str, str | None]:
    """'main', 'container:<id>', or 'execute:<id>'."""
    if key == MAIN:
        return MAIN, None
    kind, _, group_id = key.partition(":")
    return kind, group_id or None


def default_main_order(config: AppConfig) -> list[str]:
    """Containers first, then every launcher. Used when the user has not dragged yet."""
    tokens = [container_token(group.id) for group in config.container_groups]
    tokens.extend(launcher_token(launcher.id) for launcher in config.launchers)
    return tokens


def visible_main_tokens(config: AppConfig) -> list[str]:
    """Rows of the main popup, in the saved order."""
    containers = {group.id: group for group in config.container_groups}
    launchers = {launcher.id: launcher for launcher in config.launchers}
    source = config.main_order or default_main_order(config)
    full = [token for token in source if _known_token(token, containers, launchers)]
    seen = set(full)
    # Launchers the saved order does not mention yet follow the saved rows.
    # A container that is not in the order is placed at the front, so a new
    # container group shows up where container rows used to live.
    for token in default_main_order(config):
        kind, _, _ident = token.partition(":")
        if token not in seen and kind == "launcher":
            full.append(token)
            seen.add(token)

    shown: list[str] = []
    seen_shown: set[str] = set()
    for token in full:
        if not _token_visible(token, config, containers, launchers):
            continue
        shown.append(token)
        seen_shown.add(token)
    missing_containers = []
    for group in config.container_groups:
        token = container_token(group.id)
        if token not in seen_shown:
            missing_containers.append(token)
            seen_shown.add(token)
    shown = missing_containers + shown
    for launcher in config.launchers:
        token = launcher_token(launcher.id)
        if token not in seen_shown and shown_in_main_menu(launcher, config.container_groups):
            shown.append(token)
    return shown


def apply_visible_row_order(config: AppConfig, visible_tokens: list[str]) -> None:
    """Save a new main-popup order. Tokens not in visible_tokens stay in their slots."""
    containers = {group.id: group for group in config.container_groups}
    launchers = {launcher.id: launcher for launcher in config.launchers}
    full = [token for token in (config.main_order or default_main_order(config)) if _known_token(token, containers, launchers)]
    seen = set(full)
    for token in default_main_order(config):
        if token not in seen:
            full.append(token)
            seen.add(token)
    in_play = {token for token in visible_tokens if _known_token(token, containers, launchers)}
    entries = [(token, token in in_play) for token in full]
    for token in visible_tokens:
        if token in in_play and token not in seen:
            entries.append((token, True))
    config.main_order = merge_visible_order(entries, [token for token in visible_tokens if token in in_play])
    _sync_relative_orders(config)


def reorder_members(members: list, ordered_ids: list[str]) -> list:
    """Permute members. Ids that are missing from ordered_ids keep their relative order at the end."""
    by_id = {member.launcher_id: member for member in members}
    ordered = []
    for launcher_id in ordered_ids:
        member = by_id.pop(launcher_id, None)
        if member is not None:
            ordered.append(member)
    ordered.extend(by_id.values())
    return ordered


def enabled_member_launchers(members: list, launchers: list[Launcher]) -> list[Launcher]:
    """Enabled launchers in member order."""
    by_id = {launcher.id: launcher for launcher in launchers}
    found: list[Launcher] = []
    for member in members:
        launcher = by_id.get(member.launcher_id)
        if launcher is not None and launcher.enabled:
            found.append(launcher)
    return found


def move_launcher(
    config: AppConfig,
    launcher_id: str,
    source_key: str,
    dest_key: str,
    dest_index: int,
    dest_visible_ids: list[str] | None = None,
) -> bool:
    """Take a launcher out of one menu and insert it in another.

    dest_visible_ids is the destination's on-screen launcher ids, or the main
    popup's on-screen row tokens when dest_key is main. None uses the full
    unfiltered order. Returns False when the launcher or a group is unknown.
    """
    if source_key == dest_key:
        return False
    launcher = _find_launcher(config, launcher_id)
    if launcher is None:
        return False
    source_kind, source_id = split_menu_key(source_key)
    dest_kind, dest_id = split_menu_key(dest_key)
    if source_kind == "container" and _find_container(config, source_id) is None:
        return False
    if source_kind == "execute" and _find_execute(config, source_id) is None:
        return False
    if dest_kind == "container" and _find_container(config, dest_id) is None:
        return False
    if dest_kind == "execute" and _find_execute(config, dest_id) is None:
        return False
    if source_kind not in (MAIN, "container", "execute") or dest_kind not in (MAIN, "container", "execute"):
        return False

    source_concurrent = False
    if source_kind == "execute":
        source_group = _find_execute(config, source_id)
        source_member = _member(source_group.members if source_group else [], launcher.id)
        source_concurrent = bool(source_member and source_member.concurrent)

    was_hidden = not shown_in_main_menu(launcher, config.container_groups)
    _remove_source_membership(config, launcher.id, source_kind, source_id)
    if dest_kind == MAIN:
        show = True
    elif source_kind == MAIN:
        show = False
    else:
        show = not was_hidden
    if dest_kind == MAIN:
        _place_on_main(config, launcher.id, dest_index, dest_visible_ids)
    elif dest_kind == "container":
        _place_in_container(
            config,
            dest_id or "",
            launcher.id,
            dest_index,
            not show,
            dest_visible_ids,
        )
    else:
        _place_in_execute(
            config,
            dest_id or "",
            launcher.id,
            dest_index,
            dest_visible_ids,
            concurrent=source_concurrent if source_kind == "execute" else False,
        )
    set_shown_in_main_menu(launcher, config.container_groups, show)
    return True


def _remove_source_membership(config: AppConfig, launcher_id: str, kind: str, group_id: str | None) -> None:
    """Take the launcher out of the menu it was dragged from."""
    if kind == "container":
        container = _find_container(config, group_id)
        if container is not None:
            container.members = [item for item in container.members if item.launcher_id != launcher_id]
    elif kind == "execute":
        group = _find_execute(config, group_id)
        if group is not None:
            group.members = [item for item in group.members if item.launcher_id != launcher_id]


def _place_on_main(config: AppConfig, launcher_id: str, index: int, visible_tokens: list[str] | None) -> None:
    token = launcher_token(launcher_id)
    visible = list(visible_tokens) if visible_tokens is not None else visible_main_tokens(config)
    visible = _insert_at(visible, token, index)
    apply_visible_row_order(config, visible)


def _place_in_container(
    config: AppConfig,
    group_id: str,
    launcher_id: str,
    index: int,
    only_in_container: bool,
    visible_ids: list[str] | None,
) -> None:
    container = _find_container(config, group_id)
    if container is None:
        return

    def make() -> ContainerMember:
        return ContainerMember(launcher_id, only_in_container=only_in_container)

    container.members = _insert_member(container.members, launcher_id, index, visible_ids, make)
    for member in container.members:
        if member.launcher_id == launcher_id:
            member.only_in_container = only_in_container


def _place_in_execute(
    config: AppConfig,
    group_id: str,
    launcher_id: str,
    index: int,
    visible_ids: list[str] | None,
    *,
    concurrent: bool = False,
) -> None:
    group = _find_execute(config, group_id)
    if group is None:
        return

    def make() -> GroupMember:
        # A launcher new to this group keeps the concurrent flag it had in the
        # group it left. One that is already here keeps this group's flag.
        return GroupMember(launcher_id, concurrent=concurrent)

    group.members = _insert_member(group.members, launcher_id, index, visible_ids, make)


def _insert_member(members: list, launcher_id: str, index: int, visible_ids: list[str] | None, make) -> list:
    by_id = {member.launcher_id: member for member in members}
    ids = [member.launcher_id for member in members if member.launcher_id != launcher_id]
    if visible_ids is None:
        visible = list(ids)
    else:
        known = set(ids)
        visible = [item_id for item_id in visible_ids if item_id in known and item_id != launcher_id]
    visible = _insert_at(visible, launcher_id, index)
    original_visible = set(visible_ids) if visible_ids is not None else set(ids)
    original_visible.add(launcher_id)
    entries = [(item_id, item_id in original_visible) for item_id in ids]
    entries.append((launcher_id, True))
    new_ids = merge_visible_order(entries, visible)
    placed = []
    for item_id in new_ids:
        if item_id == launcher_id:
            placed.append(by_id.get(launcher_id) or make())
        elif item_id in by_id:
            placed.append(by_id[item_id])
    return placed


def _insert_at(items: list[str], item: str, index: int) -> list[str]:
    items = list(items)
    if item in items:
        old = items.index(item)
        items.pop(old)
        if old < index:
            index -= 1
    if index < 0:
        index = len(items)
    index = max(0, min(index, len(items)))
    items.insert(index, item)
    return items


def _sync_relative_orders(config: AppConfig) -> None:
    launcher_ids = []
    container_ids = []
    for token in config.main_order:
        kind, _, ident = token.partition(":")
        if kind == "launcher":
            launcher_ids.append(ident)
        elif kind == "container":
            container_ids.append(ident)
    by_launcher = {launcher.id: launcher for launcher in config.launchers}
    launchers = []
    for launcher_id in launcher_ids:
        launcher = by_launcher.pop(launcher_id, None)
        if launcher is not None:
            launchers.append(launcher)
    launchers.extend(by_launcher.values())
    config.launchers = launchers
    by_container = {group.id: group for group in config.container_groups}
    containers = []
    for group_id in container_ids:
        group = by_container.pop(group_id, None)
        if group is not None:
            containers.append(group)
    containers.extend(by_container.values())
    config.container_groups = containers


def _known_token(token: str, containers: dict, launchers: dict) -> bool:
    kind, _, ident = token.partition(":")
    if kind == "container":
        return ident in containers
    if kind == "launcher":
        return ident in launchers
    return False


def _token_visible(token: str, config: AppConfig, containers: dict, launchers: dict) -> bool:
    kind, _, ident = token.partition(":")
    if kind == "container":
        return ident in containers
    if kind == "launcher":
        launcher = launchers.get(ident)
        return launcher is not None and shown_in_main_menu(launcher, config.container_groups)
    return False


def _find_launcher(config: AppConfig, launcher_id: str) -> Launcher | None:
    for launcher in config.launchers:
        if launcher.id == launcher_id:
            return launcher
    return None


def _find_container(config: AppConfig, group_id: str | None):
    if not group_id:
        return None
    for group in config.container_groups:
        if group.id == group_id:
            return group
    return None


def _find_execute(config: AppConfig, group_id: str | None):
    if not group_id:
        return None
    for group in config.groups:
        if group.id == group_id:
            return group
    return None


def _member(members: list, launcher_id: str):
    for member in members:
        if member.launcher_id == launcher_id:
            return member
    return None


