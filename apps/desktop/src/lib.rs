// SPDX-License-Identifier: Apache-2.0
//! Praelector desktop shell: window, sidecar lifecycle, native dialogs.
//!
//! Product logic stays in the engine. This crate resolves paths, supervises the
//! sidecar, and hands the WebView a token exactly once.

mod clipboard;
mod commands;
pub mod engine;
mod logging;
mod paths;

#[cfg(all(windows, test))]
mod windows_test_manifest;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use tauri::{Emitter, Manager, RunEvent};
use tokio::sync::{watch, Notify};

use crate::engine::supervisor::{supervise, Control, LaunchEnv, OsHost, SupervisorEvent, Timing};
use crate::engine::{EngineError, EngineFailure, EngineHandle, Shared, EVENT_FAILURE, EVENT_STATE};
use crate::paths::AppPaths;

/// Stop flag for the supervisor task. Managed so the exit handler can reach it
/// without capturing the setup closure's locals twice.
struct StopHandle {
    stop: watch::Sender<bool>,
    done: Arc<Notify>,
}

/// Build the window, start supervision, and block on the Tauri event loop.
pub fn run() -> tauri::Result<()> {
    let paths = AppPaths::from_process_env();
    let level = logging::level_from_env(&|key| std::env::var(key).ok());
    let shared = Shared::new();
    let engine = EngineHandle(Arc::clone(&shared));
    let setup_paths = paths.clone();
    let exit_once = Arc::new(AtomicBool::new(false));

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            focus_main(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(logging::plugin(&paths.log_dir, level))
        .manage(engine)
        .setup(move |app| {
            start_supervisor(app, setup_paths, level, shared);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_endpoint,
            commands::engine_status,
            commands::engine_logs,
            commands::copy_engine_logs,
            commands::open_path,
            commands::pick_file,
            commands::app_paths,
        ]);

    let app = builder.build(tauri::generate_context!())?;
    app.run(move |app, event| {
        if let RunEvent::ExitRequested { api, .. } = event {
            on_exit_requested(app, &exit_once, api);
        }
    });
    Ok(())
}

fn start_supervisor(
    app: &mut tauri::App,
    paths: AppPaths,
    level: log::LevelFilter,
    shared: Arc<Shared>,
) {
    if let Err(err) = paths.ensure_dirs() {
        log::error!("cannot create shell directories: {err}");
    }
    let resource_dir = app.path().resource_dir().ok();
    let paths = paths.with_resource_dir(resource_dir);
    log::info!(
        "shell paths data={} logs={}",
        paths.data_dir.display(),
        paths.log_dir.display()
    );
    let launch = LaunchEnv {
        paths: paths.clone(),
        dev_search_roots: engine::supervisor::dev_search_roots(),
        log_level: logging::level_name(level).to_string(),
        parent_pid: std::process::id(),
        engine_cmd: std::env::var(engine::config::ENV_ENGINE_CMD).ok(),
    };
    app.manage(paths.clone());

    let host = match OsHost::new() {
        Ok(host) => host,
        Err(err) => {
            surface_failure(app.handle(), &shared, &paths, &err);
            return;
        }
    };

    let (stop_tx, stop_rx) = watch::channel(false);
    let done = Arc::new(Notify::new());
    app.manage(StopHandle {
        stop: stop_tx,
        done: Arc::clone(&done),
    });

    let app_handle = app.handle().clone();
    let task_shared = Arc::clone(&shared);
    tauri::async_runtime::spawn(async move {
        let sink_app = app_handle.clone();
        let sink_shared = Arc::clone(&task_shared);
        let sink_paths = launch.paths.clone();
        supervise(
            host,
            task_shared,
            launch,
            Timing::production(),
            Control {
                stop: stop_rx,
                done,
                sink: Box::new(move |event| on_event(&sink_app, &sink_shared, &sink_paths, event)),
            },
        )
        .await;
    });
}

fn on_event(app: &tauri::AppHandle, shared: &Shared, paths: &AppPaths, event: SupervisorEvent) {
    match event {
        SupervisorEvent::State(status) => {
            let _ = app.emit(EVENT_STATE, status);
        }
        SupervisorEvent::Failure(failure) => {
            let _ = app.emit(EVENT_FAILURE, &failure);
            let logs = shared.render_logs();
            let diagnostics = paths.log_dir.join("engine-diagnostics.txt");
            if std::fs::write(&diagnostics, &logs).is_ok() {
                log::error!("engine diagnostics written to {}", diagnostics.display());
            }
            let _ = clipboard::copy_text(&logs);
            show_fatal_dialog(app, &failure);
        }
    }
}

fn surface_failure(app: &tauri::AppHandle, shared: &Shared, paths: &AppPaths, err: &EngineError) {
    shared.fail(err);
    let failure = EngineFailure::from(err);
    on_event(app, shared, paths, SupervisorEvent::State(shared.status()));
    on_event(app, shared, paths, SupervisorEvent::Failure(failure));
}

/// Code plus the error's `Display` text. No extra sentence: the UI localises
/// `failure.code`, and this dialog only exists until that panel ships.
fn show_fatal_dialog(app: &tauri::AppHandle, failure: &EngineFailure) {
    use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

    let message = format!("{}\n{}", failure.code, failure.message);
    app.dialog()
        .message(message)
        .title(failure.code.as_str())
        .kind(MessageDialogKind::Error)
        .buttons(MessageDialogButtons::Ok)
        .show(|_| {});
}

fn focus_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn on_exit_requested(app: &tauri::AppHandle, exit_once: &AtomicBool, api: tauri::ExitRequestApi) {
    // `swap` returns the previous value. The first request is the one that has
    // to wait for the engine; the second is the `app.exit` we issue ourselves.
    if exit_once.swap(true, Ordering::SeqCst) {
        return;
    }
    api.prevent_exit();
    let handle = app.clone();
    let Some((stop_tx, done)) = handle.try_state::<StopHandle>().map(|stop| {
        let stop_tx = stop.stop.clone();
        let done = Arc::clone(&stop.done);
        (stop_tx, done)
    }) else {
        handle.exit(0);
        return;
    };
    tauri::async_runtime::spawn(async move {
        let _ = stop_tx.send(true);
        tokio::select! {
            _ = done.notified() => {}
            _ = tokio::time::sleep(std::time::Duration::from_secs(20)) => {
                log::error!("engine shutdown timed out; exiting");
            }
        }
        handle.exit(0);
    });
}
