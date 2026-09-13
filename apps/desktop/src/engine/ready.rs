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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_valid_ready_line() {
        let line =
            r#"PRAELECTOR_READY {"port": 5000, "pid": 1234, "version": "0.1.0", "schema": 1}"#;
        let payload = parse_ready_line(line).expect("Should parse valid ready line");
        assert_eq!(payload.port, 5000);
        assert_eq!(payload.pid, 1234);
        assert_eq!(payload.version, "0.1.0");
        assert_eq!(payload.schema, 1);
    }

    #[test]
    fn test_parse_invalid_ready_line() {
        assert!(parse_ready_line("Some random log line").is_none());
        assert!(parse_ready_line("PRAELECTOR_READY not-json").is_none());
    }
}
