// SPDX-License-Identifier: Apache-2.0
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use rand::RngCore;

use crate::engine::logbuf::RollingLogBuffer;
use crate::engine::ready::{parse_ready_line, ReadyPayload};
use crate::paths::get_data_dir;

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
}

impl EngineSupervisor {
    pub fn spawn() -> Result<Self, String> {
        // 1. Generate 32-byte random authentication token
        let mut token_bytes = [0u8; 32];
        rand::thread_rng().fill_bytes(&mut token_bytes);
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
        {
            if let Ok(job) = crate::engine::job_object_win::win::JobObject::create() {
                use std::os::windows::io::AsRawHandle;
                unsafe {
                    let _ = job.assign_process(child.as_raw_handle() as _);
                }
            }
        }

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

        // Wait for handshake with 30s timeout
        let ready_payload = ready_rx
            .recv_timeout(Duration::from_secs(30))
            .map_err(|_| {
                let last_logs = log_buffer.lines().join("\n");
                format!(
                    "Timed out waiting for engine ready handshake (30s).\nLast engine output:\n{}",
                    last_logs
                )
            })?;

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
