// SPDX-License-Identifier: Apache-2.0
//! The engine sidecar: what the shell knows about it, and how it fails.
//!
//! Everything the WebView learns about the engine arrives through
//! [`EngineHandle`] (managed as `tauri::State`) plus the [`EVENT_STATE`] and
//! [`EVENT_FAILURE`] events. The shell never interprets engine data beyond
//! liveness — REPO_LAYOUT.md §3: "Contains no product logic".

/// Lifecycle snapshot for the WebView. Payload is [`EngineStatusReport`] and
/// deliberately has no token.
pub const EVENT_STATE: &str = "engine://state";

/// Terminal failure. Payload is [`EngineFailure`]. The UI localises [`EngineFailure::code`].
pub const EVENT_FAILURE: &str = "engine://failure";

pub mod config;
pub mod logbuf;
pub mod ready;
pub mod supervisor;

#[cfg(windows)]
pub(crate) mod job_object_win;
#[cfg(unix)]
pub(crate) mod pgroup_unix;

use std::sync::{Arc, Mutex, RwLock};

use serde::Serialize;
use thiserror::Error;

use crate::engine::logbuf::{LogBuffer, LogSink, LogStream, DEFAULT_CAPACITY};

/// Everything that can go wrong between "spawn" and "the UI can talk to it".
///
/// Deliberately not `anyhow::Error`: the fatal panel shows a *stable reason code*
/// that the UI localises (PLAN.md D-16 applies to the shell for the same reason it
/// applies to the engine). The `Display` text is for `desktop.log` and for us, never
/// for the user.
#[derive(Debug, Error)]
pub enum EngineError {
    #[error("no engine binary found; searched: {searched:?}")]
    NotFound { searched: Vec<String> },

    #[error("cannot spawn the engine: {source}")]
    SpawnFailed {
        #[source]
        source: std::io::Error,
    },

    #[error("no readiness line within {timeout_s}s")]
    ReadyTimeout { timeout_s: u64 },

    #[error("the readiness announcement was unusable: {reason}")]
    ReadyMalformed { reason: String },

    #[error("the engine exited with code {code:?} before announcing readiness")]
    ExitedBeforeReady { code: Option<i32> },

    #[error("health endpoint unreachable {consecutive} times in a row: {reason}")]
    HealthUnreachable { consecutive: u32, reason: String },

    #[error("the engine did not exit within {timeout_s}s of POST /v1/shutdown")]
    ShutdownTimeout { timeout_s: u64 },

    #[error("cannot terminate the engine process: {source}")]
    KillFailed {
        #[source]
        source: std::io::Error,
    },

    #[error("gave up after {restarts} restarts within {window_s}s")]
    RestartBudgetExhausted { restarts: u32, window_s: u64 },

    // Not named `source`: thiserror treats that field name as `Error::source`,
    // which a plain string cannot satisfy.
    #[error("the engine HTTP client could not be built: {detail}")]
    HttpClient { detail: String },
}

impl EngineError {
    /// The stable code the UI maps onto an i18n key (PLAN.md D-16).
    pub fn code(&self) -> &'static str {
        match self {
            Self::NotFound { .. } => "engine.not_found",
            Self::SpawnFailed { .. } => "engine.spawn_failed",
            Self::ReadyTimeout { .. } => "engine.ready_timeout",
            Self::ReadyMalformed { .. } => "engine.ready_malformed",
            Self::ExitedBeforeReady { .. } => "engine.exited_before_ready",
            Self::HealthUnreachable { .. } => "engine.health_unreachable",
            Self::ShutdownTimeout { .. } => "engine.shutdown_timeout",
            Self::KillFailed { .. } => "engine.kill_failed",
            Self::RestartBudgetExhausted { .. } => "engine.restart_budget_exhausted",
            Self::HttpClient { .. } => "engine.http_client",
        }
    }

    /// Whether another attempt can plausibly succeed.
    ///
    /// A missing binary or a broken announcement is a contract violation, not a
    /// transient fault: retrying five times just delays the fatal panel by 31 s.
    pub fn is_retryable(&self) -> bool {
        !matches!(self, Self::NotFound { .. } | Self::ReadyMalformed { .. })
    }
}

/// The two things the WebView needs to reach the engine: where it is, and the
/// bearer token. Never logged — see [`crate::logging::redact`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineEndpoint {
    pub base_url: String,
    pub token: String,
}

impl EngineEndpoint {
    pub fn new(port: u16, token: impl Into<String>) -> Self {
        Self {
            base_url: format!("http://127.0.0.1:{port}"),
            token: token.into(),
        }
    }

    pub fn url(&self, path: &str) -> String {
        format!("{}{}", self.base_url, path)
    }
}

