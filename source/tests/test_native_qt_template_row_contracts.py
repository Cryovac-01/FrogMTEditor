from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import native_qt_app
from native_qt.widgets import TemplateListDelegate
from native_services import NativeEditorService


def test_template_row_delegate_regions_do_not_compete(qapp):
    native_qt_app.apply_theme(qapp)
    font = QtGui.QFont()
    meta_font = QtGui.QFont(font)
    meta_font.setPointSizeF(max(8.2, meta_font.pointSizeF() - 0.6))
    badge_font = QtGui.QFont(meta_font)
    badge_font.setWeight(QtGui.QFont.Weight.DemiBold)
    badge_metrics = QtGui.QFontMetrics(badge_font)

    delegate = TemplateListDelegate("engine")
    regions = delegate._row_layout(
        QtCore.QRect(0, 0, 314, delegate.ENGINE_ROW_HEIGHT),
        {"fuel_label": "Diesel"},
        badge_metrics,
    )

    assert regions["accent"].right() < regions["icon_slot"].left()
    assert regions["icon_slot"].right() < regions["title"].left()
    assert regions["title"].right() < regions["badge"].left()
    assert regions["title"].bottom() < regions["meta"].bottom()
    assert regions["meta"].left() == regions["title"].left()


def test_engine_and_tire_template_rows_keep_stable_heights(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    window = native_qt_app.NativeQtEditorWindow(NativeEditorService(), smoke_test=True)
    qtbot.addWidget(window)
    window.resize(1280, 800)
    window.show()
    qapp.processEvents()

    window.open_engine_creator()
    qapp.processEvents()
    engine_delegate = window.creator_sidebar.list_view.itemDelegate()
    assert isinstance(engine_delegate, TemplateListDelegate)
    assert engine_delegate.sizeHint(QtWidgets.QStyleOptionViewItem(), QtCore.QModelIndex()).height() == TemplateListDelegate.ENGINE_ROW_HEIGHT

    engine_index = window.creator_sidebar.list_model.index(0, 0)
    assert window.creator_sidebar.list_view.visualRect(engine_index).height() == TemplateListDelegate.ENGINE_ROW_HEIGHT

    window.open_tire_creator()
    qapp.processEvents()
    tire_delegate = window.creator_sidebar.list_view.itemDelegate()
    assert isinstance(tire_delegate, TemplateListDelegate)
    assert tire_delegate.sizeHint(QtWidgets.QStyleOptionViewItem(), QtCore.QModelIndex()).height() == TemplateListDelegate.TIRE_ROW_HEIGHT

    tire_index = window.creator_sidebar.list_model.index(0, 0)
    assert window.creator_sidebar.list_view.visualRect(tire_index).height() == TemplateListDelegate.TIRE_ROW_HEIGHT
