use crate::backend::BackendHandle;
use crate::cache::StartupCache;
use crate::models::{AppBootstrap, DraftEnvelope, EngineSummary, PartDetail, TemplateSummary};
use crate::runtime::DesktopRuntime;
use anyhow::{Context, Result};
use crossbeam_channel::{unbounded, Receiver, Sender};
use native_windows_gui as nwg;
use serde_json::{json, Value};
use std::cell::RefCell;
use std::rc::{Rc, Weak};
use std::thread;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BrowserMode {
    Engines,
    Templates,
}

#[derive(Debug, Clone)]
enum BrowserEntry {
    Engine(EngineSummary),
    Template(TemplateSummary),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ActionKind {
    Save,
    Create,
    Delete,
    RecommendPrice,
    PackCurrent,
    PackListed,
    PackTemplates,
}

#[derive(Debug)]
enum WorkerMessage {
    Bootstrap(Result<AppBootstrap, String>),
    LoadDraft(Result<DraftEnvelope, String>),
    Action(ActionKind, Result<Value, String>),
}

#[derive(Debug)]
struct UiState {
    bootstrap: Option<AppBootstrap>,
    browser_mode: BrowserMode,
    browser_entries: Vec<BrowserEntry>,
    selected_entry: Option<BrowserEntry>,
    current_detail: Option<PartDetail>,
    current_draft: Option<Value>,
}

impl Default for UiState {
    fn default() -> Self {
        Self {
            bootstrap: None,
            browser_mode: BrowserMode::Engines,
            browser_entries: Vec::new(),
            selected_entry: None,
            current_detail: None,
            current_draft: None,
        }
    }
}

pub fn run() -> Result<()> {
    nwg::init().context("failed to initialize native-windows-gui")?;
    nwg::Font::set_global_family("Segoe UI").ok();

    let runtime = DesktopRuntime::discover()?;
    let backend = BackendHandle::start(&runtime)?;
    let cache = StartupCache::new()?;
    let (tx, rx) = unbounded();

    let app = DesktopApp::build(backend, cache, tx, rx)?;
    DesktopApp::run(app);
    Ok(())
}

struct DesktopApp {
    backend: BackendHandle,
    cache: StartupCache,
    tx: Sender<WorkerMessage>,
    rx: Receiver<WorkerMessage>,
    state: UiState,

    window: nwg::Window,
    notice: nwg::Notice,
    search_input: nwg::TextInput,
    browse_list: nwg::ListBox<String>,
    summary_label: nwg::Label,
    draft_label: nwg::Label,
    draft_editor: nwg::TextBox,
    status_label: nwg::Label,

    engines_button: nwg::Button,
    templates_button: nwg::Button,
    refresh_button: nwg::Button,
    recommend_button: nwg::Button,
    save_button: nwg::Button,
    create_button: nwg::Button,
    fork_button: nwg::Button,
    delete_button: nwg::Button,
    pack_current_button: nwg::Button,
    pack_listed_button: nwg::Button,
    pack_templates_button: nwg::Button,

    grid: nwg::GridLayout,
    handler: Option<nwg::EventHandler>,
}

impl DesktopApp {
    fn build(
        backend: BackendHandle,
        cache: StartupCache,
        tx: Sender<WorkerMessage>,
        rx: Receiver<WorkerMessage>,
    ) -> Result<Rc<RefCell<Self>>> {
        let mut app = DesktopApp {
            backend,
            cache,
            tx,
            rx,
            state: UiState::default(),
            window: Default::default(),
            notice: Default::default(),
            search_input: Default::default(),
            browse_list: Default::default(),
            summary_label: Default::default(),
            draft_label: Default::default(),
            draft_editor: Default::default(),
            status_label: Default::default(),
            engines_button: Default::default(),
            templates_button: Default::default(),
            refresh_button: Default::default(),
            recommend_button: Default::default(),
            save_button: Default::default(),
            create_button: Default::default(),
            fork_button: Default::default(),
            delete_button: Default::default(),
            pack_current_button: Default::default(),
            pack_listed_button: Default::default(),
            pack_templates_button: Default::default(),
            grid: Default::default(),
            handler: None,
        };
        app.build_ui()?;

        if let Some(cached) = app.cache.load() {
            app.apply_bootstrap(cached);
            app.set_status("Loaded cached index while the backend warms up.");
        } else {
            app.set_status("Starting Frog Mod Editor...");
        }

        let app = Rc::new(RefCell::new(app));
        DesktopApp::bind_events(&app);
        app.borrow().refresh_async();
        Ok(app)
    }

