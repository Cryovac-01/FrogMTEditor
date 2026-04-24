"""
Transmission Editor panel for the Frog Mod Editor Qt UI.

Provides:
  - Browse all vanilla transmissions from unpacked game files
  - View gear ratios, shift time, clutch type, description
  - Modify shift time (the main "clutch upgrade" feature)
  - Clone a transmission with modified shift time under a new name
  - Output staged to the mod tree for packing
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

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
_PILL_BG = "#21303a"
_EDITABLE_BG = "#2a3a4a"


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
            QPushButton:disabled {{ background: {_BORDER}; color: {_MUTED}; }}
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


_SLIDER_STYLE = f"""
    QSlider::groove:horizontal {{
        background: {_CARD}; border: 1px solid {_BORDER};
        height: 6px; border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {_ACCENT}; border: none;
        width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{ background: #7dcce4; }}
    QSlider::sub-page:horizontal {{
        background: {_ACCENT}; border-radius: 3px;
    }}
"""

_TABLE_STYLE = f"""
    QTableWidget {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        gridline-color: {_BORDER}; font-size: 12px;
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QTableWidget::item:selected {{ background: {_EDITABLE_BG}; }}
    QHeaderView::section {{
        background: {_SURFACE}; color: {_MUTED};
        border: 1px solid {_BORDER}; padding: 6px 8px;
        font-size: 11px; font-weight: 600;
    }}
"""

_LIST_STYLE = f"""
    QListWidget {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        font-size: 12px; outline: none;
    }}
    QListWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid {_BORDER};
    }}
    QListWidget::item:selected {{
        background: {_ACCENT}; color: #0b1410;
    }}
    QListWidget::item:hover {{
        background: {_EDITABLE_BG};
    }}
"""

_INPUT_STYLE = f"""
    QLineEdit {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        padding: 6px 12px; font-size: 13px;
    }}
    QLineEdit:focus {{ border-color: {_ACCENT}; }}
