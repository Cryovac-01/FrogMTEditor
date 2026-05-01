"""Main Qt editor window and application shell behavior."""
from __future__ import annotations

from .theme import *
from .widgets import *
from .forms import PartEditorForm
from .creator import CreatorCatalogSidebar, CreatorWorkspace
from .economy_panel import EconomyEditorPanel
from .bus_route_panel import BusRouteConfigPanel
from .transmission_panel import TransmissionEditorPanel
from .policy_panel import PolicyEditorPanel
from .lua_scripts_panel import LuaScriptsPanel

class NativeQtEditorWindow(QtWidgets.QMainWindow):
    def __init__(self, service: NativeEditorService, smoke_test: bool = False) -> None:
        super().__init__()
        self.service = service
        self.smoke_test = smoke_test

        self.live_state_version = ""
        self.latest_live_state_version = ""
        self.parts_payload: Dict[str, Any] = {}
        self.workspace_summary = WorkspaceSummary(state_version="", engine_count=0, tire_count=0, part_count=0, groups={})
        self.current_part: Optional[Dict[str, Any]] = None
        self.current_document: Optional[AssetDocument] = None
        self.current_curve: Optional[Dict[str, Any]] = None
        self.sound_options: List[Dict[str, str]] = []
        self.path_to_item: Dict[str, QtGui.QStandardItem] = {}
        self._busy = False
        self._task_tokens: List[TaskSignals] = []
        self.activity_history: List[str] = []
        self.workspace_mode = "empty"
        self._creator_return_path = ""

        self.icons = {
            "reload": load_icon("reload.svg"),
            "package": load_icon("package.svg"),
            "engine": load_icon("engine.svg"),
            "tire": load_icon("tire.svg"),
            "save": load_icon("save.svg"),
            "revert": load_icon("revert.svg"),
            "delete": load_icon("delete.svg"),
            "fork": load_icon("fork.svg"),
            "audio": load_icon("audio.svg"),
            "diagnostics": load_icon("diagnostics.svg"),
            "curve": load_icon("curve.svg"),
            "parts": load_icon("parts.svg"),
        }
        self.primary_icons = {
            "engine": load_tinted_icon("engine.svg", "#0b1410", size=PRIMARY_BUTTON_ICON_SIZE),
            "tire": load_tinted_icon("tire.svg", "#0b1410", size=PRIMARY_BUTTON_ICON_SIZE),
            "save": load_tinted_icon("save.svg", "#0b1410", size=PRIMARY_BUTTON_ICON_SIZE),
            "package": load_tinted_icon("package.svg", "#0b1410", size=PRIMARY_BUTTON_ICON_SIZE),
        }
        self.brand_icon = load_pixmap("brand_mark.png", 36)

        self.setWindowTitle(APP_NAME)
        self.resize(1600, 980)
        self.setMinimumSize(1280, 800)
        if not self.brand_icon.isNull():
            self.setWindowIcon(QtGui.QIcon(self.brand_icon))

        self._build_ui()

        self.live_timer = QtCore.QTimer(self)
        self.live_timer.timeout.connect(self.poll_live_state)

        if smoke_test:
            self.load_initial_state()
        else:
            QtCore.QTimer.singleShot(0, self.load_initial_state)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(
            SHELL_METRICS.root_margin,
            SHELL_METRICS.root_margin,
            SHELL_METRICS.root_margin,
            SHELL_METRICS.root_margin,
        )
        root.setSpacing(SHELL_METRICS.root_spacing)

        topbar = QtWidgets.QFrame()
        self.command_bar = topbar
        self.command_bar.setObjectName("commandBar")
        set_surface(topbar, "topbar")
        topbar.setMinimumHeight(command_bar_height(self.font()))
        top_layout = QtWidgets.QHBoxLayout(topbar)
        top_layout.setContentsMargins(
            SHELL_METRICS.command_bar_horizontal_padding,
            SHELL_METRICS.command_bar_vertical_padding,
            SHELL_METRICS.command_bar_horizontal_padding,
            SHELL_METRICS.command_bar_vertical_padding,
        )
        top_layout.setSpacing(SPACING.lg)

        brand_lockup = QtWidgets.QWidget()
        brand_layout = QtWidgets.QHBoxLayout(brand_lockup)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(SPACING.sm)
        if not self.brand_icon.isNull():
            brand_icon = QtWidgets.QLabel()
            brand_icon.setPixmap(self.brand_icon)
            brand_layout.addWidget(brand_icon, 0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        brand_copy = QtWidgets.QVBoxLayout()
        brand_copy.setContentsMargins(0, 0, 0, 0)
        brand_copy.setSpacing(0)
        product_meta = QtWidgets.QLabel("MOD WORKSPACE")
        set_label_kind(product_meta, "appEyebrow")
        product_title = QtWidgets.QLabel(APP_NAME)
        set_label_kind(product_title, "product")
        brand_copy.addWidget(product_meta)
        brand_copy.addWidget(product_title)
        brand_layout.addLayout(brand_copy)

        context_widget = QtWidgets.QWidget()
        context_layout = QtWidgets.QVBoxLayout(context_widget)
        context_layout.setContentsMargins(0, 0, 0, 0)
        context_layout.setSpacing(0)
        self.command_context_label = QtWidgets.QLabel("Generated parts workspace")
        self.command_context_label.setWordWrap(False)
        self.command_context_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        set_label_kind(self.command_context_label, "section")
        self.command_context_meta_label = QtWidgets.QLabel("Waiting for local workspace bootstrap.")
        self.command_context_meta_label.setWordWrap(True)
        self.command_context_meta_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        set_label_kind(self.command_context_meta_label, "meta")
        context_layout.addWidget(self.command_context_label)
        context_layout.addWidget(self.command_context_meta_label)

        top_actions_widget = QtWidgets.QWidget()
        top_actions = QtWidgets.QHBoxLayout(top_actions_widget)
        top_actions.setContentsMargins(0, 0, 0, 0)
        top_actions.setSpacing(SPACING.sm)
        top_actions.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.status_label = QtWidgets.QLabel("Starting local workspace...")
        self.status_label.setObjectName("statusPill")
        set_label_kind(self.status_label, "pill")
        self.status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
        top_actions.addWidget(self.status_label)

        self.reload_button = make_action_button("Reload", role="subtle", icon=self.icons["reload"])
        self.command_button = make_action_button("Quick Actions", role="secondary", icon=self.icons["parts"])
        self.pack_templates_button = make_action_button("Pack Templates", role="secondary", icon=self.icons["package"])
        self.pack_mod_button = make_action_button("Pack Mod", role="secondary", icon=self.icons["package"])
        top_actions.addWidget(self.reload_button)
        top_actions.addWidget(self.command_button)
        top_actions.addWidget(self.pack_templates_button)
        top_actions.addWidget(self.pack_mod_button)

        top_layout.addWidget(brand_lockup, 0)
        top_layout.addWidget(context_widget, 1)
        top_layout.addWidget(top_actions_widget, 0, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(topbar)

        # Persistent compatibility notice. Engines, tires, and other
        # parts created in older Frog Mod Editor releases used a
        # different sidecar format and binary layout — opening or
        # forking them in this build can produce incomplete payloads,
        # missing volume/level metadata, and (worst case) corrupted
        # DataTable rows. Until a proper migration tool exists (#7),
        # we surface this as a visible warning above the workspace
        # so users don't silently lose data.
        self.compat_notice = QtWidgets.QLabel(
            "  ⚠  This build is NOT compatible with engines or tires "
            "created in earlier Frog Mod Editor versions. Re-create them "
            "in this version before saving — opening or forking older "
            "parts may produce incomplete or corrupted output."
        )
        self.compat_notice.setWordWrap(True)
        self.compat_notice.setStyleSheet(
            "QLabel {"
            "  background-color: #3a2a18;"   # warm warning brown
            "  color: #f5c98e;"              # soft amber text
            "  border-bottom: 1px solid #5a3a1a;"
            "  padding: 8px 14px;"
            "  font-size: 12px;"
            "  font-weight: 500;"
            "}"
        )
        self.compat_notice.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        root.addWidget(self.compat_notice)

        self.live_banner = QtWidgets.QLabel("")
        self.live_banner.setWordWrap(True)
        set_label_kind(self.live_banner, "warning")
        self.live_banner.hide()
        root.addWidget(self.live_banner)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        self.sidebar_stack = QtWidgets.QStackedWidget()
        self.sidebar_stack.setMinimumWidth(SHELL_METRICS.sidebar_min_width)
        self.sidebar_stack.setMaximumWidth(SHELL_METRICS.sidebar_max_width)

        self.parts_sidebar = QtWidgets.QFrame()
        set_surface(self.parts_sidebar, "sidebar")
        self.parts_sidebar.setMinimumWidth(SHELL_METRICS.sidebar_min_width - 10)
        self.parts_sidebar.setMaximumWidth(SHELL_METRICS.sidebar_max_width - 12)
        sidebar_layout = QtWidgets.QVBoxLayout(self.parts_sidebar)
        sidebar_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        sidebar_layout.setSpacing(SPACING.md)

        sidebar_header = QtWidgets.QHBoxLayout()
        sidebar_header.setContentsMargins(0, 0, 0, 0)
        sidebar_header.setSpacing(SPACING.sm)
        sidebar_icon = QtWidgets.QLabel()
        sidebar_icon.setPixmap(load_icon_pixmap("parts.svg", ICON_SIZES.inline, color="#9aacbd"))
        sidebar_icon.setFixedSize(ICON_SIZES.inline, ICON_SIZES.inline)
        sidebar_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        sidebar_header.addWidget(sidebar_icon)
        sidebar_title = QtWidgets.QLabel("Generated Parts")
        set_label_kind(sidebar_title, "section")
        sidebar_header.addWidget(sidebar_title)
        sidebar_header.addStretch(1)
        sidebar_layout.addLayout(sidebar_header)

        self.sidebar_stats_label = QtWidgets.QLabel("")
        self.sidebar_stats_label.setWordWrap(True)
        set_label_kind(self.sidebar_stats_label, "muted")
        sidebar_layout.addWidget(self.sidebar_stats_label)

        sidebar_counts = QtWidgets.QHBoxLayout()
        sidebar_counts.setContentsMargins(0, 0, 0, 0)
        sidebar_counts.setSpacing(8)
        self.engine_count_badge = QtWidgets.QLabel("Engines 0")
        set_label_kind(self.engine_count_badge, "pill")
        self.tire_count_badge = QtWidgets.QLabel("Tires 0")
        set_label_kind(self.tire_count_badge, "pill")
        sidebar_counts.addWidget(self.engine_count_badge)
        sidebar_counts.addWidget(self.tire_count_badge)
        sidebar_counts.addStretch(1)
        sidebar_layout.addLayout(sidebar_counts)

        search_label = QtWidgets.QLabel("Search")
        set_label_kind(search_label, "muted")
        sidebar_layout.addWidget(search_label)
        self.search_edit = QtWidgets.QLineEdit()
        configure_field_control(self.search_edit, "search")
        self.search_edit.setPlaceholderText("Search parts")
        self.search_edit.addAction(load_icon("search.svg"), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        sidebar_layout.addWidget(self.search_edit)

        filter_label = QtWidgets.QLabel("Filter")
        set_label_kind(filter_label, "muted")
        sidebar_layout.addWidget(filter_label)
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(SPACING.xs)
        self.filter_group = QtWidgets.QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_all_button = QtWidgets.QPushButton("All")
        self.filter_engine_button = QtWidgets.QPushButton("Engines")
        self.filter_tire_button = QtWidgets.QPushButton("Tires")
        for button in (self.filter_all_button, self.filter_engine_button, self.filter_tire_button):
            button.setCheckable(True)
            set_button_role(button, "chip")
            self.filter_group.addButton(button)
            filter_row.addWidget(button)
        self.filter_all_button.setChecked(True)
        sidebar_layout.addLayout(filter_row)

        create_buttons_widget = QtWidgets.QWidget()
        create_buttons = QtWidgets.QGridLayout(create_buttons_widget)
        create_buttons.setContentsMargins(0, SPACING.xs, 0, SPACING.xs)
        create_buttons.setHorizontalSpacing(SPACING.sm)
        create_buttons.setVerticalSpacing(SPACING.sm)
        self.new_engine_button = QtWidgets.QPushButton("New Engine")
        self.new_engine_button.setObjectName("newEngineButton")
        configure_launcher_button(
            self.new_engine_button,
            "primary",
            load_tinted_icon("engine.svg", "#0b1410", size=LAUNCHER_BUTTON_ICON_SIZE),
        )
        self.new_tire_button = QtWidgets.QPushButton("New Tire")
        self.new_tire_button.setObjectName("newTireButton")
        configure_launcher_button(self.new_tire_button, "secondary", self.icons["tire"])
        create_buttons.addWidget(self.new_engine_button, 0, 0)
        create_buttons.addWidget(self.new_tire_button, 1, 0)

        self.economy_editor_button = QtWidgets.QPushButton("Economy Editor")
        self.economy_editor_button.setObjectName("economyEditorButton")
        configure_launcher_button(self.economy_editor_button, "secondary", self.icons["parts"])
        self.bus_route_button = QtWidgets.QPushButton("Bus Routes")
        self.bus_route_button.setObjectName("busRouteButton")
        configure_launcher_button(self.bus_route_button, "secondary", self.icons["curve"])
        self.transmission_editor_button = QtWidgets.QPushButton("Transmissions")
        self.transmission_editor_button.setObjectName("transmissionEditorButton")
        configure_launcher_button(self.transmission_editor_button, "secondary", self.icons["parts"])
        self.policy_editor_button = QtWidgets.QPushButton("Policies")
        self.policy_editor_button.setObjectName("policyEditorButton")
        configure_launcher_button(self.policy_editor_button, "secondary", self.icons["parts"])
        self.lua_scripts_button = QtWidgets.QPushButton("Lua Mods")
        self.lua_scripts_button.setObjectName("luaScriptsButton")
        configure_launcher_button(self.lua_scripts_button, "secondary", self.icons["parts"])
        create_buttons.addWidget(self.economy_editor_button, 2, 0)
        create_buttons.addWidget(self.bus_route_button, 3, 0)
        create_buttons.addWidget(self.transmission_editor_button, 4, 0)
        create_buttons.addWidget(self.policy_editor_button, 5, 0)
        create_buttons.addWidget(self.lua_scripts_button, 6, 0)
        sidebar_layout.addWidget(create_buttons_widget)

        tree_frame = QtWidgets.QFrame()
        set_surface(tree_frame, "panel")
        tree_layout = QtWidgets.QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        tree_layout.setSpacing(0)
        self.parts_model = QtGui.QStandardItemModel(self)
        self.parts_tree = QtWidgets.QTreeView()
        self.parts_tree.setModel(self.parts_model)
        self.parts_tree.setHeaderHidden(True)
        self.parts_tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts_tree.setUniformRowHeights(True)
        self.parts_tree.setIconSize(QtCore.QSize(TREE_ICON_SIZE, TREE_ICON_SIZE))
        self.parts_tree.setIndentation(18)
        self.parts_tree.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.parts_tree.setExpandsOnDoubleClick(False)
        tree_layout.addWidget(self.parts_tree)
        sidebar_layout.addWidget(tree_frame, 1)
        self.sidebar_stack.addWidget(self.parts_sidebar)

        self.creator_sidebar = CreatorCatalogSidebar()
        self.creator_sidebar.template_selected.connect(self._on_creator_template_selected)
        self.sidebar_stack.addWidget(self.creator_sidebar)

        splitter.addWidget(self.sidebar_stack)

        main_area = QtWidgets.QWidget()
        main_layout = QtWidgets.QVBoxLayout(main_area)
        set_widget_margins(main_layout)
        main_layout.setSpacing(0)
        splitter.addWidget(main_area)
        splitter.setSizes([SHELL_METRICS.sidebar_min_width, 1280])
        self.stack = QtWidgets.QStackedWidget()
        main_layout.addWidget(self.stack, 1)

        empty_page = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(SPACING.xl)
        empty_layout.addStretch(1)

        empty_shell = QtWidgets.QWidget()
        empty_shell.setMaximumWidth(1120)
        empty_shell_layout = QtWidgets.QVBoxLayout(empty_shell)
        empty_shell_layout.setContentsMargins(0, 0, 0, 0)
        empty_shell_layout.setSpacing(SPACING.md)

        welcome_card = QtWidgets.QFrame()
        self.welcome_card = welcome_card
        set_surface(welcome_card, "heroCard")
        welcome_layout = QtWidgets.QHBoxLayout(welcome_card)
        welcome_layout.setContentsMargins(SPACING.xl, SPACING.lg, SPACING.xl, SPACING.lg)
        welcome_layout.setSpacing(SPACING.xxl)

        welcome_copy_widget = QtWidgets.QWidget()
        welcome_copy_widget.setMinimumWidth(320)
        welcome_copy_widget.setMaximumWidth(380)
        welcome_copy_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)
        welcome_copy = QtWidgets.QVBoxLayout(welcome_copy_widget)
        welcome_copy.setContentsMargins(0, 0, 0, 0)
        welcome_copy.setSpacing(0)
        empty_eyebrow = QtWidgets.QLabel("WORKSPACE OVERVIEW")
        set_label_kind(empty_eyebrow, "eyebrow")
        empty_title = QtWidgets.QLabel("Generated Parts Workspace")
        set_label_kind(empty_title, "title")
        empty_title.setWordWrap(True)
        empty_copy = QtWidgets.QLabel(
            "Use the navigator to edit generated parts, inspect diagnostics, manage audio, and package the current workspace without leaving the shell."
        )
        empty_copy.setWordWrap(True)
        set_label_kind(empty_copy, "muted")
        welcome_copy.addWidget(empty_eyebrow)
        welcome_copy.addSpacing(SPACING.xs)
        welcome_copy.addWidget(empty_title)
        welcome_copy.addSpacing(SPACING.xs)
        welcome_copy.addWidget(empty_copy)
        welcome_copy.addSpacing(SPACING.md)
        empty_actions_widget = QtWidgets.QWidget()
        empty_actions_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        empty_actions = QtWidgets.QGridLayout(empty_actions_widget)
        empty_actions.setContentsMargins(0, 0, 0, 0)
        empty_actions.setHorizontalSpacing(SPACING.sm)
        empty_actions.setVerticalSpacing(SPACING.xs)
        empty_actions.setColumnStretch(0, 1)
        empty_actions.setColumnStretch(1, 1)
        self.empty_new_engine_button = QtWidgets.QPushButton("New Engine")
        self.empty_new_engine_button.setObjectName("emptyNewEngineButton")
        configure_launcher_button(
            self.empty_new_engine_button,
            "primary",
            load_tinted_icon("engine.svg", "#0b1410", size=LAUNCHER_BUTTON_ICON_SIZE),
        )
        self.empty_new_tire_button = QtWidgets.QPushButton("New Tire")
        self.empty_new_tire_button.setObjectName("emptyNewTireButton")
        configure_launcher_button(self.empty_new_tire_button, "secondary", self.icons["tire"])
        self.empty_new_engine_button.ensurePolished()
        self.empty_new_tire_button.ensurePolished()
        target_width = max(self.empty_new_engine_button.sizeHint().width(), self.empty_new_tire_button.sizeHint().width())
        self.empty_new_engine_button.setMinimumWidth(target_width)
        self.empty_new_tire_button.setMinimumWidth(target_width)
        empty_actions.addWidget(self.empty_new_engine_button, 0, 0)
        empty_actions.addWidget(self.empty_new_tire_button, 0, 1)
        welcome_copy.addWidget(empty_actions_widget, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        welcome_copy.addSpacing(SPACING.md)
        self.welcome_stats_label = QtWidgets.QLabel("")
        self.welcome_stats_label.setWordWrap(True)
        set_label_kind(self.welcome_stats_label, "meta")
        welcome_copy.addWidget(self.welcome_stats_label)
        welcome_layout.addWidget(welcome_copy_widget, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        welcome_hero = load_pixmap_contained("welcome_hero.png", 340, 192)
        if not welcome_hero.isNull():
            hero_wrap = QtWidgets.QWidget()
            hero_wrap.setMinimumWidth(320)
            hero_wrap.setMaximumWidth(360)
            hero_wrap.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            hero_layout = QtWidgets.QVBoxLayout(hero_wrap)
            hero_layout.setContentsMargins(0, 0, 0, 0)
            hero_layout.setSpacing(0)
            hero = QtWidgets.QLabel()
            self.welcome_hero_label = hero
            hero.setPixmap(welcome_hero)
            hero.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            hero_layout.addWidget(hero, 0, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            welcome_layout.addWidget(hero_wrap, 0, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        welcome_layout.addStretch(1)

        empty_shell_layout.addWidget(welcome_card)

        empty_metrics_frame = QtWidgets.QFrame()
        set_surface(empty_metrics_frame, "section")
        empty_metrics_layout = QtWidgets.QHBoxLayout(empty_metrics_frame)
        empty_metrics_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        empty_metrics_layout.setSpacing(SPACING.md)
        self.empty_metrics: Dict[str, QtWidgets.QLabel] = {}
        for key, title in (
            ("total", "Total Parts"),
            ("engines", "Engines"),
            ("tires", "Tires"),
            ("live", "Live State"),
        ):
            card = QtWidgets.QFrame()
            set_surface(card, "metric")
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(SPACING.md, SPACING.sm, SPACING.md, SPACING.sm)
            card_layout.setSpacing(SPACING.xxs)
            value = QtWidgets.QLabel("—")
            set_label_kind(value, "metricValue")
            label = QtWidgets.QLabel(title)
            set_label_kind(label, "metricLabel")
            card_layout.addWidget(value)
            card_layout.addWidget(label)
            empty_metrics_layout.addWidget(card, 1)
            self.empty_metrics[key] = value
        empty_shell_layout.addWidget(empty_metrics_frame)
        empty_layout.addWidget(
            empty_shell,
            0,
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
        )
        empty_layout.addStretch(1)
        self.stack.addWidget(empty_page)

        workspace_page = QtWidgets.QWidget()
        workspace_layout = QtWidgets.QVBoxLayout(workspace_page)
        set_widget_margins(workspace_layout)
        workspace_layout.setSpacing(SPACING.md)

        header_card = QtWidgets.QFrame()
        set_surface(header_card, "card")
        header_layout = QtWidgets.QVBoxLayout(header_card)
        header_layout.setContentsMargins(SPACING.xl, SPACING.lg, SPACING.xl, SPACING.lg)
        header_layout.setSpacing(SPACING.md)
        header_top = QtWidgets.QHBoxLayout()
        header_top.setSpacing(SPACING.md)
        header_copy = QtWidgets.QVBoxLayout()
        header_copy.setSpacing(4)
        header_eyebrow = QtWidgets.QLabel("CURRENT PART")
        set_label_kind(header_eyebrow, "eyebrow")
        self.part_title_label = QtWidgets.QLabel("")
        self.part_title_label.setWordWrap(True)
        set_label_kind(self.part_title_label, "title")
        self.part_subtitle_label = QtWidgets.QLabel("")
        self.part_subtitle_label.setWordWrap(True)
        set_label_kind(self.part_subtitle_label, "muted")
        self.part_hint_label = QtWidgets.QLabel("")
        self.part_hint_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        set_label_kind(self.part_hint_label, "subtle")
        header_copy.addWidget(header_eyebrow)
        header_copy.addWidget(self.part_title_label)
        header_copy.addWidget(self.part_subtitle_label)
        header_copy.addWidget(self.part_hint_label)
        header_top.addLayout(header_copy, 1)

        header_actions = QtWidgets.QHBoxLayout()
        header_actions.setSpacing(SPACING.xs)
        self.fork_button = make_action_button("Fork Engine", role="subtle", icon=self.icons["fork"], chrome="headerAction")
        self.revert_button = make_action_button("Revert", role="subtle", icon=self.icons["revert"], chrome="headerAction")
        self.delete_button = make_action_button("Delete", role="subtle", icon=self.icons["delete"], chrome="headerAction")
        self.pack_current_button = make_action_button("Pack Current", role="secondary", icon=self.icons["package"], chrome="headerAction")
        self.save_button = make_action_button("Save Changes", role="primary", icon=self.primary_icons["save"], chrome="headerAction")
        header_actions.addWidget(self.fork_button)
        header_actions.addWidget(self.revert_button)
        header_actions.addWidget(self.delete_button)
        header_actions.addWidget(self.pack_current_button)
        header_actions.addWidget(self.save_button)
        header_top.addLayout(header_actions)
        header_layout.addLayout(header_top)

        self.metrics_layout = QtWidgets.QHBoxLayout()
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setSpacing(SPACING.sm)
        header_layout.addLayout(self.metrics_layout)
        self.header_notice_label = QtWidgets.QLabel("")
        self.header_notice_label.setWordWrap(True)
        set_label_kind(self.header_notice_label, "notice")
        header_layout.addWidget(self.header_notice_label)
        workspace_layout.addWidget(header_card)

        workspace_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        workspace_splitter.setChildrenCollapsible(False)
        workspace_layout.addWidget(workspace_splitter, 1)

        document_shell = QtWidgets.QWidget()
        document_layout = QtWidgets.QVBoxLayout(document_shell)
        document_layout.setContentsMargins(0, 0, 0, 0)
        document_layout.setSpacing(0)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setIconSize(QtCore.QSize(ICON_SIZES.tab, ICON_SIZES.tab))
        document_layout.addWidget(self.tabs, 1)

        overview_tab = QtWidgets.QWidget()
        overview_layout = QtWidgets.QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(12, 12, 12, 12)
        overview_layout.setSpacing(12)
        overview_intro = QtWidgets.QFrame()
        set_surface(overview_intro, "panel")
        overview_intro_layout = QtWidgets.QVBoxLayout(overview_intro)
        overview_intro_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        overview_intro_layout.setSpacing(SPACING.xs)
        overview_eyebrow = QtWidgets.QLabel("DOCUMENT OVERVIEW")
        set_label_kind(overview_eyebrow, "eyebrow")
        self.overview_title_label = QtWidgets.QLabel("Choose a generated part")
        set_label_kind(self.overview_title_label, "section")
        self.overview_body_label = QtWidgets.QLabel("The overview summarises the selected part, its current risk status, and the next recommended actions.")
        self.overview_body_label.setWordWrap(True)
        set_label_kind(self.overview_body_label, "muted")
        overview_intro_layout.addWidget(overview_eyebrow)
        overview_intro_layout.addWidget(self.overview_title_label)
        overview_intro_layout.addWidget(self.overview_body_label)
        overview_layout.addWidget(overview_intro)

        self.overview_metrics_frame = QtWidgets.QFrame()
        set_surface(self.overview_metrics_frame, "card")
        self.overview_metrics_layout = QtWidgets.QHBoxLayout(self.overview_metrics_frame)
        self.overview_metrics_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        self.overview_metrics_layout.setSpacing(SPACING.md)
        overview_layout.addWidget(self.overview_metrics_frame)

        overview_details = QtWidgets.QFrame()
        set_surface(overview_details, "panel")
        overview_details_layout = QtWidgets.QVBoxLayout(overview_details)
        overview_details_layout.setContentsMargins(12, 12, 12, 12)
        overview_details_layout.setSpacing(8)
        overview_details_title = QtWidgets.QLabel("Current document snapshot")
        set_label_kind(overview_details_title, "section")
        self.overview_tree = build_key_value_tree("Overview", "Current value")
        overview_details_layout.addWidget(overview_details_title)
        overview_details_layout.addWidget(self.overview_tree, 1)
        overview_layout.addWidget(overview_details, 1)
        self.tabs.addTab(overview_tab, self.icons["diagnostics"], "Overview")

        properties_tab = QtWidgets.QWidget()
        properties_layout = QtWidgets.QVBoxLayout(properties_tab)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_form = PartEditorForm()
        self.editor_form.changed.connect(self._on_editor_change)
        properties_layout.addWidget(self.editor_form)
        self.tabs.addTab(properties_tab, self.icons["parts"], "Properties")

        curve_tab = QtWidgets.QWidget()
        curve_layout = QtWidgets.QVBoxLayout(curve_tab)
        curve_layout.setContentsMargins(0, 0, 0, 0)
        self.curve_card = CurveChartCard("curve_banner.png")
        curve_layout.addWidget(self.curve_card)
        self.tabs.addTab(curve_tab, self.icons["curve"], "Curve")
        workspace_splitter.addWidget(document_shell)

        inspector_card = QtWidgets.QFrame()
        set_surface(inspector_card, "sidebar")
        inspector_card.setMinimumWidth(SHELL_METRICS.inspector_min_width)
        inspector_card.setMaximumWidth(SHELL_METRICS.inspector_max_width)
        inspector_layout = QtWidgets.QVBoxLayout(inspector_card)
        inspector_layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        inspector_layout.setSpacing(SPACING.sm)
        inspector_title = QtWidgets.QLabel("Contextual Inspector")
        set_label_kind(inspector_title, "section")
        self.inspector_summary_label = QtWidgets.QLabel("Selection context, validation, audio routing, and metadata stay visible here while you work.")
        self.inspector_summary_label.setWordWrap(True)
        set_label_kind(self.inspector_summary_label, "muted")
        inspector_layout.addWidget(inspector_title)
        inspector_layout.addWidget(self.inspector_summary_label)

        self.inspector_tabs = QtWidgets.QTabWidget()
        self.inspector_tabs.setIconSize(QtCore.QSize(ICON_SIZES.tab, ICON_SIZES.tab))
        inspector_layout.addWidget(self.inspector_tabs, 1)

        validation_tab = QtWidgets.QWidget()
        validation_layout = QtWidgets.QVBoxLayout(validation_tab)
        validation_layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        validation_layout.setSpacing(SPACING.sm)
        self.validation_status_label = QtWidgets.QLabel("Choose a generated part to inspect validation status.")
        self.validation_status_label.setWordWrap(True)
        set_label_kind(self.validation_status_label, "notice")
        self.validation_counts_label = QtWidgets.QLabel("")
        self.validation_counts_label.setWordWrap(True)
        set_label_kind(self.validation_counts_label, "muted")
        self.validation_list = QtWidgets.QListWidget()
        self.validation_list.setAlternatingRowColors(False)
        self.validation_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        validation_layout.addWidget(self.validation_status_label)
        validation_layout.addWidget(self.validation_counts_label)
        validation_layout.addWidget(self.validation_list, 1)
        self.inspector_tabs.addTab(validation_tab, self.icons["diagnostics"], "Validation")

        audio_tab = QtWidgets.QWidget()
        audio_layout = QtWidgets.QVBoxLayout(audio_tab)
        audio_layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        audio_layout.setSpacing(SPACING.sm)
        self.audio_summary_label = QtWidgets.QLabel("Audio routing is available when an engine is selected.")
        self.audio_summary_label.setWordWrap(True)
        set_label_kind(self.audio_summary_label, "muted")
        audio_actions = QtWidgets.QHBoxLayout()
        self.audio_override_checkbox = QtWidgets.QCheckBox("Enable template override")
        self.audio_apply_button = make_action_button(
            "Apply",
            role="secondary",
            icon=self.icons["audio"],
            chrome="detailsToggle",
            height=DETAILS_BUTTON_HEIGHT,
        )
        self.audio_refresh_button = make_action_button(
            "Refresh",
            role="subtle",
            icon=self.icons["reload"],
            chrome="detailsToggle",
            height=DETAILS_BUTTON_HEIGHT,
        )
        audio_actions.addWidget(self.audio_override_checkbox)
        audio_actions.addStretch(1)
        audio_actions.addWidget(self.audio_apply_button)
        audio_actions.addWidget(self.audio_refresh_button)
        self.audio_tree = build_key_value_tree("Audio", "Value")
        audio_layout.addWidget(self.audio_summary_label)
        audio_layout.addLayout(audio_actions)
        audio_layout.addWidget(self.audio_tree, 1)
        self.inspector_tabs.addTab(audio_tab, self.icons["audio"], "Audio")

        metadata_tab = QtWidgets.QWidget()
        metadata_layout = QtWidgets.QVBoxLayout(metadata_tab)
        metadata_layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        metadata_layout.setSpacing(SPACING.sm)
        metadata_intro = QtWidgets.QLabel("Current metadata and serialized surface for the selected part.")
        metadata_intro.setWordWrap(True)
        set_label_kind(metadata_intro, "muted")
        self.metadata_tree = build_key_value_tree("Metadata", "Value")
        metadata_layout.addWidget(metadata_intro)
        metadata_layout.addWidget(self.metadata_tree, 1)
        self.inspector_tabs.addTab(metadata_tab, self.icons["parts"], "Metadata")

        activity_tab = QtWidgets.QWidget()
        activity_layout = QtWidgets.QVBoxLayout(activity_tab)
        activity_layout.setContentsMargins(SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm)
        activity_layout.setSpacing(SPACING.sm)
        activity_intro = QtWidgets.QLabel("Recent session activity stays visible so pack, save, reload, and create operations are easier to audit.")
        activity_intro.setWordWrap(True)
        set_label_kind(activity_intro, "muted")
        self.history_list = QtWidgets.QListWidget()
        self.history_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        activity_layout.addWidget(activity_intro)
        activity_layout.addWidget(self.history_list, 1)
        self.inspector_tabs.addTab(activity_tab, self.icons["reload"], "Activity")

        workspace_splitter.addWidget(inspector_card)
        workspace_splitter.setSizes([1040, SHELL_METRICS.inspector_min_width])
        self.stack.addWidget(workspace_page)

        creator_page = QtWidgets.QWidget()
        creator_layout = QtWidgets.QVBoxLayout(creator_page)
        creator_layout.setContentsMargins(0, 0, 0, 0)
        creator_layout.setSpacing(0)
        self.creator_workspace = CreatorWorkspace(self, self.service)
        self.creator_workspace.cancel_requested.connect(self.cancel_creator_mode)
        self.creator_workspace.created.connect(self.on_part_created)
        creator_layout.addWidget(self.creator_workspace)
        self.stack.addWidget(creator_page)

        # ── Economy Editor page (stack index 3) ──────────────────────
        economy_page = QtWidgets.QWidget()
        economy_layout = QtWidgets.QVBoxLayout(economy_page)
        economy_layout.setContentsMargins(0, 0, 0, 0)
        economy_layout.setSpacing(0)
        self.economy_panel = EconomyEditorPanel()
        self.economy_panel.economy_applied.connect(self._on_economy_applied)
        economy_layout.addWidget(self.economy_panel)
        self.stack.addWidget(economy_page)

        # ── Bus Route Configurator page (stack index 4) ──────────────
        bus_route_page = QtWidgets.QWidget()
        bus_route_layout = QtWidgets.QVBoxLayout(bus_route_page)
        bus_route_layout.setContentsMargins(0, 0, 0, 0)
        bus_route_layout.setSpacing(0)
        self.bus_route_panel = BusRouteConfigPanel()
        bus_route_layout.addWidget(self.bus_route_panel)
        self.stack.addWidget(bus_route_page)

        # ── Transmission Editor page (stack index 5) ────────────────
        transmission_page = QtWidgets.QWidget()
        transmission_layout = QtWidgets.QVBoxLayout(transmission_page)
        transmission_layout.setContentsMargins(0, 0, 0, 0)
        transmission_layout.setSpacing(0)
        self.transmission_panel = TransmissionEditorPanel()
        self.transmission_panel.transmission_created.connect(self._on_transmission_created)
        transmission_layout.addWidget(self.transmission_panel)
        self.stack.addWidget(transmission_page)

        # ── Policy Editor page (stack index 6) ─────────────────────
        policy_page = QtWidgets.QWidget()
        policy_layout = QtWidgets.QVBoxLayout(policy_page)
        policy_layout.setContentsMargins(0, 0, 0, 0)
        policy_layout.setSpacing(0)
        self.policy_panel = PolicyEditorPanel()
        self.policy_panel.policy_applied.connect(self._on_policy_applied)
        policy_layout.addWidget(self.policy_panel)
        self.stack.addWidget(policy_page)

        # ── LUA Scripts page (stack index 7) ───────────────────────
        lua_scripts_page = QtWidgets.QWidget()
        lua_scripts_layout = QtWidgets.QVBoxLayout(lua_scripts_page)
        lua_scripts_layout.setContentsMargins(0, 0, 0, 0)
        lua_scripts_layout.setSpacing(0)
        self.lua_scripts_panel = LuaScriptsPanel()
        lua_scripts_layout.addWidget(self.lua_scripts_panel)
        self.stack.addWidget(lua_scripts_page)

        self.stack.setCurrentIndex(0)

        self.activity_rail = QtWidgets.QFrame()
        set_surface(self.activity_rail, "statusStrip")
        activity_rail_layout = QtWidgets.QHBoxLayout(self.activity_rail)
        activity_rail_layout.setContentsMargins(SPACING.md, SPACING.xs, SPACING.md, SPACING.xs)
        activity_rail_layout.setSpacing(SPACING.sm)
        self.activity_state_label = QtWidgets.QLabel("Session ready.")
        self.activity_state_label.setWordWrap(True)
        set_label_kind(self.activity_state_label, "notice")
        self.activity_preview_label = QtWidgets.QLabel("No recent activity yet.")
        self.activity_preview_label.setWordWrap(True)
        set_label_kind(self.activity_preview_label, "muted")
        activity_rail_layout.addWidget(self.activity_state_label, 2)
        activity_rail_layout.addWidget(self.activity_preview_label, 3)
        root.addWidget(self.activity_rail)

        self.reload_button.clicked.connect(self.reload_workspace)
        self.command_button.clicked.connect(self.open_quick_actions)
        self.pack_templates_button.clicked.connect(self.pack_templates)
        self.pack_mod_button.clicked.connect(self.pack_mod)
        self.search_edit.textChanged.connect(self.render_part_tree)
        self.filter_group.buttonClicked.connect(lambda *_: self.render_part_tree())
        self.new_engine_button.clicked.connect(self.open_engine_creator)
        self.new_tire_button.clicked.connect(self.open_tire_creator)
        self.empty_new_engine_button.clicked.connect(self.open_engine_creator)
        self.empty_new_tire_button.clicked.connect(self.open_tire_creator)
        self.economy_editor_button.clicked.connect(self.open_economy_editor)
        self.bus_route_button.clicked.connect(self.open_bus_route_planner)
        self.transmission_editor_button.clicked.connect(self.open_transmission_editor)
        self.policy_editor_button.clicked.connect(self.open_policy_editor)
        self.lua_scripts_button.clicked.connect(self.open_lua_scripts_editor)
        self.parts_tree.clicked.connect(self._on_tree_clicked)
        self.parts_tree.activated.connect(self._on_tree_clicked)
        self.save_button.clicked.connect(self.save_current)
        self.revert_button.clicked.connect(self.revert_current)
        self.delete_button.clicked.connect(self.delete_current)
        self.pack_current_button.clicked.connect(self.pack_current_part)
        self.fork_button.clicked.connect(self.fork_engine)
        self.audio_apply_button.clicked.connect(self.apply_audio_override)
        self.audio_refresh_button.clicked.connect(self.refresh_audio_panel)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._configure_menus()
        self._configure_shortcuts()
        self._update_action_state()
        self._update_inspector()

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or ""))
        if hasattr(self, "activity_state_label"):
            self.activity_state_label.setText(str(text or ""))
        logging.info("status: %s", text)

    def set_live_banner(self, text: str) -> None:
        self.live_banner.setText(str(text or ""))
        self.live_banner.setVisible(bool(text))

    def _make_action(
        self,
        text: str,
        callback: Callable[[], None],
        *,
        shortcut: str = "",
        status_tip: str = "",
    ) -> QtGui.QAction:
        action = QtGui.QAction(text, self)
        if shortcut:
            action.setShortcut(QtGui.QKeySequence(shortcut))
        if status_tip:
            action.setStatusTip(status_tip)
        action.triggered.connect(callback)
        return action

    def _configure_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self._make_action("Reload Workspace", self.reload_workspace, shortcut="Ctrl+R"))
        file_menu.addAction(self._make_action("Save Changes", self.save_current, shortcut="Ctrl+S"))
        file_menu.addAction(self._make_action("Revert Changes", self.revert_current, shortcut="Ctrl+Shift+R"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Pack Current Part", self.pack_current_part, shortcut="Ctrl+Alt+P"))
        file_menu.addAction(self._make_action("Pack Workspace", self.pack_mod, shortcut="Ctrl+P"))
        file_menu.addAction(self._make_action("Pack Templates", self.pack_templates, shortcut="Ctrl+Shift+P"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_action("Quick Actions", self.open_quick_actions, shortcut="Ctrl+K"))

        create_menu = menu_bar.addMenu("&Create")
        create_menu.addAction(self._make_action("New Engine", self.open_engine_creator, shortcut="Ctrl+Shift+N"))
        create_menu.addAction(self._make_action("New Tire", self.open_tire_creator, shortcut="Ctrl+Alt+N"))
        create_menu.addAction(self._make_action("Fork Current Engine", self.fork_engine, shortcut="Ctrl+Shift+F"))

        tools_menu = menu_bar.addMenu("&Tools")
        tools_menu.addAction(self._make_action("Economy Editor", self.open_economy_editor, shortcut="Ctrl+E"))
        tools_menu.addAction(self._make_action("Bus Route Planner", self.open_bus_route_planner, shortcut="Ctrl+B"))
        tools_menu.addAction(self._make_action("Transmission Editor", self.open_transmission_editor, shortcut="Ctrl+T"))

        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction(self._make_action("Focus Search", lambda: self.search_edit.setFocus(), shortcut="Ctrl+F"))
        view_menu.addAction(self._make_action("Open Validation Inspector", lambda: self.inspector_tabs.setCurrentIndex(0)))
        view_menu.addAction(self._make_action("Open Audio Inspector", lambda: self.inspector_tabs.setCurrentIndex(1)))
        view_menu.addAction(self._make_action("Open Metadata Inspector", lambda: self.inspector_tabs.setCurrentIndex(2)))
        view_menu.addAction(self._make_action("Open Activity Inspector", lambda: self.inspector_tabs.setCurrentIndex(3)))

        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(self._make_action("Keyboard Shortcuts", self.show_shortcuts_help))

    def _configure_shortcuts(self) -> None:
        shortcuts = {
            "save_shortcut": ("Ctrl+S", self.save_current),
            "reload_shortcut": ("Ctrl+R", self.reload_workspace),
            "search_shortcut": ("Ctrl+F", lambda: self.search_edit.setFocus()),
            "quick_actions_shortcut": ("Ctrl+K", self.open_quick_actions),
            "new_engine_shortcut": ("Ctrl+Shift+N", self.open_engine_creator),
            "new_tire_shortcut": ("Ctrl+Alt+N", self.open_tire_creator),
            "pack_workspace_shortcut": ("Ctrl+P", self.pack_mod),
            "pack_templates_shortcut": ("Ctrl+Shift+P", self.pack_templates),
            "pack_current_shortcut": ("Ctrl+Alt+P", self.pack_current_part),
            "delete_shortcut": ("Delete", self.delete_current),
            "economy_shortcut": ("Ctrl+E", self.open_economy_editor),
            "bus_route_shortcut": ("Ctrl+B", self.open_bus_route_planner),
            "transmission_shortcut": ("Ctrl+T", self.open_transmission_editor),
        }
        for attr_name, (key, callback) in shortcuts.items():
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.activated.connect(callback)
            setattr(self, attr_name, shortcut)

    def show_shortcuts_help(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            APP_NAME,
            "\n".join(
                [
                    "Ctrl+F  Focus part search",
                    "Ctrl+K  Open quick actions",
                    "Ctrl+S  Save changes",
                    "Ctrl+R  Reload workspace",
                    "Ctrl+Shift+N  Create engine",
                    "Ctrl+Alt+N  Create tire",
                    "Ctrl+P  Pack workspace",
                    "Ctrl+Shift+P  Pack templates",
                    "Ctrl+Alt+P  Pack current part",
                    "Delete  Delete current generated part",
                    "Ctrl+E  Open Economy Editor",
                    "Ctrl+B  Open Bus Route Planner",
                ]
            ),
        )

    def open_quick_actions(self) -> None:
        dialog = QuickActionDialog(
            [
                {
                    "title": "Focus Search",
                    "shortcut": "Ctrl+F",
                    "description": "Move focus to the generated-parts search field.",
                    "keywords": "search filter find parts",
                    "callback": lambda: self.search_edit.setFocus(),
                },
                {
                    "title": "Reload Workspace",
                    "shortcut": "Ctrl+R",
                    "description": "Refresh generated parts and live state from disk.",
                    "keywords": "reload refresh workspace",
                    "callback": self.reload_workspace,
                },
                {
                    "title": "New Engine",
                    "shortcut": "Ctrl+Shift+N",
                    "description": "Start the guided engine creation flow.",
                    "keywords": "create engine new",
                    "callback": self.open_engine_creator,
                },
                {
                    "title": "New Tire",
                    "shortcut": "Ctrl+Alt+N",
                    "description": "Start the guided tire creation flow.",
                    "keywords": "create tire new",
                    "callback": self.open_tire_creator,
                },
                {
                    "title": "Save Changes",
                    "shortcut": "Ctrl+S",
                    "description": "Write the current editor changes to generated data.",
                    "keywords": "save write",
                    "callback": self.save_current,
                },
                {
                    "title": "Pack Current Part",
                    "shortcut": "Ctrl+Alt+P",
                    "description": "Package only the currently selected generated part.",
                    "keywords": "pack current package selected",
                    "callback": self.pack_current_part,
                },
                {
                    "title": "Pack Workspace",
                    "shortcut": "Ctrl+P",
                    "description": "Package the current generated mod workspace.",
                    "keywords": "pack workspace package mod",
                    "callback": self.pack_mod,
                },
                {
                    "title": "Pack Templates",
                    "shortcut": "Ctrl+Shift+P",
                    "description": "Package the curated engine templates.",
                    "keywords": "pack templates",
                    "callback": self.pack_templates,
                },
                {
                    "title": "Economy Editor",
                    "shortcut": "Ctrl+E",
                    "description": "Open the economy multiplier editor for cargo payments, bus/taxi rates.",
                    "keywords": "economy multiplier cargo bus taxi payment price money",
                    "callback": self.open_economy_editor,
                },
                {
                    "title": "Bus Route Planner",
                    "shortcut": "Ctrl+B",
                    "description": "Open the interactive bus route configurator with map and payout estimator.",
                    "keywords": "bus route map planner payout jeju stops",
                    "callback": self.open_bus_route_planner,
                },
                {
                    "title": "Open Activity Inspector",
                    "shortcut": "",
                    "description": "Review the recent session activity log.",
                    "keywords": "activity history audit",
                    "callback": lambda: self.inspector_tabs.setCurrentIndex(3),
                },
            ],
            self,
        )
        dialog.exec()

    def _show_pack_preview(self, preview: PackPreview) -> bool:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(APP_NAME)
        dialog.setModal(True)
        dialog.resize(560, 300)
        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.setSpacing(SPACING.md)

        header = make_section_header(
            f"Package {preview.selection_label}?",
            eyebrow="PACK PREVIEW",
            body="Review the output target before Frog Mod Editor writes the pak.",
            icon_name="package.svg",
            icon_color="#88bfd0",
        )
        root.addWidget(header)

        details = QtWidgets.QFrame()
        set_surface(details, "panel")
        details_layout = QtWidgets.QVBoxLayout(details)
        details_layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        details_layout.setSpacing(SPACING.sm)
        for label, value in (
            ("Output", preview.output_path),
            ("Items", str(preview.item_count)),
            ("Live state", preview.state_version or "unknown"),
        ):
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(SPACING.md)
            key_label = QtWidgets.QLabel(label)
            key_label.setMinimumWidth(80)
            set_label_kind(key_label, "fieldLabel")
            value_label = QtWidgets.QLabel(value)
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            set_label_kind(value_label, "muted")
            row.addWidget(key_label)
            row.addWidget(value_label, 1)
            details_layout.addLayout(row)
        root.addWidget(details)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = make_action_button("Cancel", role="secondary", chrome="headerAction")
        ok_button = make_action_button("Package", role="primary", icon=self.primary_icons["package"], chrome="headerAction")
        cancel_button.clicked.connect(dialog.reject)
        ok_button.clicked.connect(dialog.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(ok_button)
        root.addLayout(buttons)
        return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def run_task(
        self,
        status: str,
        func: Callable[[], Dict[str, Any]],
        on_done: Optional[Callable[[Optional[Dict[str, Any]], Optional[Exception]], None]] = None,
    ) -> None:
        if self._busy:
            QtWidgets.QMessageBox.information(self, APP_NAME, "Another task is already running.")
            return
        self._busy = True
        self.set_status(status)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        token = TaskSignals(self)
        self._task_tokens.append(token)

        def finish(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if QtWidgets.QApplication.overrideCursor() is not None:
                QtWidgets.QApplication.restoreOverrideCursor()
            self._busy = False
            self.set_status((result or {}).get("message") or ("Task failed" if error else "Ready"))
            try:
                if on_done:
                    on_done(result, error)
            finally:
                if token in self._task_tokens:
                    self._task_tokens.remove(token)

        token.finished.connect(finish)

        def worker() -> None:
            result: Optional[Dict[str, Any]] = None
            error: Optional[Exception] = None
            try:
                result = func()
            except Exception as exc:  # pragma: no cover
                error = exc
                log_exception("background task failed")
            token.finished.emit(result, error)

        threading.Thread(target=worker, daemon=True).start()

    def load_initial_state(self) -> None:
        bootstrap = self.service.bootstrap()
        self.live_state_version = bootstrap.get("state", {}).get("version", "")
        self.latest_live_state_version = self.live_state_version
        self.sound_options = list(bootstrap.get("sound_options") or [])
        self.parts_payload = bootstrap.get("parts") or {}
        self.workspace_summary = WorkspaceSummary.from_payload(self.parts_payload, state_version=self.live_state_version)
        self._update_workspace_stats()
        self.render_part_tree()
        self._record_activity("Workspace loaded from local runtime data.")
        self.set_status("Ready")
        self._refresh_command_context()
        self._update_inspector()
        if not self.smoke_test:
            self.live_timer.start(4000)

    def _update_workspace_stats(self) -> None:
        summary_model = self.workspace_summary
        engine_count = summary_model.engine_count
        tire_count = summary_model.tire_count
        total = summary_model.part_count
        summary = f"{total} generated parts loaded: {engine_count} engines, {tire_count} tires."
        self.sidebar_stats_label.setText(summary)
        self.welcome_stats_label.setText(summary + " Start with the sidebar, or create something new from the curated donor catalogs.")
        self.engine_count_badge.setText(f"Engines {engine_count}")
        self.tire_count_badge.setText(f"Tires {tire_count}")
        if hasattr(self, "empty_metrics"):
            self.empty_metrics["total"].setText(str(total))
            self.empty_metrics["engines"].setText(str(engine_count))
            self.empty_metrics["tires"].setText(str(tire_count))
            live_state = "Synced" if self.latest_live_state_version == self.live_state_version else "Refresh"
            self.empty_metrics["live"].setText(live_state)
        self._refresh_command_context()

    def _creator_mode_active(self) -> bool:
        return self.workspace_mode in {"create-engine", "create-tire", "fork-engine"}

    def _set_workspace_mode(self, mode: str) -> None:
        self.workspace_mode = mode
        if mode == "empty":
            self.stack.setCurrentIndex(0)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "edit":
            self.stack.setCurrentIndex(1)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "economy":
            self.stack.setCurrentIndex(3)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "bus-routes":
            self.stack.setCurrentIndex(4)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "transmission":
            self.stack.setCurrentIndex(5)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "policies":
            self.stack.setCurrentIndex(6)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        elif mode == "lua-scripts":
            self.stack.setCurrentIndex(7)
            self.sidebar_stack.setCurrentWidget(self.parts_sidebar)
        else:
            self.stack.setCurrentIndex(2)
            self.sidebar_stack.setCurrentWidget(self.creator_sidebar)
        self._refresh_command_context()

    def _refresh_command_context(self) -> None:
        if not hasattr(self, "command_context_label"):
            return
        if self.workspace_mode == "create-engine":
            title = "Engine creation flow"
            meta = "Choose a donor template, adjust the draft, then create a new generated engine."
        elif self.workspace_mode == "create-tire":
            title = "Tire creation flow"
            meta = "Choose a donor tire, tune the exposed fields, then create a new generated tire."
        elif self.workspace_mode == "fork-engine":
            title = "Fork engine draft"
            meta = "This workflow starts from the selected generated engine and writes a new generated asset."
        elif self.workspace_mode == "economy":
            title = "Economy Editor"
            meta = "Configure global economy multipliers for cargo payments, bus fares, and taxi rates."
        elif self.workspace_mode == "bus-routes":
            title = "Bus Route Planner"
            meta = "Plan bus routes on the Jeju Island map and estimate payouts with current economy settings."
        elif self.workspace_mode == "transmission":
            title = "Transmission Editor"
            meta = "Browse vanilla transmissions, modify shift time, and create upgraded variants."
        elif self.workspace_mode == "policies":
            title = "Policy Editor"
            meta = "Edit town policy costs and effect values, or add new policies."
        elif self.workspace_mode == "lua-scripts":
            title = "LUA Scripts"
            meta = "Configure and deploy runtime Lua mods (UE4SS). Check the mods you want, tune each card, then Deploy."
        elif self.current_document:
            title = self.current_document.display_name or self.current_document.name or "Selected document"
            type_label = "Engine" if self.current_document.is_engine else "Tire" if self.current_document.is_tire else "Part"
            suffix_bits = [type_label]
            if self.current_document.variant:
                suffix_bits.append(VARIANT_LABELS.get(self.current_document.variant, self.current_document.variant))
            elif self.current_document.group_label:
                suffix_bits.append(self.current_document.group_label)
            meta = "  •  ".join(bit for bit in suffix_bits if bit)
        else:
            title = "Generated parts workspace"
            meta = (
                f"{self.workspace_summary.part_count} parts ready"
                f"  •  {self.workspace_summary.engine_count} engines"
                f"  •  {self.workspace_summary.tire_count} tires"
            )
        self.command_context_label.setText(title)
        self.command_context_meta_label.setText(meta)

    def _set_content_mode(self, has_part: bool) -> None:
        if self._creator_mode_active():
            return
        self._set_workspace_mode("edit" if has_part else "empty")

    def _confirm_leave_creator_mode(self) -> bool:
        if not self._creator_mode_active() or not self.creator_workspace.has_changes():
            return True
        answer = QtWidgets.QMessageBox.question(
            self,
            APP_NAME,
            "Discard the current create draft and leave creator mode?",
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Yes

    def cancel_creator_mode(self) -> None:
        if not self._confirm_leave_creator_mode():
            return
        self.creator_workspace.clear_mode()
        self.creator_sidebar.clear_mode()
        if self.current_part:
            self._set_workspace_mode("edit")
            path = str(self.current_part.get("path") or "")
            item = self.path_to_item.get(path)
            if item:
                self.parts_tree.setCurrentIndex(item.index())
        else:
            self._set_workspace_mode("empty")
        self.set_status("Ready")

    def _selected_type_filter(self) -> str:
        if self.filter_engine_button.isChecked():
            return "Engines"
        if self.filter_tire_button.isChecked():
            return "Tires"
        return "All Parts"

    def _record_activity(self, text: str) -> None:
        timestamp = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.activity_history.insert(0, f"{timestamp}  {text}")
        self.activity_history = self.activity_history[:18]
        self._render_history()

    def _render_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        self.history_list.clear()
        if not self.activity_history:
            self.history_list.addItem("No session activity yet.")
            if hasattr(self, "activity_preview_label"):
                self.activity_preview_label.setText("No recent activity yet.")
            return
        for row in self.activity_history:
            self.history_list.addItem(row)
        if hasattr(self, "activity_preview_label"):
            self.activity_preview_label.setText("  •  ".join(recent_activity(self.activity_history, limit=3)))

    def _update_inspector(self) -> None:
        has_external_changes = bool(
            self.latest_live_state_version
            and self.live_state_version
            and self.latest_live_state_version != self.live_state_version
        )
        if not hasattr(self, "header_notice_label"):
            return
        if not self.current_part:
            if has_external_changes:
                self.header_notice_label.setText("External live data changed. Reload the workspace before making new edits.")
                set_label_kind(self.header_notice_label, "warning")
            else:
                self.header_notice_label.setText("Choose a generated part from the left rail or create one from a curated donor template.")
                set_label_kind(self.header_notice_label, "notice")
            if hasattr(self, "inspector_summary_label"):
                self.inspector_summary_label.setText("No document selected. Use the navigator to inspect a generated part or start a new asset flow.")
            if hasattr(self, "activity_state_label"):
                self.activity_state_label.setText("Waiting for a document selection.")
            refresh_style(self.header_notice_label)
            self.refresh_overview_panel()
            self.refresh_diagnostics()
            self.refresh_audio_panel()
            self.refresh_metadata_panel()
            return

        detail = self.current_part
        metadata = detail.get("metadata") or {}
        if detail.get("type") == "engine":
            state = self.editor_form.get_engine_state()
            warnings = build_engine_warnings(state)
            if warnings:
                summary = f"{len(warnings)} warning(s) need review. Open Diagnostics for the full breakdown."
                set_label_kind(self.header_notice_label, "warning")
            else:
                summary = "No risky engine values detected. Save when you are happy with the current tuning pass."
                set_label_kind(self.header_notice_label, "notice")
            missing_possible = metadata.get("missing_possible_properties") or []
            if missing_possible:
                summary += " Some known fields are intentionally absent on this engine layout."
        else:
            coverage = get_tire_field_coverage(detail)
            if coverage:
                summary = f"Tire field coverage: {coverage['property_count']} of {coverage['known_count']} known fields exposed on this donor layout."
            else:
                summary = "Coverage metadata was not available for this tire donor."
            set_label_kind(self.header_notice_label, "notice")
        if has_external_changes:
            summary = "Live data changed externally. Reload before continuing. " + summary
            set_label_kind(self.header_notice_label, "warning")
        self.header_notice_label.setText(summary)
        if hasattr(self, "inspector_summary_label"):
            self.inspector_summary_label.setText(summary)
        if hasattr(self, "activity_state_label"):
            self.activity_state_label.setText(
                "Live data changed externally." if has_external_changes else "Document state is synced with the latest loaded workspace."
            )
        refresh_style(self.header_notice_label)
        self.refresh_overview_panel()
        self.refresh_diagnostics()
        self.refresh_audio_panel()
        self.refresh_metadata_panel()

    def render_part_tree(self) -> None:
        selected_path = self.current_part.get("path") if self.current_part else ""
        self.parts_model.clear()
        self.path_to_item = {}
        query = self.search_edit.text().strip().lower()
        type_filter = self._selected_type_filter()
        groups = self.parts_payload.get("groups") or {}
        dirty_path = self.current_part.get("path") if self.current_part and self.editor_form.has_changes() else ""

        def make_parent(label: str, icon: QtGui.QIcon) -> QtGui.QStandardItem:
            item = QtGui.QStandardItem(label)
            item.setEditable(False)
            item.setSelectable(False)
            item.setIcon(icon)
            return item

        engine_rows = list(self.workspace_summary.groups.get("Engine", []))
        tire_rows = list(self.workspace_summary.groups.get("Tire", []))
        transmission_rows = list(self.workspace_summary.groups.get("Transmission", []))

        if type_filter in {"All Parts", "Engines"}:
            engines_parent = make_parent(f"Engines ({len(engine_rows)})", self.icons["engine"])
            for row in engine_rows:
                if query and query not in row.display_name.lower() and query not in row.name.lower():
                    continue
                text = row.display_name
                variant = row.variant
                if variant:
                    text = f"{text} [{VARIANT_LABELS.get(str(variant), variant)}]"
                path = row.path
                if path and path == dirty_path:
                    text = f"{text}  •  unsaved"
                child = QtGui.QStandardItem(text)
                child.setEditable(False)
                child.setIcon(self.icons["engine"])
                child.setData(path, PATH_ROLE)
                engines_parent.appendRow(child)
                if path:
                    self.path_to_item[path] = child
            self.parts_model.appendRow(engines_parent)

        if type_filter in {"All Parts", "Tires"}:
            tires_parent = make_parent(f"Tires ({len(tire_rows)})", self.icons["tire"])
            for row in tire_rows:
                if query and query not in row.display_name.lower() and query not in row.name.lower():
                    continue
                path = row.path
                text = row.display_name
                if path and path == dirty_path:
                    text = f"{text}  •  unsaved"
                child = QtGui.QStandardItem(text)
                child.setEditable(False)
                child.setIcon(self.icons["tire"])
                child.setData(path, PATH_ROLE)
                tires_parent.appendRow(child)
                if path:
                    self.path_to_item[path] = child
            self.parts_model.appendRow(tires_parent)

        if type_filter in {"All Parts", "Transmissions"}:
            trans_parent = make_parent(
                f"Transmissions ({len(transmission_rows)})",
                self.icons.get("parts", self.icons["engine"]),
            )
            for row in transmission_rows:
                if query and query not in row.display_name.lower() and query not in row.name.lower():
                    continue
                path = row.path
                text = row.display_name
                if path and path == dirty_path:
                    text = f"{text}  •  unsaved"
                child = QtGui.QStandardItem(text)
                child.setEditable(False)
                child.setIcon(self.icons.get("parts", self.icons["engine"]))
                child.setData(path, PATH_ROLE)
                trans_parent.appendRow(child)
                if path:
                    self.path_to_item[path] = child
            self.parts_model.appendRow(trans_parent)

        self.parts_tree.expandAll()
        if selected_path and selected_path in self.path_to_item:
            index = self.path_to_item[selected_path].index()
            self.parts_tree.setCurrentIndex(index)

    def _on_tree_clicked(self, index: QtCore.QModelIndex) -> None:
        if not index.isValid():
            return
        path = index.data(PATH_ROLE) or ""
        if path:
            self.select_part(str(path))

    def select_path_if_present(self, path: str) -> None:
        item = self.path_to_item.get(path)
        if not item:
            return
        index = item.index()
        self.parts_tree.setCurrentIndex(index)
        self.parts_tree.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        self.select_part(path)

    def select_part(self, path: str) -> None:
        detail = self.service.get_part_detail(path)
        if detail.get("error"):
            QtWidgets.QMessageBox.critical(self, APP_NAME, str(detail.get("error")))
            return
        self.current_part = detail
        self.current_document = AssetDocument.from_detail(detail)
        self.live_state_version = detail.get("state_version", self.live_state_version)
        self.latest_live_state_version = self.live_state_version
        self.editor_form.load_part(detail, self.sound_options)
        self._set_content_mode(True)
        self._update_part_header()
        self.tabs.setCurrentIndex(0)
        self._update_action_state()
        self.refresh_diagnostics()
        self.refresh_curve_panel()
        self.refresh_audio_panel()
        self._record_activity(f"Selected {detail.get('name') or 'part'} for editing.")
        self._update_inspector()

    def _on_creator_template_selected(self, row: Dict[str, Any]) -> None:
        if not self._creator_mode_active():
            return
        if not row:
            if self.workspace_mode == "create-engine":
                self.creator_workspace.begin_engine(self.sound_options, self.live_state_version)
            elif self.workspace_mode == "create-tire":
                self.creator_workspace.begin_tire(self.live_state_version)
            return
        if self.workspace_mode == "create-engine":
            template_name = str(row.get("name") or "").strip()
            if not template_name:
                return
            if template_name == self.creator_workspace.current_source_identifier():
                return
            detail = self.service.get_part_detail(f"template/Engine/{template_name}")
        else:
            part_path = str(row.get("path") or "").strip()
            if not part_path:
                return
            if part_path == self.creator_workspace.current_source_identifier():
                return
            detail = self.service.get_part_detail(part_path)
        if detail.get("error"):
            QtWidgets.QMessageBox.critical(self, APP_NAME, str(detail.get("error")))
            return
        self.creator_workspace.load_part(detail, row)

    def _clear_metrics(self) -> None:
        while self.metrics_layout.count():
            item = self.metrics_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _set_metrics(self, rows: Iterable[tuple[str, str]]) -> None:
        self._clear_metrics()
        for value, label in rows:
            self.metrics_layout.addWidget(MetricCard(value or "—", label))
        self.metrics_layout.addStretch(1)

    def _set_overview_metrics(self, rows: Iterable[tuple[str, str]]) -> None:
        while self.overview_metrics_layout.count():
            item = self.overview_metrics_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for value, label in rows:
            self.overview_metrics_layout.addWidget(MetricCard(value or "—", label))
        self.overview_metrics_layout.addStretch(1)

    def _update_part_header(self) -> None:
        detail = self.current_part or {}
        document = self.current_document
        metadata = detail.get("metadata") or {}
        shop = metadata.get("shop") or {}
        title = (document.display_name if document else "") or shop.get("display_name") or detail.get("name") or "Generated Part"
        self.part_title_label.setText(title)

        subtitle_bits = []
        if (document and document.is_engine) or detail.get("type") == "engine":
            subtitle_bits.append("Engine")
            variant = (document.variant if document else "") or metadata.get("variant")
            if variant:
                subtitle_bits.append(VARIANT_LABELS.get(str(variant), str(variant)))
        elif (document and document.is_tire) or detail.get("type") == "tire":
            subtitle_bits.append("Tire")
            subtitle_bits.append((document.group_label if document else "") or str(metadata.get("group_label") or metadata.get("family") or ""))
        self.part_subtitle_label.setText("  •  ".join(bit for bit in subtitle_bits if bit))
        self.part_hint_label.setText("Edits stay local until you save them into generated data.")

        if not detail:
            self._clear_metrics()
            return
        if detail.get("type") == "engine":
            state = self.editor_form.get_engine_state()
            warnings = build_engine_warnings(state)
            metrics = [
                (format_number(metadata.get("estimated_hp")), "Estimated HP"),
                (f"{format_number(state.get('maxTorqueNm'))} Nm", "Torque"),
                (f"{format_number(state.get('maxRPM'))} rpm", "Redline"),
                (str(len(warnings)), "Warnings"),
            ]
        else:
            grip = self.editor_form.get_tire_grip_g()
            coverage = get_tire_field_coverage(detail)
            shop_weight = (metadata.get("shop") or {}).get("weight")
            max_speed = get_edit_value("MaxSpeed", (detail.get("properties") or {}).get("MaxSpeed") or {}, "tire")
            metrics = [
                (f"{format_number(grip)} G", "Grip Estimate"),
                (f"{coverage['property_count']}/{coverage['known_count']}" if coverage else "", "Field Coverage"),
                (max_speed or "—", "Max Speed"),
                (f"{format_number(shop_weight)} kg", "Shop Weight"),
            ]
        self._set_metrics(metrics)

    def _update_action_state(self) -> None:
        creator_active = self._creator_mode_active()
        has_part = bool(self.current_part) and not creator_active
        has_changes = self.editor_form.has_changes() if has_part else False
        can_delete = bool(has_part and (self.current_part or {}).get("can_delete"))
        is_engine = bool(has_part and self.current_part and self.current_part.get("type") == "engine")
        self.save_button.setEnabled(has_part and has_changes)
        self.revert_button.setEnabled(has_part and has_changes)
        self.delete_button.setEnabled(can_delete)
        self.fork_button.setEnabled(is_engine)
        self.pack_current_button.setEnabled(has_part)
        self.audio_override_checkbox.setEnabled(is_engine)
        self.audio_apply_button.setEnabled(is_engine)
        self.audio_refresh_button.setEnabled(is_engine)
        if creator_active:
            self._set_workspace_mode(self.workspace_mode)
        else:
            self._set_content_mode(bool(self.current_part))
        if not self.current_part and not creator_active:
            self.current_document = None
            self.editor_form.clear()
            self.part_title_label.setText("")
            self.part_subtitle_label.setText("")
            self.part_hint_label.setText("")
            self._clear_metrics()
        self._refresh_command_context()
        self.render_part_tree()
        self._update_inspector()

    def _on_editor_change(self) -> None:
        self._update_action_state()
        if self.current_part:
            self._update_part_header()
        self._update_inspector()

    def refresh_overview_panel(self) -> None:
        if not self.current_part or not self.current_document:
            self.overview_title_label.setText("Choose a generated part")
            self.overview_body_label.setText("The overview summarises the selected part, its current risk status, and the next recommended actions.")
            self._set_overview_metrics([])
            populate_key_value_tree(self.overview_tree, [], empty_message="No document selected.")
            return

        detail = self.current_part
        document = self.current_document
        metadata = detail.get("metadata") or {}
        self.overview_title_label.setText(document.display_name or document.name)
        if document.is_engine:
            state = self.editor_form.get_engine_state()
            warnings = build_engine_warnings(state)
            self.overview_body_label.setText(
                "Engine editing stays local until saved. Review validation before packaging or publishing changes into generated data."
            )
            self._set_overview_metrics(
                [
                    (format_number(metadata.get("estimated_hp")), "Estimated HP"),
                    (f"{format_number(state.get('maxTorqueNm'))} Nm", "Torque"),
                    (f"{format_number(state.get('maxRPM'))} rpm", "Redline"),
                    (str(len(warnings)), "Warnings"),
                ]
            )
            overview_rows = [
                ("Source", document.source),
                ("Variant", VARIANT_LABELS.get(document.variant, document.variant or "—")),
                ("Display name", document.display_name or document.name),
                ("Description", document.description or "—"),
                ("Sound pack", self.editor_form.collect_sound_dir() or document.sound_dir or "—"),
                ("Live version", document.state_version or self.live_state_version or "—"),
            ]
        else:
            grip = self.editor_form.get_tire_grip_g()
            coverage = get_tire_field_coverage(detail)
            self.overview_body_label.setText(
                "Tire editing keeps donor-layout coverage visible so you can judge what is serialized before packaging."
            )
            self._set_overview_metrics(
                [
                    (f"{format_number(grip)} G", "Grip Estimate"),
                    (
                        f"{coverage['property_count']}/{coverage['known_count']}" if coverage else "—",
                        "Field Coverage",
                    ),
                    (document.group_label or "—", "Family"),
                    (format_number((metadata.get("shop") or {}).get("weight")), "Shop Weight"),
                ]
            )
            overview_rows = [
                ("Source", document.source),
                ("Family", document.group_label or "—"),
                ("Display name", document.display_name or document.name),
                ("Code", str((metadata.get("shop") or {}).get("code") or "—")),
                ("Live version", document.state_version or self.live_state_version or "—"),
            ]
        populate_key_value_tree(self.overview_tree, overview_rows)

    def refresh_diagnostics(self) -> None:
        self.validation_list.clear()
        self.validation_counts_label.setText("")
        if not self.current_part:
            self.validation_status_label.setText("Choose a generated part to inspect validation status.")
            set_label_kind(self.validation_status_label, "notice")
            refresh_style(self.validation_status_label)
            self.validation_list.addItem("Validation results will appear here.")
            return
        detail = self.current_part
        metadata = detail.get("metadata") or {}
        if detail.get("type") == "engine":
            state = self.editor_form.get_engine_state()
            warnings = build_engine_warnings(state)
            if warnings:
                danger_count = sum(1 for row in warnings if row.get("level") == "danger")
                warning_count = sum(1 for row in warnings if row.get("level") == "warning")
                notice_count = sum(1 for row in warnings if row.get("level") == "notice")
                summary = []
                if danger_count:
                    summary.append(f"{danger_count} danger")
                if warning_count:
                    summary.append(f"{warning_count} warning")
                if notice_count:
                    summary.append(f"{notice_count} notice")
                self.validation_status_label.setText("Validation review required before packaging or save handoff.")
                set_label_kind(self.validation_status_label, "warning" if not danger_count else "danger")
                self.validation_counts_label.setText(
                    "  •  ".join(summary)
                    + f"  •  {VARIANT_LABELS.get(str(metadata.get('variant') or ''), str(metadata.get('variant') or ''))}"
                )
                for row in warnings:
                    self.validation_list.addItem(f"[{str(row.get('level') or '').upper()}] {row.get('text') or ''}")
            else:
                self.validation_status_label.setText("Validation OK. No risky engine values detected.")
                set_label_kind(self.validation_status_label, "ok")
                self.validation_counts_label.setText(
                    f"Estimated HP {format_number(metadata.get('estimated_hp'))}  •  Max torque {format_number(state.get('maxTorqueNm'))} Nm  •  Redline {format_number(state.get('maxRPM'))} rpm"
                )
                self.validation_list.addItem("No risky values detected.")
            missing_possible = metadata.get("missing_possible_properties") or []
            if missing_possible:
                self.validation_list.addItem(
                    "Fields not serialized on this layout: "
                    + ", ".join(format_property_name(name) for name in missing_possible)
                )
        elif detail.get("type") == "tire":
            coverage = get_tire_field_coverage(detail)
            grip = self.editor_form.get_tire_grip_g()
            self.validation_status_label.setText("Coverage review for the current tire donor layout.")
            set_label_kind(self.validation_status_label, "warning" if coverage and coverage.get("missing_known") else "notice")
            if grip is not None:
                self.validation_counts_label.setText(f"Estimated grip {format_number(grip)} G")
            if coverage:
                self.validation_list.addItem(
                    f"Coverage: {coverage['property_count']} of {coverage['known_count']} known tire fields exposed"
                )
                if coverage["missing_known"]:
                    self.validation_list.addItem(
                        "Missing fields: " + ", ".join(format_property_name(name) for name in coverage["missing_known"])
                    )
                else:
                    self.validation_list.addItem("This donor already exposes the full known tire surface.")
            elif not self.validation_counts_label.text():
                self.validation_counts_label.setText("Coverage metadata was not available for this donor.")
        refresh_style(self.validation_status_label)

    def refresh_curve_panel(self) -> None:
        self.current_curve = None
        if not self.current_part:
            self.curve_card.show_empty("Torque-curve data will appear here when available.")
            return
        if self.current_part.get("curve_data"):
            self.current_curve = self.current_part
            note = "Showing curve data stored directly on this asset."
        elif self.current_part.get("type") == "engine":
            self.current_curve = self.service.get_referenced_curve(self.current_part)
            if self.current_curve:
                curve_name = ((self.current_part.get("asset_info") or {}).get("torque_curve_name") or "")
                note = f"Showing referenced torque curve: {curve_name}"
            else:
                note = "This engine references a torque curve asset, but that curve was not available in the runtime bundle."
        else:
            note = "Curve visualisation is only available for torque-curve-backed assets."
        points = ((self.current_curve or {}).get("curve_data") or {}).get("points") if self.current_curve else None
        self.curve_card.set_curve(points, note, eager=self.tabs.currentIndex() == 2)

    def refresh_audio_panel(self) -> None:
        if not self.current_part or self.current_part.get("type") != "engine":
            self.audio_summary_label.setText("Audio routing is available when an engine is selected.")
            populate_key_value_tree(self.audio_tree, [], empty_message="Select an engine to inspect audio routing.")
            self.audio_override_checkbox.blockSignals(True)
            self.audio_override_checkbox.setChecked(False)
            self.audio_override_checkbox.blockSignals(False)
            return
        engine_name = str(self.current_part.get("name") or "").strip()
        row = self.service.get_engine_audio_row(engine_name)
        metadata = self.current_part.get("metadata") or {}
        sound_meta = metadata.get("sound") or {}
        rows = [
            ("Current sound dir", self.editor_form.collect_sound_dir() or sound_meta.get("dir") or "—"),
            ("Sound cue", str(sound_meta.get("cue") or "—")),
            ("Valid reference", str(sound_meta.get("valid"))),
        ]
        self.audio_override_checkbox.blockSignals(True)
        if row:
            self.audio_override_checkbox.setChecked(bool(row.get("override_enabled")))
            self.audio_summary_label.setText("Review the resolved template audio before saving or packaging this engine.")
            rows.extend(
                [
                    ("Manifest status", str(row.get("status") or "—")),
                    ("Sound profile", str(row.get("sound_profile") or "—")),
                    ("Template sound asset", str(row.get("template_sound_asset") or "—")),
                    ("Vanilla sound asset", str(row.get("vanilla_sound_asset") or "—")),
                    ("Override sound asset", str(row.get("override_sound_asset") or "—")),
                    ("Override dir", str(row.get("override_sound_dir") or "—")),
                    ("Override enabled", "Yes" if row.get("override_enabled") else "No"),
                    ("Sample slots", str(row.get("sample_slots") or "—")),
                ]
            )
        else:
            self.audio_override_checkbox.setChecked(False)
            self.audio_summary_label.setText("No engine-audio manifest entry was found for this engine.")
        self.audio_override_checkbox.blockSignals(False)
        populate_key_value_tree(self.audio_tree, rows)

    def refresh_metadata_panel(self) -> None:
        if not self.current_part or not self.current_document:
            populate_key_value_tree(self.metadata_tree, [], empty_message="Choose a generated part to inspect metadata.")
            return
        rows = [
            ("name", self.current_document.name),
            ("path", self.current_document.path),
            ("type", self.current_document.part_type),
            ("source", self.current_document.source),
            ("live_state", self.current_document.state_version or self.live_state_version or "—"),
        ]
        rows.extend(flatten_metadata_rows(self.current_document.metadata))
        populate_key_value_tree(self.metadata_tree, rows)

    def _on_tab_changed(self, index: int) -> None:
        if index == 2:
            self.curve_card.activate()

    def apply_audio_override(self) -> None:
        if not self.current_part or self.current_part.get("type") != "engine":
            return
        engine_name = str(self.current_part.get("name") or "")
        sound_dir = self.editor_form.collect_sound_dir()

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Audio override failed."))
                return
            self.refresh_audio_panel()
            self._record_activity(f"Updated audio override for {engine_name}.")
            self._update_inspector()

        self.run_task(
            "Updating audio override...",
            lambda: self.service.set_engine_audio_override(engine_name, bool(self.audio_override_checkbox.isChecked()), sound_dir),
            on_done,
        )

    def reload_workspace(self) -> None:
        creator_active = self._creator_mode_active()
        if self.current_part and self.editor_form.has_changes() and not creator_active:
            result = QtWidgets.QMessageBox.question(
                self,
                APP_NAME,
                "Reload the latest live part data and discard unsaved edits?",
            )
            if result != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        selected_path = self.current_part.get("path") if self.current_part else ""
        bootstrap = self.service.bootstrap()
        self.parts_payload = bootstrap.get("parts") or {}
        self.workspace_summary = WorkspaceSummary.from_payload(self.parts_payload, state_version=self.live_state_version)
        self.sound_options = list(bootstrap.get("sound_options") or [])
        state_version = str((bootstrap.get("state") or {}).get("version") or "")
        if state_version:
            self.live_state_version = state_version
            self.latest_live_state_version = state_version
        self._update_workspace_stats()
        self.render_part_tree()
        self.set_live_banner("")
        if creator_active:
            self.creator_workspace.live_version = self.live_state_version
            self._set_workspace_mode(self.workspace_mode)
        elif selected_path and selected_path in self.path_to_item:
            self.select_path_if_present(selected_path)
        else:
            self.current_part = None
            self.current_document = None
            self._update_action_state()
            self._update_inspector()
        self._record_activity("Reloaded workspace from disk.")
        self.set_status("Ready")

    def save_current(self) -> None:
        if not self.current_part:
            return
        payload = self.editor_form.get_changed_payload()
        if not payload:
            self.set_status("No changes to save.")
            return
        # Pre-flight input validation. Same gate as the Engine Creator
        # uses — out-of-safe-range values are blocked, unusual values
        # prompt for confirmation. Only run when there's something to
        # validate (skipping for non-engine parts that have no bounds
        # is handled inside validation_summary).
        from .creator import _confirm_validation
        if not _confirm_validation(self, self.editor_form):
            return
        payload["expected_version"] = self.current_part.get("state_version", self.live_state_version)
        part_path = self.current_part.get("path", "")
        part_name = str(self.current_part.get("name") or "part")

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result:
                QtWidgets.QMessageBox.critical(self, APP_NAME, "Save returned no result.")
                return
            if result.get("error"):
                if result.get("conflict"):
                    conflict = self.service.build_conflict_state(result, "Live data changed externally.")
                    reload_now = QtWidgets.QMessageBox.question(
                        self,
                        APP_NAME,
                        f"{conflict.message}\n\nReload the latest workspace state now?",
                    )
                    if reload_now == QtWidgets.QMessageBox.StandardButton.Yes:
                        self.reload_workspace()
                    return
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(result.get("error")))
                return
            self.reload_workspace()
            self.select_path_if_present(part_path)
            self._record_activity(f"Saved {part_name} to generated data.")

        self.run_task("Saving part...", lambda: self.service.save_part(part_path, payload), on_done)

    def revert_current(self) -> None:
        if not self.current_part:
            return
        self.editor_form.load_part(self.current_part, self.sound_options)
        self._update_action_state()
        self.refresh_diagnostics()
        self.refresh_audio_panel()
        self._update_inspector()
        self.set_status("Reverted unsaved edits.")

    def delete_current(self) -> None:
        if not self.current_part or not self.current_part.get("can_delete"):
            return
        name = str(self.current_part.get("name") or "")
        result = QtWidgets.QMessageBox.question(
            self,
            APP_NAME,
            f"Delete {name}? This removes the generated asset and its shop entry.",
        )
        if result != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        expected_version = self.current_part.get("state_version", self.live_state_version)

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                if result and result.get("conflict"):
                    conflict = self.service.build_conflict_state(result, "Live data changed externally.")
                    QtWidgets.QMessageBox.warning(self, APP_NAME, conflict.message)
                    return
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Delete failed."))
                return
            self._record_activity(f"Deleted {name}.")
            self.current_part = None
            self.current_document = None
            self.reload_workspace()

        self.run_task("Deleting part...", lambda: self.service.delete_part(self.current_part.get("path", ""), expected_version), on_done)

    def on_part_created(self, path: str) -> None:
        if path:
            self._record_activity(f"Created {Path(path).stem} from template data.")
        self.creator_workspace.clear_mode()
        self.creator_sidebar.clear_mode()
        self.current_part = None
        self._set_workspace_mode("edit" if path else "empty")
        self.reload_workspace()
        if path:
            self.select_path_if_present(path)

    # Default vanilla donor for "New Engine" — fills the form with sane
    # starting values so the user can tweak instead of starting blank.
    # Matches the first non-empty entry in VEHICLE_TYPE_CHOICES so the
    # combo and the loaded data agree out of the gate.
    _DEFAULT_NEW_ENGINE_DONOR = "HeavyDuty_440HP"

    def open_engine_creator(self) -> None:
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._creator_return_path = str((self.current_part or {}).get("path") or "")

        # Pre-load a default vanilla engine so the user drops straight
        # into the editable form instead of an empty template picker.
        # The legacy templates folder is empty since v6.x; vanilla
        # engines are the new starting point.
        donor_path = f"vanilla/Engine/{self._DEFAULT_NEW_ENGINE_DONOR}"
        donor_detail = self.service.get_part_detail(donor_path)
        if donor_detail.get("error"):
            QtWidgets.QMessageBox.critical(
                self, APP_NAME,
                f"Could not load default donor engine "
                f"'{self._DEFAULT_NEW_ENGINE_DONOR}': {donor_detail.get('error')}"
            )
            return

        self.creator_workspace.begin_engine(
            self.sound_options, self.live_state_version,
            initial_donor={"name": self._DEFAULT_NEW_ENGINE_DONOR, "detail": donor_detail},
        )
        self._set_workspace_mode("create-engine")
        # Sidebar intentionally NOT populated with the (empty) template
        # catalog — the form is the entire workflow now.
        self.creator_sidebar.clear_mode()
        self._record_activity("Opened in-window engine creator.")

    def fork_engine(self) -> None:
        if not self.current_part or self.current_part.get("type") != "engine":
            QtWidgets.QMessageBox.information(self, APP_NAME, "Select an existing generated engine to fork.")
            return
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        fixed_template = {"name": self.current_part.get("name", ""), "detail": self.current_part}
        self._creator_return_path = str((self.current_part or {}).get("path") or "")
        self.creator_sidebar.show_fork_source(self.current_part)
        self.creator_workspace.begin_engine(self.sound_options, self.live_state_version, fixed_template=fixed_template)
        self._set_workspace_mode("fork-engine")
        self._record_activity(f"Forking {self.current_part.get('name') or 'engine'} in the main workspace.")

    def open_tire_creator(self) -> None:
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        catalog = self.service.get_tire_templates()
        self._creator_return_path = str((self.current_part or {}).get("path") or "")
        self.creator_workspace.begin_tire(self.live_state_version)
        self._set_workspace_mode("create-tire")
        self.creator_sidebar.show_tire_catalog(catalog)
        self._record_activity("Opened in-window tire creator.")

    def open_economy_editor(self) -> None:
        """Switch to the Economy Editor panel."""
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._set_workspace_mode("economy")
        self._record_activity("Opened Economy Editor.")

    def open_bus_route_planner(self) -> None:
        """Switch to the Bus Route Planner panel."""
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._set_workspace_mode("bus-routes")
        self._record_activity("Opened Bus Route Planner.")

    def open_policy_editor(self) -> None:
        """Switch to the Policy Editor panel."""
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._set_workspace_mode("policies")
        self._record_activity("Opened Policy Editor.")

    def open_transmission_editor(self) -> None:
        """Switch to the Transmission Editor panel."""
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._set_workspace_mode("transmission")
        self._record_activity("Opened Transmission Editor.")

    def open_lua_scripts_editor(self) -> None:
        """Switch to the LUA Scripts panel."""
        if self._creator_mode_active() and not self._confirm_leave_creator_mode():
            return
        self._set_workspace_mode("lua-scripts")
        self._record_activity("Opened LUA Scripts panel.")

    def _on_transmission_created(self, result: dict) -> None:
        """Handle transmission created signal."""
        name = result.get('name', '?')
        shift = result.get('shift_time', 0)
        self._record_activity(f"Created transmission '{name}' with shift time {shift:.2f}s.")
        self.set_status(f"Transmission '{name}' created and staged for packing.")
        # Refresh the workspace so the new transmission appears in the
        # Generated Parts sidebar immediately, like engines and tires do.
        try:
            self.reload_workspace()
        except Exception:
            pass

    def _on_policy_applied(self, result: dict) -> None:
        """Handle policy settings applied signal."""
        modified = result.get('modified', 0)
        added = result.get('added', 0)
        total = result.get('total_rows', 0)
        self._record_activity(
            f"Policy changes applied: {modified} modified, {added} added ({total} total)."
        )
        self.set_status("Policy changes applied and staged for packing.")

    def _on_economy_applied(self, result: dict) -> None:
        """Handle economy settings applied signal."""
        mults = result.get('multipliers', {})
        self._record_activity(
            f"Economy settings applied: ×{mults.get('economy', 1):.0f} cargo, "
            f"×{mults.get('bus', 1):.0f} bus, ×{mults.get('taxi', 1):.0f} taxi"
        )
        self.set_status("Economy settings applied and staged for packing.")

    def _choose_save_path(self, title: str, initial_path: str) -> str:
        output_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            title,
            initial_path,
            "PAK Files (*.pak)",
        )
        return output_path or ""

    def pack_mod(self) -> None:
        initial_path = os.path.join(self.service.default_paks_dir, self.service.default_mod_pak_name)
        output_path = self._choose_save_path("Pack Mod", initial_path)
        if not output_path:
            return
        preview = self.service.build_pack_preview("workspace", output_path, "the generated workspace", self.workspace_summary.part_count)
        if not self._show_pack_preview(preview):
            return

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Pack failed."))
                return
            self._record_activity(f"Packed mod output to {Path(output_path).name}.")
            QtWidgets.QMessageBox.information(self, APP_NAME, result.get("message") or "Packed mod.")

        self.run_task("Packing mod...", lambda: self.service.pack_mod(output_path), on_done)

    def pack_current_part(self) -> None:
        if not self.current_part or not self.current_document:
            QtWidgets.QMessageBox.information(self, APP_NAME, "Choose a generated engine or tire first.")
            return
        suggested_name = f"{self.current_document.name or 'part'}_P.pak"
        initial_path = os.path.join(self.service.default_paks_dir, suggested_name)
        output_path = self._choose_save_path("Pack Current Part", initial_path)
        if not output_path:
            return
        preview = self.service.build_pack_preview("current", output_path, self.current_document.display_name or self.current_document.name, 1)
        if not self._show_pack_preview(preview):
            return

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Pack failed."))
                return
            self._record_activity(f"Packed current part to {Path(output_path).name}.")
            QtWidgets.QMessageBox.information(self, APP_NAME, result.get("message") or "Packed current part.")

        self.run_task(
            "Packing current part...",
            lambda: self.service.pack_mod(output_path, [self.current_part.get("path", "")]),
            on_done,
        )

    def pack_templates(self) -> None:
        initial_path = os.path.join(self.service.default_paks_dir, self.service.default_template_pak_name)
        output_path = self._choose_save_path("Pack Engine Templates", initial_path)
        if not output_path:
            return
        engine_catalog = self.service.get_engine_template_catalog_view()
        template_count = len({str(item.get("name") or "") for item in engine_catalog.items if item.get("name")})
        preview = self.service.build_pack_preview("templates", output_path, "the curated engine templates", template_count)
        if not self._show_pack_preview(preview):
            return

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Pack templates failed."))
                return
            self._record_activity(f"Packed template output to {Path(output_path).name}.")
            QtWidgets.QMessageBox.information(self, APP_NAME, result.get("message") or "Packed templates.")

        self.run_task("Packing templates...", lambda: self.service.pack_templates(output_path), on_done)

    def poll_live_state(self) -> None:
        try:
            state = self.service.get_live_state()
            version = str(state.get("version") or "")
            if version:
                self.latest_live_state_version = version
            if version and self.live_state_version and version != self.live_state_version:
                if self.current_part and self.editor_form.has_changes():
                    self.set_live_banner("Someone else updated the live part data. Reload before continuing.")
                else:
                    self.set_live_banner("New live part updates are available. Reload when ready.")
                self._update_workspace_stats()
                self._update_inspector()
            elif version == self.live_state_version:
                self.set_live_banner("")
                self._update_workspace_stats()
                self._update_inspector()
        except Exception:
            log_exception("live poll failed")


def center_window(window: QtWidgets.QWidget) -> None:
    screen = QtGui.QGuiApplication.primaryScreen()
    if not screen:
        return
    available = screen.availableGeometry()
    frame = window.frameGeometry()
    frame.moveCenter(available.center())
    window.move(frame.topLeft())
