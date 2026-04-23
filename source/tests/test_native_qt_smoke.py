from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_native_qt_smoke_script_exits_cleanly():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "src" / "native_qt_app.py"), "--smoke-test"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

