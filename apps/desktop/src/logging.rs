// SPDX-License-Identifier: Apache-2.0
//! `tauri-plugin-log` wiring (PLAN.md §1.7, LM-03).
//!
//! The engine keeps its own JSON log at `<logDir>/engine.log`; this file is the
//! *shell's* log and deliberately covers only lifecycle events, because the fatal
//! panel already shows the last 200 engine lines from the rolling buffer.

use std::path::Path;

use log::LevelFilter;
use tauri_plugin_log::{RotationStrategy, Target, TargetKind};

/// `desktop.log` plus one rotated predecessor, so a stuck engine cannot fill the
/// disk over a long session.
const MAX_LOG_BYTES: u128 = 5 * 1024 * 1024;

/// What replaces a secret in anything that reaches a log or the fatal panel.
pub const REDACTION: &str = "[redacted]";

/// Environment variable shared with the engine, so one setting controls both logs.
pub const ENV_LOG_LEVEL: &str = "PRAELECTOR_LOG_LEVEL";

/// Build the log plugin for `log_dir`.
///
/// Mirroring to stderr only happens in debug builds: a release build started from
/// a terminal would otherwise duplicate every line into the user's shell, and on
/// Windows a GUI-subsystem binary has no stderr to write to at all.
pub fn plugin(log_dir: &Path, level: LevelFilter) -> tauri::plugin::TauriPlugin<tauri::Wry> {
    let mut targets = vec![Target::new(TargetKind::Folder {
        path: log_dir.to_path_buf(),
        file_name: Some("desktop".to_string()),
    })];
    if cfg!(debug_assertions) {
        targets.push(Target::new(TargetKind::Stderr));
    }

    tauri_plugin_log::Builder::new()
        .targets(targets)
        .level(level)
        .max_file_size(MAX_LOG_BYTES)
        .rotation_strategy(RotationStrategy::KeepOne)
        .build()
}

/// Level from `PRAELECTOR_LOG_LEVEL`, defaulting to `INFO` in release and `DEBUG`
/// in a debug build (the same default the engine uses, so the two agree).
pub fn level_from_env(var: &dyn Fn(&str) -> Option<String>) -> LevelFilter {
    let default = if cfg!(debug_assertions) {
        "DEBUG"
    } else {
        "INFO"
    };
    let raw = var(ENV_LOG_LEVEL).unwrap_or_default();
    parse_level(raw.trim()).unwrap_or_else(|| parse_level(default).unwrap_or(LevelFilter::Info))
}

/// The engine's `PRAELECTOR_LOG_LEVEL` vocabulary (`logging.configure_logging`).
pub fn level_name(level: LevelFilter) -> &'static str {
    match level {
        LevelFilter::Off => "OFF",
        LevelFilter::Error => "ERROR",
        LevelFilter::Warn => "WARN",
        LevelFilter::Info => "INFO",
        LevelFilter::Debug => "DEBUG",
        LevelFilter::Trace => "TRACE",
    }
}

fn parse_level(raw: &str) -> Option<LevelFilter> {
    match raw.to_ascii_uppercase().as_str() {
        "" => None,
        "OFF" => Some(LevelFilter::Off),
        "ERROR" => Some(LevelFilter::Error),
        "WARN" | "WARNING" => Some(LevelFilter::Warn),
        "INFO" => Some(LevelFilter::Info),
        "DEBUG" => Some(LevelFilter::Debug),
        "TRACE" => Some(LevelFilter::Trace),
        _ => None,
    }
}

/// Replace every occurrence of `secret` with [`REDACTION`].
///
/// The launch token is the one secret this process holds, and it is the thing a
/// diagnostics dump is most likely to contain: the UI passes it as a WS query
/// parameter (`security.websocket_token`), so it can appear in a URL that ends up
/// in a panic message or a `reqwest` error. This is the last line of defence — the
/// first rule is simply never to pass it to a log statement.
///
/// The token is URL-safe base64, so `-` and `_` are never percent-encoded and a
/// plain substring match catches both the raw and the query-parameter form.
pub fn redact<'a>(text: &'a str, secret: &str) -> std::borrow::Cow<'a, str> {
    if secret.is_empty() || !text.contains(secret) {
        return std::borrow::Cow::Borrowed(text);
    }
    std::borrow::Cow::Owned(text.replace(secret, REDACTION))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn redact_replaces_every_occurrence() {
        let out = redact(
            "ws://127.0.0.1:1/?token=abc-DEF_123 then abc-DEF_123",
            "abc-DEF_123",
        );
        assert_eq!(
            out,
            format!("ws://127.0.0.1:1/?token={REDACTION} then {REDACTION}")
        );
    }

    #[test]
    fn redact_borrows_when_there_is_nothing_to_hide() {
        let text = "engine listening on 127.0.0.1:54321";
        assert!(matches!(
            redact(text, "secret"),
            std::borrow::Cow::Borrowed(_)
        ));
        // An empty secret must not turn every line into a wall of redactions.
        assert_eq!(redact(text, ""), text);
    }

    #[test]
    fn level_parsing_is_case_insensitive_and_tolerates_garbage() {
        let var = |_: &str| Some("warn".to_string());
        assert_eq!(level_from_env(&var), LevelFilter::Warn);
        let var = |_: &str| Some("nonsense".to_string());
        assert_eq!(level_from_env(&var), default_level());
        let var = |_: &str| None;
        assert_eq!(level_from_env(&var), default_level());
        let var = |_: &str| Some("  TRACE  ".to_string());
        assert_eq!(level_from_env(&var), LevelFilter::Trace);
    }

    fn default_level() -> LevelFilter {
        if cfg!(debug_assertions) {
            LevelFilter::Debug
        } else {
            LevelFilter::Info
        }
    }

    #[test]
    fn the_plugin_builds_against_a_directory_that_does_not_exist_yet() {
        // The plugin creates the folder on first write; building it must not touch
        // the filesystem, because `run()` registers the plugin before `setup`.
        let _ = plugin(Path::new("Z:/definitely/not/here"), LevelFilter::Info);
    }
}