/// Lifecycle state as the UI understands it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub enum EngineState {
    /// No endpoint yet: first launch, or a restart in progress.
    #[default]
    Launching,
    /// An endpoint is published and health is answering.
    Ready,
    /// The previous engine is being torn down or the backoff is running.
    Restarting,
    /// The supervisor has stopped trying. `error_code` says why.
    Fatal,
}

/// A failure the UI can act on. `code` is [`EngineError::code`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineFailure {
    pub code: String,
    pub message: String,
}

impl From<&EngineError> for EngineFailure {
    fn from(err: &EngineError) -> Self {
        Self {
            code: err.code().to_string(),
            message: err.to_string(),
        }
    }
}

/// What `engine_status` returns. The token is *not* here — `engine_endpoint` is the
/// only command that hands it out, so a diagnostics dump can never include it.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineStatusReport {
    pub state: EngineState,
    pub restarts: u32,
    pub base_url: Option<String>,
    pub engine_pid: Option<u32>,
    pub engine_version: Option<String>,
    pub health_status: Option<String>,
    pub last_exit_code: Option<i32>,
    pub error: Option<EngineFailure>,
}

#[derive(Debug, Default)]
struct Inner {
    endpoint: Option<EngineEndpoint>,
    state: EngineState,
    restarts: u32,
    pid: Option<u32>,
    version: Option<String>,
    health_status: Option<String>,
    last_exit_code: Option<i32>,
    error: Option<EngineFailure>,
}

/// Everything the commands and the supervisor share.
///
/// Plain `std` locks on purpose: no critical section ever spans an `.await`, and a
/// supervisor that blocks the window thread while holding a mutex would be worse
/// than the race it was trying to avoid.
pub struct Shared {
    inner: RwLock<Inner>,
    logs: Mutex<LogBuffer>,
}

impl Shared {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            inner: RwLock::new(Inner::default()),
            logs: Mutex::new(LogBuffer::new(DEFAULT_CAPACITY)),
        })
    }

    /// Record one engine output line. A poisoned log mutex must not take the
    /// supervisor down, so poisoning is absorbed rather than propagated.
    pub fn record(&self, stream: LogStream, line: &str) {
        if let Ok(mut logs) = self.logs.lock() {
            logs.push(stream, line);
        }
    }

    /// Install the token so every buffered line is scrubbed as it arrives.
    pub fn set_secret(&self, token: &str) {
        if let Ok(mut logs) = self.logs.lock() {
            logs.set_secret(token);
        }
    }

    /// Remember another launch token. A restart rotates the secret while the
    /// previous process can still be flushing a line that contains the old one.
    pub fn add_secret(&self, token: &str) {
        if let Ok(mut logs) = self.logs.lock() {
            logs.add_secret(token);
        }
    }

    pub fn render_logs(&self) -> String {
        match self.logs.lock() {
            Ok(logs) => logs.render(),
            // Poisoning means something panicked mid-write; the tail we do have is
            // still the best diagnostics available.
            Err(poisoned) => poisoned.into_inner().render(),
        }
    }

    pub fn endpoint(&self) -> Option<EngineEndpoint> {
        self.read(|inner| inner.endpoint.clone())
    }

    pub fn status(&self) -> EngineStatusReport {
        self.read(|inner| EngineStatusReport {
            state: inner.state,
            restarts: inner.restarts,
            base_url: inner.endpoint.as_ref().map(|e| e.base_url.clone()),
            engine_pid: inner.pid,
            engine_version: inner.version.clone(),
            health_status: inner.health_status.clone(),
            last_exit_code: inner.last_exit_code,
            error: inner.error.clone(),
        })
    }

    /// A successful handshake: publish the endpoint and clear any previous failure.
    pub fn publish(&self, endpoint: EngineEndpoint, pid: u32, version: String) {
        if let Ok(mut inner) = self.inner.write() {
            inner.endpoint = Some(endpoint);
            inner.pid = Some(pid);
            inner.version = Some(version);
            inner.state = EngineState::Ready;
            inner.error = None;
            inner.last_exit_code = None;
        }
    }

    pub fn set_state(&self, state: EngineState) {
        if let Ok(mut inner) = self.inner.write() {
            inner.state = state;
            // The old endpoint is dead as soon as we start again; leaving it
            // published would let the UI keep polling a port nothing owns.
            if state != EngineState::Ready {
                inner.endpoint = None;
            }
        }
    }

    /// A new launch. Clears the published endpoint and any previous error so a
    /// restart is not still reported as fatal while the next process starts.
    pub fn begin_attempt(&self, state: EngineState) {
        if let Ok(mut inner) = self.inner.write() {
            inner.state = state;
            inner.endpoint = None;
            inner.error = None;
            inner.health_status = None;
        }
    }

    pub fn set_restarts(&self, restarts: u32) {
        if let Ok(mut inner) = self.inner.write() {
            inner.restarts = restarts;
        }
    }

    pub fn set_health(&self, status: &str) {
        if let Ok(mut inner) = self.inner.write() {
            inner.health_status = Some(status.to_string());
        }
    }

    pub fn set_exit_code(&self, code: Option<i32>) {
        if let Ok(mut inner) = self.inner.write() {
            inner.last_exit_code = code;
        }
    }

    pub fn fail(&self, err: &EngineError) {
        if let Ok(mut inner) = self.inner.write() {
            inner.state = EngineState::Fatal;
            inner.endpoint = None;
            inner.error = Some(EngineFailure::from(err));
        }
    }

    fn read<T>(&self, f: impl FnOnce(&Inner) -> T) -> T {
        match self.inner.read() {
            Ok(inner) => f(&inner),
            Err(poisoned) => {
                let inner = poisoned.into_inner();
                f(&inner)
            }
        }
    }
}

