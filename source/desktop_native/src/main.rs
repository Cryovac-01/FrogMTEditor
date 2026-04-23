mod app;
mod backend;
mod cache;
mod models;
mod runtime;

fn main() {
    if let Err(err) = app::run() {
        eprintln!("frog_mod_editor_desktop failed: {err:#}");
    }
}
