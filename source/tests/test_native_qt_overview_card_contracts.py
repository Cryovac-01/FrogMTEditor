from __future__ import annotations

from PySide6 import QtWidgets

import native_qt_app
from native_services import NativeEditorService


OVERVIEW_BODY = (
    "Use the navigator to edit generated parts, inspect diagnostics, manage audio, "
    "and package the current workspace without leaving the shell."
)


def _map_geom(child: QtWidgets.QWidget, parent: QtWidgets.QWidget) -> tuple[int, int, int, int]:
    point = child.mapTo(parent, child.rect().topLeft())
    return point.x(), point.y(), child.width(), child.height()


def _find_label(root: QtWidgets.QWidget, text: str) -> QtWidgets.QLabel:
    for label in root.findChildren(QtWidgets.QLabel):
        if label.text() == text:
            return label
    raise AssertionError(f"Missing label: {text}")


def test_workspace_overview_card_stack_reserves_cta_and_metadata_space(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()

    card = window.welcome_card
    title = _find_label(card, "Generated Parts Workspace")
    body = _find_label(card, OVERVIEW_BODY)
    stats = window.welcome_stats_label
    engine_button = window.empty_new_engine_button
    tire_button = window.empty_new_tire_button

    title_x, _, title_w, _ = _map_geom(title, card)
    body_x, body_y, body_w, body_h = _map_geom(body, card)
    engine_x, engine_y, _, engine_h = _map_geom(engine_button, card)
    tire_x, tire_y, _, tire_h = _map_geom(tire_button, card)
    stats_x, stats_y, stats_w, _ = _map_geom(stats, card)

    assert title_x == body_x == engine_x == stats_x
    assert title_w >= 320
    assert body_w >= 320
    assert stats_w >= 320
    assert engine_y - (body_y + body_h) >= 10
    assert stats_y - max(engine_y + engine_h, tire_y + tire_h) >= 10
    assert abs(engine_y - tire_y) <= 1


def test_workspace_overview_illustration_is_contained(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()

    hero = window.welcome_hero_label
    pixmap = hero.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    dpr = max(1.0, pixmap.devicePixelRatio())
    assert pixmap.width() / dpr <= 340
    assert pixmap.height() / dpr <= 192

    card = window.welcome_card
    hero_x, hero_y, hero_w, hero_h = _map_geom(hero, card)
    assert hero_x > window.empty_new_tire_button.mapTo(card, window.empty_new_tire_button.rect().topRight()).x()
    assert hero_y >= 0
    assert hero_x + hero_w <= card.width()
    assert hero_y + hero_h <= card.height()
