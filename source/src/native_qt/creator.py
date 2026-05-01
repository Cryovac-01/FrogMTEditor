"""Creator-side catalog and workspace panels."""
from __future__ import annotations

from .theme import *
from .widgets import TemplateListDelegate
from .forms import PartEditorForm

class CreatorCatalogSidebar(QtWidgets.QFrame):
    template_selected = QtCore.Signal(dict)

    ENGINE_SORT_OPTIONS = {
        "Horsepower": lambda item: (-(item.get("hp") or 0), str(item.get("title") or item.get("name") or "").lower()),
        "Name": lambda item: str(item.get("title") or item.get("name") or "").lower(),
        "Torque": lambda item: (-(item.get("torque") or 0), str(item.get("title") or item.get("name") or "").lower()),
        "RPM": lambda item: (-(item.get("rpm") or 0), str(item.get("title") or item.get("name") or "").lower()),
        "Fuel": lambda item: (str(item.get("fuel") or ""), str(item.get("title") or item.get("name") or "").lower()),
    }

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        set_surface(self, "sidebar")
        self.mode = ""
        self.template_rows: List[Dict[str, Any]] = []
        self.filtered_rows: List[Dict[str, Any]] = []
        self.fixed_detail: Optional[Dict[str, Any]] = None
        self._refreshing_catalog = False
        self._selected_identifier = ""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)

        self.title_label = QtWidgets.QLabel("Create")
        set_label_kind(self.title_label, "section")
        layout.addWidget(self.title_label)

        self.subtitle_label = QtWidgets.QLabel("")
        self.subtitle_label.setWordWrap(True)
        set_label_kind(self.subtitle_label, "muted")
        layout.addWidget(self.subtitle_label)

        self.search_edit = QtWidgets.QLineEdit()
        configure_field_control(self.search_edit, "search")
        self.search_edit.addAction(load_icon("search.svg"), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        layout.addWidget(self.search_edit)

        self.group_combo = QtWidgets.QComboBox()
        configure_field_control(self.group_combo, "filter")
        layout.addWidget(self.group_combo)

        self.sort_combo = QtWidgets.QComboBox()
        configure_field_control(self.sort_combo, "filter")
        self.sort_combo.addItems(list(self.ENGINE_SORT_OPTIONS.keys()))
        layout.addWidget(self.sort_combo)

        self.summary_card = QtWidgets.QFrame()
        set_surface(self.summary_card, "panel")
        self.summary_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        summary_layout = QtWidgets.QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        summary_layout.setSpacing(SPACING.sm)
        self.summary_kicker = QtWidgets.QLabel("")
        set_label_kind(self.summary_kicker, "eyebrow")
        self.summary_name = QtWidgets.QLabel("")
        self.summary_name.setWordWrap(True)
        set_label_kind(self.summary_name, "section")
        self.summary_meta = QtWidgets.QLabel("")
        self.summary_meta.setWordWrap(True)
        set_label_kind(self.summary_meta, "muted")
        self.summary_stats = QtWidgets.QLabel("")
        self.summary_stats.setWordWrap(True)
        set_label_kind(self.summary_stats, "subtle")
        self.summary_note = QtWidgets.QLabel("")
        self.summary_note.setWordWrap(True)
        set_label_kind(self.summary_note, "muted")
        summary_layout.addWidget(self.summary_kicker)
        summary_layout.addWidget(self.summary_name)
        summary_layout.addWidget(self.summary_meta)
        summary_layout.addWidget(self.summary_stats)
        summary_layout.addWidget(self.summary_note)
        summary_layout.addStretch(1)
        layout.addWidget(self.summary_card)

        self.list_model = QtGui.QStandardItemModel(self)
        self.list_view = QtWidgets.QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.list_view.setMouseTracking(True)
        self.list_view.setUniformItemSizes(False)
        self.list_view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_view, 1)

        self.search_edit.textChanged.connect(self.refresh_catalog)
        self.group_combo.currentTextChanged.connect(self.refresh_catalog)
        self.sort_combo.currentTextChanged.connect(self.refresh_catalog)
        self.list_view.selectionModel().selectionChanged.connect(lambda *_: self._emit_current_selection())

        self.clear_mode()

    def clear_mode(self) -> None:
        self.mode = ""
        self.template_rows = []
        self.filtered_rows = []
        self.fixed_detail = None
        self._refreshing_catalog = False
        self._selected_identifier = ""
        self.title_label.setText("Create")
        self.subtitle_label.setText("Choose a flow from the workspace to start.")
        self.search_edit.hide()
        self.group_combo.hide()
        self.sort_combo.hide()
        self.summary_card.hide()
        self.summary_card.setMinimumHeight(0)
        self.summary_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        self.summary_stats.clear()
        self.summary_note.clear()
        self.list_view.hide()
        self.list_model.clear()

    def show_engine_catalog(self, catalog: Dict[str, Any]) -> None:
        self.mode = "engine"
        self.fixed_detail = None
        self.template_rows = list(catalog.get("items") or [])
        self._selected_identifier = ""
        self.title_label.setText("Template Catalog")
        self.subtitle_label.setText("Choose a donor engine template for the new part.")
        self.search_edit.setPlaceholderText("Search engines")
        self.search_edit.show()
        self.group_combo.show()
        self.sort_combo.show()
        self.summary_card.hide()
        self.summary_card.setMinimumHeight(0)
        self.summary_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        self.list_view.show()
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("All Variants")
        for row in catalog.get("groups", []):
            self.group_combo.addItem(str(row.get("label") or row.get("key") or ""))
        self.group_combo.blockSignals(False)
        self.sort_combo.blockSignals(True)
        self.sort_combo.setCurrentText("Horsepower")
        self.sort_combo.blockSignals(False)
        self.list_view.setItemDelegate(TemplateListDelegate("engine", self.list_view))
        self.refresh_catalog()

    def show_tire_catalog(self, catalog: Dict[str, Any]) -> None:
        self.mode = "tire"
        self.fixed_detail = None
        self.template_rows = list(catalog.get("items") or [])
        self._selected_identifier = ""
        self.title_label.setText("Donor Tire Catalog")
        self.subtitle_label.setText("Choose a donor tire family and template.")
        self.search_edit.setPlaceholderText("Search tires")
        self.search_edit.show()
        self.group_combo.show()
        self.sort_combo.hide()
        self.summary_card.hide()
        self.summary_card.setMinimumHeight(0)
        self.summary_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Maximum)
        self.list_view.show()
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("All Families")
        for row in catalog.get("groups", []):
            self.group_combo.addItem(str(row.get("label") or row.get("key") or ""))
        self.group_combo.blockSignals(False)
        self.list_view.setItemDelegate(TemplateListDelegate("tire", self.list_view))
        self.refresh_catalog()

    def show_fork_source(self, detail: Dict[str, Any]) -> None:
        self.mode = "fork-engine"
        self.fixed_detail = dict(detail or {})
        self.template_rows = []
        self.filtered_rows = []
        self._selected_identifier = ""
        self.list_model.clear()
        self.title_label.setText("Fork Source")
        self.subtitle_label.setText("Create a new engine from the current generated part.")
        self.search_edit.hide()
        self.group_combo.hide()
        self.sort_combo.hide()
        self.list_view.hide()
        metadata = self.fixed_detail.get("metadata") or {}
        shop = metadata.get("shop") or {}
        stats: List[str] = []
        if metadata.get("estimated_hp") not in (None, ""):
            stats.append(f"{format_compact_metric(metadata.get('estimated_hp'))} HP")
        if metadata.get("max_torque_nm") not in (None, ""):
            stats.append(f"{format_compact_metric(metadata.get('max_torque_nm'))} Nm")
        if metadata.get("max_rpm") not in (None, ""):
            stats.append(f"{format_compact_metric(metadata.get('max_rpm'))} rpm")
        self.summary_kicker.setText("CURRENT GENERATED ENGINE")
        self.summary_name.setText(str(shop.get("display_name") or self.fixed_detail.get("name") or ""))
        meta_bits = [
            str(shop.get("description") or "").strip(),
            VARIANT_LABELS.get(str(metadata.get("variant") or ""), str(metadata.get("variant") or "").replace("_", " ").title()),
        ]
        self.summary_meta.setText("  •  ".join(bit for bit in meta_bits if bit))
        self.summary_stats.setText("  •  ".join(stats))
        self.summary_note.setText("Forking creates a new generated engine from the current part so you can branch tuning without overwriting the original.")
        self.summary_card.setMinimumHeight(232)
        self.summary_card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.summary_card.show()

    def current_identifier(self) -> str:
        index = self.list_view.currentIndex()
        if not index.isValid():
            return ""
        row = index.data(ROW_ROLE) or {}
        if self.mode == "engine":
            return str(row.get("name") or "")
        if self.mode == "tire":
            return str(row.get("path") or "")
        return ""

    @staticmethod
    def _dedupe_all_engine_variant_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Collapse aggregate/cylinder duplicates for the unfiltered engine catalog."""
        deduped: List[Dict[str, Any]] = []
        index_by_name: Dict[str, int] = {}

        def is_gas_aggregate(row: Dict[str, Any]) -> bool:
            return str(row.get("group_key") or "") == "gas"

        def merge_with_gas_label(base: Dict[str, Any], gas_row: Dict[str, Any]) -> Dict[str, Any]:
            merged = dict(base)
            merged["group_key"] = gas_row.get("group_key", "gas")
            merged["group_label"] = gas_row.get("group_label", "Gas")
            return merged

        for row in rows:
            name = str(row.get("name") or "").strip()
            if not name:
                deduped.append(row)
                continue
            existing_index = index_by_name.get(name)
            if existing_index is None:
                index_by_name[name] = len(deduped)
                deduped.append(row)
                continue
            existing = deduped[existing_index]
            if is_gas_aggregate(row) and not is_gas_aggregate(existing):
                deduped[existing_index] = merge_with_gas_label(existing, row)
            elif is_gas_aggregate(existing) and not is_gas_aggregate(row):
                deduped[existing_index] = merge_with_gas_label(row, existing)
        return deduped

    def refresh_catalog(self) -> None:
        if self.mode not in {"engine", "tire"}:
            return
        query = self.search_edit.text().strip().lower()
        group_label = self.group_combo.currentText().strip()
        rows = list(self.template_rows)
        current_identifier = self._selected_identifier or self.current_identifier()
        if self.mode == "engine":
            if group_label and group_label != "All Variants":
                rows = [row for row in rows if row.get("group_label") == group_label]
            if query:
                rows = [
                    row for row in rows
                    if query in str(row.get("name") or "").lower()
                    or query in str(row.get("title") or "").lower()
                    or query in str(row.get("description") or "").lower()
                ]
            rows.sort(key=self.ENGINE_SORT_OPTIONS.get(self.sort_combo.currentText(), self.ENGINE_SORT_OPTIONS["Horsepower"]))
            if group_label == "All Variants":
                rows = self._dedupe_all_engine_variant_rows(rows)
        else:
            if group_label and group_label != "All Families":
                rows = [row for row in rows if row.get("group_label") == group_label]
            if query:
                rows = [
                    row for row in rows
                    if query in str(row.get("name") or "").lower()
                    or query in str(row.get("title") or "").lower()
                    or query in str(row.get("code") or "").lower()
                ]
            rows.sort(key=lambda item: (str(item.get("group_label") or "").lower(), str(item.get("title") or item.get("name") or "").lower()))

        self.filtered_rows = rows
        selection_model = self.list_view.selectionModel()
        selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
        self._refreshing_catalog = True
        try:
            self.list_model.clear()
            match_index: Optional[QtCore.QModelIndex] = None
            for row in rows:
                row_data = enrich_engine_template_row(row) if self.mode == "engine" else enrich_tire_template_row(row)
                item = QtGui.QStandardItem(str(row_data.get("title") or row_data.get("name") or "Template"))
                item.setEditable(False)
                item.setData(row_data, ROW_ROLE)
                self.list_model.appendRow(item)
                identifier = str(row_data.get("name") or "") if self.mode == "engine" else str(row_data.get("path") or "")
                if current_identifier and identifier == current_identifier:
                    match_index = item.index()
            if self.list_model.rowCount():
                index = match_index or self.list_model.index(0, 0)
                self.list_view.setCurrentIndex(index)
            else:
                self._selected_identifier = ""
        finally:
            self._refreshing_catalog = False
            if selection_blocker is not None:
                del selection_blocker
        if self.list_model.rowCount():
            self._emit_current_selection()
        elif current_identifier:
            self.template_selected.emit({})

    def _emit_current_selection(self) -> None:
        if self.mode not in {"engine", "tire"} or self._refreshing_catalog:
            return
        index = self.list_view.currentIndex()
        row = index.data(ROW_ROLE) or {} if index.isValid() else {}
        identifier = str(row.get("name") or "") if self.mode == "engine" else str(row.get("path") or "")
        if not row:
            if self._selected_identifier:
                self._selected_identifier = ""
                self.template_selected.emit({})
            return
        if identifier == self._selected_identifier:
            return
        self._selected_identifier = identifier
        self.template_selected.emit(row)

class CreatorWorkspace(QtWidgets.QWidget):
    cancel_requested = QtCore.Signal()
    created = QtCore.Signal(str)
    changed = QtCore.Signal()

    def __init__(self, app: "NativeQtEditorWindow", service: NativeEditorService, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app
        self.service = service
        self.mode = ""
        self.live_version = ""
        self.current_detail: Optional[Dict[str, Any]] = None
        self.current_row: Optional[Dict[str, Any]] = None
        self.fixed_template: Optional[Dict[str, Any]] = None
        self.sound_options: List[Dict[str, str]] = []
        self.part_type = ""
        self.original_name = ""
        self.form: Optional[PartEditorForm] = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACING.md)

        self.header_frame = QtWidgets.QFrame()
        set_surface(self.header_frame, "creatorHeader")
        header = QtWidgets.QVBoxLayout(self.header_frame)
        header.setContentsMargins(SPACING.lg, SPACING.sm, SPACING.lg, SPACING.sm)
        header.setSpacing(SPACING.xxs)
        self.eyebrow_label = QtWidgets.QLabel("CREATE")
        set_label_kind(self.eyebrow_label, "eyebrow")
        self.title_label = QtWidgets.QLabel("Create")
        set_label_kind(self.title_label, "dialogTitle")
        header.addWidget(self.eyebrow_label)
        header.addWidget(self.title_label)
        summary_row = QtWidgets.QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.setSpacing(SPACING.sm)
        self.badge_label = QtWidgets.QLabel("")
        self.badge_label.hide()
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setWordWrap(True)
        set_label_kind(self.summary_label, "appSubtitle")
        summary_row.addWidget(self.badge_label, 0, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        summary_row.addWidget(self.summary_label, 1)
        header.addLayout(summary_row)
        root.addWidget(self.header_frame)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        self.scroll_content = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)

        self.body_shell = QtWidgets.QFrame()
        set_surface(self.body_shell, "panel")
        self.body_shell_layout = QtWidgets.QVBoxLayout(self.body_shell)
        self.body_shell_layout.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)
        self.body_shell_layout.setSpacing(SPACING.md)
        self.scroll_layout.addWidget(self.body_shell)

        self.name_group, name_layout = build_creator_card("New Asset")
        name_label = QtWidgets.QLabel("Internal Name")
        set_label_kind(name_label, "fieldLabel")
        self.name_edit = QtWidgets.QLineEdit()
        configure_field_control(self.name_edit, "editor")
        name_layout.addWidget(build_creator_row(name_label, self.name_edit))
        self.body_shell_layout.addWidget(self.name_group)

        self.form_holder = QtWidgets.QWidget()
        self.form_holder_layout = QtWidgets.QVBoxLayout(self.form_holder)
        self.form_holder_layout.setContentsMargins(0, 0, 0, 0)
        self.form_holder_layout.setSpacing(0)
        self.body_shell_layout.addWidget(self.form_holder)

        self.status_strip = QtWidgets.QFrame()
        set_surface(self.status_strip, "statusStrip")
        status_layout = QtWidgets.QHBoxLayout(self.status_strip)
        status_layout.setContentsMargins(SPACING.md, SPACING.xs, SPACING.md, SPACING.xs)
        status_layout.setSpacing(SPACING.sm)
        self.status_label = QtWidgets.QLabel("Choose a template or donor to begin.")
        set_label_kind(self.status_label, "notice")
        status_layout.addWidget(self.status_label, 1)
        self.details_toggle = QtWidgets.QPushButton("Show Details")
        set_button_role(self.details_toggle, "subtle", icon_size=14)
        set_button_chrome(self.details_toggle, "detailsToggle", height=DETAILS_BUTTON_HEIGHT, icon_size=TOPBAR_BUTTON_ICON_SIZE)
        self.details_toggle.hide()
        status_layout.addWidget(self.details_toggle)
        root.addWidget(self.status_strip)

        self.details_text = QtWidgets.QPlainTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(110)
        self.details_text.hide()
        root.addWidget(self.details_text)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(SPACING.sm)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addStretch(1)
        self.recommend_button = make_action_button("Recommend Price", role="subtle", icon=load_icon("curve.svg"), chrome="creatorFooter", height=CREATOR_BUTTON_HEIGHT)
        self.cancel_button = make_action_button("Cancel", role="secondary", chrome="creatorFooter", height=CREATOR_BUTTON_HEIGHT)
        self.create_button = make_action_button("Create", role="primary", chrome="creatorFooterPrimary", height=CREATOR_BUTTON_HEIGHT, icon_size=PRIMARY_BUTTON_ICON_SIZE)
        buttons.addWidget(self.recommend_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.create_button)
        root.addLayout(buttons)

        self.name_edit.textChanged.connect(lambda *_: self.changed.emit())
        self.name_edit.textChanged.connect(lambda *_: self._refresh_status())
        self.details_toggle.clicked.connect(self._toggle_details)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.recommend_button.clicked.connect(self.recommend_price)
        self.create_button.clicked.connect(self.submit)
        self.clear_mode()

    def _install_form(self, *, hidden_properties: Iterable[str] = (), section_title_overrides: Optional[Dict[str, str]] = None) -> None:
        while self.form_holder_layout.count():
            item = self.form_holder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.form = PartEditorForm(
            creator_mode=True,
            hidden_properties=hidden_properties,
            section_title_overrides=section_title_overrides,
        )
        self.form.changed.connect(self.changed.emit)
        self.form.changed.connect(self._refresh_status)
        # When the user picks a Fuel Type that needs a different binary
        # donor (Gas/Diesel <-> Electric), the form asks us to swap
        # donors. We confirm with the user if there are unsaved property
        # edits, then refetch + reload.
        self.form.donor_change_requested.connect(self._handle_donor_change_request)
        self.form_holder_layout.addWidget(self.form)

    def clear_mode(self) -> None:
        self.mode = ""
        self.live_version = ""
        self.current_detail = None
        self.current_row = None
        self.fixed_template = None
        self.sound_options = []
        self.part_type = ""
        self.original_name = ""
        self.name_edit.blockSignals(True)
        self.name_edit.clear()
        self.name_edit.setPlaceholderText("")
        self.name_edit.blockSignals(False)
        self.eyebrow_label.setText("CREATE")
        self.title_label.setText("Create")
        self.badge_label.hide()
        self.summary_label.setText("Choose a flow from the left rail to begin.")
        self.recommend_button.hide()
        self.create_button.setText("Create")
        self.create_button.setIcon(QtGui.QIcon())
        self.create_button.setEnabled(False)
        self.details_text.hide()
        self.details_toggle.hide()
        if self.form is None:
            self._install_form()
        if self.form:
            self.form.clear()
        self._set_status("Choose a template or donor to begin.", "notice")

    # Engine-creator fields the user shouldn't touch directly. They're
    # either set automatically from other inputs (FuelType -> derived
    # from the Fuel Type combo) or kept at the donor's template default
    # to avoid users accidentally producing broken engines (Thermal and
    # Effects, EngineType enum).
    _ALWAYS_HIDDEN_ENGINE_FIELDS = (
        "FuelType",
        "HeatingPower",
        "AfterFireProbability",
        "EngineType",
    )

    def begin_engine(self, sound_options: List[Dict[str, str]], live_version: str,
                     fixed_template: Optional[Dict[str, Any]] = None,
                     initial_donor: Optional[Dict[str, Any]] = None) -> None:
        # `fixed_template`  → forking an existing user-generated engine.
        # `initial_donor`   → fresh "Create New" with a default vanilla
        #                     engine pre-loaded so the form starts
        #                     populated (mode stays "create-engine").
        # Neither           → legacy empty-form behaviour (kept as a
        #                     fallback if some caller passes nothing).
        self.mode = "fork-engine" if fixed_template else "create-engine"
        self.live_version = live_version
        self.sound_options = list(sound_options or [])
        self.fixed_template = fixed_template
        self.part_type = "engine"
        self.current_row = None
        self.current_detail = None
        self._install_form(hidden_properties=self._ALWAYS_HIDDEN_ENGINE_FIELDS)
        self.eyebrow_label.setText("FORK" if fixed_template else "CREATE")
        self.title_label.setText("Fork Engine" if fixed_template else "Create Engine")
        self.recommend_button.show()
        self.create_button.setText("Create Engine")
        self.create_button.setIcon(self.app.primary_icons["engine"])
        self.name_edit.blockSignals(True)
        self.name_edit.clear()
        if fixed_template:
            placeholder = f"{fixed_template.get('name', '')}Copy"
        else:
            placeholder = "myCustomEngine"
        self.name_edit.setPlaceholderText(placeholder)
        self.name_edit.blockSignals(False)
        self.original_name = ""
        if fixed_template:
            self.load_part(dict(fixed_template.get("detail") or {}), row=None)
        elif initial_donor:
            # Drop straight into the editable form using the donor as
            # the starting point. User can switch donor via the
            # Vehicle Type combo if they want different defaults.
            self.load_part(dict(initial_donor.get("detail") or {}), row=None)
        else:
            self.badge_label.hide()
            self.summary_label.setText("Pick a Vehicle Type below to set the donor, then fill in the form.")
            if self.form:
                self.form.clear("Choose a vehicle type to start building a new engine.")
            self._set_status("Pick a Vehicle Type to start.", "notice")
            self.create_button.setEnabled(False)

    def begin_tire(self, live_version: str) -> None:
        self.mode = "create-tire"
        self.live_version = live_version
        self.sound_options = []
        self.fixed_template = None
        self.part_type = "tire"
        self.current_row = None
        self.current_detail = None
        self._install_form(hidden_properties=("MaxSpeed",), section_title_overrides={"Load and Speed": "Load and Resistance"})
        self.eyebrow_label.setText("CREATE")
        self.title_label.setText("Create Tire")
        self.badge_label.hide()
        self.summary_label.setText("Choose a donor tire from the left rail.")
        self.recommend_button.hide()
        self.create_button.setText("Create Tire")
        self.create_button.setIcon(self.app.primary_icons["tire"])
        self.name_edit.blockSignals(True)
        self.name_edit.clear()
        self.name_edit.setPlaceholderText("myCustomTire")
        self.name_edit.blockSignals(False)
        self.original_name = ""
        if self.form:
            self.form.clear("Choose a donor tire from the left rail to start building a new tire.")
        self._set_status("Choose a donor tire to preview coverage.", "notice")
        self.create_button.setEnabled(False)

    def load_part(self, detail: Dict[str, Any], row: Optional[Dict[str, Any]]) -> None:
        self.current_detail = detail
        self.current_row = dict(row or {})
        if not self.form:
            return
        self.form.load_part(detail, self.sound_options if self.part_type == "engine" else [])
        self.scroll.verticalScrollBar().setValue(0)
        self.create_button.setEnabled(True)
        self._set_summary()
        self._refresh_status()

    def _handle_donor_change_request(self, target_path: str, intended_fuel_type: str) -> None:
        """Form is asking us to swap donors because the user picked a
        Fuel Type that the current binary doesn't support (Gas/Diesel
        <-> Electric). Confirm with the user if they have unsaved
        property edits, then fetch the new donor and reload."""
        if self.form is None:
            return
        if self.form.has_property_edits():
            answer = QtWidgets.QMessageBox.question(
                self,
                APP_NAME,
                "Switching to a different fuel type requires reloading the "
                "form using a different donor engine. Your current property "
                "values will be replaced with the new donor's defaults.\n\n"
                "Continue?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                self.form.revert_fuel_type_combo()
                return

        detail = self.service.get_part_detail(target_path)
        if not detail or detail.get("error"):
            QtWidgets.QMessageBox.critical(
                self, APP_NAME,
                f"Could not load donor '{target_path}': "
                f"{(detail or {}).get('error', 'unknown error')}",
            )
            self.form.revert_fuel_type_combo()
            return

        # Inject the user's intended fuel_type into creation_inputs so
        # the reloaded form's combo lands on the user's pick instead of
        # the donor's default heuristic. (For Diesel via an ICE donor
        # the heuristic would default to Gas, losing the user's intent.)
        metadata = detail.setdefault("metadata", {})
        creation_inputs = dict(metadata.get("creation_inputs") or {})
        creation_inputs["fuel_type"] = intended_fuel_type
        metadata["creation_inputs"] = creation_inputs

        self.load_part(detail, row=None)

    def _set_summary(self) -> None:
        if self.part_type == "engine":
            row = self.current_row or {}
            if row:
                theme = engine_fuel_theme(row.get("fuel"), row.get("variant"))
                apply_tone_badge(self.badge_label, theme["label"], theme["key"])
                self.badge_label.show()
                details = "  •  ".join(part for part in [str(row.get("group_label") or "").strip(), str(row.get("description") or "").strip()] if part)
                self.summary_label.setText(details or "Template loaded.")
                return
            if self.fixed_template and self.current_detail:
                state = build_engine_state(self.current_detail)
                theme = engine_fuel_theme(variant=state.get("variant"), is_ev=bool(state.get("isEV")))
                apply_tone_badge(self.badge_label, theme["label"], theme["key"])
                self.badge_label.show()
                name = str(self.fixed_template.get("name") or self.current_detail.get("name") or "").strip()
                self.summary_label.setText(f"Forking from {name}")
                return
            self.badge_label.hide()
            self.summary_label.setText("Choose an engine template from the left rail.")
            return
        self.badge_label.hide()
        if self.current_row:
            group_label = str(self.current_row.get("group_label") or "").strip()
            source = str(self.current_row.get("source") or "template donor").strip()
            self.summary_label.setText("  •  ".join(bit for bit in [group_label, source] if bit))
        else:
            self.summary_label.setText("Choose a donor tire from the left rail.")

    def _set_status(self, text: str, kind: str) -> None:
        self.status_label.setText(text)
        set_label_kind(self.status_label, kind)
        refresh_style(self.status_label)

    def _toggle_details(self) -> None:
        showing = not self.details_text.isVisible()
        self.details_text.setVisible(showing)
        self.details_toggle.setText("Hide Details" if showing else "Show Details")

    def _refresh_status(self) -> None:
        if not self.form or not self.current_detail:
            default_text = "Choose a donor tire to preview coverage." if self.part_type == "tire" else "Choose a template to start."
            self._set_status(default_text, "notice")
            self.details_text.hide()
            self.details_toggle.hide()
            return
        if self.part_type == "engine":
            warnings = build_engine_warnings(self.form.get_engine_state())
            if not warnings:
                self._set_status("Validation OK. No risky values detected.", "ok")
                self.details_text.hide()
                self.details_toggle.hide()
                return
            danger_count = sum(1 for item in warnings if item.get("level") == "danger")
            warning_count = sum(1 for item in warnings if item.get("level") == "warning")
            notice_count = sum(1 for item in warnings if item.get("level") == "notice")
            parts = []
            if danger_count:
                parts.append(f"{danger_count} danger")
            if warning_count:
                parts.append(f"{warning_count} warning")
            if notice_count:
                parts.append(f"{notice_count} notice")
            self._set_status("  •  ".join(parts) + " need attention.", "danger" if danger_count else "warning")
            self.details_text.setPlainText("\n".join(f"• [{item['level'].upper()}] {item['text']}" for item in warnings))
            self.details_text.hide()
            self.details_toggle.setText("Show Details")
            self.details_toggle.show()
            return

        coverage = get_tire_field_coverage(self.current_detail)
        grip = self.form.get_tire_grip_g()
        summary_parts = []
        details = []
        if grip is not None:
            summary_parts.append(f"{format_compact_metric(grip)} G grip")
            details.append(f"Estimated grip: {format_number(grip)} G")
        if coverage:
            summary_parts.append(f"{coverage['property_count']}/{coverage['known_count']} fields")
            details.append(f"Editable fields on this layout: {coverage['property_count']} of {coverage['known_count']} known tire fields.")
            if coverage["missing_known"]:
                details.append("Missing on this layout: " + ", ".join(format_property_name(name) for name in coverage["missing_known"]))
        self._set_status("  •  ".join(summary_parts) if summary_parts else "Coverage ready.", "warning" if coverage and coverage.get("missing_known") else "ok")
        self.details_text.setPlainText("\n".join(details))
        if coverage and coverage.get("missing_known"):
            self.details_text.hide()
            self.details_toggle.setText("Show Details")
            self.details_toggle.show()
        else:
            self.details_text.hide()
            self.details_toggle.hide()

    def has_changes(self) -> bool:
        form_changed = self.form.has_changes() if self.form else False
        return bool(self.name_edit.text().strip() != self.original_name or form_changed)

    def current_source_identifier(self) -> str:
        if not self.current_row:
            return ""
        if self.part_type == "engine":
            return str(self.current_row.get("name") or "")
        if self.part_type == "tire":
            return str(self.current_row.get("path") or "")
        return ""

    def recommend_price(self) -> None:
        if self.part_type != "engine" or not self.form or not self.current_detail:
            return
        torque_nm = self.form.get_engine_state().get("maxTorqueNm")
        if torque_nm is None:
            QtWidgets.QMessageBox.information(self, APP_NAME, "Set a valid Max Torque value first.")
            return
        include_bikes = self.form.get_engine_state().get("variant") == "bike"
        result = self.service.recommend_engine_price(torque_nm, include_bikes=include_bikes)
        if result.get("error"):
            QtWidgets.QMessageBox.critical(self, APP_NAME, str(result.get("error")))
            return
        widget = self.form.shop_widgets.get("price")
        if isinstance(widget, QtWidgets.QLineEdit):
            widget.setText(str(result.get("price") or ""))

    def submit(self) -> None:
        if not self.current_detail or not self.form:
            QtWidgets.QMessageBox.information(self, APP_NAME, "Choose a template or donor first.")
            return
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.information(self, APP_NAME, f"Enter the new {self.part_type} name.")
            return
        if self.app.current_part and self.app.editor_form.has_changes():
            answer = QtWidgets.QMessageBox.question(
                self,
                APP_NAME,
                "Creating a new part reloads the workspace and will discard unsaved edits on the currently selected generated part. Continue?",
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        expected_version = self.app.latest_live_state_version or self.live_version or self.app.live_state_version
        if self.part_type == "engine":
            shop = self.form.collect_shop_values()
            template_name = str(self.fixed_template.get("name") if self.fixed_template else self.current_detail.get("name") or "").strip()
            props = self.form.collect_property_payload_for_create()
            vehicle_type = props.pop('_vehicle_type', '')
            fuel_type = props.pop('_fuel_type', '')
            level_requirements_json = props.pop('_level_requirements', '')
            volume_offset = props.pop('_volume_offset', '0')
            payload = {
                "template": template_name,
                "name": name,
                "display_name": shop.get("display_name", ""),
                "description": shop.get("description", ""),
                "price": shop.get("price", ""),
                "weight": shop.get("weight", ""),
                "sound_dir": self.form.collect_sound_dir(),
                "properties": props,
                "expected_version": expected_version,
                "vehicle_type": vehicle_type,
                "fuel_type": fuel_type,
                "level_requirements_json": level_requirements_json,
                "volume_offset": volume_offset,
            }

            def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
                if error:
                    QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                    return
                if not result or result.get("error"):
                    if result and result.get("conflict"):
                        conflict = self.service.build_conflict_state(result, "Live data changed before the engine was created.")
                        reload_now = QtWidgets.QMessageBox.question(
                            self,
                            APP_NAME,
                            f"{conflict.message}\n\nReload the workspace before trying again?",
                        )
                        if reload_now == QtWidgets.QMessageBox.StandardButton.Yes:
                            self.app.reload_workspace()
                        return
                    QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Create engine failed."))
                    return
                self.created.emit(str(result.get("path") or ""))

            self.app.run_task("Creating engine...", lambda: self.service.create_engine(payload), on_done)
            return

        shop = self.form.collect_shop_values()
        props = self.form.collect_property_payload_for_create()
        vehicle_type = props.pop('_vehicle_type', '')
        payload = {
            "template_path": self.current_detail.get("path", ""),
            "name": name,
            "display_name": shop.get("display_name", ""),
            "code": shop.get("code", ""),
            "price": shop.get("price", ""),
            "weight": shop.get("weight", ""),
            "properties": props,
            "expected_version": expected_version,
            "vehicle_type": vehicle_type,
        }

        def on_done(result: Optional[Dict[str, Any]], error: Optional[Exception]) -> None:
            if error:
                QtWidgets.QMessageBox.critical(self, APP_NAME, str(error))
                return
            if not result or result.get("error"):
                if result and result.get("conflict"):
                    conflict = self.service.build_conflict_state(result, "Live data changed before the tire was created.")
                    reload_now = QtWidgets.QMessageBox.question(
                        self,
                        APP_NAME,
                        f"{conflict.message}\n\nReload the workspace before trying again?",
                    )
                    if reload_now == QtWidgets.QMessageBox.StandardButton.Yes:
                        self.app.reload_workspace()
                    return
                QtWidgets.QMessageBox.critical(self, APP_NAME, str((result or {}).get("error") or "Create tire failed."))
                return
            self.created.emit(str(result.get("path") or ""))

        self.app.run_task("Creating tire...", lambda: self.service.create_tire(payload), on_done)
