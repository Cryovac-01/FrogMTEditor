use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LiveState {
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub engine_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EngineCollection {
    #[serde(default)]
    pub items: Vec<EngineSummary>,
    #[serde(default)]
    pub count: usize,
    #[serde(default)]
    pub state_version: String,
    #[serde(default)]
    pub engine_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct EngineSummary {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub uexp_size: u64,
    #[serde(default)]
    pub variant: String,
    #[serde(default)]
    pub in_shop: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TemplateCollection {
    #[serde(default)]
    pub groups: Vec<TemplateGroup>,
    #[serde(default)]
    pub items: Vec<TemplateSummary>,
    #[serde(default)]
    pub count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TemplateGroup {
    #[serde(default)]
    pub key: String,
    #[serde(default)]
    pub label: String,
    #[serde(default)]
    pub variant: String,
    #[serde(default)]
    pub properties: Vec<String>,
    #[serde(default)]
    pub count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TemplateSummary {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub group_key: String,
    #[serde(default)]
    pub group_label: String,
    #[serde(default)]
    pub variant: String,
    #[serde(default)]
    pub properties: Vec<String>,
    #[serde(default)]
    pub hp: f64,
    #[serde(default)]
    pub torque: f64,
    #[serde(default)]
    pub rpm: f64,
    #[serde(default)]
    pub weight: f64,
    #[serde(default)]
    pub price: i64,
    #[serde(default)]
    pub fuel: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SoundCollection {
    #[serde(default)]
    pub by_cue: HashMap<String, Vec<SoundEntry>>,
    #[serde(default)]
    pub bike: Vec<SoundEntry>,
    #[serde(default)]
    pub electric: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SoundEntry {
    #[serde(default)]
    pub dir: String,
    #[serde(default)]
    pub source: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppBootstrap {
    #[serde(default)]
    pub state: LiveState,
    #[serde(default)]
    pub engines: EngineCollection,
    #[serde(default)]
    pub templates: TemplateCollection,
    #[serde(default)]
    pub sounds: SoundCollection,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DraftEnvelope {
    #[serde(default)]
    pub detail: PartDetail,
    #[serde(default)]
    pub draft: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PartDetail {
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub name: String,
    #[serde(default, rename = "type")]
    pub part_type: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub can_delete: bool,
    #[serde(default)]
    pub uexp_size: u64,
    #[serde(default)]
    pub asset_info: Option<AssetInfo>,
    #[serde(default)]
    pub properties: HashMap<String, PropertyValue>,
    #[serde(default)]
    pub metadata: Option<PartMetadata>,
    #[serde(default)]
    pub state_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AssetInfo {
    #[serde(default)]
    pub class_type: String,
    #[serde(default)]
    pub asset_name: String,
    #[serde(default)]
    pub asset_path: String,
    #[serde(default)]
    pub torque_curve_name: Option<String>,
    #[serde(default)]
    pub sound_refs: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PropertyValue {
    #[serde(default)]
    pub raw: Value,
    #[serde(default)]
    pub display: String,
    #[serde(default)]
    pub unit: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PartMetadata {
    #[serde(default)]
    pub variant: Option<String>,
    #[serde(default)]
    pub estimated_hp: Option<f64>,
    #[serde(default)]
    pub max_torque_nm: Option<f64>,
    #[serde(default)]
    pub max_rpm: Option<f64>,
    #[serde(default)]
    pub is_ev: Option<bool>,
    #[serde(default)]
    pub sound: Option<CurrentSound>,
    #[serde(default)]
    pub shop: Option<ShopMeta>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CurrentSound {
    #[serde(default)]
    pub dir: Option<String>,
    #[serde(default)]
    pub cue: Option<String>,
    #[serde(default)]
    pub valid: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ShopMeta {
    #[serde(default)]
    pub display_name: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub price: Option<i64>,
    #[serde(default)]
    pub weight: Option<f64>,
    #[serde(default)]
    pub exists: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeRequest {
    pub id: u64,
    pub cmd: String,
    pub args: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BridgeResponse {
    pub id: u64,
    #[serde(default)]
    pub ok: bool,
    #[serde(default)]
    pub result: Option<Value>,
    #[serde(default)]
    pub error: Option<String>,
}
