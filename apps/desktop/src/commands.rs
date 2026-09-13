// SPDX-License-Identifier: Apache-2.0
use serde::Serialize;
use tauri::State;

use crate::engine::EngineHandle;
use crate::paths::{get_data_dir, get_log_dir};

#[derive(Serialize)]
pub struct EngineEndpointResponse {
    pub base_url: String,
    pub token: String,
    pub version: String,
    pub schema: u32,
}

#[derive(Serialize)]
pub struct AppPathsResponse {
    pub data_dir: String,
    pub log_dir: String,
}

#[tauri::command]
pub fn engine_endpoint(handle: State<EngineHandle>) -> EngineEndpointResponse {
    EngineEndpointResponse {
        base_url: handle.base_url.clone(),
        token: handle.token.clone(),
        version: handle.version.clone(),
        schema: handle.schema,
    }
}

#[tauri::command]
pub fn engine_logs(handle: State<EngineHandle>) -> Vec<String> {
    handle.log_buffer.lines()
}

#[tauri::command]
pub fn app_paths() -> AppPathsResponse {
    AppPathsResponse {
        data_dir: get_data_dir().to_string_lossy().to_string(),
        log_dir: get_log_dir().to_string_lossy().to_string(),
    }
}
