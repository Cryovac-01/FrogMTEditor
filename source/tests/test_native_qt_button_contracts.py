from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui

import native_qt_app
from native_qt.theme import (
    CREATOR_BUTTON_HEIGHT,
    DETAILS_BUTTON_HEIGHT,
    LAUNCHER_BUTTON_HEIGHT,
    TOPBAR_BUTTON_HEIGHT,
    load_icon_pixmap,
)
from native_services import NativeEditorService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
THEME_QSS = PROJECT_ROOT / "src" / "native_assets" / "native_qt_theme.qss"


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


def _assert_fixed_height(button, height: int) -> None:
    assert button.height() == height
    assert button.minimumHeight() == height
    assert button.maximumHeight() == height


def test_button_chromes_have_single_fixed_height_contract(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()

    for button in (window.reload_button, window.command_button, window.pack_templates_button, window.pack_mod_button):
        _assert_fixed_height(button, TOPBAR_BUTTON_HEIGHT)

    for button in (
        window.new_engine_button,
        window.new_tire_button,
        window.empty_new_engine_button,
        window.empty_new_tire_button,
    ):
        _assert_fixed_height(button, LAUNCHER_BUTTON_HEIGHT)

    window.open_engine_creator()
    qapp.processEvents()

    for button in (window.creator_workspace.recommend_button, window.creator_workspace.cancel_button, window.creator_workspace.create_button):
        _assert_fixed_height(button, CREATOR_BUTTON_HEIGHT)
    _assert_fixed_height(window.creator_workspace.details_toggle, DETAILS_BUTTON_HEIGHT)
    _assert_fixed_height(window.audio_apply_button, DETAILS_BUTTON_HEIGHT)
    _assert_fixed_height(window.audio_refresh_button, DETAILS_BUTTON_HEIGHT)


def test_button_icon_pixmaps_are_centered_in_their_slots(qapp):
    native_qt_app.apply_theme(qapp)
    for icon_name, size in (
        ("reload.svg", 16),
        ("parts.svg", 16),
        ("package.svg", 16),
        ("engine.svg", 20),
        ("tire.svg", 20),
    ):
        bounds = _opaque_bounds(load_icon_pixmap(icon_name, size, color="#ffffff"))
        assert not bounds.isNull(), icon_name
        left = bounds.left()
        top = bounds.top()
        right = size - bounds.right() - 1
        bottom = size - bounds.bottom() - 1
        assert abs(left - right) <= 2, f"{icon_name} horizontal margins are {left}, {right}"
        assert abs(top - bottom) <= 2, f"{icon_name} vertical margins are {top}, {bottom}"


def test_button_qss_does_not_reintroduce_chrome_max_height_overrides():
    qss = THEME_QSS.read_text(encoding="utf-8")
    assert 'QPushButton[chrome="topbarAction"]' in qss
    assert "max-height" not in qss


def test_tab_qss_matches_compact_baseline_contract():
    qss = THEME_QSS.read_text(encoding="utf-8")
    assert "QTabBar::tab" in qss
    assert "padding: 8px 13px;" in qss
    assert "margin-right: 4px;" in qss
    assert "min-width" not in qss
