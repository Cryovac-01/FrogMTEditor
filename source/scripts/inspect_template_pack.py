"""Inspect a Frog Mod Editor template pak for template export coverage."""
from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.routes import inspect_template_pack  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/inspect_template_pack.py <path-to-pak>", file=sys.stderr)
        return 2
    result = inspect_template_pack(argv[1])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
