// SPDX-License-Identifier: Apache-2.0
//! Commands the WebView may call (REPO_LAYOUT.md §3).
//!
//! `engine_endpoint` is the only one that returns the bearer token. Everything
//! else — status, logs, paths, dialogs — is safe to dump into a bug report.

use serde::Serialize;
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

use crate::clipboard;
use crate::engine::{EngineEndpoint, EngineFailure, EngineHandle};
use crate::paths::{AppPaths, AppPathsDto};

/// Returned when the engine has not published an endpoint and has not failed.
/// The message is the code on purpose: user-facing prose lives in the UI catalogues.
const NOT_READY: &str = "engine.not_ready";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CopyLogsResult {
    pub text: String,
    pub copied: bool,
}

/// Where the engine is, and the bearer token. `None` is not used: a missing
/// endpoint is [`EngineFailure`] so the UI can localise `error.code`.
#[tauri::command]
pub fn engine_endpoint(engine: State<'_, EngineHandle>) -> Result<EngineEndpoint, EngineFailure> {
    if let Some(endpoint) = engine.shared().endpoint() {
        return Ok(endpoint);
    }
    Err(engine.shared().status().error.unwrap_or(EngineFailure {
        code: NOT_READY.to_string(),
        message: NOT_READY.to_string(),
    }))
}

/// Liveness only. The token is not on this struct.
#[tauri::command]
pub fn engine_status(engine: State<'_, EngineHandle>) -> crate::engine::EngineStatusReport {
    engine.shared().status()
}

/// The rolling engine buffer, already redacted.
#[tauri::command]
pub fn engine_logs(engine: State<'_, EngineHandle>) -> String {
    engine.shared().render_logs()
}

/// Redacted buffer plus whether it landed on the system clipboard.
#[tauri::command]
pub fn copy_engine_logs(engine: State<'_, EngineHandle>) -> CopyLogsResult {
    let text = engine.shared().render_logs();
    let copied = clipboard::copy_text(&text);
    CopyLogsResult { text, copied }
}

/// Open `path` with the platform default handler. Wire paths are POSIX-style;
/// the opener wants the native separator.
#[tauri::command]
pub fn open_path(
    app: tauri::AppHandle,
    engine: State<'_, EngineHandle>,
    path: String,
) -> Result<(), String> {
    let native = crate::paths::from_wire(&path);
    app.opener()
        .open_path(native.display().to_string(), None::<&str>)
        .map_err(|err| redact_error(&engine, &err.to_string()))
}

/// Native file picker. `None` is the user cancelling, not an error.
#[tauri::command]
pub async fn pick_file(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let (tx, rx) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_file(move |picked| {
        let _ = tx.send(picked.map(|path| file_path_to_wire(&path)));
    });
    match rx.await {
        Ok(path) => Ok(path),
        Err(_) => Ok(None),
    }
}

/// Resolved directories, in the same POSIX wire form the engine serialises.
#[tauri::command]
pub fn app_paths(paths: State<'_, AppPaths>) -> AppPathsDto {
    AppPathsDto::from(&*paths)
}

fn file_path_to_wire(path: &tauri_plugin_dialog::FilePath) -> String {
    if let Some(native) = path.as_path() {
        crate::paths::to_wire(native)
    } else {
        path.to_string()
    }
}

fn redact_error(engine: &EngineHandle, text: &str) -> String {
    match engine.shared().endpoint() {
        Some(endpoint) => crate::logging::redact(text, &endpoint.token).into_owned(),
        None => text.to_string(),
    }
}
