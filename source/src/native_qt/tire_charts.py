"""Inline analysis charts for the tire creator form.

Five visualizations stacked in one card under the property cards:

  1. Grip vs Temperature — dual-line (street + offroad), Gaussian
     around TireTemperature with width driven by ThermalSensitivity.
     APPROXIMATED.

  2. Grip vs Load — single-line factor (1.0 = full grip), 12 sample
     points across 0..2×high_anchor. Where high_anchor = max of
     (LoadRating, MaxLoad), low_anchor = min. APPROXIMATED.

  3. Lateral Force vs Slip Angle — classic rise-peak-fall Pacejka-
     style curve. MATH-GROUNDED shape; magnitude is "kN-relative"
     because LateralStiffness units are unknown.

  4. Tread vs Distance — linear wear projection, baseline at
     WearRate=0.01 wears 100% over 5000 km; everything else is
     scaled relative to that baseline. RELATIVE only.

  5. Stiffness Profile — five horizontal bars (Lateral, Long,
     Cornering, Camber, Long Slip) normalized vs typical-vanilla
     reference maxes, so the user can see the tire's "shape" at a
     glance.

All five refresh whenever the user types in any of the relevant
property fields, via :meth:`refresh`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets

import tire_analysis as _ta


# ── Palette — picked to match the existing curve_preview accent set ──
_STREET_COLOR = QtGui.QColor("#73c686")    # green
_OFFROAD_COLOR = QtGui.QColor("#d9a13a")   # gold
_PRIMARY_COLOR = QtGui.QColor("#5fa9d9")   # blue
_GRID_COLOR    = QtGui.QColor("#314153")
_TEXT_COLOR    = QtGui.QColor("#9da7b0")
_BG_COLOR      = QtGui.QColor("#0c1622")


def _new_chart(title: str = "") -> QtCharts.QChart:
    """Build a chart pre-styled to match the editor theme."""
    chart = QtCharts.QChart()
    chart.setBackgroundBrush(QtGui.QBrush(_BG_COLOR))
    chart.setBackgroundRoundness(0)
    chart.setMargins(QtCore.QMargins(0, 0, 0, 0))
    chart.legend().setVisible(True)
    chart.legend().setLabelColor(_TEXT_COLOR)
    chart.legend().setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
    chart.setTitle(title)
    return chart


def _new_view(chart: QtCharts.QChart) -> QtCharts.QChartView:
    view = QtCharts.QChartView(chart)
    view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    view.setBackgroundBrush(QtGui.QBrush(_BG_COLOR))
    view.setStyleSheet(
        f"background-color: {_BG_COLOR.name()}; "
        f"border: 1px solid {_GRID_COLOR.name()};"
    )
    return view


def _make_axis(title: str = "", colour: QtGui.QColor = _TEXT_COLOR,
               label_format: str = "%.0f") -> QtCharts.QValueAxis:
    axis = QtCharts.QValueAxis()
    axis.setLabelFormat(label_format)
    axis.setLabelsBrush(QtGui.QBrush(colour))
    axis.setGridLineColor(_GRID_COLOR)
    axis.setLinePenColor(_GRID_COLOR)
    axis.setTickCount(5)
    if title:
        axis.setTitleText(title)
        axis.setTitleBrush(QtGui.QBrush(colour))
    return axis


def _new_caption(text: str) -> QtWidgets.QLabel:
    """Tiny gray caption label for chart subtitles / disclaimers."""
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {_TEXT_COLOR.name()}; font-size: 10px;")
    return label


# ──────────────────────────────────────────────────────────────────────
# Top-level container widget — five chart panels stacked vertically.
# ──────────────────────────────────────────────────────────────────────
class InlineTireCharts(QtWidgets.QWidget):
    """Composite widget — owns five chart panels and exposes a single
    :meth:`refresh(part, overrides)` that updates all of them.

    Designed to live inside the tire creator form below the property
    cards. The parent form wires its `changed` signal to this
    widget's :meth:`refresh` so every keystroke recomputes."""

    PANEL_HEIGHT = 180   # each chart is fixed height; total ~5x180 + captions

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # 1. Temperature chart
        self._temp_chart = _new_chart("Grip vs Temperature")
        self._temp_view = _new_view(self._temp_chart)
        self._temp_view.setFixedHeight(self.PANEL_HEIGHT)
        self._temp_caption = _new_caption(
            "Approximated — Gaussian around TireTemperature, width driven by "
            "ThermalSensitivity. Shape is correct; absolute magnitude is the "
            "estimated grip × falloff factor."
        )
        outer.addWidget(self._temp_view)
        outer.addWidget(self._temp_caption)

        # 2. Load chart
        self._load_chart = _new_chart("Grip Factor vs Load")
        self._load_view = _new_view(self._load_chart)
        self._load_view.setFixedHeight(self.PANEL_HEIGHT)
        self._load_caption = _new_caption(
            "Approximated — flat at 1.0 below the lower of (LoadRating, "
            "MaxLoad), declining linearly to 0.7 at the higher value, then "
            "steep falloff past it. Load units are MT-internal, not Newtons."
        )
        outer.addWidget(self._load_view)
        outer.addWidget(self._load_caption)

        # 3. Slip-angle chart
        self._slip_chart = _new_chart("Lateral Force vs Slip Angle")
        self._slip_view = _new_view(self._slip_chart)
        self._slip_view.setFixedHeight(self.PANEL_HEIGHT)
        self._slip_caption = _new_caption(
            "Math-grounded shape (Pacejka rational form). Higher Cornering "
            "Stiffness shifts the peak earlier and makes it sharper. "
            "Y axis is relative — exact in-game forces depend on units we "
            "don't fully know."
        )
        outer.addWidget(self._slip_view)
        outer.addWidget(self._slip_caption)

        # 4. Wear chart
        self._wear_chart = _new_chart("Tread Remaining vs Distance")
        self._wear_view = _new_view(self._wear_chart)
        self._wear_view.setFixedHeight(self.PANEL_HEIGHT)
        self._wear_caption = _new_caption(
            "Relative — baseline (WearRate = 0.01) wears 100% over 5,000 km. "
            "Lower WearRate lasts longer; higher rate wears faster. "
            "Absolute mileage isn't accurate (WearRate units are unclear), "
            "but the comparison across edits is meaningful."
        )
        outer.addWidget(self._wear_view)
        outer.addWidget(self._wear_caption)

        # 5. Stiffness profile (custom-painted, no QtCharts)
        self._stiff_panel = _StiffnessProfilePanel()
        self._stiff_panel.setFixedHeight(self.PANEL_HEIGHT)
        self._stiff_caption = _new_caption(
            "Five stiffness fields normalized to a 0–1 scale (1.0 = "
            "race-tire stiff). Lets you see the tire's 'shape' at a "
            "glance — race tires have uniformly tall bars, comfort tires "
            "are short/medium, drift tires drop Cornering."
        )
        outer.addWidget(self._stiff_panel)
        outer.addWidget(self._stiff_caption)

        outer.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self, part: Optional[Dict[str, Any]] = None,
                overrides: Optional[Dict[str, Any]] = None) -> None:
        """Recompute every panel from the current (part, overrides)
        snapshot. Safe to call with part=None — all panels render an
        empty state."""
        if not part:
            self._render_empty()
            return
        try:
            self._render_temperature(part, overrides)
            self._render_load(part, overrides)
            self._render_slip(part, overrides)
            self._render_wear(part, overrides)
            self._stiff_panel.set_profile(_ta.stiffness_radar(part, overrides))
        except Exception:
            # Charts are non-critical — don't blow up the form.
            self._render_empty()

    # ── Panel renders ─────────────────────────────────────────────────
    def _render_empty(self) -> None:
        for chart in (self._temp_chart, self._load_chart,
                      self._slip_chart, self._wear_chart):
            self._clear_chart(chart)
        self._stiff_panel.set_profile([])

    def _clear_chart(self, chart: QtCharts.QChart) -> None:
        for series in list(chart.series()):
            chart.removeSeries(series)
        for axis in list(chart.axes()):
            chart.removeAxis(axis)

    def _render_temperature(self, part: Dict[str, Any],
                            overrides: Optional[Dict[str, Any]]) -> None:
        self._clear_chart(self._temp_chart)
        points = _ta.thermal_curve(part, overrides, num_samples=80)
        if not points:
            return
        street = QtCharts.QSplineSeries()
        street.setName("Street grip (G)")
        pen_s = QtGui.QPen(_STREET_COLOR); pen_s.setWidth(2)
        street.setPen(pen_s)
        offroad = QtCharts.QSplineSeries()
        offroad.setName("Offroad grip (G)")
        pen_o = QtGui.QPen(_OFFROAD_COLOR); pen_o.setWidth(2)
        offroad.setPen(pen_o)
        for t, s, o in points:
            street.append(t, s)
            offroad.append(t, o)
        self._temp_chart.addSeries(street)
        self._temp_chart.addSeries(offroad)
        max_y = max(max(s, o) for _, s, o in points) * 1.1 + 0.05
        ax_x = _make_axis("Temperature (°C)", label_format="%.0f")
        ax_x.setRange(20, 140)
        ax_y = _make_axis("G", label_format="%.2f")
        ax_y.setRange(0, max(0.5, max_y))
        self._temp_chart.addAxis(ax_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._temp_chart.addAxis(ax_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        for s in (street, offroad):
            s.attachAxis(ax_x); s.attachAxis(ax_y)

    def _render_load(self, part: Dict[str, Any],
                     overrides: Optional[Dict[str, Any]]) -> None:
        self._clear_chart(self._load_chart)
        points = _ta.load_curve(part, overrides, num_samples=12)
        if not points:
            return
        series = QtCharts.QLineSeries()
        series.setName("Grip factor")
        pen = QtGui.QPen(_PRIMARY_COLOR); pen.setWidth(2)
        series.setPen(pen)
        scatter = QtCharts.QScatterSeries()
        scatter.setMarkerShape(QtCharts.QScatterSeries.MarkerShape.MarkerShapeCircle)
        scatter.setMarkerSize(8.0)
        scatter.setColor(_PRIMARY_COLOR)
        scatter.setBorderColor(_PRIMARY_COLOR)
        scatter.setName("samples")
        for load, factor in points:
            series.append(load, factor)
            scatter.append(load, factor)
        self._load_chart.addSeries(series)
        self._load_chart.addSeries(scatter)
        max_x = max(p[0] for p in points)
        ax_x = _make_axis("Load (MT-internal units)", label_format="%.0f")
        ax_x.setRange(0, max_x)
        ax_y = _make_axis("Factor", label_format="%.2f")
        ax_y.setRange(0, 1.1)
        self._load_chart.addAxis(ax_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._load_chart.addAxis(ax_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        for s in (series, scatter):
            s.attachAxis(ax_x); s.attachAxis(ax_y)

    def _render_slip(self, part: Dict[str, Any],
                     overrides: Optional[Dict[str, Any]]) -> None:
        self._clear_chart(self._slip_chart)
        points = _ta.slip_curve(part, overrides, num_samples=80)
        if not points:
            return
        series = QtCharts.QSplineSeries()
        series.setName("Lateral force (relative)")
        pen = QtGui.QPen(_STREET_COLOR); pen.setWidth(2)
        series.setPen(pen)
        for d, f in points:
            series.append(d, f)
        self._slip_chart.addSeries(series)
        max_y = max(f for _, f in points) * 1.15 + 0.5
        ax_x = _make_axis("Slip angle (°)", label_format="%.1f")
        ax_x.setRange(0, points[-1][0])
        ax_y = _make_axis("F_lat (relative)", label_format="%.1f")
        ax_y.setRange(0, max(1.0, max_y))
        self._slip_chart.addAxis(ax_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._slip_chart.addAxis(ax_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(ax_x); series.attachAxis(ax_y)

    def _render_wear(self, part: Dict[str, Any],
                     overrides: Optional[Dict[str, Any]]) -> None:
        self._clear_chart(self._wear_chart)
        points = _ta.wear_curve(part, overrides, num_samples=80, max_distance_km=5000.0)
        if not points:
            return
        series = QtCharts.QLineSeries()
        series.setName("Tread remaining (%)")
        pen = QtGui.QPen(_OFFROAD_COLOR); pen.setWidth(2)
        series.setPen(pen)
        for km, pct in points:
            series.append(km, pct)
        self._wear_chart.addSeries(series)
        ax_x = _make_axis("Distance (km, relative)", label_format="%.0f")
        ax_x.setRange(0, 5000)
        ax_y = _make_axis("Tread %", label_format="%.0f")
        ax_y.setRange(0, 100)
        self._wear_chart.addAxis(ax_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._wear_chart.addAxis(ax_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(ax_x); series.attachAxis(ax_y)


# ──────────────────────────────────────────────────────────────────────
# Stiffness profile — custom-painted horizontal bar chart. Five rows,
# each labeled and showing a normalized fill bar. We don't use
# QtCharts here because horizontal bar charts in QtCharts require
# extra ceremony for what's a pretty trivial layout.
# ──────────────────────────────────────────────────────────────────────
class _StiffnessProfilePanel(QtWidgets.QWidget):
    """Five-row horizontal bar widget for stiffness fields."""

    LABEL_WIDTH = 90
    BAR_HEIGHT = 12
    ROW_GAP = 8

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._profile: List[tuple] = []  # list of (label, raw, norm_0_1)
        self.setStyleSheet(
            f"background-color: {_BG_COLOR.name()}; "
            f"border: 1px solid {_GRID_COLOR.name()};"
        )

    def set_profile(self, profile: List[tuple]) -> None:
        self._profile = list(profile or [])
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Title
        painter.setPen(_TEXT_COLOR)
        painter.setFont(QtGui.QFont("", 9, QtGui.QFont.Weight.Bold))
        painter.drawText(QtCore.QPoint(10, 18), "Stiffness Profile")
        if not self._profile:
            painter.setPen(_TEXT_COLOR)
            painter.setFont(QtGui.QFont("", 9))
            painter.drawText(self.rect(),
                             QtCore.Qt.AlignmentFlag.AlignCenter,
                             "No stiffness data")
            return
        rect = self.rect()
        painter.setFont(QtGui.QFont("", 9))
        bar_x = self.LABEL_WIDTH + 16
        bar_max_w = max(40, rect.width() - bar_x - 80)
        # Compute total height and centre vertically below the title
        total_h = len(self._profile) * (self.BAR_HEIGHT + self.ROW_GAP)
        top = max(28, (rect.height() - total_h) // 2)
        for i, (label, raw, norm) in enumerate(self._profile):
            y = top + i * (self.BAR_HEIGHT + self.ROW_GAP)
            # Label
            painter.setPen(_TEXT_COLOR)
            painter.drawText(QtCore.QPoint(10, y + self.BAR_HEIGHT - 1),
                             label)
            # Track (full-width gray)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#1a2532")))
            painter.setPen(QtGui.QPen(_GRID_COLOR))
            painter.drawRect(bar_x, y, bar_max_w, self.BAR_HEIGHT)
            # Fill (accent colour scaled by norm)
            fill_w = max(0, int(bar_max_w * max(0.0, min(1.0, norm))))
            if fill_w > 0:
                painter.setBrush(QtGui.QBrush(_PRIMARY_COLOR))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.drawRect(bar_x + 1, y + 1, fill_w - 1, self.BAR_HEIGHT - 1)
            # Value text on the right
            painter.setPen(_TEXT_COLOR)
            value_text = (f"{raw:,.2f}" if abs(raw) < 100 else f"{raw:,.0f}")
            painter.drawText(QtCore.QPoint(bar_x + bar_max_w + 6,
                                           y + self.BAR_HEIGHT - 1),
                             value_text)
