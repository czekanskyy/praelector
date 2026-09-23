// SPDX-License-Identifier: Apache-2.0
//! Optional end-to-end check. `cargo test --features engine-it` spawns the real
//! engine through `uv`. Off by default so CI does not need a Python toolchain.
#![cfg(feature = "engine-it")]
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use praelector_desktop_lib::engine::supervisor::{
    dev_search_roots, supervise, Control, LaunchEnv, OsHost, Timing,
};
use praelector_desktop_lib::engine::{EngineState, Shared};
use praelector_desktop_lib::paths::AppPaths;

#[tokio::test]
async fn the_real_engine_announces_ready() {
    let root = std::env::temp_dir().join(format!("praelector-engine-it-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let paths = AppPaths {
        data_dir: root.join("data"),
        config_dir: root.join("config"),
        log_dir: root.join("logs"),
        projects_dir: root.join("projects"),
        resource_dir: None,
    };
    paths.ensure_dirs().expect("shell directories");

    let mut roots = dev_search_roots();
    roots.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")));
    let shared = Shared::new();
    let host = OsHost::new().expect("supervisor host");
    let (stop_tx, stop_rx) = tokio::sync::watch::channel(false);
    let done = Arc::new(tokio::sync::Notify::new());
    let launch = LaunchEnv {
        paths,
        dev_search_roots: roots,
        log_level: "INFO".to_string(),
        parent_pid: std::process::id(),
        engine_cmd: None,
    };
    let watched = Arc::clone(&shared);
    let finished = Arc::clone(&done);
    tokio::spawn(async move {
        supervise(
            host,
            watched,
            launch,
            Timing::production(),
            Control {
                stop: stop_rx,
                done: finished,
                sink: Box::new(|_| {}),
            },
        )
        .await;
    });

    let mut ready = false;
    let deadline = tokio::time::Instant::now() + Duration::from_secs(90);
    while tokio::time::Instant::now() < deadline {
        match shared.status().state {
            EngineState::Ready => {
                ready = true;
                break;
            }
            EngineState::Fatal => break,
            EngineState::Launching | EngineState::Restarting => {}
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }

    let _ = stop_tx.send(true);
    let _ = tokio::time::timeout(Duration::from_secs(20), done.notified()).await;
    let status = shared.status();
    assert!(ready, "engine did not become ready: {status:?}");
    assert!(shared.endpoint().is_some());
    let _ = std::fs::remove_dir_all(&root);
}
