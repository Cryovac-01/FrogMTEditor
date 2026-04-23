use crate::models::{BridgeRequest, BridgeResponse};
use crate::runtime::DesktopRuntime;
use anyhow::{anyhow, Context, Result};
use parking_lot::Mutex;
use serde::de::DeserializeOwned;
use serde_json::{json, Value};
use std::io::{BufReader, Read, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Arc;

#[derive(Clone)]
pub struct BackendHandle {
    inner: Arc<Mutex<BackendClient>>,
}

struct BackendClient {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl BackendHandle {
    pub fn start(runtime: &DesktopRuntime) -> Result<Self> {
        let mut child = Command::new(&runtime.python_exe)
            .arg("-X")
            .arg("utf8")
            .arg("-u")
            .arg("-B")
            .arg(&runtime.bridge_script)
            .current_dir(&runtime.root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .with_context(|| format!("failed to launch desktop bridge: {}", runtime.bridge_script.display()))?;

        let stdin = child.stdin.take().context("desktop bridge stdin was unavailable")?;
        let stdout = child.stdout.take().context("desktop bridge stdout was unavailable")?;

        Ok(Self {
            inner: Arc::new(Mutex::new(BackendClient {
                child,
                stdin,
                stdout: BufReader::new(stdout),
                next_id: 1,
            })),
        })
    }

    pub fn send_value(&self, cmd: &str, args: Value) -> Result<Value> {
        let mut client = self.inner.lock();
        client.send_value(cmd, args)
    }

    pub fn send_typed<T: DeserializeOwned>(&self, cmd: &str, args: Value) -> Result<T> {
        let value = self.send_value(cmd, args)?;
        serde_json::from_value(value).with_context(|| format!("failed to decode desktop response for {cmd}"))
    }

    pub fn ping(&self) -> Result<Value> {
        self.send_value("ping", json!({}))
    }
}

impl BackendClient {
    fn send_value(&mut self, cmd: &str, args: Value) -> Result<Value> {
        let request = BridgeRequest {
            id: self.next_id,
            cmd: cmd.to_string(),
            args,
        };
        self.next_id += 1;

        let request_bytes = serde_json::to_vec(&request).context("failed to encode desktop request")?;
        self.stdin
            .write_all(&(request_bytes.len() as u32).to_le_bytes())
            .context("failed to write desktop request length")?;
        self.stdin
            .write_all(&request_bytes)
            .context("failed to write desktop request body")?;
        self.stdin.flush().context("failed to flush desktop request")?;

        let mut len_buf = [0u8; 4];
        self.stdout
            .read_exact(&mut len_buf)
            .context("failed to read desktop response length")?;
        let response_len = u32::from_le_bytes(len_buf) as usize;
        let mut response_buf = vec![0u8; response_len];
        self.stdout
            .read_exact(&mut response_buf)
            .context("failed to read desktop response body")?;
        let response: BridgeResponse =
            serde_json::from_slice(&response_buf).context("failed to decode desktop response")?;

        if !response.ok {
            return Err(anyhow!(
                "{}",
                response.error.unwrap_or_else(|| format!("desktop command {cmd} failed"))
            ));
        }

        response
            .result
            .ok_or_else(|| anyhow!("desktop command {cmd} returned no result"))
    }
}

impl Drop for BackendClient {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