    fn run(app: Rc<RefCell<Self>>) {
        let _keep_alive = app;
        nwg::dispatch_thread_events();
    }

    fn build_ui(&mut self) -> Result<()> {
        let window_title = format!("Frog Mod Editor v{}", env!("CARGO_PKG_VERSION"));

        nwg::Window::builder()
            .size((1620, 980))
            .position((60, 40))
            .title(&window_title)
            .flags(nwg::WindowFlags::WINDOW | nwg::WindowFlags::VISIBLE)
            .build(&mut self.window)?;

        nwg::Notice::builder().parent(&self.window).build(&mut self.notice)?;
        nwg::TextInput::builder()
            .parent(&self.window)
            .placeholder_text(Some("Filter engines or templates..."))
            .text("")
            .build(&mut self.search_input)?;
        nwg::ListBox::builder()
            .parent(&self.window)
            .collection(Vec::<String>::new())
            .build(&mut self.browse_list)?;

        nwg::Button::builder().text("Engines").parent(&self.window).build(&mut self.engines_button)?;
        nwg::Button::builder().text("Templates").parent(&self.window).build(&mut self.templates_button)?;
        nwg::Button::builder().text("Refresh").parent(&self.window).build(&mut self.refresh_button)?;
        nwg::Button::builder().text("Recommend Price").parent(&self.window).build(&mut self.recommend_button)?;
        nwg::Button::builder().text("Save").parent(&self.window).build(&mut self.save_button)?;
        nwg::Button::builder().text("Create").parent(&self.window).build(&mut self.create_button)?;
        nwg::Button::builder().text("Fork").parent(&self.window).build(&mut self.fork_button)?;
        nwg::Button::builder().text("Delete").parent(&self.window).build(&mut self.delete_button)?;
        nwg::Button::builder().text("Pack Current").parent(&self.window).build(&mut self.pack_current_button)?;
        nwg::Button::builder().text("Pack Listed").parent(&self.window).build(&mut self.pack_listed_button)?;
        nwg::Button::builder().text("Pack Templates").parent(&self.window).build(&mut self.pack_templates_button)?;

        nwg::Label::builder()
            .parent(&self.window)
            .text("Select a generated engine or template.")
            .build(&mut self.summary_label)?;
        nwg::Label::builder().parent(&self.window).text("Draft JSON").build(&mut self.draft_label)?;
        nwg::Label::builder().parent(&self.window).text("Ready").build(&mut self.status_label)?;

        nwg::TextBox::builder()
            .parent(&self.window)
            .text("{\r\n}")
            .flags(
                nwg::TextBoxFlags::VISIBLE
                    | nwg::TextBoxFlags::TAB_STOP
                    | nwg::TextBoxFlags::VSCROLL,
            )
            .build(&mut self.draft_editor)?;

        nwg::GridLayout::builder()
            .parent(&self.window)
            .margin([12, 12, 12, 12])
            .spacing(8)
            .child_item(nwg::GridLayoutItem::new(&self.search_input, 0, 0, 1, 3))
            .child_item(nwg::GridLayoutItem::new(&self.engines_button, 0, 3, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.templates_button, 0, 4, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.refresh_button, 0, 5, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.recommend_button, 0, 6, 1, 2))
            .child_item(nwg::GridLayoutItem::new(&self.save_button, 0, 8, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.create_button, 0, 9, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.fork_button, 0, 10, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.delete_button, 0, 11, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.pack_current_button, 0, 12, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.pack_listed_button, 0, 13, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.pack_templates_button, 0, 14, 1, 1))
            .child_item(nwg::GridLayoutItem::new(&self.browse_list, 1, 0, 9, 4))
            .child_item(nwg::GridLayoutItem::new(&self.summary_label, 1, 4, 1, 11))
            .child_item(nwg::GridLayoutItem::new(&self.draft_label, 2, 4, 1, 11))
            .child_item(nwg::GridLayoutItem::new(&self.draft_editor, 3, 4, 7, 11))
            .child_item(nwg::GridLayoutItem::new(&self.status_label, 10, 0, 1, 15))
            .build(&mut self.grid)?;

        self.update_action_buttons();
        Ok(())
    }

