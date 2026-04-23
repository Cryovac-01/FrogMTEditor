from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets

import native_qt_app
from native_qt.widgets import QuickActionDialog
from native_services import NativeEditorService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEME_QSS = PROJECT_ROOT / "src" / "native_assets" / "native_qt_theme.qss"


def _show_and_process(qapp, qtbot, widget: QtWidgets.QWidget) -> None:
    qtbot.addWidget(widget)
    widget.show()
    qapp.processEvents()


def test_single_line_inputs_are_sized_by_python_contract_not_qss_min_height(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    window.resize(1280, 800)
    _show_and_process(qapp, qtbot, window)

    assert 28 <= window.search_edit.height() <= 34

    window.open_engine_creator()
    qapp.processEvents()

    creator_sidebar = window.creator_sidebar
    for field in (creator_sidebar.search_edit, creator_sidebar.group_combo, creator_sidebar.sort_combo):
        assert 28 <= field.height() <= 34

    rendered_fields = list((window.creator_workspace.form.property_widgets if window.creator_workspace.form else {}).values())
    line_fields = [field for field in rendered_fields if isinstance(field, (QtWidgets.QLineEdit, QtWidgets.QComboBox))]
    assert line_fields
    assert all(28 <= field.height() <= 34 for field in line_fields[:8])


def test_quick_action_search_uses_same_single_line_input_contract(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    dialog = QuickActionDialog(
        [
            {"title": "Reload Workspace", "shortcut": "Ctrl+R", "keywords": "reload"},
            {"title": "New Engine", "shortcut": "Ctrl+Shift+N", "keywords": "engine create"},
        ]
    )
    dialog.resize(620, 420)
    _show_and_process(qapp, qtbot, dialog)

    assert 28 <= dialog.search_edit.height() <= 34


def test_qss_does_not_reintroduce_field_min_height_ownership():
    qss = THEME_QSS.read_text(encoding="utf-8")
    forbidden_blocks = (
        "QLineEdit,\nQComboBox {\n    min-height",
        "QPlainTextEdit {\n    min-height",
    )
    for block in forbidden_blocks:
        assert block not in qss
