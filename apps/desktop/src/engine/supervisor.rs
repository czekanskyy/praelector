// SPDX-License-Identifier: Apache-2.0
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use rand::RngExt;

use crate::engine::logbuf::RollingLogBuffer;
use crate::engine::ready::{parse_ready_line, ReadyPayload};
use crate::paths::get_data_dir;

fn find_workspace_root() -> Option<PathBuf> {
    if let Ok(root) = std::env::var("PRAELECTOR_WORKSPACE_ROOT") {
        let p = PathBuf::from(root);
        if p.join("engine").join("pyproject.toml").exists() {
            return Some(p);
        }
    }
    if let Ok(mut current) = std::env::current_dir() {
        for _ in 0..5 {
            if current.join("engine").join("pyproject.toml").exists() {
                return Some(current);
            }
            if let Some(parent) = current.parent() {
                current = parent.to_path_buf();
            } else {
                break;
            }
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        let mut current = exe;
        for _ in 0..6 {
            if current.join("engine").join("pyproject.toml").exists() {
                return Some(current);
            }
            if let Some(parent) = current.parent() {
                current = parent.to_path_buf();
            } else {
                break;
            }
        }
    }
    None
}

#[derive(Clone)]
pub struct EngineHandle {
    pub base_url: String,
    pub token: String,
    pub version: String,
    pub schema: u32,
    pub log_buffer: RollingLogBuffer,
}

pub struct EngineSupervisor {
    child: Option<Child>,
    handle: EngineHandle,
    is_running: Arc<AtomicBool>,
    #[cfg(windows)]
    _job: Option<crate::engine::job_object_win::win::JobObject>,
}

impl EngineSupervisor {
    pub fn spawn() -> Result<Self, String> {
        // 1. Generate 32-byte random authentication token
        let mut token_bytes = [0u8; 32];
        rand::rng().fill(&mut token_bytes);
        let token: String = token_bytes.iter().map(|b| format!("{:02x}", b)).collect();

        // 2. Resolve engine command
        let engine_cmd = std::env::var("PRAELECTOR_ENGINE_CMD").unwrap_or_else(|_| {
            // Default dev mode invocation
            "uv run --project engine praelector-engine".to_string()
        });

        let parts: Vec<&str> = engine_cmd.split_whitespace().collect();
        if parts.is_empty() {
            return Err("Empty engine command".into());
        }

        let mut cmd = Command::new(parts[0]);
        for arg in &parts[1..] {
            cmd.arg(arg);
        }

        if let Some(workspace_root) = find_workspace_root() {
            log::info!(
                "Setting engine working directory to: {}",
                workspace_root.display()
            );
            cmd.current_dir(&workspace_root);
        }

        let parent_pid = std::process::id();
        let data_dir = get_data_dir();
        std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

        cmd.env("PRAELECTOR_TOKEN", &token)
            .env(
                "PRAELECTOR_DATA_DIR",
                data_dir.to_string_lossy().to_string(),
            )
            .env("PRAELECTOR_LOG_LEVEL", "INFO")
            .env("PRAELECTOR_PARENT_PID", parent_pid.to_string())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(unix)]
        crate::engine::pgroup_unix::unix::set_process_group(&mut cmd);

        log::info!("Spawning engine sidecar with command: {}", engine_cmd);
        let mut child = cmd
            .spawn()
            .map_err(|e| format!("Failed to spawn engine: {}", e))?;

        #[cfg(windows)]
        let job = match crate::engine::job_object_win::win::JobObject::create() {
            Ok(job) => {
                use std::os::windows::io::AsRawHandle;
                unsafe {
                    let _ = job.assign_process(child.as_raw_handle() as _);
                }
                Some(job)
            }
            Err(e) => {
                log::warn!("Failed to create Windows Job Object: {}", e);
                None
            }
        };

        let stdout = child
            .stdout
            .take()
            .ok_or("Failed to capture child stdout")?;
        let stderr = child
            .stderr
            .take()
            .ok_or("Failed to capture child stderr")?;

        let log_buffer = RollingLogBuffer::new(200);

        // Reader channel for the ready line
        let (ready_tx, ready_rx) = std::sync::mpsc::channel::<ReadyPayload>();

        // Stdout reader thread
        let log_buf_out = log_buffer.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            let mut sent_ready = false;
            for line in reader.lines().map_while(Result::ok) {
                if !sent_ready {
                    if let Some(payload) = parse_ready_line(&line) {
                        let _ = ready_tx.send(payload);
                        sent_ready = true;
                    }
                }
                log_buf_out.push(line);
            }
        });

        // Stderr reader thread
        let log_buf_err = log_buffer.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                log_buf_err.push(line);
            }
        });

        // Wait for handshake with 30s timeout while checking child liveness
        let start = Instant::now();
        let timeout = Duration::from_secs(30);
        let ready_payload = loop {
            match ready_rx.recv_timeout(Duration::from_millis(100)) {
                Ok(payload) => break payload,
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                    // Check if child process has exited prematurely
                    match child.try_wait() {
                        Ok(Some(status)) => {
                            std::thread::sleep(Duration::from_millis(150));
                            let last_logs = log_buffer.lines().join("\n");
                            return Err(format!(
                                "Engine process exited prematurely with status: {}.\nEngine output:\n{}",
                                status, last_logs
                            ));
                        }
                        Ok(None) => {
                            if start.elapsed() >= timeout {
                                let last_logs = log_buffer.lines().join("\n");
                                return Err(format!(
                                    "Timed out waiting for engine ready handshake (30s).\nEngine output:\n{}",
                                    last_logs
                                ));
                            }
                        }
                        Err(e) => {
                            return Err(format!("Failed to monitor engine child process: {}", e));
                        }
                    }
                }
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                    // Transmitter hung up without sending ready payload
                    std::thread::sleep(Duration::from_millis(150));
                    let status_str = match child.try_wait() {
                        Ok(Some(status)) => format!("{}", status),
                        Ok(None) => "still running (stdout closed)".to_string(),
                        Err(e) => format!("unknown ({})", e),
                    };
                    let last_logs = log_buffer.lines().join("\n");
                    return Err(format!(
                        "Engine stdout closed unexpectedly without ready handshake (child status: {}).\nEngine output:\n{}",
                        status_str, last_logs
                    ));
                }
            }
        };

        let base_url = format!("http://127.0.0.1:{}/v1", ready_payload.port);
        log::info!("Engine ready at {} (pid: {})", base_url, ready_payload.pid);

        let is_running = Arc::new(AtomicBool::new(true));

        // Start health monitor
        let monitor_url = format!("{}/health", base_url);
        let monitor_token = token.clone();
        let running_flag = is_running.clone();

        std::thread::spawn(move || {
            let client = reqwest::blocking::Client::builder()
                .timeout(Duration::from_secs(3))
                .build()
                .unwrap();

            let mut consecutive_failures = 0;

            while running_flag.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_secs(5));
                if !running_flag.load(Ordering::SeqCst) {
                    break;
                }

                let res = client
                    .get(&monitor_url)
                    .header("Authorization", format!("Bearer {}", monitor_token))
                    .send();

                match res {
                    Ok(resp) if resp.status().is_success() => {
                        consecutive_failures = 0;
                    }
                    _ => {
                        consecutive_failures += 1;
                        log::warn!(
                            "Engine health poll failed (count: {})",
                            consecutive_failures
                        );
                        if consecutive_failures >= 3 {
                            log::error!("Engine failed 3 consecutive health checks");
                            break;
                        }
                    }
                }
            }
        });

        let handle = EngineHandle {
            base_url,
            token,
            version: ready_payload.version,
            schema: ready_payload.schema,
            log_buffer,
        };

        Ok(Self {
            child: Some(child),
            handle,
            is_running,
            #[cfg(windows)]
            _job: job,
        })
    }

    pub fn handle(&self) -> EngineHandle {
        self.handle.clone()
    }

    pub fn shutdown(&mut self) {
        self.is_running.store(false, Ordering::SeqCst);

        // Attempt graceful POST /v1/shutdown
        let shutdown_url = format!("{}/shutdown", self.handle.base_url);
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build()
            .unwrap();

        let _ = client
            .post(&shutdown_url)
            .header("Authorization", format!("Bearer {}", self.handle.token))
            .send();

        // Wait up to 5s for clean child exit
        if let Some(mut child) = self.child.take() {
            let start = Instant::now();
            loop {
                match child.try_wait() {
                    Ok(Some(_status)) => break,
                    Ok(None) => {
                        if start.elapsed() > Duration::from_secs(5) {
                            log::warn!("Killing unresponsive engine child process");
                            let _ = child.kill();
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(100));
                    }
                    Err(_) => {
                        let _ = child.kill();
                        break;
                    }
                }
            }
        }
    }
}

impl Drop for EngineSupervisor {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_workspace_root() {
        let root = find_workspace_root();
        assert!(root.is_some(), "Workspace root should be discovered");
        let root = root.unwrap();
        assert!(
            root.join("engine").join("pyproject.toml").exists(),
            "Discovered root {:?} does not contain engine/pyproject.toml",
            root
        );
    }

    #[test]
    #[ignore]
    fn test_engine_handshake_integration() {
        let mut supervisor = EngineSupervisor::spawn().expect("Should spawn engine and handshake");
        let handle = supervisor.handle();
        assert!(handle.base_url.starts_with("http://127.0.0.1:"));
        assert!(!handle.token.is_empty());
        assert_eq!(handle.schema, 1);
        supervisor.shutdown();
    }
}