    fn bind_events(app: &Rc<RefCell<Self>>) {
        let weak: Weak<RefCell<Self>> = Rc::downgrade(app);
        let (
            handle,
            window_handle,
            notice_handle,
            search_input_handle,
            browse_list_handle,
            engines_button_handle,
            templates_button_handle,
            refresh_button_handle,
            recommend_button_handle,
            save_button_handle,
            create_button_handle,
            fork_button_handle,
            delete_button_handle,
            pack_current_button_handle,
            pack_listed_button_handle,
            pack_templates_button_handle,
            notice_sender,
        ) = {
            let app_ref = app.borrow();
            (
                app_ref.window.handle,
                app_ref.window.handle,
                app_ref.notice.handle,
                app_ref.search_input.handle,
                app_ref.browse_list.handle,
                app_ref.engines_button.handle,
                app_ref.templates_button.handle,
                app_ref.refresh_button.handle,
                app_ref.recommend_button.handle,
                app_ref.save_button.handle,
                app_ref.create_button.handle,
                app_ref.fork_button.handle,
                app_ref.delete_button.handle,
                app_ref.pack_current_button.handle,
                app_ref.pack_listed_button.handle,
                app_ref.pack_templates_button.handle,
                app_ref.notice.sender(),
            )
        };
        let event_handler = nwg::full_bind_event_handler(&handle, move |evt, _evt_data, control| {
            let Some(app_rc) = weak.upgrade() else { return; };
            let Ok(mut app) = app_rc.try_borrow_mut() else {
                if evt == nwg::Event::OnNotice && control == notice_handle {
                    notice_sender.notice();
                }
                return;
            };

            if evt == nwg::Event::OnWindowClose && control == window_handle {
                nwg::stop_thread_dispatch();
                return;
            }
            if evt == nwg::Event::OnNotice && control == notice_handle {
                app.drain_worker_messages();
                return;
            }
            if evt == nwg::Event::OnTextInput && control == search_input_handle {
                app.render_browser_entries();
                return;
            }
            if evt == nwg::Event::OnListBoxSelect && control == browse_list_handle {
                app.load_selected_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == engines_button_handle {
                app.set_mode(BrowserMode::Engines);
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == templates_button_handle {
                app.set_mode(BrowserMode::Templates);
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == refresh_button_handle {
                app.refresh_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == recommend_button_handle {
                app.recommend_price_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == save_button_handle {
                app.save_current_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == create_button_handle {
                app.create_current_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == fork_button_handle {
                app.fork_current();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == delete_button_handle {
                app.delete_current_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == pack_current_button_handle {
                app.pack_current_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == pack_listed_button_handle {
                app.pack_listed_async();
                return;
            }
            if evt == nwg::Event::OnButtonClick && control == pack_templates_button_handle {
                app.pack_templates_async();
            }
        });
        app.borrow_mut().handler = Some(event_handler);
    }

    fn set_mode(&mut self, mode: BrowserMode) {
        self.state.browser_mode = mode;
        self.render_browser_entries();
        match mode {
            BrowserMode::Engines => self.set_status("Showing generated engines."),
            BrowserMode::Templates => self.set_status("Showing source templates."),
        }
    }

    fn set_status(&self, message: &str) {
        self.status_label.set_text(message);
    }

    fn update_action_buttons(&self) {
        let draft = self.current_draft_json().ok().or_else(|| self.state.current_draft.clone());
        let kind = draft
            .as_ref()
            .and_then(|value| value.get("kind"))
            .and_then(Value::as_str)
            .unwrap_or_default();

        let is_engine = kind == "engine";
        let is_template = kind == "template";
        let has_selection = self.browse_list.selection().is_some();
        let listed_engine_count = self
            .state
            .browser_entries
            .iter()
            .filter(|entry| matches!(entry, BrowserEntry::Engine(_)))
            .count();

        self.save_button.set_enabled(is_engine);
        self.create_button.set_enabled(is_template);
        self.delete_button.set_enabled(is_engine);
        self.fork_button
            .set_enabled(matches!(self.state.selected_entry, Some(BrowserEntry::Engine(_))) || is_engine);
        self.recommend_button.set_enabled(is_engine || is_template);
        self.pack_current_button.set_enabled(is_engine);
        self.pack_listed_button
            .set_enabled(self.state.browser_mode == BrowserMode::Engines && listed_engine_count > 0);
        self.pack_templates_button
            .set_enabled(self.state.browser_mode == BrowserMode::Templates || !has_selection);
    }

    fn refresh_async(&self) {
        let tx = self.tx.clone();
        let notice = self.notice.sender();
        let backend = self.backend.clone();
        thread::spawn(move || {
            let result = backend
                .send_typed::<AppBootstrap>("app_bootstrap", json!({}))
                .map_err(|err| err.to_string());
            let _ = tx.send(WorkerMessage::Bootstrap(result));
            notice.notice();
        });
    }

    fn render_browser_entries(&mut self) {
        let filter = self.search_input.text().to_lowercase();
        self.state.browser_entries.clear();
        let mut labels = Vec::new();

        if let Some(bootstrap) = &self.state.bootstrap {
            match self.state.browser_mode {
                BrowserMode::Engines => {
                    for engine in &bootstrap.engines.items {
                        let label = format!(
                            "{}  [{} | {} bytes{}]",
                            engine.name,
                            engine.variant,
                            engine.uexp_size,
                            if engine.in_shop { " | shop" } else { "" }
                        );
                        if !filter.is_empty() && !label.to_lowercase().contains(&filter) {
                            continue;
                        }
                        labels.push(label);
                        self.state.browser_entries.push(BrowserEntry::Engine(engine.clone()));
                    }
                    self.summary_label.set_text(&format!(
                        "Generated engines: {} visible / {} total\r\nUse search to curate a pack quickly, or select one to edit its draft JSON.",
                        self.state.browser_entries.len(),
                        bootstrap.engines.count
                    ));
                }
                BrowserMode::Templates => {
                    for template in &bootstrap.templates.items {
                        let label = format!(
                            "{}  [{} | {:.0} HP | {:.0} N-m]",
                            template.title,
                            template.group_label,
                            template.hp,
                            template.torque
                        );
                        if !filter.is_empty() && !label.to_lowercase().contains(&filter) {
                            continue;
                        }
                        labels.push(label);
                        self.state.browser_entries.push(BrowserEntry::Template(template.clone()));
                    }
                    self.summary_label.set_text(&format!(
                        "Templates: {} visible / {} total\r\nSelect a template to generate a new engine draft with backend-derived defaults.",
                        self.state.browser_entries.len(),
                        bootstrap.templates.count
                    ));
                }
            }
        }

        self.browse_list.set_collection(labels);
        self.update_action_buttons();
    }

    fn load_selected_async(&mut self) {
        let Some(index) = self.browse_list.selection() else {
            self.update_action_buttons();
            return;
        };
        let Some(entry) = self.state.browser_entries.get(index).cloned() else {
            self.update_action_buttons();
            return;
        };
        self.state.selected_entry = Some(entry.clone());
        self.set_status("Loading draft...");
        self.update_action_buttons();

        let tx = self.tx.clone();
        let notice = self.notice.sender();
        let backend = self.backend.clone();
        thread::spawn(move || {
            let result = match entry {
                BrowserEntry::Engine(engine) => backend
                    .send_typed::<DraftEnvelope>("load_engine_draft", json!({ "name": engine.name }))
                    .map_err(|err| err.to_string()),
                BrowserEntry::Template(template) => backend
                    .send_typed::<DraftEnvelope>("load_template_draft", json!({ "name": template.name }))
                    .map_err(|err| err.to_string()),
            };
            let _ = tx.send(WorkerMessage::LoadDraft(result));
            notice.notice();
        });
    }

    fn apply_bootstrap(&mut self, bootstrap: AppBootstrap) {
        self.state.bootstrap = Some(bootstrap);
        self.render_browser_entries();
    }

    fn set_current_draft(&mut self, detail: Option<PartDetail>, draft: Value) {
        self.state.current_detail = detail.clone();
        self.state.current_draft = Some(draft.clone());
        let pretty = serde_json::to_string_pretty(&draft).unwrap_or_else(|_| "{}".to_string());
        self.draft_editor.set_text(&pretty);

        let summary = if let Some(detail) = detail {
            if let Some(meta) = &detail.metadata {
                let shop_title = meta
                    .shop
                    .as_ref()
                    .and_then(|shop| shop.display_name.clone())
                    .unwrap_or_else(|| detail.name.clone());
                let description = meta
                    .shop
                    .as_ref()
                    .and_then(|shop| shop.description.clone())
                    .unwrap_or_default();
                format!(
                    "{}\r\n{}\r\nVariant: {} | HP: {:.1} | Torque: {:.1} N-m | RPM: {:.0}",
                    shop_title,
                    description,
                    meta.variant.clone().unwrap_or_default(),
                    meta.estimated_hp.unwrap_or_default(),
                    meta.max_torque_nm.unwrap_or_default(),
                    meta.max_rpm.unwrap_or_default(),
                )
            } else {
                format!("{}\r\n{}", detail.name, detail.path)
            }
        } else if draft.get("kind").and_then(Value::as_str) == Some("template") {
            let title = draft
                .get("display_name")
                .and_then(Value::as_str)
                .unwrap_or("Fork Draft");
            let description = draft.get("description").and_then(Value::as_str).unwrap_or_default();
            let template = draft.get("template").and_then(Value::as_str).unwrap_or_default();
            format!(
                "{}\r\n{}\r\nFork draft based on source asset: {}",
                title,
                description,
                template
            )
        } else {
            "Draft JSON".to_string()
        };
        self.summary_label.set_text(&summary);
        self.update_action_buttons();
    }

    fn apply_draft(&mut self, envelope: DraftEnvelope) {
        self.set_current_draft(Some(envelope.detail), envelope.draft);
    }

    fn current_draft_json(&self) -> Result<Value> {
        let raw = self.draft_editor.text();
        serde_json::from_str(&raw).context("draft editor does not contain valid JSON")
    }

    fn patch_draft_price(&mut self, price: i64) {
        let Ok(mut draft) = self.current_draft_json() else {
            return;
        };
        draft["price"] = json!(price);
        let detail = self.state.current_detail.clone();
        self.set_current_draft(detail, draft);
    }

    fn fork_current(&mut self) {
        let Ok(mut draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        if draft.get("kind").and_then(Value::as_str) != Some("engine") {
            self.set_status("Fork expects a generated engine draft.");
            return;
        }

        let source_name = draft
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let fallback_copy_name = if source_name.is_empty() {
            "EngineCopy".to_string()
        } else {
            format!("{source_name}Copy")
        };
        let live_version = self
            .state
            .bootstrap
            .as_ref()
            .map(|boot| boot.state.version.clone())
            .unwrap_or_default();

        draft["kind"] = json!("template");
        draft["template"] = json!(source_name);
        draft["name"] = json!(fallback_copy_name);
        draft["path"] = Value::Null;
        draft["expected_version"] = json!(live_version);

        self.state.selected_entry = None;
        self.browse_list.set_selection(None);
        self.set_current_draft(None, draft);
        self.set_status("Fork draft seeded from the selected engine.");
    }

    fn drain_worker_messages(&mut self) {
        while let Ok(message) = self.rx.try_recv() {
            match message {
                WorkerMessage::Bootstrap(result) => match result {
                    Ok(bootstrap) => {
                        let _ = self.cache.save(&bootstrap);
                        self.apply_bootstrap(bootstrap);
                        self.set_status("Desktop index refreshed.");
                    }
                    Err(err) => self.set_status(&format!("Bootstrap failed: {err}")),
                },
                WorkerMessage::LoadDraft(result) => match result {
                    Ok(envelope) => {
                        self.apply_draft(envelope);
                        self.set_status("Draft loaded.");
                    }
                    Err(err) => self.set_status(&format!("Load failed: {err}")),
                },
                WorkerMessage::Action(kind, result) => match result {
                    Ok(value) => match kind {
                        ActionKind::RecommendPrice => {
                            if let Some(price) = value.get("price").and_then(Value::as_i64) {
                                self.patch_draft_price(price);
                            }
                            let message = value
                                .get("message")
                                .and_then(Value::as_str)
                                .unwrap_or("Price recommendation updated.");
                            self.set_status(message);
                        }
                        ActionKind::Create => {
                            let message = value
                                .get("message")
                                .and_then(Value::as_str)
                                .unwrap_or("Engine created.");
                            self.set_status(message);
                            self.refresh_async();
                        }
                        ActionKind::Save | ActionKind::Delete => {
                            let message = value
                                .get("message")
                                .and_then(Value::as_str)
                                .unwrap_or("Engine updated.");
                            self.set_status(message);
                            self.refresh_async();
                        }
                        ActionKind::PackCurrent | ActionKind::PackListed | ActionKind::PackTemplates => {
                            let message = value
                                .get("message")
                                .and_then(Value::as_str)
                                .unwrap_or("Pack completed.");
                            self.set_status(message);
                        }
                    },
                    Err(err) => self.set_status(&format!("Command failed: {err}")),
                },
            }
        }
        self.update_action_buttons();
    }

    fn spawn_action(&self, kind: ActionKind, cmd: &'static str, payload: Value) {
        let tx = self.tx.clone();
        let notice = self.notice.sender();
        let backend = self.backend.clone();
        thread::spawn(move || {
            let result = backend.send_value(cmd, payload).map_err(|err| err.to_string());
            let _ = tx.send(WorkerMessage::Action(kind, result));
            notice.notice();
        });
    }

    fn save_current_async(&self) {
        let Ok(draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        if draft.get("kind").and_then(Value::as_str) != Some("engine") {
            self.set_status("Save applies only to generated engine drafts.");
            return;
        }

        let payload = json!({
            "path": draft.get("path").and_then(Value::as_str).unwrap_or_default(),
            "data": {
                "expected_version": draft.get("expected_version").and_then(Value::as_str).unwrap_or_default(),
                "properties": draft.get("properties").cloned().unwrap_or_else(|| json!({})),
                "sound_dir": draft.get("sound_dir").and_then(Value::as_str).unwrap_or_default(),
                "shop": {
                    "display_name": draft.get("display_name").and_then(Value::as_str).unwrap_or_default(),
                    "description": draft.get("description").and_then(Value::as_str).unwrap_or_default(),
                    "price": draft.get("price").and_then(Value::as_i64).unwrap_or_default(),
                    "weight": draft.get("weight").and_then(Value::as_f64).unwrap_or_default(),
                }
            }
        });
        self.set_status("Saving engine...");
        self.spawn_action(ActionKind::Save, "save_engine", payload);
    }

    fn create_current_async(&self) {
        let Ok(draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        if draft.get("kind").and_then(Value::as_str) != Some("template") {
            self.set_status("Create expects a template or fork draft.");
            return;
        }

        let payload = json!({
            "template": draft.get("template").and_then(Value::as_str).unwrap_or_default(),
            "name": draft.get("name").and_then(Value::as_str).unwrap_or_default(),
            "display_name": draft.get("display_name").and_then(Value::as_str).unwrap_or_default(),
            "description": draft.get("description").and_then(Value::as_str).unwrap_or_default(),
            "price": draft.get("price").and_then(Value::as_i64).unwrap_or_default(),
            "weight": draft.get("weight").and_then(Value::as_f64).unwrap_or_default(),
            "sound_dir": draft.get("sound_dir").and_then(Value::as_str).unwrap_or_default(),
            "expected_version": draft.get("expected_version").and_then(Value::as_str).unwrap_or_default(),
            "properties": draft.get("properties").cloned().unwrap_or_else(|| json!({})),
        });
        self.set_status("Creating engine...");
        self.spawn_action(ActionKind::Create, "create_engine", payload);
    }

    fn delete_current_async(&self) {
        let Ok(draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        if draft.get("kind").and_then(Value::as_str) != Some("engine") {
            self.set_status("Delete applies only to generated engines.");
            return;
        }

        let payload = json!({
            "path": draft.get("path").and_then(Value::as_str).unwrap_or_default(),
            "expected_version": draft.get("expected_version").and_then(Value::as_str).unwrap_or_default(),
        });
        self.set_status("Deleting engine...");
        self.spawn_action(ActionKind::Delete, "delete_engine", payload);
    }

    fn recommend_price_async(&self) {
        let Ok(draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        let torque = draft
            .get("properties")
            .and_then(|props| props.get("MaxTorque"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .parse::<f64>();
        let Ok(torque_nm) = torque else {
            self.set_status("Draft MaxTorque must be numeric.");
            return;
        };
        let include_bikes = draft
            .get("variant")
            .and_then(Value::as_str)
            .map(|variant| variant.contains("bike"))
            .unwrap_or(false);

        self.set_status("Calculating recommended price...");
        self.spawn_action(
            ActionKind::RecommendPrice,
            "recommend_price",
            json!({ "torque_nm": torque_nm, "include_bikes": include_bikes }),
        );
    }

    fn pack_current_async(&self) {
        let Ok(draft) = self.current_draft_json() else {
            self.set_status("Draft JSON is invalid.");
            return;
        };
        let Some(path) = draft.get("path").and_then(Value::as_str) else {
            self.set_status("Pack Current expects a generated engine draft.");
            return;
        };
        let Some(output_path) = self.choose_output_path("Pack Current Engine") else {
            return;
        };

        self.set_status("Packing current engine...");
        self.spawn_action(
            ActionKind::PackCurrent,
            "pack_mod",
            json!({ "output_path": output_path, "parts": [path] }),
        );
    }

    fn pack_listed_async(&self) {
        if self.state.browser_mode != BrowserMode::Engines {
            self.set_status("Pack Listed works from the engine browser.");
            return;
        }
        let part_paths: Vec<String> = self
            .state
            .browser_entries
            .iter()
            .filter_map(|entry| match entry {
                BrowserEntry::Engine(engine) => {
                    if !engine.path.is_empty() {
                        Some(engine.path.clone())
                    } else {
                        Some(format!("mod/Engine/{}", engine.name))
                    }
                }
                BrowserEntry::Template(_) => None,
            })
            .collect();
        if part_paths.is_empty() {
            self.set_status("No generated engines are currently listed.");
            return;
        }
        let Some(output_path) = self.choose_output_path("Pack Listed Engines") else {
            return;
        };

        self.set_status(&format!("Packing {} listed engines...", part_paths.len()));
        self.spawn_action(
            ActionKind::PackListed,
            "pack_mod",
            json!({ "output_path": output_path, "parts": part_paths }),
        );
    }

    fn pack_templates_async(&self) {
        let Some(output_path) = self.choose_output_path("Pack Template Engines") else {
            return;
        };

        self.set_status("Packing templates...");
        self.spawn_action(
            ActionKind::PackTemplates,
            "pack_templates",
            json!({ "output_path": output_path }),
        );
    }

    fn choose_output_path(&self, title: &str) -> Option<String> {
        let mut dialog = nwg::FileDialog::default();
        if nwg::FileDialog::builder()
            .action(nwg::FileDialogAction::Save)
            .title(title)
            .filters("PAK Files (*.pak)|*.pak")
            .build(&mut dialog)
            .is_err()
        {
            self.set_status("Failed to open native file dialog.");
            return None;
        }

        if !dialog.run(Some(&self.window)) {
            return None;
        }

        dialog
            .get_selected_item()
            .ok()
            .map(|path| path.to_string_lossy().to_string())
    }
}
