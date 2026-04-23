from __future__ import annotations

from PySide6 import QtCore, QtGui

import native_qt_app
from native_qt.theme import LAUNCHER_BUTTON_HEIGHT, load_icon_pixmap
from native_services import NativeEditorService


def _opaque_bounds(pixmap: QtGui.QPixmap) -> QtCore.QRect:
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    min_x = image.width()
    min_y = image.height()
    max_x = -1
    max_y = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if QtGui.QColor.fromRgba(image.pixel(x, y)).alpha() <= 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return QtCore.QRect()
    return QtCore.QRect(min_x, min_y, (max_x - min_x) + 1, (max_y - min_y) + 1)


def _button_has_text_headroom(button) -> bool:
    required_width = button.fontMetrics().horizontalAdvance(button.text()) + button.iconSize().width() + 18
    return (
        button.height() >= button.fontMetrics().height() + 14
        and button.width() >= required_width
    )


def test_command_bar_and_actions_have_headroom(qapp, qtbot):
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.show()
    qapp.processEvents()

    assert window.command_bar.height() >= window.status_label.sizeHint().height() + 10
    for button in (
        window.reload_button,
        window.command_button,
        window.pack_templates_button,
        window.pack_mod_button,
    ):
        assert _button_has_text_headroom(button)


def test_launcher_buttons_share_geometry_and_fit_text(qapp, qtbot):
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.show()
    qapp.processEvents()

    for left, right in (
        (window.new_engine_button, window.new_tire_button),
        (window.empty_new_engine_button, window.empty_new_tire_button),
    ):
        assert left.height() == right.height()
        assert left.iconSize() == right.iconSize()
        assert left.height() >= LAUNCHER_BUTTON_HEIGHT
        assert _button_has_text_headroom(left)
        assert _button_has_text_headroom(right)


def test_engine_and_tire_icons_have_comparable_visual_bounds():
    engine_bounds = _opaque_bounds(load_icon_pixmap("engine.svg", 24, color="#ffffff"))
    tire_bounds = _opaque_bounds(load_icon_pixmap("tire.svg", 24, color="#ffffff"))

    assert engine_bounds.height() >= tire_bounds.height() - 1
    assert abs(engine_bounds.height() - tire_bounds.height()) <= 3
    assert engine_bounds.width() >= tire_bounds.width() - 4
