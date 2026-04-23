"""
Policy Editor panel for the Frog Mod Editor Qt UI.

Provides:
  - Table of existing vanilla policies (editable cost and effect value)
  - Ability to add new policies with existing effect types
  - Apply/Reset controls
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import policy_editor as pol
from parsers.uexp_policies_dt import (
    EFFECT_TYPE_LABELS, EFFECT_TYPE_UNITS, EFFECT_TYPES, PolicyRow,
)


# ---------------------------------------------------------------------------
# Colour tokens (consistent with main app theme)
# ---------------------------------------------------------------------------
_BG = "#161c26"
_SURFACE = "#1c2533"
_CARD = "#212c3d"
_BORDER = "#2d3948"
_TEXT = "#edf2f7"
_MUTED = "#8b97a8"
_ACCENT = "#67bfd9"
_SUCCESS = "#6fcf97"
_WARNING = "#f2c94c"
_DANGER = "#e74c3c"
_EDITABLE_BG = "#2a3a4a"
_NEW_ROW_BG = "#1a2f2a"


def _label(text: str, kind: str = "body") -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setWordWrap(True)
    styles = {
        "title": f"color: {_TEXT}; font-size: 16px; font-weight: 600;",
        "section": f"color: {_TEXT}; font-size: 13px; font-weight: 600;",
        "muted": f"color: {_MUTED}; font-size: 12px;",
        "eyebrow": f"color: {_MUTED}; font-size: 10px; font-weight: 700; letter-spacing: 1px;",
        "accent": f"color: {_ACCENT}; font-size: 13px; font-weight: 600;",
        "success": f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;",
        "warning": f"color: {_WARNING}; font-size: 12px;",
        "body": f"color: {_TEXT}; font-size: 13px;",
    }
    lbl.setStyleSheet(styles.get(kind, styles["body"]))
    return lbl


def _action_button(text: str, role: str = "primary") -> QtWidgets.QPushButton:
    btn = QtWidgets.QPushButton(text)
    if role == "primary":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: #0b1410; border: none;
                border-radius: 4px; padding: 8px 20px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #7dcce4; }}
        """)
    elif role == "danger":
        btn.setStyleSheet(f"""
            QPushButton {{
                background: #c0392b; color: {_TEXT}; border: none;
                border-radius: 4px; padding: 8px 20px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: #e74c3c; }}
        """)
    else:
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                border-radius: 4px; padding: 8px 20px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {_BORDER}; }}
        """)
    return btn


_TABLE_STYLE = f"""
    QTableWidget {{
        background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
        border-radius: 4px; gridline-color: {_BORDER}; font-size: 12px;
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QTableWidget::item:selected {{ background: {_EDITABLE_BG}; }}
    QHeaderView::section {{
        background: {_SURFACE}; color: {_MUTED}; border: 1px solid {_BORDER};
        padding: 6px 8px; font-size: 11px; font-weight: 600;
    }}
"""

_INPUT_STYLE = f"""
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background: {_EDITABLE_BG}; color: {_TEXT}; border: 1px solid {_BORDER};
        border-radius: 4px; padding: 6px 10px; font-size: 13px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {_ACCENT};
    }}
