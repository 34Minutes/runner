"""Moving a launcher between the main popup, a container, and an execute group."""

from runner.config import (
    AppConfig,
    ConfigManager,
    ContainerGroup,
    ContainerMember,
    Group,
    GroupMember,
    Launcher,
)
from runner.containers import shown_in_main_menu
from runner.moves import (
    apply_visible_row_order,
    container_token,
    launcher_token,
    move_launcher,
    visible_main_tokens,
)


def _launcher(name: str, **kwargs) -> Launcher:
    return Launcher.new(name, name.lower(), **kwargs)


def _config() -> tuple[AppConfig, Launcher, Launcher, ContainerGroup, Group, Group]:
    alpha = _launcher("Alpha")
    beta = _launcher("Beta")
    folder = ContainerGroup.new("Folder", [ContainerMember(alpha.id)])
    work = Group.new("Work", [GroupMember(beta.id, concurrent=True)])
    play = Group.new("Play", [])
    config = AppConfig(launchers=[alpha, beta], container_groups=[folder], groups=[work, play])
    return config, alpha, beta, folder, work, play


def test_empty_main_order_lists_containers_then_launchers():
    config, alpha, beta, folder, _work, _play = _config()
    hidden = _launcher("Hidden", enabled=False)
    config.launchers.append(hidden)
    assert visible_main_tokens(config) == [
        container_token(folder.id),
        launcher_token(alpha.id),
        launcher_token(beta.id),
    ]


def test_saved_main_order_interleaves_and_keeps_a_hidden_launcher_in_its_slot():
    config, alpha, beta, folder, _work, _play = _config()
    hidden = _launcher("Hidden", only_in_groups=True)
    config.launchers.append(hidden)
    config.main_order = [
        launcher_token(alpha.id),
        launcher_token(hidden.id),
        container_token(folder.id),
        launcher_token(beta.id),
    ]
    assert visible_main_tokens(config) == [
        launcher_token(alpha.id),
        container_token(folder.id),
        launcher_token(beta.id),
    ]
    apply_visible_row_order(
        config,
        [container_token(folder.id), launcher_token(beta.id), launcher_token(alpha.id)],
    )
    assert config.main_order == [
        container_token(folder.id),
        launcher_token(hidden.id),
        launcher_token(beta.id),
        launcher_token(alpha.id),
    ]
    # Hidden stays in its slot, so the launcher list follows the token order.
    assert [item.name for item in config.launchers] == ["Hidden", "Beta", "Alpha"]
    assert [group.name for group in config.container_groups] == ["Folder"]


def test_a_new_container_shows_at_the_front_until_it_is_in_the_saved_order():
    config, alpha, _beta, folder, _work, _play = _config()
    config.main_order = [launcher_token(alpha.id), container_token(folder.id)]
    extra = ContainerGroup.new("Extra")
    config.container_groups.append(extra)
    assert visible_main_tokens(config)[0] == container_token(extra.id)


def test_same_menu_and_unknown_ids_do_not_move():
    config, alpha, _beta, folder, work, _play = _config()
    assert move_launcher(config, alpha.id, "main", "main", 0) is False
    assert move_launcher(config, "missing", "main", f"container:{folder.id}", 0) is False
    assert move_launcher(config, alpha.id, "container:missing", "main", 0) is False
    assert move_launcher(config, alpha.id, "main", "execute:missing", 0) is False
    assert move_launcher(config, alpha.id, "main", f"execute:{work.id}", 0) is True


def test_main_to_container_hides_the_launcher_and_inserts_it():
    config, alpha, beta, folder, _work, _play = _config()
    other = ContainerGroup.new("Other", [ContainerMember(beta.id, only_in_container=False)])
    config.container_groups.append(other)
    assert move_launcher(
        config,
        beta.id,
        "main",
        f"container:{folder.id}",
        0,
        [alpha.id],
    )
    assert [member.launcher_id for member in folder.members] == [beta.id, alpha.id]
    assert folder.members[0].only_in_container is True
    assert beta.only_in_groups is True
    assert other.members[0].only_in_container is True
    assert shown_in_main_menu(beta, config.container_groups) is False
    # Already in the destination: the flag is still forced on, and the index accounts for the old slot.
    assert move_launcher(config, alpha.id, "main", f"container:{folder.id}", 0, [beta.id, alpha.id])
    assert [member.launcher_id for member in folder.members] == [alpha.id, beta.id]
    assert all(member.only_in_container for member in folder.members)


def test_disabled_member_stays_in_its_slot_when_a_launcher_is_inserted():
    config, alpha, beta, folder, _work, _play = _config()
    disabled = _launcher("Disabled", enabled=False)
    config.launchers.append(disabled)
    folder.members = [ContainerMember(alpha.id), ContainerMember(disabled.id), ContainerMember(beta.id)]
    gamma = _launcher("Gamma")
    config.launchers.append(gamma)
    assert move_launcher(
        config,
        gamma.id,
        "main",
        f"container:{folder.id}",
        1,
        [alpha.id, beta.id],
    )
    assert [member.launcher_id for member in folder.members] == [
        alpha.id,
        disabled.id,
        gamma.id,
        beta.id,
    ]