"""


class TransmissionEditorPanel(QtWidgets.QWidget):
    """Transmission editor panel — browse, modify shift time, clone."""

    transmission_created = QtCore.Signal(dict)  # emitted after successful create

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent)
        self._vanilla_dir: str = ""
        self._transmissions: Dict[str, dict] = {}  # name → parsed info cache
        self._current_name: str = ""
        self._build_ui()

        # Auto-load bundled vanilla transmissions shipped with this release
        # (data/vanilla/Transmission/) so the user doesn't have to point at
        # their unpacked game folder for stock entries.
        bundled_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "vanilla"
        ))
        if os.path.isdir(bundled_root):
            self.set_unpacked_folder(bundled_root)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {_BG};")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable content
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_BG}; border: none; }}")
        root.addWidget(scroll)

        container = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(container)
        scroll_layout.setContentsMargins(20, 16, 20, 20)
        scroll_layout.setSpacing(14)
        scroll.setWidget(container)

        # ── Header ──
        scroll_layout.addWidget(_label("Transmission Editor", "title"))
        scroll_layout.addWidget(_label(
            "Browse vanilla transmissions, modify shift time and gear ratios, "
            "then create a modified clone. Faster shift times simulate clutch upgrades.",
            "muted",
        ))

        # ── Unpacked folder selector ──
        folder_card = self._make_card()
        folder_layout = folder_card.layout()
        folder_layout.addWidget(_label("UNPACKED GAME FILES", "eyebrow"))

        folder_row = QtWidgets.QHBoxLayout()
        self.folder_label = _label("Not set", "muted")
        folder_row.addWidget(self.folder_label, 1)
        self.folder_button = _action_button("Select Unpacked Folder", "secondary")
        self.folder_button.clicked.connect(self._on_select_folder)
        folder_row.addWidget(self.folder_button)
        folder_layout.addLayout(folder_row)
        scroll_layout.addWidget(folder_card)

        # ── Two-column: transmission list + details ──
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(14)

        # Left: transmission list
        left_card = self._make_card()
        left_layout = left_card.layout()
        left_layout.addWidget(_label("VANILLA TRANSMISSIONS", "eyebrow"))

        self.trans_list = QtWidgets.QListWidget()
        self.trans_list.setStyleSheet(_LIST_STYLE)
        self.trans_list.setMinimumHeight(300)
        self.trans_list.currentRowChanged.connect(self._on_transmission_selected)
        left_layout.addWidget(self.trans_list)
        columns.addWidget(left_card, 2)

        # Right: details + editor
        right_card = self._make_card()
        right_layout = right_card.layout()
        right_layout.addWidget(_label("TRANSMISSION DETAILS", "eyebrow"))

        # Info labels
        self.info_name = _label("—", "accent")
        right_layout.addWidget(self.info_name)

        self.info_description = _label("", "muted")
        right_layout.addWidget(self.info_description)

        # Properties grid
        info_grid = QtWidgets.QGridLayout()
        info_grid.setSpacing(6)
        self._info_labels = {}
        info_fields = [
            ("Clutch Type", "clutch_type"),
            ("Category", "category"),
            ("Forward Gears", "forward_gears"),
            ("Reverse Gears", "reverse_gears"),
            ("Shift Time", "shift_time"),
        ]
        for row_idx, (display_name, key) in enumerate(info_fields):
            name_lbl = _label(display_name, "muted")
            name_lbl.setFixedWidth(110)
            val_lbl = _label("—", "body")
            info_grid.addWidget(name_lbl, row_idx, 0)
            info_grid.addWidget(val_lbl, row_idx, 1)
            self._info_labels[key] = val_lbl
        right_layout.addLayout(info_grid)

        # Gear ratio table
        right_layout.addWidget(_label("Gear Ratios", "section"))
        self.gear_table = QtWidgets.QTableWidget()
        self.gear_table.setStyleSheet(_TABLE_STYLE)
        self.gear_table.setColumnCount(3)
        self.gear_table.setHorizontalHeaderLabels(["Gear", "Ratio", "Efficiency"])
        self.gear_table.horizontalHeader().setStretchLastSection(True)
        self.gear_table.verticalHeader().setVisible(False)
        self.gear_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.gear_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.gear_table.setMaximumHeight(220)
        right_layout.addWidget(self.gear_table)

        columns.addWidget(right_card, 3)
        scroll_layout.addLayout(columns)

        # ── Modification card ──
        mod_card = self._make_card()
        mod_layout = mod_card.layout()
        mod_layout.addWidget(_label("CREATE MODIFIED TRANSMISSION", "eyebrow"))
        mod_layout.addWidget(_label(
            "Adjust the shift time below then create a new transmission asset. "
            "Lower shift time = faster gear changes (clutch upgrade effect).",
            "muted",
        ))

        # New name input
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(_label("New Name:", "body"))
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setStyleSheet(_INPUT_STYLE)
        self.name_edit.setPlaceholderText("e.g. Truck_6Speed_Stage2")
        name_row.addWidget(self.name_edit, 1)
        mod_layout.addLayout(name_row)

        # Shift time slider
        mod_layout.addWidget(_label("Shift Time", "section"))

        shift_row = QtWidgets.QHBoxLayout()
        shift_row.setSpacing(12)

        self.shift_min_label = _label("0.02s", "muted")
        self.shift_min_label.setFixedWidth(40)
        shift_row.addWidget(self.shift_min_label)

        self.shift_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.shift_slider.setRange(2, 200)  # 0.02s to 2.00s in 0.01 steps
        self.shift_slider.setValue(80)  # default 0.80s
        self.shift_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.shift_slider.setTickInterval(20)
        self.shift_slider.setSingleStep(1)
        self.shift_slider.setPageStep(10)
        self.shift_slider.setStyleSheet(_SLIDER_STYLE)
        shift_row.addWidget(self.shift_slider, 1)

        self.shift_max_label = _label("2.00s", "muted")
        self.shift_max_label.setFixedWidth(40)
        shift_row.addWidget(self.shift_max_label)

        self.shift_value_label = _label("0.80s", "accent")
        self.shift_value_label.setFixedWidth(55)
        self.shift_value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.shift_value_label.setStyleSheet(f"color: {_ACCENT}; font-size: 15px; font-weight: 700;")
        shift_row.addWidget(self.shift_value_label)

        mod_layout.addLayout(shift_row)

        # Preview text
        self.shift_preview = _label("", "accent")
        mod_layout.addWidget(self.shift_preview)

        def _on_shift_changed(int_pos):
            val = int_pos * 0.01
            self.shift_value_label.setText(f"{val:.2f}s")
            if self._current_name and self._current_name in self._transmissions:
                orig = self._transmissions[self._current_name].get('shift_time')
                if orig is not None:
                    pct = ((orig - val) / orig) * 100 if orig > 0 else 0
                    if abs(pct) < 0.5:
                        self.shift_preview.setText("")
                    elif pct > 0:
                        self.shift_preview.setText(
                            f"{pct:.1f}% faster than vanilla ({orig:.3f}s → {val:.2f}s)"
                        )
                    else:
                        self.shift_preview.setText(
                            f"{abs(pct):.1f}% slower than vanilla ({orig:.3f}s → {val:.2f}s)"
                        )
                else:
                    self.shift_preview.setText("")
            style = f"color: {_MUTED};" if abs(val - 0.80) < 0.005 else f"color: {_ACCENT};"
            self.shift_value_label.setStyleSheet(style + " font-size: 15px; font-weight: 700;")

        self.shift_slider.valueChanged.connect(_on_shift_changed)

        # Create button
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        self.create_button = _action_button("Create Modified Transmission", "primary")
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self._on_create)
        button_row.addWidget(self.create_button)
        mod_layout.addLayout(button_row)

        scroll_layout.addWidget(mod_card)

        # Status
        self.status_label = _label("", "muted")
        scroll_layout.addWidget(self.status_label)

        scroll_layout.addStretch()

    def _make_card(self) -> QtWidgets.QWidget:
        card = QtWidgets.QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: {_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        return card

    # ------------------------------------------------------------------
    # Folder selection and transmission loading
    # ------------------------------------------------------------------
    def _on_select_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Unpacked MotorTown Folder",
        )
        if path:
            self.set_unpacked_folder(path)

    def set_unpacked_folder(self, path: str) -> None:
        """Set the unpacked game folder and load transmissions.

        Tries several candidate layouts so the selected folder can be:
          - The repo's bundled data/vanilla/ (has Transmission/ directly)
          - A Transmission/ folder selected directly
          - The MotorTown-prefixed layout produced by UnrealPak.exe
            (...\\Unpacked\\MotorTown\\Content\\Cars\\Parts\\Transmission\\)
          - The "Content" folder selected directly
          - The folder one above Content
        """
        candidates = [
            os.path.join(path, 'Content', 'Cars', 'Parts', 'Transmission'),
            os.path.join(path, 'Cars', 'Parts', 'Transmission'),
            os.path.join(path, 'MotorTown', 'Content', 'Cars', 'Parts', 'Transmission'),
            os.path.join(path, 'Transmission'),
            path,  # user pointed directly at a folder with .uexp files
        ]
        trans_dir = None
        for candidate in candidates:
            if not os.path.isdir(candidate):
                continue
            try:
                if any(f.endswith('.uexp') for f in os.listdir(candidate)):
                    trans_dir = candidate
                    break
            except OSError:
                continue

        if trans_dir is None:
            self.status_label.setText("No Transmission folder found in selected path.")
            self.status_label.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
            return

        self._vanilla_dir = trans_dir
        self.folder_label.setText(trans_dir)
        self._load_transmissions()

    def _load_transmissions(self) -> None:
        """Scan the vanilla transmission folder and parse all .uexp files."""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from parsers.uexp_transmission import parse_transmission

        self.trans_list.clear()
        self._transmissions.clear()

        if not self._vanilla_dir or not os.path.isdir(self._vanilla_dir):
            return

        for fname in sorted(os.listdir(self._vanilla_dir)):
            if not fname.endswith('.uexp'):
                continue
            name = fname[:-5]
            uexp_path = os.path.join(self._vanilla_dir, fname)
            uasset_path = os.path.join(self._vanilla_dir, name + '.uasset')
            if not os.path.isfile(uasset_path):
                continue

            try:
                data = open(uexp_path, 'rb').read()
                trans = parse_transmission(data)

                shift = trans.shift_time
                fwd = trans.num_forward_gears
                desc = trans.description or name

                self._transmissions[name] = {
                    'uexp_path': uexp_path,
                    'uasset_path': uasset_path,
                    'shift_time': shift,
                    'forward_gears': fwd,
                    'reverse_gears': trans.num_reverse_gears,
                    'clutch_type': trans.clutch_type_name,
                    'category': trans.category_name,
                    'description': trans.description,
                    'gears': [(g.label, g.ratio, g.efficiency) for g in trans.gears],
                    'has_shift_time': trans.has_shift_time,
                }

                # Display string
                shift_str = f"{shift:.2f}s" if shift is not None else "N/A"
                display = f"{name}  ({fwd}-speed, shift {shift_str})"
                self.trans_list.addItem(display)

            except Exception as e:
                self._transmissions[name] = {'error': str(e)}
                self.trans_list.addItem(f"{name}  (parse error)")

        self.status_label.setText(f"Loaded {len(self._transmissions)} transmissions.")
        self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px;")

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------
    def _on_transmission_selected(self, row: int) -> None:
        if row < 0:
            return

        # Extract name from the list item text (before the first space)
        item_text = self.trans_list.item(row).text()
        name = item_text.split('  (')[0].strip()
        self._current_name = name

        info = self._transmissions.get(name)
        if not info or 'error' in info:
            self.info_name.setText(name)
            self.info_description.setText(f"Error: {info.get('error', 'unknown')}" if info else "Not found")
            self.create_button.setEnabled(False)
            return

        # Update info labels
        self.info_name.setText(name)
        self.info_description.setText(info.get('description') or '(no description)')

        self._info_labels['clutch_type'].setText(info['clutch_type'])
        self._info_labels['category'].setText(info['category'])
        self._info_labels['forward_gears'].setText(str(info['forward_gears']))
        self._info_labels['reverse_gears'].setText(str(info['reverse_gears']))

        shift = info.get('shift_time')
        if shift is not None:
            self._info_labels['shift_time'].setText(f"{shift:.3f}s")
            # Update slider to match
            self.shift_slider.setValue(int(round(shift / 0.01)))
        else:
            self._info_labels['shift_time'].setText("N/A (torque converter)")

        # Update gear table
        gears = info.get('gears', [])
        self.gear_table.setRowCount(len(gears))
        for i, (label, ratio, eff) in enumerate(gears):
            self.gear_table.setItem(i, 0, QtWidgets.QTableWidgetItem(label))
            self.gear_table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{ratio:.4f}"))
            self.gear_table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{eff:.1f}"))
        self.gear_table.resizeColumnsToContents()

        # Suggest a name
        self.name_edit.setText(f"{name}_Stage1")

        # Enable create only if shift time is editable
        self.create_button.setEnabled(info.get('has_shift_time', False))

    # ------------------------------------------------------------------
    # Create modified transmission
    # ------------------------------------------------------------------
    def _on_create(self) -> None:
        name = self._current_name
        if not name or name not in self._transmissions:
            return

        info = self._transmissions[name]
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.status_label.setText("Please enter a name for the new transmission.")
            self.status_label.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
            return

        # Validate name (alphanumeric + underscore)
        if not all(c.isalnum() or c == '_' for c in new_name):
            self.status_label.setText("Name must contain only letters, numbers, and underscores.")
            self.status_label.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
            return

        new_shift = self.shift_slider.value() * 0.01

        try:
            from parsers.uexp_transmission import parse_transmission, serialize_transmission
            from parsers.uasset_transmission_clone import (
                clone_transmission_uasset,
                update_serial_size,
            )
            import native_services as svc

            # Determine output directory
            mt_root = svc.get_mod_tree_root()
            out_dir = os.path.join(mt_root, 'Content', 'Cars', 'Parts', 'Transmission')
            os.makedirs(out_dir, exist_ok=True)

            out_uasset = os.path.join(out_dir, new_name + '.uasset')
            out_uexp = os.path.join(out_dir, new_name + '.uexp')

            # Parse original, modify, serialize
            orig_data = open(info['uexp_path'], 'rb').read()
            trans = parse_transmission(orig_data)

            # Set new shift time
            if trans.has_shift_time:
                trans.shift_time = new_shift

            # Update description
            old_desc = trans.description or name
            new_desc = f"{old_desc} (Shift {new_shift:.2f}s)"
            trans.description = new_desc
            trans.description_length = len(new_desc) + 1

            new_uexp_data = serialize_transmission(trans)

            # Write uexp
            with open(out_uexp, 'wb') as f:
                f.write(new_uexp_data)

            # Clone uasset
            clone_transmission_uasset(info['uasset_path'], new_name, out_uasset)

            # Update serial size in the cloned uasset
            update_serial_size(out_uasset, len(new_uexp_data))

            orig_shift = info.get('shift_time', 0) or 0
            pct = ((orig_shift - new_shift) / orig_shift * 100) if orig_shift > 0 else 0

            self.status_label.setText(
                f"Created '{new_name}' — shift time {new_shift:.2f}s "
                f"({pct:+.1f}% from vanilla {orig_shift:.3f}s). "
                f"Staged in mod tree."
            )
            self.status_label.setStyleSheet(f"color: {_SUCCESS}; font-size: 12px; font-weight: 600;")

            self.transmission_created.emit({
                'name': new_name,
                'shift_time': new_shift,
                'template': name,
                'uasset': out_uasset,
                'uexp': out_uexp,
            })

        except Exception as e:
            self.status_label.setText(f"Error creating transmission: {e}")
            self.status_label.setStyleSheet(f"color: #e74c3c; font-size: 12px;")
