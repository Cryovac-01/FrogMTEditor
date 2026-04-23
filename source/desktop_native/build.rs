use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn main() {
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=app.rc");
    println!("cargo:rerun-if-changed=app.manifest");

    if Path::new("app.rc").exists() {
        embed_resource::compile("app.rc", std::iter::empty::<&str>());
    }

    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("missing manifest dir"));
    let payload_zip = manifest_dir.join("runtime_payload.zip");
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("missing OUT_DIR"));
    let generated = out_dir.join("embedded_runtime.rs");

    if payload_zip.is_file() {
        println!("cargo:rerun-if-changed={}", payload_zip.display());
        let payload = fs::read(&payload_zip).expect("failed to read runtime payload");
        let hash = hex_sha256(&payload);
        fs::write(
            &generated,
            format!(
                "pub const EMBEDDED_RUNTIME_BYTES: &[u8] = include_bytes!(r#\"{}\"#);\n\
                 pub const EMBEDDED_RUNTIME_HASH: &str = \"{}\";\n",
                payload_zip.display(),
                hash
            ),
        )
        .expect("failed to write embedded runtime source");
    } else {
        fs::write(
            &generated,
            "pub const EMBEDDED_RUNTIME_BYTES: &[u8] = &[];\n\
             pub const EMBEDDED_RUNTIME_HASH: &str = \"dev-runtime\";\n",
        )
        .expect("failed to write empty embedded runtime source");
    }
}

fn hex_sha256(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        let _ = write!(&mut out, "{byte:02x}");
    }
    out
}