"""

_COMBO_STYLE = f"""
    QComboBox {{
        background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
        border-radius: 4px; padding: 6px 12px; font-size: 13px; min-width: 180px;
    }}
    QComboBox::drop-down {{ border: none; }}
    QComboBox QAbstractItemView {{
        background: {_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
        selection-background-color: {_ACCENT};
    }}
"""


class PolicyEditorPanel(QtWidgets.QWidget):
    """Policy editor panel with table of policies and add-new controls."""

    policy_applied = QtCore.Signal(dict)

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self._vanilla_rows: list = []
        self._new_policies: list = []   # list of dicts for new rows
        self._build_ui()
        self._load_state()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {_BG};")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Scroll wrapper
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{
                background: {_SURFACE}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER}; border-radius: 4px; min-height: 30px;
            }}
        """)
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)

        # ── Header ──────────────────────────────────────────────────
        layout.addWidget(_label("POLICY EDITOR", "eyebrow"))
        layout.addWidget(_label("Town Policy Editor"))

        desc = _label(
            "Edit existing policy costs and effect values, or add new policies "
            "using the available effect types. Changes are staged into the mod "
            "and included when you Pack Mod.",
            "muted",
        )
        layout.addWidget(desc)

        # ── Status ──────────────────────────────────────────────────
        self.status_label = _label("", "muted")
        layout.addWidget(self.status_label)

        # ── Existing Policies Table ─────────────────────────────────
        layout.addWidget(_label("Existing Policies", "section"))
        layout.addWidget(_label(
            "Edit Cost or Effect Value directly in the table. "
            "Display Name can also be changed.",
            "muted",
        ))

        self.policy_table = QtWidgets.QTableWidget()
        self.policy_table.setStyleSheet(_TABLE_STYLE)
        self.policy_table.setColumnCount(5)
        self.policy_table.setHorizontalHeaderLabels([
            "Row Name", "Display Name", "Effect Type", "Cost", "Effect Value",
        ])
        header = self.policy_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.policy_table.verticalHeader().setVisible(False)
        self.policy_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.policy_table.setMinimumHeight(280)
        layout.addWidget(self.policy_table)

        # ── Add New Policy ──────────────────────────────────────────
        add_frame = QtWidgets.QFrame()
        add_frame.setStyleSheet(f"""
            QFrame {{
                background: {_SURFACE}; border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        add_layout = QtWidgets.QVBoxLayout(add_frame)
        add_layout.setContentsMargins(16, 12, 16, 12)
        add_layout.setSpacing(10)

        add_layout.addWidget(_label("Add New Policy", "section"))
        add_layout.addWidget(_label(
            "Create additional policies using an existing effect type. "
            "For example, add a second Fuel Subsidy with a higher percentage.",
            "muted",
        ))

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        # Effect type combo
        self.new_effect_combo = QtWidgets.QComboBox()
        self.new_effect_combo.setStyleSheet(_COMBO_STYLE)
        for short, label in EFFECT_TYPE_LABELS.items():
            self.new_effect_combo.addItem(label, short)
        self.new_effect_combo.currentIndexChanged.connect(self._on_effect_type_changed)
        form.addRow(_label("Effect Type:", "body"), self.new_effect_combo)

        # Display name
        self.new_display_edit = QtWidgets.QLineEdit()
        self.new_display_edit.setStyleSheet(_INPUT_STYLE)
        self.new_display_edit.setPlaceholderText("e.g. Fuel Subsidy 40%")
        form.addRow(_label("Display Name:", "body"), self.new_display_edit)

        # Cost
        self.new_cost_spin = QtWidgets.QSpinBox()
        self.new_cost_spin.setStyleSheet(_INPUT_STYLE)
        self.new_cost_spin.setRange(0, 999999)
        self.new_cost_spin.setValue(100)
        form.addRow(_label("Cost:", "body"), self.new_cost_spin)

        # Effect value
        self.new_value_spin = QtWidgets.QDoubleSpinBox()
        self.new_value_spin.setStyleSheet(_INPUT_STYLE)
        self.new_value_spin.setRange(-999999.0, 999999.0)
        self.new_value_spin.setDecimals(4)
        self.new_value_spin.setValue(0.4)
        form.addRow(_label("Effect Value:", "body"), self.new_value_spin)

        # Unit hint
        self.unit_hint_label = _label("", "muted")
        form.addRow(QtWidgets.QLabel(""), self.unit_hint_label)

        add_layout.addLayout(form)

        add_btn_row = QtWidgets.QHBoxLayout()
        add_btn_row.addStretch(1)
        self.add_policy_button = _action_button("Add Policy", "secondary")
        self.add_policy_button.clicked.connect(self._on_add_policy)
        add_btn_row.addWidget(self.add_policy_button)
        add_layout.addLayout(add_btn_row)

        layout.addWidget(add_frame)

        # ── New Policies Queue ──────────────────────────────────────
        self.new_table_label = _label("New Policies (pending)", "section")
        self.new_table_label.hide()
        layout.addWidget(self.new_table_label)

        self.new_table = QtWidgets.QTableWidget()
        self.new_table.setStyleSheet(_TABLE_STYLE)
        self.new_table.setColumnCount(5)
        self.new_table.setHorizontalHeaderLabels([
            "Display Name", "Effect Type", "Cost", "Effect Value", "",
        ])
        new_header = self.new_table.horizontalHeader()
        new_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        new_header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        new_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        new_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        new_header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.new_table.horizontalHeader().resizeSection(4, 80)
        self.new_table.verticalHeader().setVisible(False)
        self.new_table.setMaximumHeight(200)
        self.new_table.hide()
        layout.addWidget(self.new_table)

        # ── Action Buttons ──────────────────────────────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(12)
        self.apply_button = _action_button("Apply Policy Changes", "primary")
        self.reset_button = _action_button("Reset to Vanilla", "danger")
        btn_row.addStretch(1)
        btn_row.addWidget(self.reset_button)
        btn_row.addWidget(self.apply_button)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── Connect signals ─────────────────────────────────────────
        self.apply_button.clicked.connect(self._on_apply)
        self.reset_button.clicked.connect(self._on_reset)

        # Trigger initial hint
        self._on_effect_type_changed()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        """Load vanilla policies and any saved modifications."""
        data = pol.load_vanilla_policies()
        if data is None:
            self.status_label.setText("⚠ Could not load vanilla policy data.")
            self.status_label.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
            return

        self._vanilla_rows = list(data.rows)
        self._populate_table()

        # Load saved settings
        saved = pol.load_saved_settings()
        if saved:
            self._restore_saved(saved)

        if pol.is_policy_mod_staged():
            self.status_label.setText("Policy mod is staged for packing.")
            self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px;")
        else:
            self.status_label.setText("No policy modifications applied yet.")
            self.status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")

    def _populate_table(self) -> None:
        """Fill the existing policies table."""
        self.policy_table.setRowCount(len(self._vanilla_rows))
        for i, row in enumerate(self._vanilla_rows):
            # Row name (read-only)
            name_item = QtWidgets.QTableWidgetItem(row.row_name)
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            name_item.setForeground(QtGui.QColor(_MUTED))
            self.policy_table.setItem(i, 0, name_item)

            # Display name (editable)
            self.policy_table.setItem(i, 1, QtWidgets.QTableWidgetItem(row.display_name))

            # Effect type (read-only)
            effect_item = QtWidgets.QTableWidgetItem(row.effect_label())
            effect_item.setFlags(effect_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            effect_item.setForeground(QtGui.QColor(_ACCENT))
            self.policy_table.setItem(i, 2, effect_item)

            # Cost (editable)
            cost_item = QtWidgets.QTableWidgetItem(str(row.cost))
            self.policy_table.setItem(i, 3, cost_item)

            # Effect value (editable)
            val_item = QtWidgets.QTableWidgetItem(f"{row.effect_value:.4f}")
            self.policy_table.setItem(i, 4, val_item)

    def _restore_saved(self, saved: dict) -> None:
        """Restore saved modifications into the UI."""
        # Restore existing row modifications
        mods = saved.get('modifications', {})
        for i, row in enumerate(self._vanilla_rows):
            m = mods.get(row.row_name)
            if not m:
                continue
            if 'display_name' in m:
                self.policy_table.item(i, 1).setText(m['display_name'])
            if 'cost' in m:
                self.policy_table.item(i, 3).setText(str(m['cost']))
            if 'effect_value' in m:
                self.policy_table.item(i, 4).setText(f"{float(m['effect_value']):.4f}")

        # Restore new policies
        for np in saved.get('new_policies', []):
            self._new_policies.append(np)
        self._refresh_new_table()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_effect_type_changed(self) -> None:
        short = self.new_effect_combo.currentData()
        if short:
            unit, desc = EFFECT_TYPE_UNITS.get(short, ('', ''))
            self.unit_hint_label.setText(desc)
        else:
            self.unit_hint_label.setText("")

    def _on_add_policy(self) -> None:
        display = self.new_display_edit.text().strip()
        if not display:
            self.status_label.setText("⚠ Display name is required.")
            self.status_label.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")
            return

        effect_type = self.new_effect_combo.currentData()
        cost = self.new_cost_spin.value()
        value = self.new_value_spin.value()

        self._new_policies.append({
            'display_name': display,
            'effect_type': effect_type,
            'cost': cost,
            'effect_value': value,
        })
        self._refresh_new_table()

        # Clear inputs
        self.new_display_edit.clear()
        self.new_cost_spin.setValue(100)

        self.status_label.setText(f"Added new policy: {display}")
        self.status_label.setStyleSheet(f"color: {_ACCENT}; font-size: 12px;")

    def _on_remove_new(self, idx: int) -> None:
        if 0 <= idx < len(self._new_policies):
            removed = self._new_policies.pop(idx)
            self._refresh_new_table()
            self.status_label.setText(f"Removed: {removed.get('display_name', '?')}")
            self.status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")

    def _refresh_new_table(self) -> None:
        """Update the new policies queue table."""
        if not self._new_policies:
            self.new_table.hide()
            self.new_table_label.hide()
            return

        self.new_table_label.show()
        self.new_table.show()
        self.new_table.setRowCount(len(self._new_policies))

        for i, np in enumerate(self._new_policies):
            self.new_table.setItem(i, 0, QtWidgets.QTableWidgetItem(np['display_name']))

            effect_label = EFFECT_TYPE_LABELS.get(np['effect_type'], np['effect_type'])
            effect_item = QtWidgets.QTableWidgetItem(effect_label)
            effect_item.setForeground(QtGui.QColor(_ACCENT))
            self.new_table.setItem(i, 1, effect_item)

            self.new_table.setItem(i, 2, QtWidgets.QTableWidgetItem(str(np['cost'])))
            self.new_table.setItem(i, 3, QtWidgets.QTableWidgetItem(f"{np['effect_value']:.4f}"))

            # Remove button
            remove_btn = _action_button("Remove", "danger")
            remove_btn.setFixedHeight(28)
            idx_capture = i
            remove_btn.clicked.connect(lambda checked, idx=idx_capture: self._on_remove_new(idx))
            self.new_table.setCellWidget(i, 4, remove_btn)

    def _on_apply(self) -> None:
        """Collect all changes and apply."""
        settings = self._collect_settings()

        # Check if there are any actual changes
        has_mods = bool(settings.get('modifications'))
        has_new = bool(settings.get('new_policies'))
        if not has_mods and not has_new:
            self.status_label.setText("No changes to apply.")
            self.status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
            return

        result = pol.apply_policy_changes(settings)

        if result.get('success'):
            msg = (
                f"Policy changes applied: {result.get('modified', 0)} modified, "
                f"{result.get('added', 0)} added "
                f"({result.get('total_rows', 0)} total policies)."
            )
            self.status_label.setText(msg)
            self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px;")
            self.policy_applied.emit(result)
        else:
            self.status_label.setText(f"⚠ {result.get('error', 'Unknown error')}")
            self.status_label.setStyleSheet(f"color: {_WARNING}; font-size: 12px;")

    def _on_reset(self) -> None:
        """Reset everything to vanilla."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset Policies",
            "Remove all policy modifications and revert to vanilla values?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        pol.remove_policy_mod()
        self._new_policies.clear()
        self._refresh_new_table()
        self._populate_table()  # reset table to vanilla values

        self.status_label.setText("Policies reset to vanilla.")
        self.status_label.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------
    def _collect_settings(self) -> dict:
        """Gather current UI state into a settings dict."""
        modifications = {}
        for i, row in enumerate(self._vanilla_rows):
            display_item = self.policy_table.item(i, 1)
            cost_item = self.policy_table.item(i, 3)
            value_item = self.policy_table.item(i, 4)

            if not display_item or not cost_item or not value_item:
                continue

            current_display = display_item.text().strip()
            try:
                current_cost = int(cost_item.text().strip())
            except ValueError:
                current_cost = row.cost
            try:
                current_value = float(value_item.text().strip())
            except ValueError:
                current_value = row.effect_value

            # Only record if changed from vanilla
            changed = False
            mod = {}
            if current_display != row.display_name:
                mod['display_name'] = current_display
                changed = True
            if current_cost != row.cost:
                mod['cost'] = current_cost
                changed = True
            if abs(current_value - row.effect_value) > 1e-6:
                mod['effect_value'] = current_value
                changed = True

            if changed:
                modifications[row.row_name] = mod

        return {
            'modifications': modifications,
            'new_policies': list(self._new_policies),
        }
