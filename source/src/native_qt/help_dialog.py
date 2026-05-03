"""Per-tab Help popup. Modal dialog with a navigable section list +
content viewer.

Two pieces of UX:

  - Search box at the top of the left panel filters sections by
    title (case-insensitive substring match).
  - Section list on the left; selecting one renders its body on
    the right via QTextBrowser (HTML-aware, scrollable).
  - Each section row is collapsible / expandable in place via
    QTreeWidget — expanding a row also auto-scrolls the
    content viewer to the section's anchor for fast navigation.

Built with QDialog so it's modal-by-default but can be made
non-modal if needed. Uses QTextBrowser for the content area
because it gives us free scrolling, anchor navigation, and a
restricted-but-safe HTML subset.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from help_content import get_topic
from . import theme_palette as _palette
from . import scale as _scale
from i18n import _ as _t


# Visual constants resolved at call time from the central palette so
# the dialog re-themes correctly when the user switches between dark
# / light / high-contrast via File > Customize. Constants below kept
# only for backward-compat with the static QSS — the live dialog
# rebuilds its stylesheet from the palette.
_BG          = "#0c1622"
_BG_PANEL    = "#13202f"
_BORDER      = "#314153"
_TEXT        = "#cdd6e0"
_MUTED       = "#9da7b0"
_ACCENT      = "#73c686"
_ACCENT_TEXT = "#0c1622"


_DIALOG_QSS = f"""
QDialog {{
    background-color: {_BG};
    color: {_TEXT};
}}
QLabel {{ color: {_TEXT}; }}
QLabel[role="dialogTitle"] {{
    font-size: 18px;
    font-weight: 700;
    padding-bottom: 4px;
}}
QLabel[role="dialogSubtitle"] {{
    color: {_MUTED};
    font-size: 12px;
    padding-bottom: 8px;
}}
QLineEdit {{
    background: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}
QLineEdit:focus {{
    border-color: {_ACCENT};
}}
QTreeWidget {{
    background: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 4px;
    font-size: 12px;
    show-decoration-selected: 1;
}}
QTreeWidget::item {{
    padding: 6px 4px;
    border-radius: 3px;
}}
QTreeWidget::item:hover {{
    background: rgba(115, 198, 134, 0.10);
}}
QTreeWidget::item:selected {{
    background: {_ACCENT};
    color: {_ACCENT_TEXT};
}}
QTextBrowser {{
    background: {_BG_PANEL};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 14px 18px;
    font-size: 13px;
}}
QPushButton {{
    background: transparent;
    color: {_TEXT};
    border: 1px solid {_BORDER};
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
QPushButton[primary="true"] {{
    background: {_ACCENT};
    color: {_ACCENT_TEXT};
    border-color: {_ACCENT};
    font-weight: 600;
}}
QPushButton[primary="true"]:hover {{
    background: #8bd599;
    border-color: #8bd599;
}}
"""


class HelpDialog(QtWidgets.QDialog):
    """Modal help popup for one editor page.

    Construct with the page's help key (e.g. 'creator', 'lua_scripts')
    and call .exec() to show it. The dialog handles its own search +
    navigation + rendering.
    """

    def __init__(self, topic_key: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._topic = get_topic(topic_key)
        self._sections: List[Dict[str, Any]] = list(self._topic.get('sections') or [])

        self.setWindowTitle(_t("Help — {title}").format(title=self._topic.get('title', 'Frog Mod Editor')))
        # Build QSS from the active palette so the popup follows the
        # current theme (dark / light / high-contrast). Falls back to
        # the static _DIALOG_QSS only if the palette module is
        # unavailable for some reason.
        try:
            self.setStyleSheet(_palette.build_dialog_qss())
        except Exception:
            self.setStyleSheet(_DIALOG_QSS)
        self.resize(_scale.sx(1100), _scale.sx(720))

        self._build_ui()
        self._populate_tree()
        # Auto-select first section so the content area isn't empty
        if self._sections:
            first = self._tree.topLevelItem(0)
            if first is not None:
                self._tree.setCurrentItem(first)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        # Header (title + subtitle)
        title_label = QtWidgets.QLabel(self._topic.get('title', 'Help'))
        title_label.setProperty('role', 'dialogTitle')
        outer.addWidget(title_label)
        subtitle = self._topic.get('subtitle')
        if subtitle:
            sub_label = QtWidgets.QLabel(subtitle)
            sub_label.setProperty('role', 'dialogSubtitle')
            sub_label.setWordWrap(True)
            outer.addWidget(sub_label)

        # Body splitter — left nav, right content
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left panel: search + section tree ──
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._search_box = QtWidgets.QLineEdit()
        self._search_box.setPlaceholderText(_t("Search sections…"))
        self._search_box.textChanged.connect(self._apply_search)
        left_layout.addWidget(self._search_box)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(12)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._tree, 1)

        splitter.addWidget(left)

        # ── Right panel: content viewer ──
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._content = QtWidgets.QTextBrowser()
        self._content.setOpenExternalLinks(False)
        self._content.setReadOnly(True)
        right_layout.addWidget(self._content, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 800])

        outer.addWidget(splitter, 1)

        # Footer — close button
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        close_btn = QtWidgets.QPushButton(_t("Close"))
        close_btn.setProperty('primary', True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

    # ------------------------------------------------------------------
    def _populate_tree(self) -> None:
        """Build a QTreeWidget item for every section (and subsection
        when present). Each item carries the section dict on the
        UserRole so selection callbacks can pull it back out."""
        self._tree.clear()
        for section in self._sections:
            item = QtWidgets.QTreeWidgetItem([section.get('title', '?')])
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, section)
            for sub in section.get('subsections') or []:
                child = QtWidgets.QTreeWidgetItem([sub.get('title', '?')])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, sub)
                item.addChild(child)
            self._tree.addTopLevelItem(item)
        self._tree.expandAll()

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        section = items[0].data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(section, dict):
            return
        self._render_section(section)

    def _render_section(self, section: Dict[str, Any]) -> None:
        """Render a single section into the content viewer."""
        title = section.get('title', '')
        body = section.get('body', '')
        html = f'<h2 style="color:{_TEXT}; margin-top: 0;">{title}</h2>{body}'
        # Subsections rendered inline below the parent body for
        # context — nested expansion in the tree is for navigation,
        # the content viewer always shows the selected entry's body.
        self._content.setHtml(html)
        self._content.verticalScrollBar().setValue(0)

    def _apply_search(self, text: str) -> None:
        """Hide tree items whose titles don't match the search query.
        Empty query restores the full tree."""
        needle = (text or '').strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            self._filter_item(top, needle)

    def _filter_item(self, item: QtWidgets.QTreeWidgetItem, needle: str) -> bool:
        """Recursively filter; returns True if this item OR any
        descendant matched, which lets us cascade visibility up."""
        title = (item.text(0) or '').lower()
        any_child = False
        for i in range(item.childCount()):
            if self._filter_item(item.child(i), needle):
                any_child = True
        matches = (not needle) or (needle in title) or any_child
        item.setHidden(not matches)
        return matches


def open_help(topic_key: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
    """Convenience: build and show the help dialog for ``topic_key``."""
    dlg = HelpDialog(topic_key, parent)
    dlg.exec()


def make_need_help_header(topic_key,
                          parent: Optional[QtWidgets.QWidget] = None
                          ) -> QtWidgets.QWidget:
    """Build the "Need Help?" header strip that goes at the top of
    every editor page. Returns a QWidget the caller adds to the
    page's layout (typically as the first widget).

    ``topic_key`` is either:
      - a static string (e.g. ``'workspace'``) — opens that topic
        every time the button is clicked; OR
      - a zero-arg callable returning a string — resolved at click
        time, so a page like the Creator can route to
        ``'creator_engine'`` vs ``'creator_tire'`` based on the
        currently-loaded part type.

    The button is right-aligned so it doesn't compete with the page's
    own header text.
    """
    container = QtWidgets.QWidget(parent)
    layout = QtWidgets.QHBoxLayout(container)
    layout.setContentsMargins(14, 8, 14, 4)
    layout.setSpacing(6)
    layout.addStretch(1)

    # i18n: button label flows through the translation layer so a
    # Spanish (or other) pack can localize it.
    from i18n import _ as _t
    btn = QtWidgets.QPushButton(_t("Need Help?"))
    btn.setStyleSheet(
        f"QPushButton {{"
        f"  background: transparent;"
        f"  color: {_ACCENT};"
        f"  border: 1px solid {_ACCENT};"
        f"  border-radius: 4px;"
        f"  padding: 4px 12px;"
        f"  font-size: 12px;"
        f"  font-weight: 600;"
        f"}}"
        f"QPushButton:hover {{"
        f"  background: {_ACCENT};"
        f"  color: {_ACCENT_TEXT};"
        f"}}"
    )
    btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(_t("Open detailed help for this page"))

    def _on_click() -> None:
        # Resolve the topic key per-click so callable resolvers can
        # consult live UI state (e.g. "is the user editing an engine
        # or a tire right now?").
        try:
            key = topic_key() if callable(topic_key) else topic_key
        except Exception:
            key = 'workspace'  # safe fallback; always exists
        open_help(str(key or 'workspace'), container.window())

    btn.clicked.connect(_on_click)
    layout.addWidget(btn, 0)

    return container
