// SPDX-License-Identifier: Apache-2.0
pub mod commands;
pub mod engine;
pub mod paths;

use std::sync::Mutex;
use tauri::Manager;

use crate::commands::{app_paths, engine_endpoint, engine_logs};
use crate::engine::EngineSupervisor;

pub fn run() {
    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|_app, _argv, _cwd| {
            log::info!("Another instance attempted to start; focusing existing window");
        }))
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Spawn engine sidecar and obtain handshake
            log::info!("Initializing EngineSupervisor...");
            let supervisor =
                EngineSupervisor::spawn().expect("Failed to initialize engine supervisor");
            let handle = supervisor.handle();

            app.manage(handle);
            app.manage(Mutex::new(supervisor));

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine_endpoint,
            engine_logs,
            app_paths
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
