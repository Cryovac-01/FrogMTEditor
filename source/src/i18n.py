"""Minimal i18n / translation layer for Frog Mod Editor.

Design choice: rolled our own instead of using gettext / Qt's
QTranslator. Reasons:
  - Translation packs are tiny key→value JSON dicts that any
    contributor can edit without compiling .mo or .qm files.
  - Lazy translation (resolves at the wrapped string's first
    use) — no setup ceremony, no startup cost.
  - Falls back to the source string when a translation is
    missing, so partial translations still work.

Usage in code:

    from i18n import _

    label = QtWidgets.QLabel(_("Save Changes"))
    button.setText(_("Cancel"))

The wrapped string is the lookup key — it IS the English
source. Translation packs map the English source to the target
language string. Missing keys fall back to the English source.

Translation packs live in src/translations/<lang>.json.
Currently shipped: 'es' (Spanish — proof of concept). Pack files
are loaded lazily on first lookup for that language.

API:

    set_language(code)   — switches the active language.
                            Loads the translation pack on demand.
    _(text)              — translate the source string. Returns
                            text unchanged if pack is missing or
                            doesn't contain a translation.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, Optional


logger = logging.getLogger(__name__)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATIONS_DIR = os.path.join(_PROJECT_ROOT, 'src', 'translations')


_active_lang: str = 'en'
_loaded_packs: Dict[str, Dict[str, str]] = {}


def set_language(code: str) -> None:
    """Switch the active language. ``code`` is an ISO 639-1
    code (e.g. 'en', 'es', 'fr'). Loads the translation pack on
    demand — falls back to English silently if the pack file
    doesn't exist."""
    global _active_lang
    code = (code or 'en').strip().lower()
    if code == _active_lang:
        return
    _active_lang = code
    if code != 'en' and code not in _loaded_packs:
        _load_pack(code)


def _load_pack(code: str) -> None:
    """Read translations/<code>.json into _loaded_packs. Silent
    no-op on missing file or parse error."""
    path = os.path.join(TRANSLATIONS_DIR, f'{code}.json')
    if not os.path.isfile(path):
        logger.info("i18n: no translation pack for %r at %s", code, path)
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Normalise to str -> str. Drop entries whose keys or
            # values aren't strings (defensive against malformed
            # packs).
            cleaned = {
                str(k): str(v)
                for k, v in data.items()
                if isinstance(k, str) and isinstance(v, str)
            }
            _loaded_packs[code] = cleaned
            logger.info("i18n: loaded %d entries from %s", len(cleaned), path)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("i18n: failed to load %s: %s", path, exc)


def active() -> str:
    return _active_lang


def _(text: str) -> str:
    """Translate *text* into the active language. Returns *text*
    unchanged if no translation is available."""
    if _active_lang == 'en' or not text:
        return text
    pack = _loaded_packs.get(_active_lang)
    if not pack:
        return text
    return pack.get(text, text)


def is_translated(text: str) -> bool:
    """True if *text* has a translation in the active pack. Useful
    for tests that want to verify coverage of a curated string set."""
    if _active_lang == 'en':
        return False
    pack = _loaded_packs.get(_active_lang) or {}
    return text in pack


def all_keys() -> list:
    """Return every key in the active translation pack — useful
    for tests + a debug "missing translations" check at startup."""
    pack = _loaded_packs.get(_active_lang) or {}
    return list(pack.keys())