/// Adapts the shared handle to [`LogSink`] so the handshake can fill it directly.
pub struct SharedSink(pub Arc<Shared>);

impl LogSink for SharedSink {
    fn record(&mut self, stream: LogStream, line: &str) {
        self.0.record(stream, line);
    }
}

/// What the WebView reads through `tauri::State<EngineHandle>`.
#[derive(Clone)]
pub struct EngineHandle(pub Arc<Shared>);

impl EngineHandle {
    pub fn shared(&self) -> &Arc<Shared> {
        &self.0
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn every_error_carries_a_stable_dotted_code() {
        let cases = [
            EngineError::NotFound { searched: vec![] },
            EngineError::SpawnFailed {
                source: std::io::Error::other("nope"),
            },
            EngineError::ReadyTimeout { timeout_s: 30 },
            EngineError::ReadyMalformed { reason: "x".into() },
            EngineError::ExitedBeforeReady { code: Some(2) },
            EngineError::HealthUnreachable {
                consecutive: 3,
                reason: "x".into(),
            },
            EngineError::ShutdownTimeout { timeout_s: 10 },
            EngineError::KillFailed {
                source: std::io::Error::other("nope"),
            },
            EngineError::RestartBudgetExhausted {
                restarts: 6,
                window_s: 600,
            },
            EngineError::HttpClient { detail: "x".into() },
        ];
        let mut seen = std::collections::BTreeSet::new();
        for err in &cases {
            let code = err.code();
            assert!(code.starts_with("engine."), "{code} is not namespaced");
            assert!(seen.insert(code), "{code} is not unique");
            assert!(!err.to_string().is_empty());
        }
    }

    #[test]
    fn contract_violations_are_not_retryable() {
        assert!(!EngineError::NotFound { searched: vec![] }.is_retryable());
        assert!(!EngineError::ReadyMalformed { reason: "x".into() }.is_retryable());
        assert!(EngineError::ReadyTimeout { timeout_s: 30 }.is_retryable());
        assert!(EngineError::SpawnFailed {
            source: std::io::Error::other("x")
        }
        .is_retryable());
    }

    #[test]
    fn the_endpoint_is_camel_case_on_the_wire() {
        let json = serde_json::to_value(EngineEndpoint::new(54321, "tok")).unwrap();
        assert_eq!(json["baseUrl"], "http://127.0.0.1:54321");
        assert_eq!(json["token"], "tok");
        assert!(json.get("base_url").is_none());
    }

    #[test]
    fn publishing_clears_a_previous_failure_and_unpublishing_hides_the_endpoint() {
        let shared = Shared::new();
        shared.fail(&EngineError::ReadyTimeout { timeout_s: 30 });
        assert_eq!(shared.status().state, EngineState::Fatal);
        assert!(shared.status().error.is_some());

        shared.publish(EngineEndpoint::new(1, "t"), 42, "0.1.0".into());
        let status = shared.status();
        assert_eq!(status.state, EngineState::Ready);
        assert!(status.error.is_none());
        assert_eq!(status.base_url.as_deref(), Some("http://127.0.0.1:1"));

        shared.set_state(EngineState::Restarting);
        let status = shared.status();
        assert!(
            status.base_url.is_none(),
            "a dead port must not stay published"
        );
        assert_eq!(status.engine_pid, Some(42));
    }

    #[test]
    fn log_recording_survives_from_many_threads() {
        let shared = Shared::new();
        shared.set_secret("s3cret");
        let handles: Vec<_> = (0..8)
            .map(|i| {
                let shared = Arc::clone(&shared);
                std::thread::spawn(move || {
                    for n in 0..50 {
                        shared.record(LogStream::Stderr, &format!("thread {i} line {n} s3cret"));
                    }
                })
            })
            .collect();
        for handle in handles {
            handle.join().expect("worker should not panic");
        }
        let rendered = shared.render_logs();
        assert_eq!(rendered.lines().count(), DEFAULT_CAPACITY);
        assert!(!rendered.contains("s3cret"));
    }
}
