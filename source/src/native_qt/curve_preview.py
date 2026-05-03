"""Synthetic torque-curve generator + inline live-preview widget for
the Engine Creator.

The Engine Creator collects five values that together determine the
torque curve the game will see:

  - MaxRPM            — engine redline
  - MaxTorque         — peak crank torque in Nm
  - peak_torque_rpm   — RPM where torque peaks
  - max_hp            — peak horsepower
  - peak_hp_rpm       — RPM where HP peaks

This module produces an *inline* live preview of the curve those
five values would generate — re-rendered on every keystroke as the
user tunes them. It is not the same thing as the .uexp curve that
ships with the engine (that's still produced by ``build_shifted_curve``
in parsers/uexp_torquecurve.py from a vanilla template); it is a
preview-only synthesis based on the same shape rules so the user
sees roughly what they're building before they save.

Curve model
-----------
A 4-segment piecewise function keeps the shape smooth without needing
a spline solver (each segment is already a smooth analytic curve, so
sampling at high resolution gives a clean line):

  Segment 1 — Idle to peak torque
      r ∈ [0, p_t]
      Torque rises from idle_T (≈ 30% of MaxTorque) to MaxTorque.
      Curve uses an "ease-out" cubic so it accelerates early and
      flattens into the peak — matches real engine torque buildup.

  Segment 2 — Plateau
      r ∈ [p_t, p_t + plateau_w]
      Torque holds at MaxTorque. Plateau width is 5% of redline,
      capped at half the distance between p_t and p_h.

  Segment 3 — Peak HP region
      r ∈ [plateau_end, p_h]
      Torque tapers from MaxTorque to T_at_peak_hp such that
      HP = T × RPM / 7121 evaluates to MaxHP at p_h. Smooth
      cosine taper for a natural-looking dropoff.

  Segment 4 — Past peak HP to redline
      r ∈ [p_h, 1.0]
      Torque drops from T_at_peak_hp to ~ 50% of that at redline.
      Cosine again for smoothness.

Throughout, ``r = rpm / max_rpm``. HP is derived from torque per
sample: ``HP = T_nm × RPM / 7121``.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from PySide6 import QtCharts, QtCore, QtGui, QtWidgets


# ──────────────────────────────────────────────────────────────────────
# Pure-Python curve synthesis (no Qt — unit-testable in isolation)
# ──────────────────────────────────────────────────────────────────────

# Conversion: HP = Torque(Nm) × RPM / 7121
# (7121 ≈ 60 × 1000 / (2π × 1.341), the standard metric kW→HP factor)
_HP_PER_TORQUE_RPM = 7121.0

# How much of MaxTorque the engine produces at idle (RPM = 0). Real
# engines actually produce close to peak torque at low RPM — the
# difference between idle torque and peak torque is small except for
# heavily turbocharged engines that have lag below boost threshold.
_IDLE_TORQUE_FRACTION = 0.32

# Plateau width as a fraction of MaxRPM. Real engines hold peak torque
# for a small RPM window before HP takes over. 5% of redline is a
# reasonable visual width.
_PLATEAU_WIDTH = 0.05

# Tail-off torque at redline as a fraction of T_at_peak_hp. A 50%
# drop past peak HP toward redline matches typical valve-train and
# breathing limits.
_REDLINE_TAIL_FRACTION = 0.50


def _smoothstep(t: float) -> float:
    """Standard 3t² - 2t³ smoothstep on [0, 1]. Used for cosine-like
    transitions without needing math.cos imports inline."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _ease_out_cubic(t: float) -> float:
    """1 - (1-t)^3. Accelerates at the start, decelerates into 1.0."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return 1.0 - (1.0 - t) ** 3


def synth_torque(rpm: float,
                 max_rpm: float,
                 max_torque_nm: float,
                 peak_torque_rpm: float,
                 max_hp: float,
                 peak_hp_rpm: float) -> float:
    """Sample the synthetic torque curve at ``rpm``.

    Returns torque in Nm. All inputs validated/clamped — out-of-range
    or zero MaxRPM returns 0 (preview just shows a flat line then).
    """
    if max_rpm <= 0 or max_torque_nm <= 0:
        return 0.0
    r = max(0.0, min(rpm / max_rpm, 1.05))  # let curve overshoot a hair past redline
    p_t = max(0.05, min(peak_torque_rpm / max_rpm, 0.95)) if peak_torque_rpm > 0 else 0.5
    p_h_raw = peak_hp_rpm / max_rpm if peak_hp_rpm > 0 else 0.85
    p_h = max(p_t + 0.02, min(p_h_raw, 1.0))

    idle_T = _IDLE_TORQUE_FRACTION * max_torque_nm
    plateau_w = min(_PLATEAU_WIDTH, (p_h - p_t) * 0.5)
    plateau_end = min(p_t + plateau_w, p_h - 0.01)

    # Compute target torque at peak HP from the requested HP value.
    # If max_hp wasn't provided, fall back to a 70% torque retention at p_h.
    if max_hp > 0 and peak_hp_rpm > 0:
        T_at_peak_hp = (max_hp * _HP_PER_TORQUE_RPM) / peak_hp_rpm
        # Cap to MaxTorque (HP target above what MaxTorque could produce
        # at p_h — the curve can't exceed MaxTorque, so T_at_peak_hp is
        # also clamped to MaxTorque).
        T_at_peak_hp = min(T_at_peak_hp, max_torque_nm)
        # And floor it to keep the curve sensible — at minimum 30% of
        # MaxTorque so the post-peak region is still a meaningful shape.
        T_at_peak_hp = max(T_at_peak_hp, 0.30 * max_torque_nm)
    else:
        T_at_peak_hp = 0.70 * max_torque_nm

    redline_T = T_at_peak_hp * _REDLINE_TAIL_FRACTION

    # ── Segment 1: idle to peak torque ──
    if r <= p_t:
        t = r / p_t if p_t > 0 else 0.0
        return idle_T + (max_torque_nm - idle_T) * _ease_out_cubic(t)

    # ── Segment 2: plateau ──
    if r <= plateau_end:
        return max_torque_nm

    # ── Segment 3: plateau end to peak HP ──
    if r <= p_h:
        span = p_h - plateau_end
        t = (r - plateau_end) / span if span > 0 else 0.0
        return max_torque_nm - (max_torque_nm - T_at_peak_hp) * _smoothstep(t)

    # ── Segment 4: peak HP to redline ──
    if r <= 1.0:
        span = 1.0 - p_h
        t = (r - p_h) / span if span > 0 else 0.0
        return T_at_peak_hp - (T_at_peak_hp - redline_T) * _smoothstep(t)

    # Past redline: continue the linear extrapolation of segment 4 so
    # the chart doesn't show a hard cliff. Mostly aesthetic — the
    # X axis caps at MaxRPM so this is rarely sampled.
    return redline_T


def synth_curve(max_rpm: float,
                max_torque_nm: float,
                peak_torque_rpm: float,
                max_hp: float,
                peak_hp_rpm: float,
                num_samples: int = 80) -> List[Tuple[float, float, float]]:
    """Sample the synthetic torque curve at ``num_samples`` evenly-spaced
    RPM positions from 0 to ``max_rpm``.

    Returns a list of ``(rpm, torque_nm, hp)`` triples. HP derived from
    ``torque × rpm / 7121`` per sample.
    """
    if max_rpm <= 0 or num_samples < 2:
        return []
    out: List[Tuple[float, float, float]] = []
    for i in range(num_samples + 1):
        rpm = (max_rpm * i) / num_samples
        t = synth_torque(rpm, max_rpm, max_torque_nm,
                         peak_torque_rpm, max_hp, peak_hp_rpm)
        hp = t * rpm / _HP_PER_TORQUE_RPM
        out.append((rpm, t, hp))
    return out


# ──────────────────────────────────────────────────────────────────────
# Inline preview widget (Qt)
# ──────────────────────────────────────────────────────────────────────

# Visual constants — pulled from the central theme_palette so they
# track the active dark / light / high-contrast theme. Helper getters
# resolve the palette at call time, not at import time, so a theme
# switch is reflected on the next refresh().
from . import theme_palette as _palette


def _torque_color():  return _palette.qcolor('chart_torque')
def _hp_color():      return _palette.qcolor('chart_hp')
def _grid_color():    return _palette.qcolor('chart_grid')
def _text_color():    return _palette.qcolor('chart_text')
def _bg_color():      return _palette.qcolor('chart_bg')


class InlineCurvePreview(QtWidgets.QWidget):
    """Compact dual-axis torque + HP chart for the Engine Creator.

    Re-rendered via :meth:`refresh` whenever any of the five input
    fields changes. Keeps a fixed height so the form layout doesn't
    jitter as values change.
    """

    PREVIEW_HEIGHT = 200

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setFixedHeight(self.PREVIEW_HEIGHT)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._chart = QtCharts.QChart()
        self._chart.setBackgroundBrush(QtGui.QBrush(_bg_color()))
        self._chart.setBackgroundRoundness(0)
        self._chart.setMargins(QtCore.QMargins(0, 0, 0, 0))
        self._chart.legend().setVisible(True)
        self._chart.legend().setLabelColor(_text_color())
        self._chart.legend().setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._chart.setTitle("")

        self._chart_view = QtCharts.QChartView(self._chart)
        self._chart_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._chart_view.setBackgroundBrush(QtGui.QBrush(_bg_color()))
        self._chart_view.setStyleSheet(
            f"background-color: {_bg_color().name()}; border: 1px solid {_grid_color().name()};"
        )
        layout.addWidget(self._chart_view, 1)

        # Status / hint line under the chart — used to surface "missing
        # input" or "invalid input" states without clearing the chart
        # entirely (we keep the last-good preview visible).
        self._status_label = QtWidgets.QLabel("")
        self._status_label.setStyleSheet(
            f"color: {_text_color().name()}; font-size: 11px;"
        )
        self._status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status_label, 0)

        # Initial empty state so the chart object exists and refresh()
        # can update it without doing first-time setup work each call.
        self._render_empty("Enter MaxTorque, MaxRPM, and Max HP to see a preview.")

        # Re-render on theme change so chart colours track the
        # active palette. Stash the last refresh() args so we can
        # re-apply them with new palette colours; falls back to
        # the empty state when nothing's been rendered yet.
        self._last_refresh_args = None
        _palette.register_listener(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """Re-render with the new palette colours. Called by the
        theme_palette listener registry on theme switch."""
        # Restyle the chart container immediately
        try:
            self._chart.setBackgroundBrush(QtGui.QBrush(_bg_color()))
            self._chart.legend().setLabelColor(_text_color())
            self._chart_view.setBackgroundBrush(QtGui.QBrush(_bg_color()))
            self._chart_view.setStyleSheet(
                f"background-color: {_bg_color().name()}; "
                f"border: 1px solid {_grid_color().name()};"
            )
            self._status_label.setStyleSheet(
                f"color: {_text_color().name()}; font-size: 11px;"
            )
        except Exception:
            pass
        # Re-run the last refresh so series + axes get the new colours.
        if self._last_refresh_args:
            try:
                self.refresh(*self._last_refresh_args)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def refresh(self,
                max_rpm: Optional[float],
                max_torque_nm: Optional[float],
                peak_torque_rpm: Optional[float],
                max_hp: Optional[float],
                peak_hp_rpm: Optional[float]) -> None:
        """Recompute and redraw the curve. Pass ``None`` for any value
        that's unparseable so the widget can fall back to an
        informative empty state instead of plotting nonsense."""
        # Stash for theme-change re-render
        self._last_refresh_args = (max_rpm, max_torque_nm, peak_torque_rpm,
                                   max_hp, peak_hp_rpm)
        # Need at least MaxRPM + MaxTorque to draw anything.
        if not max_rpm or not max_torque_nm or max_rpm <= 0 or max_torque_nm <= 0:
            self._render_empty(
                "Enter MaxTorque, MaxRPM (and ideally Max HP + the two "
                "peak RPMs) to preview the curve."
            )
            return

        # Default the missing-but-needed parameters to sensible values
        # so the preview always looks plausible even mid-typing.
        ptr = peak_torque_rpm if (peak_torque_rpm and peak_torque_rpm > 0) else max_rpm * 0.55
        phr = peak_hp_rpm if (peak_hp_rpm and peak_hp_rpm > 0) else max_rpm * 0.85
        mhp = max_hp if (max_hp and max_hp > 0) else 0.0

        points = synth_curve(max_rpm, max_torque_nm, ptr, mhp, phr)
        if not points:
            self._render_empty("Curve preview unavailable for these inputs.")
            return

        self._render_curve(points, max_rpm, max_torque_nm, mhp, ptr, phr)

    # ------------------------------------------------------------------
    def _clear_series(self) -> None:
        """Tear down all series and axes from the chart so a fresh
        render doesn't leak handles or stack legends."""
        for series in list(self._chart.series()):
            self._chart.removeSeries(series)
        for axis in list(self._chart.axes()):
            self._chart.removeAxis(axis)

    def _render_empty(self, message: str) -> None:
        """Show an empty chart with a status line. Doesn't recreate the
        chart object, just clears its series."""
        self._clear_series()
        self._status_label.setText(message)
        self._status_label.setStyleSheet(
            f"color: {_text_color().name()}; font-size: 11px;"
        )

    def _render_curve(self,
                      points: List[Tuple[float, float, float]],
                      max_rpm: float,
                      max_torque_nm: float,
                      max_hp_input: float,
                      peak_torque_rpm: float,
                      peak_hp_rpm: float) -> None:
        """Draw a torque series + HP series with dual Y axes."""
        self._clear_series()

        # Find peak HP from the sampled curve (the user's input may
        # not exactly match the curve's calculated peak when MaxTorque
        # is too small to actually achieve their requested MaxHP).
        peak_hp_value = max((hp for _, _, hp in points), default=0.0)

        # Torque series on the left axis.
        torque_series = QtCharts.QSplineSeries()
        torque_series.setName("Torque (Nm)")
        torque_pen = QtGui.QPen(_torque_color())
        torque_pen.setWidth(2)
        torque_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        torque_series.setPen(torque_pen)
        for rpm, t_nm, _hp in points:
            torque_series.append(float(rpm), float(t_nm))

        # HP series on the right axis.
        hp_series = QtCharts.QSplineSeries()
        hp_series.setName("HP")
        hp_pen = QtGui.QPen(_hp_color())
        hp_pen.setWidth(2)
        hp_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        hp_series.setPen(hp_pen)
        for rpm, _t_nm, hp in points:
            hp_series.append(float(rpm), float(hp))

        self._chart.addSeries(torque_series)
        self._chart.addSeries(hp_series)

        # X axis — RPM, 0 to MaxRPM.
        axis_x = QtCharts.QValueAxis()
        axis_x.setRange(0.0, float(max_rpm))
        axis_x.setLabelFormat("%.0f")
        axis_x.setTitleText("RPM")
        axis_x.setTitleBrush(QtGui.QBrush(_text_color()))
        axis_x.setLabelsBrush(QtGui.QBrush(_text_color()))
        axis_x.setGridLineColor(_grid_color())
        axis_x.setLinePenColor(_grid_color())
        axis_x.setTickCount(6)

        # Left Y axis — torque in Nm. Ranges to MaxTorque + 10% headroom.
        axis_torque = QtCharts.QValueAxis()
        axis_torque.setRange(0.0, max_torque_nm * 1.1)
        axis_torque.setLabelFormat("%.0f")
        axis_torque.setTitleText("Nm")
        axis_torque.setTitleBrush(QtGui.QBrush(_torque_color()))
        axis_torque.setLabelsBrush(QtGui.QBrush(_torque_color()))
        axis_torque.setGridLineColor(_grid_color())
        axis_torque.setLinePenColor(_torque_color())
        axis_torque.setTickCount(5)

        # Right Y axis — HP. Ranges to peak HP + 10% headroom (the
        # peak HP from the actual sampled curve, not the user input,
        # so the axis matches what's on screen).
        axis_hp = QtCharts.QValueAxis()
        axis_hp.setRange(0.0, max(1.0, peak_hp_value * 1.1))
        axis_hp.setLabelFormat("%.0f")
        axis_hp.setTitleText("HP")
        axis_hp.setTitleBrush(QtGui.QBrush(_hp_color()))
        axis_hp.setLabelsBrush(QtGui.QBrush(_hp_color()))
        axis_hp.setGridLineColor(_grid_color())
        axis_hp.setLinePenColor(_hp_color())
        axis_hp.setTickCount(5)

        self._chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(axis_torque, QtCore.Qt.AlignmentFlag.AlignLeft)
        self._chart.addAxis(axis_hp, QtCore.Qt.AlignmentFlag.AlignRight)
        torque_series.attachAxis(axis_x)
        torque_series.attachAxis(axis_torque)
        hp_series.attachAxis(axis_x)
        hp_series.attachAxis(axis_hp)

        # Status line under the chart: surface the headline numbers
        # so the user has a single line of "what they're looking at".
        achieved_hp = peak_hp_value
        hp_match_note = ''
        if max_hp_input > 0 and achieved_hp > 0:
            ratio = achieved_hp / max_hp_input
            if ratio < 0.92:
                hp_match_note = (
                    f"  (curve produces ~{achieved_hp:.0f} HP — "
                    f"raise MaxTorque or peak-HP RPM to reach "
                    f"{max_hp_input:.0f} HP)"
                )
        self._status_label.setText(
            f"Peak: {max_torque_nm:.0f} Nm @ {peak_torque_rpm:.0f} rpm  •  "
            f"{achieved_hp:.0f} HP @ ~{int(peak_hp_rpm)} rpm{hp_match_note}"
        )
        self._status_label.setStyleSheet(
            f"color: {_text_color().name()}; font-size: 11px;"
        )
