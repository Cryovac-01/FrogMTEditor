"""Reusable Qt widgets and delegates for the desktop shell."""
from __future__ import annotations

from .theme import *

class TaskSignals(QtCore.QObject):
    finished = QtCore.Signal(object, object)


class MetricCard(QtWidgets.QFrame):
    def __init__(self, value: str, label: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        set_surface(self, "metric")
        self.setMinimumHeight(SHELL_METRICS.metric_min_height)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
        layout.setSpacing(SPACING.xxs)
        value_label = QtWidgets.QLabel(value)
        set_label_kind(value_label, "metricValue")
        label_label = QtWidgets.QLabel(label)
        set_label_kind(label_label, "meta")
        layout.addWidget(value_label)
        layout.addWidget(label_label)


class CurveChartCard(QtWidgets.QWidget):
    def __init__(self, banner_name: str = "curve_banner.png", parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._pending_points: Optional[List[Dict[str, Any]]] = None
        self._pending_note = "Open the Curve tab to render torque data."
        self._chart_initialized = False
        self.chart_view: Optional[QtCharts.QChartView] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        layout.setSpacing(SPACING.md)

        intro_frame = QtWidgets.QFrame()
        set_surface(intro_frame, "panel")
        intro_layout = QtWidgets.QHBoxLayout(intro_frame)
        intro_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        intro_layout.setSpacing(SPACING.lg)
        intro_copy = QtWidgets.QVBoxLayout()
        intro_copy.setSpacing(4)
        intro_eyebrow = QtWidgets.QLabel("TORQUE CURVE")
        set_label_kind(intro_eyebrow, "eyebrow")
        intro_title = QtWidgets.QLabel("Curve Preview")
        set_label_kind(intro_title, "section")
        self.note_label = QtWidgets.QLabel("Open the Curve tab to render torque data.")
        self.note_label.setWordWrap(True)
        set_label_kind(self.note_label, "muted")
        intro_copy.addWidget(intro_eyebrow)
        intro_copy.addWidget(intro_title)
        intro_copy.addWidget(self.note_label)
        intro_layout.addLayout(intro_copy, 3)

        banner = load_pixmap(banner_name, 420)
        if not banner.isNull():
            banner_label = QtWidgets.QLabel()
            banner_label.setPixmap(banner)
            banner_label.setMaximumWidth(440)
            banner_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            intro_layout.addWidget(banner_label, 2)
        layout.addWidget(intro_frame)

        self.chart_host = QtWidgets.QFrame()
        set_surface(self.chart_host, "panel")
        self.chart_host.setMinimumHeight(320)
        host_layout = QtWidgets.QVBoxLayout(self.chart_host)
        host_layout.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.xl)
        host_layout.setSpacing(SPACING.sm)
        self.placeholder_icon = QtWidgets.QLabel()
        self.placeholder_icon.setPixmap(load_tinted_icon("curve.svg", "#73c686", size=30).pixmap(30, 30))
        self.placeholder_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder_title = QtWidgets.QLabel("No curve data available")
        self.placeholder_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        set_label_kind(self.placeholder_title, "section")
        self.placeholder_label = QtWidgets.QLabel("Curve visualization initializes on demand to keep the shell responsive.")
        self.placeholder_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setWordWrap(True)
        set_label_kind(self.placeholder_label, "muted")
        host_layout.addStretch(1)
        host_layout.addWidget(self.placeholder_icon, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        host_layout.addWidget(self.placeholder_title)
        host_layout.addWidget(self.placeholder_label)
        host_layout.addStretch(1)
        layout.addWidget(self.chart_host, 1)
        self.show_empty("Open the Curve tab to render torque data.")

    def _ensure_chart_view(self) -> QtCharts.QChartView:
        if self.chart_view is not None:
            return self.chart_view
        host_layout = self.chart_host.layout()
        while host_layout and host_layout.count():
            item = host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.chart_view = QtCharts.QChartView()
        self.chart_view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        self.chart_view.setMinimumHeight(340)
        self.chart_view.setStyleSheet("background: transparent; border: none;")
        host_layout.addWidget(self.chart_view, 1)
        return self.chart_view

    def _build_base_chart(self, title: str = "") -> QtCharts.QChart:
        chart = QtCharts.QChart()
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setBackgroundRoundness(0)
        chart.setMargins(QtCore.QMargins(0, 0, 0, 0))
        if title:
            chart.setTitle(title)
            chart.setTitleBrush(QtGui.QBrush(TEXT_COLOR))
        return chart

    def show_empty(self, note: str) -> None:
        self._pending_points = None
        self._pending_note = note
        self.note_label.setText(note)
        if self.chart_view is None:
            self.placeholder_title.setText("No curve data available")
            self.placeholder_label.setText(note or "Open the Curve tab to render torque data.")
            return
        chart = self._build_base_chart("No curve data available")
        chart.setTitleBrush(QtGui.QBrush(MUTED_COLOR))
        self.chart_view.setChart(chart)

    def set_curve(self, points: Optional[List[Dict[str, Any]]], note: str, eager: bool = False) -> None:
        self._pending_points = points or []
        self._pending_note = note
        self.note_label.setText(note)
        if eager:
            self.activate()
        elif not points:
            self.show_empty(note)
        elif self.chart_view is not None and self._chart_initialized:
            self.activate()
        else:
            self.placeholder_label.setText("Open the Curve tab to render this torque graph.")

    def activate(self) -> None:
        points = self._pending_points or []
        note = self._pending_note
        self.note_label.setText(note)
        if not points:
            self._ensure_chart_view()
            self._chart_initialized = True
            self.show_empty(note)
            return
        chart_view = self._ensure_chart_view()
        self._chart_initialized = True

        xs = [float(point.get("time") or 0.0) for point in points]
        ys = [float(point.get("value") or 0.0) for point in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if max_x <= min_x:
            max_x = min_x + 1.0
        if max_y <= min_y:
            max_y = min_y + 1.0

        chart = self._build_base_chart("Torque Curve")
        series = QtCharts.QLineSeries()
        pen = QtGui.QPen(LINE_COLOR)
        pen.setWidth(3)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        series.setPen(pen)
        for point in points:
            series.append(float(point.get("time") or 0.0), float(point.get("value") or 0.0))
        chart.addSeries(series)

        scatter = QtCharts.QScatterSeries()
        scatter.setMarkerShape(QtCharts.QScatterSeries.MarkerShape.MarkerShapeCircle)
        scatter.setMarkerSize(10.0)
        scatter.setColor(LINE_FILL)
        scatter.setBorderColor(LINE_COLOR)
        for point in points:
            scatter.append(float(point.get("time") or 0.0), float(point.get("value") or 0.0))
        chart.addSeries(scatter)

        axis_x = QtCharts.QValueAxis()
        axis_x.setRange(min_x, max_x)
        axis_x.setLabelFormat("%.2f")
        axis_x.setLabelsBrush(QtGui.QBrush(MUTED_COLOR))
        axis_x.setGridLineColor(GRID_COLOR)
        axis_x.setLinePenColor(QtGui.QColor("#314153"))
        axis_x.setTickCount(6)

        axis_y = QtCharts.QValueAxis()
        axis_y.setRange(min_y, max_y)
        axis_y.setLabelFormat("%.2f")
        axis_y.setLabelsBrush(QtGui.QBrush(MUTED_COLOR))
        axis_y.setGridLineColor(GRID_COLOR)
        axis_y.setLinePenColor(QtGui.QColor("#314153"))
        axis_y.setTickCount(6)

        chart.addAxis(axis_x, QtCore.Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, QtCore.Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        scatter.attachAxis(axis_x)
        scatter.attachAxis(axis_y)
        chart_view.setChart(chart)


class TemplateListDelegate(QtWidgets.QStyledItemDelegate):
    ENGINE_ROW_HEIGHT = 82
    TIRE_ROW_HEIGHT = 76
    CARD_MARGIN_X = 6
    CARD_MARGIN_Y = 4
    ROW_RADIUS = 12
    ACCENT_WIDTH = 3
    ICON_SLOT_SIZE = 28
    ICON_DRAW_SIZE = 22
    INNER_LEFT = 20
    INNER_RIGHT = 12
    CONTENT_GAP = 12
    BADGE_HEIGHT = 20
    BADGE_GAP = 10

    def __init__(self, mode: str, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.mode = mode
        icon_name = "engine.svg" if mode == "engine" else "tire.svg"
        self.icon_size = self.ICON_DRAW_SIZE
        self.icon_slot_size = self.ICON_SLOT_SIZE
        self.icon = load_tinted_icon(icon_name, "#e0e8f2", size=self.icon_size)

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtCore.QSize:
        base_width = option.rect.width() if option.rect.width() > 0 else 320
        return QtCore.QSize(base_width, self.ENGINE_ROW_HEIGHT if self.mode == "engine" else self.TIRE_ROW_HEIGHT)

    @staticmethod
    def _wrap_title_lines(text: str, metrics: QtGui.QFontMetrics, width: int) -> tuple[str, str]:
        clean = " ".join(str(text or "").split())
        if not clean or width <= 0:
            return "", ""
        if metrics.horizontalAdvance(clean) <= width:
            return clean, ""

        words = clean.split(" ")
        line_one: List[str] = []
        line_two: List[str] = []
        current = line_one
        for word in words:
            candidate = " ".join(current + [word]).strip()
            if not current or metrics.horizontalAdvance(candidate) <= width:
                current.append(word)
                continue
            if current is line_one:
                current = line_two
                if metrics.horizontalAdvance(word) <= width:
                    current.append(word)
                else:
                    current.append(metrics.elidedText(word, QtCore.Qt.TextElideMode.ElideRight, width))
            else:
                current.append(word)
        first = " ".join(line_one).strip()
        second = " ".join(line_two).strip()
        if not first:
            first = metrics.elidedText(clean, QtCore.Qt.TextElideMode.ElideRight, width)
            return first, ""
        if metrics.horizontalAdvance(first) > width:
            first = metrics.elidedText(first, QtCore.Qt.TextElideMode.ElideRight, width)
        if second and metrics.horizontalAdvance(second) > width:
            second = metrics.elidedText(second, QtCore.Qt.TextElideMode.ElideRight, width)
        return first, second

    def _row_layout(
        self,
        option_rect: QtCore.QRect,
        row: Dict[str, Any],
        badge_metrics: Optional[QtGui.QFontMetrics] = None,
    ) -> Dict[str, QtCore.QRect]:
        card = option_rect.adjusted(self.CARD_MARGIN_X, self.CARD_MARGIN_Y, -self.CARD_MARGIN_X, -self.CARD_MARGIN_Y)
        accent = QtCore.QRect(
            card.left() + 9,
            card.top() + 10,
            self.ACCENT_WIDTH,
            max(12, card.height() - 20),
        )
        icon_slot = QtCore.QRect(
            card.left() + self.INNER_LEFT,
            card.top() + (card.height() - self.icon_slot_size) // 2,
            self.icon_slot_size,
            self.icon_slot_size,
        )

        content_left = icon_slot.right() + self.CONTENT_GAP
        right_limit = card.right() - self.INNER_RIGHT
        badge = QtCore.QRect()
        if self.mode == "engine" and row.get("fuel_label") and badge_metrics is not None:
            badge_text = str(row.get("fuel_label") or "")
            badge_width = max(44, min(76, badge_metrics.horizontalAdvance(badge_text) + 16))
            badge = QtCore.QRect(
                right_limit - badge_width + 1,
                card.top() + 10,
                badge_width,
                self.BADGE_HEIGHT,
            )
            right_limit = badge.left() - self.BADGE_GAP

        title = QtCore.QRect(
            content_left,
            card.top() + 10,
            max(24, right_limit - content_left + 1),
            36,
        )
        meta = QtCore.QRect(
            content_left,
            card.bottom() - 20,
            max(24, card.right() - self.INNER_RIGHT - content_left + 1),
            18,
        )
        return {
            "card": card,
            "accent": accent,
            "icon_slot": icon_slot,
            "badge": badge,
            "title": title,
            "meta": meta,
        }

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        row = index.data(ROW_ROLE) or {}
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)

        tone = FUEL_THEME_STYLES.get(str(row.get("fuel_theme_key") or "neutral"), FUEL_THEME_STYLES["neutral"])
        accent = QtGui.QColor(tone["accent"] if self.mode == "engine" else "#4d6176")
        bg = QtGui.QColor("#101821")
        border = QtGui.QColor("#1f2d3b")
        if hovered:
            bg = QtGui.QColor("#14202a")
            border = QtGui.QColor("#2d4052")
        if selected:
            bg = QtGui.QColor("#18222c")
            border = accent

        title = str(row.get("title") or row.get("name") or index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "")
        secondary = str(row.get("secondary_metrics") or "")

        title_font = QtGui.QFont(option.font)
        title_font.setPointSizeF(max(9.3, title_font.pointSizeF()))
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        meta_font = QtGui.QFont(option.font)
        meta_font.setPointSizeF(max(8.2, meta_font.pointSizeF() - 0.6))
        badge_font = QtGui.QFont(meta_font)
        badge_font.setWeight(QtGui.QFont.Weight.DemiBold)
        badge_metrics = QtGui.QFontMetrics(badge_font)
        regions = self._row_layout(option.rect, row, badge_metrics)
        rect = regions["card"]

        painter.setPen(QtGui.QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRoundedRect(QtCore.QRectF(rect), self.ROW_RADIUS, self.ROW_RADIUS)

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QtCore.QRectF(regions["accent"]), 2, 2)

        icon_slot = regions["icon_slot"]
        icon_rect = QtCore.QRect(
            icon_slot.left() + (icon_slot.width() - self.icon_size) // 2,
            icon_slot.top() + (icon_slot.height() - self.icon_size) // 2,
            self.icon_size,
            self.icon_size,
        )
        self.icon.paint(painter, icon_rect)

        badge_rect = regions["badge"]
        if not badge_rect.isNull():
            badge_text = str(row.get("fuel_label") or "")
            painter.setPen(QtGui.QPen(QtGui.QColor(tone["badge_border"]), 1.0))
            painter.setBrush(QtGui.QColor(tone["badge_bg"]))
            painter.drawRoundedRect(QtCore.QRectF(badge_rect), 10, 10)
            painter.setFont(badge_font)
            painter.setPen(QtGui.QColor(tone["badge_text"]))
            painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.setFont(title_font)
        painter.setPen(QtGui.QColor("#f3f8fe"))
        title_metrics = QtGui.QFontMetrics(title_font)
        title_rect = regions["title"]
        line_one, line_two = self._wrap_title_lines(title, title_metrics, title_rect.width())
        line_height = title_metrics.lineSpacing()
        painter.drawText(
            QtCore.QRect(title_rect.left(), title_rect.top(), title_rect.width(), line_height),
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop,
            line_one,
        )
        if line_two:
            painter.drawText(
                QtCore.QRect(title_rect.left(), title_rect.top() + line_height - 1, title_rect.width(), line_height),
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop,
                line_two,
            )

        painter.setFont(meta_font)
        painter.setPen(QtGui.QColor("#94a3b4"))
        meta_metrics = QtGui.QFontMetrics(meta_font)
        meta_rect = regions["meta"]
        painter.drawText(
            meta_rect,
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
            meta_metrics.elidedText(secondary, QtCore.Qt.TextElideMode.ElideRight, meta_rect.width()),
        )
        painter.restore()


def build_key_value_tree(header_left: str = "Field", header_right: str = "Value") -> QtWidgets.QTreeWidget:
    tree = QtWidgets.QTreeWidget()
    tree.setColumnCount(2)
    tree.setHeaderLabels([header_left, header_right])
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(False)
    tree.setIndentation(0)
    tree.setUniformRowHeights(True)
    tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
    tree.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
    return tree


def populate_key_value_tree(
    tree: QtWidgets.QTreeWidget,
    rows: Iterable[tuple[str, str]],
    *,
    empty_message: str = "No data available.",
) -> None:
    tree.clear()
    rendered = False
    for key, value in rows:
        rendered = True
        item = QtWidgets.QTreeWidgetItem([str(key or "—"), str(value or "—")])
        tree.addTopLevelItem(item)
    if not rendered:
        tree.addTopLevelItem(QtWidgets.QTreeWidgetItem(["Status", empty_message]))


class QuickActionDialog(QtWidgets.QDialog):
    def __init__(
        self,
        actions: Iterable[Dict[str, Any]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._actions = [dict(row) for row in actions]
        self._visible_actions: List[Dict[str, Any]] = []
        self.setWindowTitle("Quick Actions")
        self.setModal(True)
        self.resize(620, 420)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        intro = QtWidgets.QLabel("Search commands, navigation actions, and pack workflows.")
        set_label_kind(intro, "muted")
        root.addWidget(intro)

        self.search_edit = QtWidgets.QLineEdit()
        configure_field_control(self.search_edit, "search")
        self.search_edit.setPlaceholderText("Type a command or shortcut")
        self.search_edit.addAction(load_icon("search.svg"), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        root.addWidget(self.search_edit)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setUniformItemSizes(True)
        root.addWidget(self.list_widget, 1)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = make_action_button("Close", role="secondary", chrome="headerAction")
        self.run_button = make_action_button("Run", role="primary", chrome="headerAction")
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.run_button)
        root.addLayout(button_row)

        self.search_edit.textChanged.connect(self._refresh)
        self.list_widget.itemDoubleClicked.connect(lambda *_: self._run_selected())
        self.run_button.clicked.connect(self._run_selected)
        self.cancel_button.clicked.connect(self.reject)
        self._refresh("")

    def _refresh(self, query: str) -> None:
        text = str(query or "").strip().lower()
        self._visible_actions = []
        self.list_widget.clear()
        for action in self._actions:
            haystack = " ".join(
                [
                    str(action.get("title") or ""),
                    str(action.get("shortcut") or ""),
                    str(action.get("keywords") or ""),
                ]
            ).lower()
            if text and text not in haystack:
                continue
            self._visible_actions.append(action)
            label = str(action.get("title") or "Action")
            shortcut = str(action.get("shortcut") or "").strip()
            description = str(action.get("description") or "").strip()
            item = QtWidgets.QListWidgetItem(label)
            tooltip_bits = [part for part in [shortcut, description] if part]
            item.setToolTip("  •  ".join(tooltip_bits))
            if shortcut:
                item.setText(f"{label}    {shortcut}")
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _run_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._visible_actions):
            return
        callback = self._visible_actions[row].get("callback")
        self.accept()
        if callable(callback):
            callback()
