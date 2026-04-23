# Frog Mod Editor Experimental Rust Host

This folder contains an experimental Windows Rust host for the editor backend. It is not the primary shipped app surface.

## Architecture

- Frontend: Rust + `native-windows-gui`
- Backend bridge: typed length-prefixed JSON over stdio
- Backend logic: existing Python parser/pak pipeline, unchanged
- Deployment shape: one native `.exe` with an embedded runtime payload that extracts to the user's local app data on first launch

## Product status

- Primary desktop app: `src/native_qt_app.py` (PySide6)
- Rust host status: experimental/future-host work only
- Support level: useful for bridge and packaging experiments, not the default user workflow

The native app does **not** use:

- a browser
- a localhost web server
- `fetch`/HTTP routing for the desktop shell
- public multi-user website behaviors

## Typed bridge

The Rust host talks to `src/desktop_bridge.py[c]` using this request envelope:

```json
{"id": 1, "cmd": "list_templates", "args": {}}
```

Responses use:

```json
{"id": 1, "ok": true, "result": {...}, "error": null}
```

Current desktop commands:

- `ping`
- `app_bootstrap`
- `list_engines`
- `list_templates`
- `load_engine`
- `load_engine_draft`
- `load_template`
- `load_template_draft`
- `save_engine`
- `create_engine`
- `delete_engine`
- `list_sounds`
- `recommend_price`
- `pack_mod`
- `pack_templates`

## Runtime packaging

The native build expects an embedded `runtime_payload.zip` during `cargo build`.

That payload contains:

- embedded Python runtime
- compiled backend modules (`.pyc`, no raw backend `.py`)
- current `data/mod`
- `data/templates/Engine`
- `data/vanilla`
- minimal vanilla DataTable assets

Generate the payload and build the native exe with:

```powershell
.\python\python.exe .\scripts\export_rust_native_desktop_exe.py
```

If Rust is not installed yet, you can still prepare the embedded payload with:

```powershell
.\python\python.exe .\scripts\export_rust_native_desktop_exe.py --prepare-only
```

Then install Rust and rerun the full exporter.

## Current host UX

The Rust host remains a narrow power-user prototype:

- fast filterable engine/template browser
- single-pane JSON draft editor backed by real backend defaults
- native buttons for save/create/fork/delete
- native pack actions for current engine, filtered engine list, and templates
- price recommendation from the backend without reimplementing pricing rules in Rust

This keeps all parser/pak behavior in the existing backend while validating an alternative host architecture.
