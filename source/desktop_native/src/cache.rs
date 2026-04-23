use crate::models::AppBootstrap;
use anyhow::{Context, Result};
use directories::ProjectDirs;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct StartupCache {
    path: PathBuf,
}

impl StartupCache {
    pub fn new() -> Result<Self> {
        let dirs = ProjectDirs::from("com", "frogmodeditor", "FrogModEditor")
            .context("failed to resolve desktop cache directory")?;
        let cache_dir = dirs.cache_dir();
        fs::create_dir_all(cache_dir).with_context(|| format!("failed to create {}", cache_dir.display()))?;
        Ok(Self {
            path: cache_dir.join("bootstrap.json"),
        })
    }

    pub fn load(&self) -> Option<AppBootstrap> {
        let raw = fs::read(&self.path).ok()?;
        serde_json::from_slice::<AppBootstrap>(&raw).ok()
    }

    pub fn save(&self, bootstrap: &AppBootstrap) -> Result<()> {
        let raw = serde_json::to_vec_pretty(bootstrap).context("failed to serialize startup cache")?;
        fs::write(&self.path, raw).with_context(|| format!("failed to write {}", self.path.display()))
    }
}
