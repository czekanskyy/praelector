// SPDX-License-Identifier: Apache-2.0
use serde::Deserialize;

pub const READY_PREFIX: &str = "PRAELECTOR_READY ";

#[derive(Debug, Clone, Deserialize)]
pub struct ReadyPayload {
    pub port: u16,
    pub pid: u32,
    pub version: String,
    pub schema: u32,
}

pub fn parse_ready_line(line: &str) -> Option<ReadyPayload> {
    if let Some(stripped) = line.strip_prefix(READY_PREFIX) {
        serde_json::from_str::<ReadyPayload>(stripped.trim()).ok()
    } else {
        None
    }
}
