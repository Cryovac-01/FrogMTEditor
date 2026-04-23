from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"

for path in (ROOT, SRC, SCRIPTS):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")
