"""Shared Qt theme, assets, constants, and UI helpers."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import functools
import json
import logging
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets


_SRC_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SRC_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from native_services import (  # noqa: E402
    NativeEditorService,
    PROPERTY_DESCRIPTIONS,
    VARIANT_LABELS,
    build_engine_state,
    build_engine_warnings,
    build_property_value_map,
    categorize_properties,
    estimate_tire_grip_g,
    format_property_name,
    get_edit_value,
    get_tire_field_coverage,
    is_readonly_property,
)
from desktop_view_models import (  # noqa: E402
    AssetDocument,
    AssetSummary,
    CatalogEntry,
    ConflictState,
    PackPreview,
    WorkspaceSummary,
    flatten_metadata_rows,
    recent_activity,
)

APP_NAME = "Frog Mod Editor"
ASSET_DIR = _SRC_DIR / "native_assets"
ICON_DIR = ASSET_DIR / "icons"
THEME_PATH = ASSET_DIR / "native_qt_theme.qss"
LOG_PATH = Path(
    os.environ.get("FROG_MOD_EDITOR_NATIVE_LOG")
    or os.environ.get("MOTORTOWN_WORKBENCH_LOG")
    or os.environ.get("FROG_MOD_EDITOR_LOG")
    or (Path(tempfile.gettempdir()) / "FrogModEditor_native_app.log")
)
PATH_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
ROW_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2

SURFACE_BG = QtGui.QColor("#161c26")
GRID_COLOR = QtGui.QColor("#2d3948")
LINE_COLOR = QtGui.QColor("#67bfd9")
LINE_FILL = QtGui.QColor("#cae9f2")
TEXT_COLOR = QtGui.QColor("#edf2f7")
MUTED_COLOR = QtGui.QColor("#8b97a8")

FUEL_THEME_STYLES: Dict[str, Dict[str, str]] = {
    "gas": {
        "key": "gas",
        "label": "Gasoline",
        "accent": "#78bfd3",
        "badge_bg": "#21303a",
        "badge_border": "#5d91a0",
        "badge_text": "#d7edf4",
    },
    "diesel": {
        "key": "diesel",
        "label": "Diesel",
        "accent": "#c9a16b",
        "badge_bg": "#2a2620",
        "badge_border": "#b48d58",
        "badge_text": "#f1e4cd",
    },
    "ev": {
        "key": "ev",
        "label": "Electric",
        "accent": "#7cc0d3",
        "badge_bg": "#182935",
        "badge_border": "#6ab3cb",
        "badge_text": "#d6eef5",
    },
    "neutral": {
        "key": "neutral",
        "label": "Unknown",
        "accent": "#8f9cad",
        "badge_bg": "#1a222d",
        "badge_border": "#49596c",
        "badge_text": "#d6dee8",
    },
}

CREATOR_SECTION_ICON_STYLES: Dict[str, tuple[str, str]] = {
    "New Asset": ("parts.svg", "#92a4b8"),
    "Identity and Shop": ("tag.svg", "#92a4b8"),
    "Performance": ("curve.svg", "#7db58b"),
    "Grip and Slip": ("spring.svg", "#7db58b"),
    "Load and Speed": ("scale.svg", "#92a4b8"),
    "Load and Resistance": ("scale.svg", "#92a4b8"),
}

CREATOR_FIELD_ICON_STYLES: Dict[str, tuple[str, str]] = {
    "internal_name": ("parts.svg", "#92a4b8"),
    "display_name": ("tag.svg", "#92a4b8"),
    "description": ("tag.svg", "#92a4b8"),
    "code": ("tag.svg", "#92a4b8"),
    "price": ("coin.svg", "#d3a54c"),
    "weight": ("scale.svg", "#92a4b8"),
    "sound_dir": ("audio.svg", "#92a4b8"),
    "MaxTorque": ("curve.svg", "#7db58b"),
    "MotorMaxPower": ("curve.svg", "#7db58b"),
    "MaxRPM": ("curve.svg", "#7db58b"),
    "LateralStiffness": ("spring.svg", "#7db58b"),
    "CorneringStiffness": ("spring.svg", "#7db58b"),
    "CamberStiffness": ("spring.svg", "#7db58b"),
    "LongStiffness": ("spring.svg", "#7db58b"),
    "LongSlipStiffness": ("spring.svg", "#7db58b"),
    "LoadRating": ("scale.svg", "#92a4b8"),
    "MaxLoad": ("scale.svg", "#92a4b8"),
    "RollingResistance": ("tire.svg", "#92a4b8"),
}

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


@dataclass(frozen=True)
class SpacingScale:
    xxs: int = 4
    xs: int = 6
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 20
    xxl: int = 24


@dataclass(frozen=True)
class RadiusScale:
    xs: int = 10
    sm: int = 12
    md: int = 16


@dataclass(frozen=True)
class TypeScale:
    product: float = 13.25
    page_title: float = 17.0
    section: float = 10.5
    body: float = 10.0
    meta: float = 8.75


@dataclass(frozen=True)
class ShellMetrics:
    root_margin: int = 16
    root_spacing: int = 12
    command_bar_min_height: int = 62
    command_bar_horizontal_padding: int = 16
    command_bar_vertical_padding: int = 10
    command_action_height: int = 36
    header_action_height: int = 36
    launcher_height: int = 42
    status_pill_height: int = 34
    creator_button_height: int = 38
    details_button_height: int = 34
    metric_min_height: int = 72
    sidebar_min_width: int = 348
    sidebar_max_width: int = 376
    inspector_min_width: int = 348
    inspector_max_width: int = 412
    creator_label_width: int = 150


@dataclass(frozen=True)
class IconSizeScale:
    inline: int = 16
    button: int = 16
    primary_button: int = 19
    launcher: int = 20
    tab: int = 18
    field: int = 15
    tree: int = 28
    list_row: int = 30
    empty_state: int = 30


@dataclass(frozen=True)
class IconSpec:
    optical_scale: float = 1.0
    offset_x: int = 0
    offset_y: int = 0


SPACING = SpacingScale()
RADIUS = RadiusScale()
TYPE_SCALE = TypeScale()
SHELL_METRICS = ShellMetrics()
ICON_SIZES = IconSizeScale()

ICON_SPECS: Dict[str, IconSpec] = {
    "default": IconSpec(),
    "audio": IconSpec(optical_scale=0.98),
    "coin": IconSpec(optical_scale=0.98),
    "curve": IconSpec(optical_scale=1.0),
    "delete": IconSpec(optical_scale=0.98),
    "diagnostics": IconSpec(optical_scale=1.0),
    "engine": IconSpec(optical_scale=1.0),
    "fork": IconSpec(optical_scale=0.98),
    "package": IconSpec(optical_scale=0.98),
    "parts": IconSpec(optical_scale=0.96),
    "reload": IconSpec(optical_scale=1.0),
    "revert": IconSpec(optical_scale=0.98),
    "save": IconSpec(optical_scale=1.0),
    "scale": IconSpec(optical_scale=1.0),
    "search": IconSpec(optical_scale=0.95),
    "spring": IconSpec(optical_scale=0.98),
    "tag": IconSpec(optical_scale=0.98),
    "tire": IconSpec(optical_scale=1.0),
}

TEMPLATE_ROW_ICON_SIZE = ICON_SIZES.list_row
TREE_ICON_SIZE = ICON_SIZES.tree
FIELD_ICON_SIZE = ICON_SIZES.field
PRIMARY_BUTTON_ICON_SIZE = ICON_SIZES.primary_button
LAUNCHER_BUTTON_ICON_SIZE = ICON_SIZES.launcher
TOPBAR_BUTTON_ICON_SIZE = ICON_SIZES.button
TOPBAR_BUTTON_HEIGHT = SHELL_METRICS.command_action_height
HEADER_BUTTON_HEIGHT = SHELL_METRICS.header_action_height
LAUNCHER_BUTTON_HEIGHT = SHELL_METRICS.launcher_height
CREATOR_BUTTON_HEIGHT = SHELL_METRICS.creator_button_height
DETAILS_BUTTON_HEIGHT = SHELL_METRICS.details_button_height
CREATOR_LABEL_WIDTH = SHELL_METRICS.creator_label_width
FIELD_CONTROL_MIN_HEIGHT = 28
MULTILINE_CONTROL_MIN_HEIGHT = 64


def log_exception(context: str) -> None:
    logging.exception(context)


def format_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(float(f"{value:.6g}"))
    return str(value)


def format_compact_metric(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def tail_text(text: str, limit: int = 4000) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[-limit:]


def set_surface(widget: QtWidgets.QWidget, surface: str) -> None:
    widget.setProperty("surface", surface)


def set_label_kind(label: QtWidgets.QLabel, kind: str) -> None:
    label.setProperty("kind", kind)


def set_button_role(button: QtWidgets.QPushButton, role: str, icon_size: Optional[int] = None) -> None:
    button.setProperty("role", role)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    if icon_size is None:
        if role in {"primary", "secondary", "subtle"}:
            icon_size = 18
        else:
            icon_size = 16
    button.setIconSize(QtCore.QSize(icon_size, icon_size))


def set_button_size(button: QtWidgets.QPushButton, size: str) -> None:
    button.setProperty("density", size)


def set_field_role(widget: QtWidgets.QWidget, role: str) -> None:
    widget.setProperty("fieldRole", role)


def configure_field_control(widget: QtWidgets.QWidget, role: str = "editor") -> None:
    set_field_role(widget, role)
    if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QComboBox)):
        widget.setMinimumHeight(FIELD_CONTROL_MIN_HEIGHT)
    elif isinstance(widget, QtWidgets.QPlainTextEdit):
        widget.setMinimumHeight(MULTILINE_CONTROL_MIN_HEIGHT)


def set_button_chrome(
    button: QtWidgets.QPushButton,
    chrome: str,
    *,
    height: Optional[int] = None,
    icon_size: Optional[int] = None,
) -> None:
    button.setProperty("chrome", chrome)
    if icon_size is not None:
        button.setIconSize(QtCore.QSize(icon_size, icon_size))
    if height is not None:
        button.setFixedHeight(height)
        button.setSizePolicy(button.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Fixed)


def make_action_button(
    text: str,
    *,
    role: str = "secondary",
    icon: Optional[QtGui.QIcon] = None,
    chrome: str = "topbarAction",
    height: Optional[int] = None,
    icon_size: Optional[int] = None,
    expanding: bool = False,
) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    if icon is not None:
        button.setIcon(icon)
    resolved_icon_size = icon_size
    if resolved_icon_size is None:
        resolved_icon_size = PRIMARY_BUTTON_ICON_SIZE if role == "primary" else ICON_SIZES.button
    set_button_role(button, role, icon_size=resolved_icon_size)
    if height is None:
        height = HEADER_BUTTON_HEIGHT if chrome == "headerAction" else TOPBAR_BUTTON_HEIGHT
    set_button_chrome(button, chrome, height=height, icon_size=resolved_icon_size)
    button.setMinimumWidth(0)
    button.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding if expanding else QtWidgets.QSizePolicy.Policy.Minimum,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )
    return button


def configure_launcher_button(button: QtWidgets.QPushButton, role: str, icon: QtGui.QIcon) -> None:
    button.setIcon(icon)
    set_button_role(button, role, icon_size=LAUNCHER_BUTTON_ICON_SIZE)
    set_button_chrome(button, "launcherAction", height=LAUNCHER_BUTTON_HEIGHT, icon_size=LAUNCHER_BUTTON_ICON_SIZE)
    button.setMinimumWidth(0)
    button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)


def set_widget_margins(layout: QtWidgets.QLayout, all_sides: int = 0) -> None:
    layout.setContentsMargins(all_sides, all_sides, all_sides, all_sides)


def set_margins(
    layout: QtWidgets.QLayout,
    horizontal: int = 0,
    vertical: Optional[int] = None,
) -> None:
    if vertical is None:
        vertical = horizontal
    layout.setContentsMargins(horizontal, vertical, horizontal, vertical)


def refresh_style(widget: QtWidgets.QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def engine_fuel_theme(fuel: Any = "", variant: Any = "", is_ev: Optional[bool] = None) -> Dict[str, str]:
    fuel_value = str(fuel or "").strip().lower()
    variant_value = str(variant or "").strip().lower()
    if is_ev or fuel_value in {"electric", "ev"} or variant_value == "ev":
        return dict(FUEL_THEME_STYLES["ev"])
    if fuel_value == "diesel" or variant_value.startswith("diesel"):
        return dict(FUEL_THEME_STYLES["diesel"])
    if fuel_value in {"gas", "gasoline", "petrol"} or fuel_value == "" or variant_value in {"ice", "ice_standard", "ice_compact", "bike"}:
        return dict(FUEL_THEME_STYLES["gas"])
    return dict(FUEL_THEME_STYLES["neutral"])


def command_bar_height(font: Optional[QtGui.QFont] = None) -> int:
    base_font = QtGui.QFont(font or QtWidgets.QApplication.font())
    product_font = QtGui.QFont(base_font)
    product_font.setPointSizeF(TYPE_SCALE.product)
    meta_font = QtGui.QFont(base_font)
    meta_font.setPointSizeF(TYPE_SCALE.meta)
    content_height = max(
        QtGui.QFontMetrics(product_font).height() + QtGui.QFontMetrics(meta_font).height() + SPACING.xs,
        SHELL_METRICS.command_action_height,
        SHELL_METRICS.status_pill_height,
    )
    return max(
        SHELL_METRICS.command_bar_min_height,
        content_height + (SHELL_METRICS.command_bar_vertical_padding * 2),
    )


def enrich_engine_template_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    theme = engine_fuel_theme(item.get("fuel"), item.get("variant"))
    metrics: List[str] = []
    hp = format_compact_metric(item.get("hp"))
    if hp:
        metrics.append(f"{hp} hp")
    torque = format_compact_metric(item.get("torque"))
    if torque:
        metrics.append(f"{torque} Nm")
    group_label = str(item.get("group_label") or "").strip()
    if group_label:
        metrics.append(group_label)
    item["fuel_theme_key"] = theme["key"]
    item["fuel_label"] = theme["label"]
    item["secondary_metrics"] = "  •  ".join(metrics)
    return item


def enrich_tire_template_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    metrics: List[str] = []
    code = str(item.get("code") or "").strip()
    if code:
        metrics.append(code)
    group_label = str(item.get("group_label") or "").strip()
    if group_label:
        metrics.append(group_label)
    grip = format_compact_metric(item.get("grip_g"))
    if grip:
        metrics.append(f"{grip} G")
    item["secondary_metrics"] = "  •  ".join(metrics)
    return item


def apply_tone_badge(label: QtWidgets.QLabel, text: str, tone: str) -> None:
    label.setText(text)
    set_label_kind(label, "templateBadge")
    label.setProperty("tone", tone)
    refresh_style(label)


def build_icon_text_widget(
    text: str,
    kind: str,
    *,
    icon_name: str = "",
    icon_color: str = "#9aacbd",
    icon_size: int = 14,
) -> QtWidgets.QWidget | QtWidgets.QLabel:
    if not icon_name:
        label = QtWidgets.QLabel(text)
        set_label_kind(label, kind)
        return label
    wrapper = QtWidgets.QWidget()
    wrapper.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACING.xs)
    icon_label = QtWidgets.QLabel()
    icon_label.setPixmap(load_icon_pixmap(icon_name, icon_size, color=icon_color))
    icon_label.setFixedSize(icon_size, icon_size)
    icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    text_label = QtWidgets.QLabel(text)
    if kind == "fieldLabel":
        text_label.setWordWrap(True)
    set_label_kind(text_label, kind)
    layout.addWidget(icon_label, 0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(text_label, 0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    layout.addStretch(1)
    return wrapper


def make_icon_label(
    icon_name: str,
    *,
    color: str = "#9aacbd",
    size: int = ICON_SIZES.inline,
    align_top: bool = False,
) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel()
    label.setPixmap(load_icon_pixmap(icon_name, size, color=color))
    label.setFixedSize(size, size)
    label.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignHCenter
        | (QtCore.Qt.AlignmentFlag.AlignTop if align_top else QtCore.Qt.AlignmentFlag.AlignVCenter)
    )
    return label


def make_section_header(
    title: str,
    *,
    eyebrow: str = "",
    body: str = "",
    icon_name: str = "",
    icon_color: str = "#9aacbd",
) -> QtWidgets.QWidget:
    wrapper = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(SPACING.sm)
    if icon_name:
        layout.addWidget(make_icon_label(icon_name, color=icon_color, size=ICON_SIZES.inline), 0, QtCore.Qt.AlignmentFlag.AlignTop)
    copy = QtWidgets.QVBoxLayout()
    copy.setContentsMargins(0, 0, 0, 0)
    copy.setSpacing(SPACING.xxs)
    if eyebrow:
        eyebrow_label = QtWidgets.QLabel(eyebrow)
        set_label_kind(eyebrow_label, "eyebrow")
        copy.addWidget(eyebrow_label)
    title_label = QtWidgets.QLabel(title)
    title_label.setWordWrap(True)
    set_label_kind(title_label, "section")
    copy.addWidget(title_label)
    if body:
        body_label = QtWidgets.QLabel(body)
        body_label.setWordWrap(True)
        set_label_kind(body_label, "muted")
        copy.addWidget(body_label)
    layout.addLayout(copy, 1)
    return wrapper


def make_status_strip(text: str = "", *, kind: str = "notice") -> tuple[QtWidgets.QFrame, QtWidgets.QLabel, QtWidgets.QHBoxLayout]:
    frame = QtWidgets.QFrame()
    set_surface(frame, "status")
    layout = QtWidgets.QHBoxLayout(frame)
    layout.setContentsMargins(SPACING.md, SPACING.xs, SPACING.md, SPACING.xs)
    layout.setSpacing(SPACING.sm)
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    set_label_kind(label, kind)
    layout.addWidget(label, 1)
    return frame, label, layout


def make_empty_state(
    title: str,
    body: str,
    *,
    icon_name: str = "parts.svg",
    icon_color: str = "#88bfd0",
) -> QtWidgets.QFrame:
    frame = QtWidgets.QFrame()
    set_surface(frame, "panel")
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
    layout.setSpacing(SPACING.sm)
    icon = make_icon_label(icon_name, color=icon_color, size=ICON_SIZES.empty_state)
    layout.addWidget(icon, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
    title_label = QtWidgets.QLabel(title)
    title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    title_label.setWordWrap(True)
    set_label_kind(title_label, "section")
    body_label = QtWidgets.QLabel(body)
    body_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    body_label.setWordWrap(True)
    set_label_kind(body_label, "muted")
    layout.addWidget(title_label)
    layout.addWidget(body_label)
    return frame


def make_metric_row(metrics: Iterable[tuple[str, str]]) -> QtWidgets.QFrame:
    frame = QtWidgets.QFrame()
    set_surface(frame, "section")
    layout = QtWidgets.QHBoxLayout(frame)
    layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
    layout.setSpacing(SPACING.sm)
    for value, label in metrics:
        card = QtWidgets.QFrame()
        set_surface(card, "metric")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        card_layout.setSpacing(SPACING.xxs)
        value_label = QtWidgets.QLabel(value)
        set_label_kind(value_label, "metricValue")
        label_label = QtWidgets.QLabel(label)
        set_label_kind(label_label, "metricLabel")
        card_layout.addWidget(value_label)
        card_layout.addWidget(label_label)
        layout.addWidget(card, 1)
    return frame


def build_creator_card(
    title: str,
    *,
    icon_name: str = "",
    icon_color: str = "#9aacbd",
) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    card = QtWidgets.QFrame()
    set_surface(card, "creatorSection")
    card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    outer = QtWidgets.QVBoxLayout(card)
    outer.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
    outer.setSpacing(SPACING.sm)

    header = build_icon_text_widget(title, "cardTitle", icon_name=icon_name, icon_color=icon_color, icon_size=FIELD_ICON_SIZE)
    outer.addWidget(header)

    body_layout = QtWidgets.QVBoxLayout()
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(6)
    outer.addLayout(body_layout)
    return card, body_layout


def build_creator_row(
    label_widget: QtWidgets.QWidget,
    editor_widget: QtWidgets.QWidget,
    *,
    helper_text: str = "",
    inline_helper_text: str = "",
    label_width: int = CREATOR_LABEL_WIDTH,
    tooltip_targets: Iterable[QtWidgets.QWidget] = (),
) -> QtWidgets.QWidget:
    row = QtWidgets.QWidget()
    row_layout = QtWidgets.QGridLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setHorizontalSpacing(SPACING.md)
    row_layout.setVerticalSpacing(SPACING.xs)
    row_layout.setColumnMinimumWidth(0, label_width)
    row_layout.setColumnStretch(1, 1)

    label_cell = QtWidgets.QWidget()
    label_cell.setFixedWidth(label_width)
    label_layout = QtWidgets.QHBoxLayout(label_cell)
    label_layout.setContentsMargins(0, 0, 0, 0)
    label_layout.setSpacing(0)
    label_layout.addWidget(label_widget, 1, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
    row_layout.addWidget(label_cell, 0, 0, QtCore.Qt.AlignmentFlag.AlignTop)
    row_layout.addWidget(editor_widget, 0, 1)

    if helper_text:
        label_cell.setToolTip(helper_text)
        for widget in tooltip_targets:
            widget.setToolTip(helper_text)

    if inline_helper_text:
        helper_label = QtWidgets.QLabel(inline_helper_text)
        helper_label.setWordWrap(True)
        set_label_kind(helper_label, "fieldDesc")
        row_layout.addWidget(helper_label, 1, 1)

    return row


def build_creator_card_row(cards: Iterable[QtWidgets.QWidget]) -> QtWidgets.QWidget:
    row_widget = QtWidgets.QWidget()
    row_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    row_layout = QtWidgets.QHBoxLayout(row_widget)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(SPACING.md)
    for card in cards:
        card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        row_layout.addWidget(card, 1, QtCore.Qt.AlignmentFlag.AlignTop)
    return row_widget


def build_creator_form_card(
    title: str,
    *,
    icon_name: str = "",
    icon_color: str = "#9aacbd",
) -> tuple[QtWidgets.QFrame, QtWidgets.QFormLayout]:
    card = QtWidgets.QFrame()
    set_surface(card, "creatorSection")
    card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    outer = QtWidgets.QVBoxLayout(card)
    outer.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
    outer.setSpacing(SPACING.sm)

    header = build_icon_text_widget(title, "cardTitle", icon_name=icon_name, icon_color=icon_color, icon_size=FIELD_ICON_SIZE)
    outer.addWidget(header)

    body = QtWidgets.QWidget()
    form = QtWidgets.QFormLayout(body)
    form.setContentsMargins(0, 0, 0, 0)
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.DontWrapRows)
    form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
    form.setHorizontalSpacing(SPACING.lg)
    form.setVerticalSpacing(SPACING.sm)
    outer.addWidget(body)
    return card, form


def build_creator_grid_card(
    title: str,
    *,
    icon_name: str = "",
    icon_color: str = "#9aacbd",
) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    card = QtWidgets.QFrame()
    set_surface(card, "creatorSection")
    card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
    outer = QtWidgets.QVBoxLayout(card)
    outer.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
    outer.setSpacing(SPACING.sm)

    header = build_icon_text_widget(title, "cardTitle", icon_name=icon_name, icon_color=icon_color, icon_size=FIELD_ICON_SIZE)
    outer.addWidget(header)

    body_layout = QtWidgets.QVBoxLayout()
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(10)
    outer.addLayout(body_layout)
    return card, body_layout


# ──────────────────────────────────────────────────────────────────────
# Theme variants — appended over the base dark QSS to recolour
# without rewriting every selector. Each variant is a self-contained
# QSS string applied via app.setStyleSheet AFTER the base sheet.
# ──────────────────────────────────────────────────────────────────────
_LIGHT_VARIANT_QSS = """
/* Light theme overrides — applied on top of the dark base.
   Keeps the existing QSS structure but inverts background and text
   so users can choose between dark / light without a full reskin.
   The accent green is kept (works on both light and dark backgrounds).

   QMenu::item and QMenuBar::item are MORE specific than QMenu /
   QMenuBar in the base QSS, so they need their own override rules
   here — otherwise the base sheet's dark colours would win and the
   menu items would render as dark-on-light (the menu's own
   background) → unreadable.
*/
QWidget { background-color: #f1f3f6; color: #1c2330; }
QFrame, QGroupBox, QScrollArea, QStackedWidget { background-color: #f1f3f6; color: #1c2330; }
QLabel { color: #1c2330; background: transparent; }
QPushButton { background: #ffffff; color: #1c2330; border: 1px solid #c8d0d9; }
QPushButton:hover { border-color: #73c686; color: #2a5a32; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {
    background: #ffffff; color: #1c2330; border: 1px solid #c8d0d9;
}
QLineEdit:focus, QComboBox:focus { border-color: #73c686; }
QHeaderView::section { background: #e2e7ee; color: #1c2330; border: 1px solid #c8d0d9; }
QTableView, QTreeView, QListView {
    background: #ffffff; color: #1c2330;
    alternate-background-color: #f7f9fb;
    selection-background-color: #c2e8c8; selection-color: #0b2310;
}
/* Menu bar: pale-blue strip; item text dark for readability. */
QMenuBar { background: #e2e7ee; color: #1c2330; border: 1px solid #c8d0d9; }
QMenuBar::item { background: transparent; color: #1c2330; padding: 6px 10px; }
QMenuBar::item:selected { background: #c2e8c8; color: #0b2310; }
QMenuBar::item:pressed { background: #a8dbb0; color: #0b2310; }
/* Drop-down menus: white panel, dark item text, green selection. */
QMenu { background: #ffffff; color: #1c2330; border: 1px solid #c8d0d9; padding: 6px; }
QMenu::item { background: transparent; color: #1c2330; padding: 7px 22px 7px 12px; border-radius: 4px; }
QMenu::item:selected { background: #c2e8c8; color: #0b2310; }
QMenu::item:disabled { color: #8a93a0; }
QMenu::separator { background: #c8d0d9; height: 1px; margin: 4px 6px; }
QToolTip { background: #ffffff; color: #1c2330; border: 1px solid #c8d0d9; }
QSplitter::handle { background: #c8d0d9; }
"""

_HIGH_CONTRAST_VARIANT_QSS = """
/* High-contrast theme — pure black background, pure white text,
   bright yellow accent. Designed for accessibility (low-vision
   users) and bright-light environments where dark UI is unreadable.
   Borders are intentionally thick to make element boundaries
   unambiguous.

   QMenu::item / QMenuBar::item need explicit overrides too —
   otherwise the base QSS's dark text colour wins on specificity
   and the menu items become invisible.
*/
QWidget { background-color: #000000; color: #ffffff; }
QFrame, QGroupBox, QScrollArea, QStackedWidget { background-color: #000000; color: #ffffff; }
QLabel { color: #ffffff; background: transparent; }
QPushButton {
    background: #000000; color: #ffff00;
    border: 2px solid #ffff00; padding: 6px 12px;
    font-weight: bold;
}
QPushButton:hover { background: #ffff00; color: #000000; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {
    background: #000000; color: #ffffff;
    border: 2px solid #ffffff; padding: 4px;
}
QLineEdit:focus, QComboBox:focus { border-color: #ffff00; }
QHeaderView::section {
    background: #000000; color: #ffff00;
    border: 2px solid #ffff00; font-weight: bold;
}
QTableView, QTreeView, QListView {
    background: #000000; color: #ffffff;
    alternate-background-color: #1a1a1a;
    selection-background-color: #ffff00; selection-color: #000000;
}
/* Menu bar: black strip, white item text, yellow selection. */
QMenuBar { background: #000000; color: #ffffff; border-bottom: 2px solid #ffffff; }
QMenuBar::item { background: transparent; color: #ffffff; padding: 6px 10px; font-weight: bold; }
QMenuBar::item:selected { background: #ffff00; color: #000000; }
QMenuBar::item:pressed { background: #ffff00; color: #000000; }
/* Drop-down menus: black panel, white item text, yellow selection. */
QMenu { background: #000000; color: #ffffff; border: 2px solid #ffffff; padding: 6px; }
QMenu::item { background: transparent; color: #ffffff; padding: 7px 22px 7px 12px; font-weight: bold; }
QMenu::item:selected { background: #ffff00; color: #000000; }
QMenu::item:disabled { color: #888888; }
QMenu::separator { background: #ffffff; height: 1px; margin: 4px 6px; }
QToolTip { background: #000000; color: #ffff00; border: 2px solid #ffff00; }
QSplitter::handle { background: #ffffff; }
"""


def _apply_dark_palette(app: QtWidgets.QApplication) -> None:
    """The original dark-theme palette — unchanged from the
    pre-customize-feature baseline."""
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#0b1117"))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, TEXT_COLOR)
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#0d141d"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, SURFACE_BG)
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#151e29"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, TEXT_COLOR)
    palette.setColor(QtGui.QPalette.ColorRole.Text, TEXT_COLOR)
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#151e29"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, TEXT_COLOR)
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#234323"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#f7fff5"))
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, MUTED_COLOR)
    app.setPalette(palette)


def _apply_light_palette(app: QtWidgets.QApplication) -> None:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f1f3f6"))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#1c2330"))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#e7ecf2"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#1c2330"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#1c2330"))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#1c2330"))
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#73c686"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#0b2310"))
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor("#7d8693"))
    app.setPalette(palette)


def _apply_high_contrast_palette(app: QtWidgets.QApplication) -> None:
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#1a1a1a"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#ffff00"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#ffff00"))
    palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor("#ffffff"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#ffff00"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#000000"))
    palette.setColor(QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor("#808080"))
    app.setPalette(palette)


def apply_app_palette(app: QtWidgets.QApplication, theme: str = 'dark') -> None:
    """Apply the platform palette for *theme*. Falls back to dark
    on unknown values."""
    if theme == 'light':
        _apply_light_palette(app)
    elif theme == 'high_contrast':
        _apply_high_contrast_palette(app)
    else:
        _apply_dark_palette(app)


def apply_theme(app: QtWidgets.QApplication, *,
                theme: str = 'dark', ui_scale: float = 1.0) -> None:
    """Apply the requested theme + UI scale to the app.

    ``theme`` is one of 'dark' | 'light' | 'high_contrast'. The base
    QSS in native_qt_theme.qss is loaded first, then the variant's
    overrides are appended (for non-dark themes).

    ``ui_scale`` is a font-size multiplier. Qt scales most widget
    metrics from font metrics, so adjusting the app font size is the
    cheapest way to scale the whole UI uniformly.

    Also updates the central theme_palette so custom-painted widgets
    (chart panels, the stiffness profile bars, themed dialogs) repaint
    with the new palette.
    """
    # Update the central palette FIRST so any listener-triggered
    # repaints see the new colours when they recompute.
    from . import theme_palette as _palette
    _palette.set_active(theme)
    # Update the scale module so registered widgets get notified
    # to re-apply their setFixedSize calls with the new scale.
    from . import scale as _scale
    _scale.set_active(ui_scale)

    app.setStyle("Fusion")
    apply_app_palette(app, theme)

    base_qss = ""
    if THEME_PATH.is_file():
        base_qss = THEME_PATH.read_text(encoding="utf-8")

    # ── UI scale: multiply every font-size in the QSS by ui_scale ──
    # The QSS file has hardcoded font-size: Npt rules that win over
    # app.setFont(), so scaling needs to happen INSIDE the QSS too.
    # We apply the multiplier to every match of "font-size: Npt" and
    # rebuild the stylesheet from the scaled version.
    if abs(ui_scale - 1.0) > 0.01:
        import re as _re

        def _scale_font_pt(match):
            try:
                size = float(match.group(1))
                return f'font-size: {size * ui_scale:.2f}pt'
            except (TypeError, ValueError):
                return match.group(0)

        base_qss = _re.sub(
            r'font-size:\s*(\d+(?:\.\d+)?)\s*pt',
            _scale_font_pt,
            base_qss,
        )

    if theme == 'light':
        app.setStyleSheet(base_qss + "\n" + _LIGHT_VARIANT_QSS)
    elif theme == 'high_contrast':
        app.setStyleSheet(base_qss + "\n" + _HIGH_CONTRAST_VARIANT_QSS)
    else:
        app.setStyleSheet(base_qss)

    # ── UI scale: also apply to app font for non-QSS-styled widgets ──
    # Qt computes most widget metrics from font height, so scaling the
    # app font catches widgets that don't get a font-size from QSS.
    if abs(ui_scale - 1.0) > 0.01:
        font = app.font()
        # Compute the scaled point size from the unscaled baseline.
        # We multiply the platform default (usually 9 or 10pt) — not
        # the current font size — so applying scale repeatedly
        # doesn't compound.
        baseline_pt = float(app.property('baselineFontPt') or font.pointSizeF() or 9)
        if app.property('baselineFontPt') is None:
            app.setProperty('baselineFontPt', baseline_pt)
        font.setPointSizeF(baseline_pt * ui_scale)
        app.setFont(font)
    else:
        # Restore baseline if we previously scaled
        baseline_pt = app.property('baselineFontPt')
        if baseline_pt is not None:
            font = app.font()
            font.setPointSizeF(float(baseline_pt))
            app.setFont(font)


@functools.lru_cache(maxsize=64)
def load_icon(name: str, role: str = "") -> QtGui.QIcon:
    return _build_icon(name, "", role or Path(name).stem)


@functools.lru_cache(maxsize=128)
def load_tinted_icon(name: str, color: str, size: int = 18, role: str = "") -> QtGui.QIcon:
    return _build_icon(name, color, role or Path(name).stem, preferred_size=size)


def load_icon_pixmap(name: str, size: int, *, color: str = "", role: str = "") -> QtGui.QPixmap:
    return QtGui.QPixmap(_render_icon_canvas(name, size, color, role or Path(name).stem))


def icon_spec_for(name: str, role: str = "") -> IconSpec:
    resolved_role = role or Path(name).stem
    return ICON_SPECS.get(resolved_role, ICON_SPECS["default"])


def _build_icon(name: str, color: str, role: str, *, preferred_size: int = 18) -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for size in sorted({14, 16, 18, 20, 24, 28, 32, 36, preferred_size}):
        pixmap = _render_icon_canvas(name, size, color, role)
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
    return icon


@functools.lru_cache(maxsize=512)
def _render_icon_canvas(name: str, size: int, color: str, role: str) -> QtGui.QPixmap:
    path = ICON_DIR / name
    if not path.is_file():
        return QtGui.QPixmap()
    base_icon = QtGui.QIcon(str(path))
    spec = icon_spec_for(name, role)
    render_size = max(1, min(size, int(round(size * spec.optical_scale))))
    source = base_icon.pixmap(render_size, render_size)
    if source.isNull():
        return QtGui.QPixmap()
    if color:
        tinted = QtGui.QPixmap(source.size())
        tinted.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(tinted)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QtGui.QColor(color))
        painter.end()
        source = tinted
    canvas = QtGui.QPixmap(size, size)
    canvas.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(canvas)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
    bounds = _opaque_pixmap_bounds(source)
    if bounds.isNull():
        x = int(round((size - source.width()) / 2 + spec.offset_x))
        y = int(round((size - source.height()) / 2 + spec.offset_y))
    else:
        x = int(round((size - bounds.width()) / 2 - bounds.left() + spec.offset_x))
        y = int(round((size - bounds.height()) / 2 - bounds.top() + spec.offset_y))
        x = max(-bounds.left(), min(x, size - 1 - bounds.right()))
        y = max(-bounds.top(), min(y, size - 1 - bounds.bottom()))
    painter.drawPixmap(x, y, source)
    painter.end()
    return canvas


def _opaque_pixmap_bounds(pixmap: QtGui.QPixmap) -> QtCore.QRect:
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    min_x = image.width()
    min_y = image.height()
    max_x = -1
    max_y = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if QtGui.QColor.fromRgba(image.pixel(x, y)).alpha() <= 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < min_x or max_y < min_y:
        return QtCore.QRect()
    return QtCore.QRect(min_x, min_y, (max_x - min_x) + 1, (max_y - min_y) + 1)


@functools.lru_cache(maxsize=64)
def _base_pixmap(name: str) -> QtGui.QPixmap:
    path = ASSET_DIR / name
    return QtGui.QPixmap(str(path)) if path.is_file() else QtGui.QPixmap()


def _device_pixel_ratio() -> float:
    app = QtWidgets.QApplication.instance()
    screen = app.primaryScreen() if app else None
    return max(1.0, float(screen.devicePixelRatio()) if screen else 1.0)


def load_pixmap(name: str, width: Optional[int] = None, height: Optional[int] = None) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(_base_pixmap(name))
    if pixmap.isNull():
        return pixmap
    dpr = _device_pixel_ratio()
    target_width = int(round(width * dpr)) if width else None
    target_height = int(round(height * dpr)) if height else None
    if width and height:
        scaled = pixmap.scaled(target_width, target_height, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        return scaled
    if width:
        scaled = pixmap.scaledToWidth(target_width, QtCore.Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        return scaled
    if height:
        scaled = pixmap.scaledToHeight(target_height, QtCore.Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        return scaled
    return pixmap


def load_pixmap_contained(name: str, max_width: int, max_height: int) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(_base_pixmap(name))
    if pixmap.isNull():
        return pixmap
    dpr = _device_pixel_ratio()
    scaled = pixmap.scaled(
        int(round(max_width * dpr)),
        int(round(max_height * dpr)),
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(dpr)
    return scaled
