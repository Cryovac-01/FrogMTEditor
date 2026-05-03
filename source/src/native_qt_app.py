"""PySide6 desktop application for Frog Mod Editor."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import traceback
from typing import Any, Callable, List, Optional

from PySide6 import QtCore, QtWidgets

from native_qt import APP_NAME, NativeQtEditorWindow, apply_theme, center_window
from native_qt.theme import log_exception, tail_text
from native_services import NativeEditorService

__all__ = [
    "APP_NAME",
    "NativeQtEditorWindow",
    "apply_theme",
    "center_window",
    "main",
    "run_with_error_dialog",
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    smoke_test = bool(args.smoke_test)

    if smoke_test:
        os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

    logging.info("native qt app start smoke_test=%s", smoke_test)
    app = QtWidgets.QApplication(sys.argv[:1])
    # Honour persisted theme + UI-scale preferences on startup. The
    # Customize dialog (File > Customize) writes to this same file.
    from customize_settings import load as _load_customize
    _cfg = _load_customize()
    apply_theme(app, theme=_cfg.get('theme', 'dark'),
                ui_scale=_cfg.get('ui_scale', 1.0))
    service = NativeEditorService()
    window = NativeQtEditorWindow(service, smoke_test=smoke_test)

    if smoke_test:
        QtCore.QTimer.singleShot(0, app.quit)
        return app.exec()

    center_window(window)
    window.show()
    window.raise_()
    window.activateWindow()
    return app.exec()


def run_with_error_dialog(func: Callable[..., int]) -> Callable[..., int]:
    def wrapper(*args: Any, **kwargs: Any) -> int:
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover
            log_exception("native qt app fatal error")
            try:
                QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
                QtWidgets.QMessageBox.critical(None, APP_NAME, f"{exc}\n\n{tail_text(traceback.format_exc(), 5000)}")
            except Exception:
                pass
            return 1

    return wrapper


if __name__ == "__main__":
    raise SystemExit(run_with_error_dialog(main)())
