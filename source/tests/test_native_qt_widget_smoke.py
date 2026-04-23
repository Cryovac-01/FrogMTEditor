from __future__ import annotations

from PySide6 import QtWidgets

import native_qt_app


def test_qt_theme_can_apply_to_a_widget(qapp, qtbot):
    native_qt_app.apply_theme(qapp)
    widget = QtWidgets.QWidget()
    qtbot.addWidget(widget)
    widget.setWindowTitle("Smoke")
    widget.resize(320, 180)
    widget.show()
    assert widget.isVisible()

