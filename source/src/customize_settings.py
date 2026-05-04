"""Persisted user preferences for theme / UI scale / language.

The settings live in a single JSON file at
<project_root>/data/customize_settings.json so they survive across
sessions. The Customize dialog (native_qt/customize_dialog.py) reads
+ writes this; the theme apply path (native_qt/theme.py) reads it on
startup.

Schema:
  {
    "theme":      "dark" | "light" | "high_contrast",
    "ui_scale":   0.85 | 1.00 | 1.15 | 1.30,
    "language":   "en" | "es" | "fr" | "de" | "ko" | ...
  }

All keys are optional in the on-disk file; missing keys fall back to
``DEFAULTS``. Invalid values fall back too — never raises on read.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict


logger = logging.getLogger(__name__)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(_PROJECT_ROOT, 'data', 'customize_settings.json')


VALID_THEMES = ('dark', 'light', 'high_contrast')
# UI scale presets — multiplier applied to font sizes + scaled
# widget metrics. Top end (200%) supports 4K / high-DPI displays
# where the default 100% renders at sub-readable sizes.
VALID_SCALES = (0.85, 1.00, 1.15, 1.30, 1.50, 1.75, 2.00)
# Language pool — UI is built around these. Translations themselves
# aren't wired yet (English-only for now); selecting a non-English
# language saves the preference but the app stays in English until
# a translation pack is added.
VALID_LANGUAGES = ('en', 'es', 'fr', 'de', 'ko', 'ja', 'pt', 'zh')

LANGUAGE_LABELS = {
    'en': 'English',
    'es': 'Español (Spanish)',
    'fr': 'Français (French)',
    'de': 'Deutsch (German)',
    'ko': '한국어 (Korean)',
    'ja': '日本語 (Japanese)',
    'pt': 'Português (Portuguese)',
    'zh': '中文 (Chinese)',
}


DEFAULTS: Dict[str, Any] = {
    'theme': 'dark',
    'ui_scale': 1.00,
    'language': 'en',
    # Where Pack Mod / Pack Current Part / Pack Templates write their
    # _P.pak output. Empty string = use the user's last-used location
    # (the historical save-dialog default). When set, the save dialog
    # opens at this folder so the user just clicks Save without
    # navigating, and so the .pak lands directly in the game's
    # ~mods directory if pointed there.
    'pak_output_dir': '',
    # Where 'Deploy enabled Lua mods' writes the per-mod folders +
    # mods.txt. Empty string = use source/data/lua_mod_output/ (the
    # historical default). When set, deployments go directly to the
    # game's UE4SS Mods directory — no copy-paste step.
    'lua_output_dir': '',
}


def load() -> Dict[str, Any]:
    """Read settings from disk. Always returns a complete dict — falls
    back to DEFAULTS for any missing or invalid keys."""
    out: Dict[str, Any] = dict(DEFAULTS)
    if not os.path.isfile(SETTINGS_PATH):
        return out
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            on_disk = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("customize_settings: read failed (%s) — using defaults", exc)
        return out
    if not isinstance(on_disk, dict):
        return out

    theme = str(on_disk.get('theme') or '').strip().lower()
    if theme in VALID_THEMES:
        out['theme'] = theme

    try:
        scale = float(on_disk.get('ui_scale') or 0)
        if any(abs(scale - v) < 0.01 for v in VALID_SCALES):
            out['ui_scale'] = scale
    except (TypeError, ValueError):
        pass

    lang = str(on_disk.get('language') or '').strip().lower()
    if lang in VALID_LANGUAGES:
        out['language'] = lang

    # Folder paths — accept any string; we don't gate on existence
    # because the user's game folder might be on a removable drive
    # that's not currently mounted, and we don't want to silently
    # forget their preference. Empty string is the "unset" sentinel.
    pak_dir = on_disk.get('pak_output_dir')
    if isinstance(pak_dir, str):
        out['pak_output_dir'] = pak_dir.strip()
    lua_dir = on_disk.get('lua_output_dir')
    if isinstance(lua_dir, str):
        out['lua_output_dir'] = lua_dir.strip()

    return out


def save(settings: Dict[str, Any]) -> bool:
    """Write settings to disk. Returns True on success.

    Only writes fields with valid values; invalid ones are silently
    dropped (i.e. defaults will apply on the next read)."""
    cleaned: Dict[str, Any] = {}
    if settings.get('theme') in VALID_THEMES:
        cleaned['theme'] = settings['theme']
    try:
        scale = float(settings.get('ui_scale') or 0)
        if any(abs(scale - v) < 0.01 for v in VALID_SCALES):
            cleaned['ui_scale'] = scale
    except (TypeError, ValueError):
        pass
    if settings.get('language') in VALID_LANGUAGES:
        cleaned['language'] = settings['language']
    pak_dir = settings.get('pak_output_dir')
    if isinstance(pak_dir, str):
        cleaned['pak_output_dir'] = pak_dir.strip()
    lua_dir = settings.get('lua_output_dir')
    if isinstance(lua_dir, str):
        cleaned['lua_output_dir'] = lua_dir.strip()

    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(cleaned, f, indent=2)
        return True
    except OSError as exc:
        logger.warning("customize_settings: write failed (%s)", exc)
        return False
