"""Lua-mod deployer registry.

Each module under this package describes one Cryovac Lua mod that the
editor can generate, configure, and deploy.

The registry is a flat list of deployer modules. Each module must expose:

    MOD_NAME           : str           — UE4SS folder name (e.g. 'CryovacCargoScaling')
    UI_TITLE           : str           — user-facing title in the LUA Scripts panel
    UI_DESCRIPTION     : str           — multi-paragraph explanation (can use <b>HTML</b>)
    DEFAULT_CONFIG     : Dict[str, Any] — defaults for every SETTINGS key
    SETTINGS           : List[Setting] — declarative UI controls (see below)
    generate_main_lua(config) -> str   — returns the Scripts/main.lua content
    generate_readme(config)   -> str   — returns the shipped README.txt
    deploy(config, output_dir) -> dict — writes the mod folder, returns {success, path}

SETTINGS entries drive the UI panel layout. Each item is a Setting
dataclass with kind in {"mode", "int", "float", "bool"}:

    mode   → 4-button row (Vanilla/Low/High/Off or custom labels)
    int    → QSpinBox
    float  → QDoubleSpinBox or slider
    bool   → QCheckBox

The LUA Scripts panel builds controls from SETTINGS, reads their values
into a dict matching DEFAULT_CONFIG's shape, and passes that to deploy().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class ModeOption:
    """One button in a mode-selector row."""
    key: str            # stored value, e.g. 'Off'
    label: str          # button text, e.g. 'Off'
    factor: float       # numeric factor this mode represents (for display)
    tooltip: str = ''


@dataclass
class Setting:
    """Declarative description of one user-configurable value."""
    key: str                             # config dict key
    label: str                           # control label
    kind: str                            # 'mode' | 'int' | 'float' | 'bool'
    default: Any
    # kind='mode':
    options: Optional[List[ModeOption]] = None
    # kind='int' / 'float':
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    suffix: str = ''                     # e.g. ' slots', ' ×', ' s'
    # kind='bool':
    # (no extras)
    tooltip: str = ''
    # Optional: long-form helper text shown below the control.
    hint: str = ''


# Standard Vanilla/Low/High/Off set reused by multiple mods.
MODE_FACTOR_OPTIONS: List[ModeOption] = [
    ModeOption('Vanilla', 'Vanilla', 1.0,
               'Default game value — no change.'),
    ModeOption('Low',     'Low',     0.5,
               'Half the vanilla effect.'),
    ModeOption('High',    'High',    1.5,
               '1.5× the vanilla effect.'),
    ModeOption('Off',     'Off',     0.0,
               'Zero out the effect entirely.'),
]


# Registry is populated lazily at import time by each deployer module.
_DEPLOYERS: List[Any] = []


def register(deployer_module: Any) -> None:
    """Called by each deployer module at import time to register itself."""
    required = ('MOD_NAME', 'UI_TITLE', 'UI_DESCRIPTION', 'DEFAULT_CONFIG',
                'SETTINGS', 'generate_main_lua', 'generate_readme', 'deploy')
    for attr in required:
        if not hasattr(deployer_module, attr):
            raise TypeError(
                f"Lua-mod deployer {deployer_module.__name__} is missing {attr!r}"
            )
    _DEPLOYERS.append(deployer_module)


def all_deployers() -> List[Any]:
    """Return all registered deployer modules in registration order."""
    # Trigger lazy imports if this is the first call.
    _ensure_loaded()
    return list(_DEPLOYERS)


def get_deployer(mod_name: str) -> Optional[Any]:
    """Look up a deployer by its MOD_NAME."""
    _ensure_loaded()
    for d in _DEPLOYERS:
        if d.MOD_NAME == mod_name:
            return d
    return None


_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Import each deployer module so its register() call fires.
    # Order here is the display order in the UI panel.
    from . import cargo_scaling                 # noqa: F401
    from . import cargo_volume_boost            # noqa: F401
    from . import company_vehicle_care          # noqa: F401
    from . import company_vehicle_limits        # noqa: F401
    from . import exp_multiplier                # noqa: F401
    from . import population_boost              # noqa: F401
    from . import skip_night                    # noqa: F401
    from . import slow_decay                    # noqa: F401


# Shared default output directory. Mirrors what cargo_scaling_deployer used
# before we moved it; kept here so every mod writes to the same place.
import os as _os
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
DEFAULT_OUTPUT_DIR = _os.path.join(_PROJECT_ROOT, 'data', 'lua_mod_output')