def test_container_to_main_shows_the_launcher_and_clears_hide_flags():
    config, alpha, beta, folder, work, _play = _config()
    folder.members = [ContainerMember(alpha.id, only_in_container=True)]
    other = ContainerGroup.new("Other", [ContainerMember(alpha.id, only_in_container=True)])
    config.container_groups.append(other)
    beta.only_in_groups = True
    work.members = [GroupMember(alpha.id)]
    alpha.only_in_groups = True
    assert move_launcher(
        config,
        alpha.id,
        f"container:{folder.id}",
        "main",
        0,
        [container_token(folder.id), launcher_token(beta.id)],
    )
    assert folder.members == []
    assert other.members[0].only_in_container is False
    assert alpha.only_in_groups is False
    assert config.main_order[0] == launcher_token(alpha.id)
    assert shown_in_main_menu(alpha, config.container_groups) is True


def test_execute_to_main_removes_that_membership_and_shows_the_launcher():
    config, _alpha, beta, _folder, work, play = _config()
    beta.only_in_groups = True
    play.members = [GroupMember(beta.id, concurrent=True)]
    assert move_launcher(config, beta.id, f"execute:{work.id}", "main", 1, [launcher_token(_alpha.id)])
    assert work.members == []
    # It is still in Play, but landing on the main list shows it there.
    assert play.members == [GroupMember(beta.id, concurrent=True)]
    assert beta.only_in_groups is False
    assert launcher_token(beta.id) in config.main_order


def test_container_to_execute_hides_from_main_only_when_the_container_did():
    config, alpha, beta, folder, work, _play = _config()
    folder.members = [
        ContainerMember(alpha.id, only_in_container=True),
        ContainerMember(beta.id, only_in_container=False),
    ]
    assert move_launcher(config, alpha.id, f"container:{folder.id}", f"execute:{work.id}", 0, [beta.id])
    assert alpha.only_in_groups is True
    assert [member.launcher_id for member in work.members] == [alpha.id, beta.id]
    assert folder.members == [ContainerMember(beta.id, only_in_container=False)]

    assert move_launcher(config, beta.id, f"container:{folder.id}", f"execute:{work.id}", -1)
    assert beta.only_in_groups is False
    assert [member.launcher_id for member in work.members] == [alpha.id, beta.id]


def test_execute_to_container_keeps_the_same_off_main_choice():
    config, alpha, _beta, folder, work, _play = _config()
    work.members = [GroupMember(alpha.id, concurrent=True)]
    alpha.only_in_groups = True
    folder.members = []
    assert move_launcher(config, alpha.id, f"execute:{work.id}", f"container:{folder.id}", 0)
    assert work.members == []
    assert alpha.only_in_groups is True
    assert folder.members == [ContainerMember(alpha.id, only_in_container=True)]


def test_execute_group_move_keeps_concurrent_and_only_in_groups():
    config, alpha, beta, _folder, work, play = _config()
    work.members = [GroupMember(alpha.id, concurrent=True)]
    alpha.only_in_groups = True
    play.members = [GroupMember(beta.id, concurrent=False)]
    assert move_launcher(config, alpha.id, f"execute:{work.id}", f"execute:{play.id}", 0, [beta.id])
    assert work.members == []
    assert play.members[0] == GroupMember(alpha.id, concurrent=True)
    assert alpha.only_in_groups is True

    # Already in the destination: that group's own concurrent flag stays.
    work.members = [GroupMember(beta.id, concurrent=True)]
    assert move_launcher(config, beta.id, f"execute:{work.id}", f"execute:{play.id}", 0, [alpha.id, beta.id])
    assert play.members[0].concurrent is False


def test_container_to_container_copies_the_hide_flag():
    config, alpha, _beta, folder, _work, _play = _config()
    folder.members = [ContainerMember(alpha.id, only_in_container=True)]
    other = ContainerGroup.new("Other", [ContainerMember(alpha.id, only_in_container=False)])
    config.container_groups.append(other)
    assert move_launcher(config, alpha.id, f"container:{folder.id}", f"container:{other.id}", 0)
    assert folder.members == []
    assert other.members == [ContainerMember(alpha.id, only_in_container=True)]


def test_config_manager_saves_a_move(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "runner.config.platformdirs.user_config_dir",
        lambda *args, **kwargs: str(tmp_path),
    )
    manager = ConfigManager()
    alpha = _launcher("Alpha")
    manager.config.launchers = [alpha]
    folder = ContainerGroup.new("Folder")
    manager.config.container_groups = [folder]
    assert manager.move_launcher(alpha.id, "main", f"container:{folder.id}", -1) is True
    reloaded = ConfigManager()
    assert reloaded.config.container_groups[0].members == [
        ContainerMember(alpha.id, only_in_container=True)
    ]


def test_main_order_roundtrip_ignores_non_strings():
    config = AppConfig()
    config.main_order = [launcher_token("a"), container_token("b")]
    restored = AppConfig.from_dict({"version": 1, "main_order": ["launcher:a", 3, None]})
    assert restored.main_order == ["launcher:a"]
    assert AppConfig.from_dict(config.to_dict()).main_order == config.main_order
    assert AppConfig.from_dict({"version": 1}).main_order == []
