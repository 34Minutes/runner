"""Drag container rows, reorder inside a menu, and move a launcher onto another menu."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from runner.config import AppConfig, Launcher
from runner.ui.dropdown import DropdownPanel, SubmenuButton
from runner.ui.launch_button import LaunchButton


def _send_mouse(button, kind, global_pos, button_state, buttons_state):
    local = button.mapFromGlobal(global_pos)
    event = QMouseEvent(
        kind,
        QPointF(local),
        QPointF(global_pos),
        button_state,
        buttons_state,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(button, event)


def _press_move_release(button, start, end):
    _send_mouse(button, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    _send_mouse(button, QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    _send_mouse(button, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)


def _show(qtbot, panel, x, y):
    panel.move(x, y)
    panel.show()
    # Height is fixed from the buttons. Rebuild while hidden skips them, so
    # measure again once the list is on screen.
    panel.update_height_for_content()
    qtbot.waitExposed(panel)
    QApplication.processEvents()


def test_container_row_drags_among_launchers(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.set_mix_rows(True)
    panel.set_drag_source_key("main")
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, beta]
    panel.set_submenu_items([("folder", "Folder")])
    panel.rebuild_buttons([alpha, beta])
    _show(qtbot, panel, 40, 40)

    folder = panel.submenu_button("folder")
    beta_button = next(button for button in panel._buttons if isinstance(button, LaunchButton) and button.launcher.name == "Beta")
    rows = []
    launchers = []
    panel.rows_reordered.connect(rows.append)
    panel.reordered.connect(launchers.append)
    panel.external_drop.connect(lambda *args: launchers.append(args))

    start = folder.mapToGlobal(folder.rect().center())
    below = beta_button.mapToGlobal(beta_button.rect().bottomLeft())
    below.setY(below.y() + 8)
    assert panel.rect().contains(panel.mapFromGlobal(below))
    try:
        _send_mouse(folder, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        _send_mouse(folder, QEvent.Type.MouseMove, below, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        assert panel._drag_active is True
        assert folder.property("dragging") == "true"
        assert "border: 4px solid rgba(255, 220, 70, 240)" in folder.styleSheet()
        _send_mouse(folder, QEvent.Type.MouseButtonRelease, below, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    finally:
        panel._cancel_drag()

    assert launchers == []
    assert rows == [[f"launcher:{alpha.id}", f"launcher:{beta.id}", f"container:folder"]]
    assert [type(button).__name__ for button in panel._buttons[:3]] == [
        "LaunchButton",
        "LaunchButton",
        "SubmenuButton",
    ]


def test_container_row_snaps_back_when_it_leaves_the_list(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    panel.set_mix_rows(True)
    panel.set_drag_source_key("main")
    alpha = Launcher.new("Alpha", "a")
    cfg.launchers = [alpha]
    panel.set_submenu_items([("folder", "Folder")])
    panel.rebuild_buttons([alpha])
    _show(qtbot, panel, 40, 40)
    folder = panel.submenu_button("folder")
    rows = []
    panel.rows_reordered.connect(rows.append)
    start = folder.mapToGlobal(folder.rect().center())
    outside = QPoint(panel.mapToGlobal(panel.rect().topRight()).x() + 80, start.y() + 24)
    try:
        _press_move_release(folder, start, outside)
    finally:
        panel._cancel_drag()
    assert rows == []
    assert isinstance(panel._buttons[0], SubmenuButton)
    assert panel._buttons[0].item_id == "folder"


def test_member_reorder_keeps_a_hidden_launcher_in_its_slot(qapp, qtbot):
    cfg = AppConfig()
    panel = DropdownPanel(cfg)
    qtbot.addWidget(panel)
    alpha = Launcher.new("Alpha", "a")
    hidden = Launcher.new("Hidden", "h", enabled=False)
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, hidden, beta]
    panel.set_drag_source_key("container:box")
    panel.set_order_ids(lambda: [alpha.id, hidden.id, beta.id])
    panel.set_peer_finder(lambda pos: panel if panel.frameGeometry().contains(pos) else None)
    panel.rebuild_buttons([alpha, beta])
    _show(qtbot, panel, 40, 40)
    buttons = [button for button in panel._buttons if isinstance(button, LaunchButton)]
    reordered = []
    external = []
    panel.reordered.connect(reordered.append)
    panel.external_drop.connect(lambda *args: external.append(args))
    start = buttons[1].mapToGlobal(buttons[1].rect().center())
    above = buttons[0].mapToGlobal(buttons[0].rect().topLeft())
    above.setY(above.y() - 4)
    try:
        _press_move_release(buttons[1], start, above)
    finally:
        panel._cancel_drag()
    assert external == []
    assert reordered == [[beta.id, hidden.id, alpha.id]]


def test_drag_onto_another_menu_emits_external_drop(qapp, qtbot):
    cfg = AppConfig()
    source = DropdownPanel(cfg)
    dest = DropdownPanel(cfg)
    qtbot.addWidget(source)
    qtbot.addWidget(dest)
    alpha = Launcher.new("Alpha", "a")
    beta = Launcher.new("Beta", "b")
    cfg.launchers = [alpha, beta]
    source.set_drag_source_key("container:box")
    source.rebuild_buttons([alpha])
    dest.set_drag_source_key("main")
    dest.rebuild_buttons([beta])
    _show(qtbot, source, 20, 30)
    _show(qtbot, dest, 420, 30)

    def finder(pos):
        if dest.frameGeometry().contains(pos):
            return dest
        if source.frameGeometry().contains(pos):
            return source
        return None

    source.set_peer_finder(finder)
    dropped = []
    reordered = []
    source.external_drop.connect(lambda *args: dropped.append(args))
    source.reordered.connect(reordered.append)
    button = next(item for item in source._buttons if isinstance(item, LaunchButton))
    start = button.mapToGlobal(button.rect().center())
    target = next(item for item in dest._buttons if isinstance(item, LaunchButton))
    end = target.mapToGlobal(target.rect().center())
    try:
        _send_mouse(button, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
        _send_mouse(button, QEvent.Type.MouseMove, end, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
        assert source._external_target is not None
        assert source._ghost is not None and source._ghost.isVisible()
        assert "border: 4px solid rgba(255, 220, 70, 240)" in source._ghost._label.styleSheet()
        _send_mouse(button, QEvent.Type.MouseButtonRelease, end, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    finally:
        source._cancel_drag()
    assert reordered == []
    assert dropped
    assert dropped[0][0] == alpha.id
    assert dropped[0][1] == "container:box"
    assert dropped[0][2] == "main"
    assert [item.launcher.name for item in source._buttons if isinstance(item, LaunchButton)] == ["Alpha"]
    assert source._ghost is None or not source._ghost.isVisible()


def test_drop_on_an_execute_group_row_appends_to_that_group(qapp, qtbot):
    cfg = AppConfig()
    source = DropdownPanel(cfg)
    groups = DropdownPanel(cfg)
    qtbot.addWidget(source)
    qtbot.addWidget(groups)
    alpha = Launcher.new("Alpha", "a")
    cfg.launchers = [alpha]
    source.set_drag_source_key("main")
    source.rebuild_buttons([alpha])
    groups.set_drag_source_key("groups")
    groups.rebuild_buttons([Launcher(id="work", name="Work", command="")])
    _show(qtbot, source, 20, 40)
    _show(qtbot, groups, 460, 40)

    def finder(pos):
        if groups.frameGeometry().contains(pos):
            return groups
        if source.frameGeometry().contains(pos):
            return source
        return None

    source.set_peer_finder(finder)
    dropped = []
    source.external_drop.connect(lambda *args: dropped.append(args))
    button = next(item for item in source._buttons if isinstance(item, LaunchButton))
    row = next(item for item in groups._buttons if isinstance(item, LaunchButton))
    try:
        _press_move_release(
            button,
            button.mapToGlobal(button.rect().center()),
            row.mapToGlobal(row.rect().center()),
        )
    finally:
        source._cancel_drag()
    assert dropped == [(alpha.id, "main", "execute:work", -1)]


def test_drop_on_a_container_row_from_another_menu_joins_that_container(qapp, qtbot):
    cfg = AppConfig()
    source = DropdownPanel(cfg)
    dest = DropdownPanel(cfg)
    qtbot.addWidget(source)
    qtbot.addWidget(dest)
    alpha = Launcher.new("Alpha", "a")
    cfg.launchers = [alpha]
    source.set_drag_source_key("execute:work")
    source.rebuild_buttons([alpha])
    dest.set_drag_source_key("main")
    dest.set_submenu_items([("folder", "Folder")])
    dest.rebuild_buttons([])
    _show(qtbot, source, 20, 50)
    _show(qtbot, dest, 480, 50)

    def finder(pos):
        if dest.frameGeometry().contains(pos):
            return dest
        if source.frameGeometry().contains(pos):
            return source
        return None

    source.set_peer_finder(finder)
    dropped = []
    source.external_drop.connect(lambda *args: dropped.append(args))
    button = next(item for item in source._buttons if isinstance(item, LaunchButton))
    folder = dest.submenu_button("folder")
    try:
        _press_move_release(
            button,
            button.mapToGlobal(button.rect().center()),
            folder.mapToGlobal(folder.rect().center()),
        )
    finally:
        source._cancel_drag()
    assert dropped == [(alpha.id, "execute:work", "container:folder", -1)]
