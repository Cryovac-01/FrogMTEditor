include!(concat!(env!("OUT_DIR"), "/embedded_runtime.rs"));

use anyhow::{bail, Context, Result};
use directories::ProjectDirs;
use std::env;
use std::fs;
use std::io::Cursor;
use std::path::{Path, PathBuf};
use zip::ZipArchive;

#[derive(Debug, Clone)]
pub struct DesktopRuntime {
    pub root: PathBuf,
    pub python_exe: PathBuf,
    pub bridge_script: PathBuf,
}

impl DesktopRuntime {
    pub fn discover() -> Result<Self> {
        if let Ok(explicit_root) = env::var("FROG_MOD_EDITOR_RUNTIME_ROOT") {
            if let Some(runtime) = Self::from_root(PathBuf::from(explicit_root))? {
                return Ok(runtime);
            }
        }

        let current_dir = env::current_dir().context("failed to resolve current directory")?;
        if let Some(runtime) = Self::from_root(current_dir.clone())? {
            return Ok(runtime);
        }

        let exe_dir = env::current_exe()
            .context("failed to resolve current executable")?
            .parent()
            .map(Path::to_path_buf)
            .context("native executable has no parent directory")?;
        if let Some(runtime) = Self::from_root(exe_dir.clone())? {
            return Ok(runtime);
        }

        if let Some(parent) = exe_dir.parent() {
            if let Some(runtime) = Self::from_root(parent.to_path_buf())? {
                return Ok(runtime);
            }
        }

        if !EMBEDDED_RUNTIME_BYTES.is_empty() {
            let embedded_root = Self::extract_embedded_runtime()?;
            if let Some(runtime) = Self::from_root(embedded_root)? {
                return Ok(runtime);
            }
        }

        bail!("could not locate runtime root with python/python.exe and src/desktop_bridge.py[c]")
    }

    fn from_root(root: PathBuf) -> Result<Option<Self>> {
        let python_exe = root.join("python").join("python.exe");
        if !python_exe.is_file() {
            return Ok(None);
        }

        let compiled_bridge = root.join("src").join("desktop_bridge.pyc");
        let source_bridge = root.join("src").join("desktop_bridge.py");
        let bridge_script = if compiled_bridge.is_file() {
            compiled_bridge
        } else if source_bridge.is_file() {
            source_bridge
        } else {
            return Ok(None);
        };

        Ok(Some(Self {
            root,
            python_exe,
            bridge_script,
        }))
    }

    fn extract_embedded_runtime() -> Result<PathBuf> {
        let dirs = ProjectDirs::from("com", "frogmodeditor", "FrogModEditor")
            .context("failed to resolve desktop data directory")?;
        let root_base = dirs.data_local_dir();
        fs::create_dir_all(root_base)
            .with_context(|| format!("failed to create {}", root_base.display()))?;

        let ready_root = root_base.join(EMBEDDED_RUNTIME_HASH);
        let ready_marker = ready_root.join(".ready");
        if ready_marker.is_file()
            && fs::read_to_string(&ready_marker).ok().as_deref() == Some(EMBEDDED_RUNTIME_HASH)
        {
            return Ok(ready_root);
        }

        if ready_root.exists() {
            fs::remove_dir_all(&ready_root)
                .with_context(|| format!("failed to remove stale {}", ready_root.display()))?;
        }

        let temp_root = root_base.join(format!("{EMBEDDED_RUNTIME_HASH}.extracting"));
        if temp_root.exists() {
            fs::remove_dir_all(&temp_root)
                .with_context(|| format!("failed to remove stale {}", temp_root.display()))?;
        }
        fs::create_dir_all(&temp_root)
            .with_context(|| format!("failed to create {}", temp_root.display()))?;

        let cursor = Cursor::new(EMBEDDED_RUNTIME_BYTES);
        let mut archive = ZipArchive::new(cursor).context("failed to open embedded runtime archive")?;
        for index in 0..archive.len() {
            let mut entry = archive.by_index(index).context("failed to read embedded archive entry")?;
            let Some(safe_name) = entry.enclosed_name().map(|path| path.to_path_buf()) else {
                continue;
            };
            let output_path = temp_root.join(safe_name);
            if entry.is_dir() {
                fs::create_dir_all(&output_path)
                    .with_context(|| format!("failed to create {}", output_path.display()))?;
                continue;
            }
            if let Some(parent) = output_path.parent() {
                fs::create_dir_all(parent)
                    .with_context(|| format!("failed to create {}", parent.display()))?;
            }
            let mut output = fs::File::create(&output_path)
                .with_context(|| format!("failed to write {}", output_path.display()))?;
            std::io::copy(&mut entry, &mut output)
                .with_context(|| format!("failed to copy {}", output_path.display()))?;
        }

        fs::write(&temp_root.join(".ready"), EMBEDDED_RUNTIME_HASH.as_bytes())
            .with_context(|| format!("failed to write {}", temp_root.join(".ready").display()))?;
        fs::rename(&temp_root, &ready_root).with_context(|| {
            format!(
                "failed to finalize embedded runtime extraction from {} to {}",
                temp_root.display(),
                ready_root.display()
            )
        })?;
        Ok(ready_root)
    }
}
