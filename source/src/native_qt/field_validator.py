"""Hook ``field_bounds.validate`` to PySide6 QLineEdit widgets.

Each call to :func:`attach` attaches one validator to one input and
returns the message label widget that should be added to the form
below the input. The validator:

  - Updates the input's border color on every keystroke (gray = ok,
    yellow = warning, red = error).
  - Updates the message label with the warning / error text (empty
    when ok).
  - Stashes the latest :class:`field_bounds.ValidationResult` on the
    line edit as a dynamic Qt property under the key
    ``"validationResult"`` so the save flow can poll it.

For the save-time pre-flight check, callers iterate widgets and read
the property via :func:`current_status` / :func:`current_message`.

This module deliberately stays thin — no business logic about which
field gets which bounds. That decision lives in the form code (which
already knows what kind of field it's building).
"""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from . import field_bounds as _fb


# Key under which the latest ValidationResult is stashed on the widget
# via setProperty(). Read back with widget.property(_RESULT_KEY).
_RESULT_KEY = "validationResult"

# Stylesheet snippets for each status. Kept loose so they don't override
# whatever theme styling already applies to the editor.
_BORDER_STYLES = {
    'ok':    "",  # No override — fall through to theme default
    'warn':  "QLineEdit { border: 1px solid #d9a13a; }",
    'error': "QLineEdit { border: 1px solid #d44848; }",
}

_MESSAGE_STYLES = {
    'ok':    "color: transparent; font-size: 11px;",
    'warn':  "color: #d9a13a; font-size: 11px;",
    'error': "color: #d44848; font-size: 11px;",
}


def attach(line_edit: QtWidgets.QLineEdit,
           bounds: Optional[_fb.FieldBounds],
           hint_label: QtWidgets.QLabel,
           allow_blank: bool = False) -> None:
    """Bind one input to its bounds. Re-validates on every text change.

    Args:
        line_edit:  The input to validate.
        bounds:     The :class:`field_bounds.FieldBounds` for this
                    input, or None to disable validation (in which
                    case the hint label is hidden).
        hint_label: A QLabel that will host either the inline range
                    hint (when ok) or the warning / error message
                    (when not). Caller is responsible for placing it
                    in the layout below the input.
        allow_blank: When True, an empty input doesn't error.
    """
    if bounds is None:
        hint_label.setVisible(False)
        return

    # Store the bounds on the widget so callers can re-validate later
    # (e.g., the save-time pre-flight) without threading them around.
    line_edit.setProperty('fieldBounds', _serialize(bounds))

    # Tooltip on the input itself, plus the inline hint label below.
    tooltip = bounds.format_tooltip()
    line_edit.setToolTip(tooltip)
    hint_label.setToolTip(tooltip)

    # Initial render: show the static "typical: a-b" hint until the
    # user types something that warrants a different message.
    _render(line_edit, hint_label, _fb.validate(line_edit.text(), bounds, allow_blank=allow_blank), bounds)

    def _on_changed(_text: str = "") -> None:
        result = _fb.validate(line_edit.text(), bounds, allow_blank=allow_blank)
        _render(line_edit, hint_label, result, bounds)

    line_edit.textChanged.connect(_on_changed)


def _render(line_edit: QtWidgets.QLineEdit,
            hint_label: QtWidgets.QLabel,
            result: _fb.ValidationResult,
            bounds: _fb.FieldBounds) -> None:
    """Update the input border and the hint label to match ``result``,
    and stash the result on the widget for later querying."""
    line_edit.setProperty(_RESULT_KEY, _result_to_dict(result))

    # Border colour: keep the existing stylesheet and append the status
    # override so we don't clobber theme rules. The simplest correct
    # approach is to re-apply the full sheet on every status change —
    # Qt is fine with that.
    base = line_edit.property('baseStyleSheet') or ''
    if not base:
        base = line_edit.styleSheet()
        line_edit.setProperty('baseStyleSheet', base)
    override = _BORDER_STYLES.get(result.status, '')
    line_edit.setStyleSheet(base + ('\n' + override if override else ''))

    # Message label: show static range hint when ok, dynamic message
    # otherwise. We always keep the label visible (avoids form layout
    # jitter as ok ↔ warn flips) but make text transparent in ok state.
    if result.status == 'ok':
        hint_label.setText(bounds.format_hint())
        hint_label.setStyleSheet("color: #888888; font-size: 11px;")
    else:
        hint_label.setText(result.message)
        hint_label.setStyleSheet(_MESSAGE_STYLES[result.status])


def make_hint_label(parent: Optional[QtWidgets.QWidget] = None) -> QtWidgets.QLabel:
    """Convenience: build a QLabel pre-styled for use as the hint
    label. Caller still owns placement in the layout."""
    label = QtWidgets.QLabel(parent)
    label.setStyleSheet("color: #888888; font-size: 11px;")
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    label.setWordWrap(True)
    return label


# ──────────────────────────────────────────────────────────────────────
# Save-time querying
# ──────────────────────────────────────────────────────────────────────
def current_status(widget: QtWidgets.QWidget) -> Optional[str]:
    """Return the latest validation status ('ok' | 'warn' | 'error')
    for ``widget``, or None if no validator is attached."""
    raw = widget.property(_RESULT_KEY)
    if not raw:
        return None
    return raw.get('status')


def current_message(widget: QtWidgets.QWidget) -> str:
    """Return the latest validation message for ``widget``, or ''."""
    raw = widget.property(_RESULT_KEY)
    if not raw:
        return ''
    return str(raw.get('message') or '')


# Qt's setProperty/property round-trip works best with simple dicts
# (anything with __getstate__ may pickle weirdly across the bridge);
# use a flat dict here.

def _result_to_dict(result: _fb.ValidationResult) -> dict:
    return {'status': result.status, 'message': result.message}


def _serialize(bounds: _fb.FieldBounds) -> dict:
    return {
        'typical_min': bounds.typical_min,
        'typical_max': bounds.typical_max,
        'hard_min':    bounds.hard_min,
        'hard_max':    bounds.hard_max,
        'unit':        bounds.unit,
        'kind':        bounds.kind,
        'zero_ok':     bounds.zero_ok,
    }
