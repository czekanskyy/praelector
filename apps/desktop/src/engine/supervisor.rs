// SPDX-License-Identifier: Apache-2.0
//! Spawn, ready handshake, health poll, backoff, and teardown (PLAN.md §1.6).
//!
//! The child process is behind [`EngineHost`] so the handshake and the restart
//! budget can be tested without `uv` or a GPU. The production host is [`OsHost`].

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::io::{AsyncBufRead, AsyncBufReadExt};
use tokio::sync::Notify;

use super::config::{child_env, generate_token, resolve, EngineCommand, Resolver};
use super::logbuf::LogStream;
use super::ready::{await_ready, AwaitError, READY_BUDGET};
use super::SharedSink;
use super::{EngineEndpoint, EngineError, EngineFailure, EngineState, EngineStatusReport, Shared};
use crate::logging::redact;
use crate::paths::AppPaths;

/// Delay before each successive restart. The fifth and later stay at 16s.
pub const BACKOFF_SECONDS: [u64; 5] = [1, 2, 4, 8, 16];

/// More than this many restarts inside [`RESTART_WINDOW`] is fatal.
pub const RESTART_LIMIT: u32 = 5;

/// Sliding window for [`RESTART_LIMIT`].
pub const RESTART_WINDOW: Duration = Duration::from_secs(10 * 60);

const HEALTH_INTERVAL: Duration = Duration::from_secs(5);
const HEALTH_FAILURES: u32 = 3;
const SHUTDOWN_WAIT: Duration = Duration::from_secs(10);
const KILL_GRACE: Duration = Duration::from_secs(5);
const HEALTH_HTTP_TIMEOUT: Duration = Duration::from_secs(4);
const SHUTDOWN_HTTP_TIMEOUT: Duration = Duration::from_secs(5);

/// Delay before restart number `prior_restarts` (0 waits 1s, the first retry).
pub fn backoff_delay(prior_restarts: u32) -> Duration {
    let index = usize::try_from(prior_restarts).unwrap_or(usize::MAX);
    let index = index.min(BACKOFF_SECONDS.len().saturating_sub(1));
    Duration::from_secs(BACKOFF_SECONDS[index])
}

/// `true` when another restart at `now` would be more than `limit` inside `window`.
///
/// `restart_times` are earlier restarts, in the same second-resolution clock as
/// `now`. A stamp exactly `window` seconds ago still counts as inside.
pub fn restart_budget_exhausted(restart_times: &[u64], now: u64, window: u64, limit: u32) -> bool {
    let recent = restart_times
        .iter()
        .filter(|&&stamp| now.saturating_sub(stamp) <= window)
        .count();
    recent >= usize::try_from(limit).unwrap_or(usize::MAX)
}

/// Intervals the production supervisor uses. Tests substitute shorter ones.
#[derive(Debug, Clone)]
pub struct Timing {
    pub ready_budget: Duration,
    pub health_interval: Duration,
    pub health_failures: u32,
    pub shutdown_wait: Duration,
    pub kill_grace: Duration,
    pub restart_window: Duration,
    pub restart_limit: u32,
}

impl Timing {
    pub fn production() -> Self {
        Self {
            ready_budget: READY_BUDGET,
            health_interval: HEALTH_INTERVAL,
            health_failures: HEALTH_FAILURES,
            shutdown_wait: SHUTDOWN_WAIT,
            kill_grace: KILL_GRACE,
            restart_window: RESTART_WINDOW,
            restart_limit: RESTART_LIMIT,
        }
    }
}

/// What one launch needs, besides the host that actually spawns.
#[derive(Debug, Clone)]
pub struct LaunchEnv {
    pub paths: AppPaths,
    pub dev_search_roots: Vec<PathBuf>,
    pub log_level: String,
    pub parent_pid: u32,
    pub engine_cmd: Option<String>,
}

/// Executable plus the environment handed to it. The token is only in `env`.
#[derive(Debug, Clone)]
pub struct SpawnRequest {
    pub command: EngineCommand,
    pub env: Vec<(String, String)>,
}

/// What the supervisor tells the shell. The shell emits these and, on failure,
/// shows the native dialog. Keeping Tauri out of this module is what makes the
/// handshake testable.
#[derive(Debug)]
pub enum SupervisorEvent {
    State(EngineStatusReport),
    Failure(EngineFailure),
}

pub struct Control {
    pub stop: tokio::sync::watch::Receiver<bool>,
    pub done: Arc<Notify>,
    pub sink: Box<dyn Fn(SupervisorEvent) + Send>,
}

/// Something that can launch an engine and call its HTTP port.
pub trait EngineHost: Send + Sync {
    fn spawn(&self, request: &SpawnRequest) -> Result<Spawned, std::io::Error>;
    fn probe_health(
        &self,
        endpoint: &EngineEndpoint,
    ) -> impl std::future::Future<Output = Result<String, String>> + Send;
    fn request_shutdown(
        &self,
        endpoint: &EngineEndpoint,
    ) -> impl std::future::Future<Output = Result<(), String>> + Send;
}

/// Directories whose ancestors are searched for `engine/pyproject.toml`.
pub fn dev_search_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots.push(parent.to_path_buf());
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd);
    }
    roots
}

/// Run until the engine is fatal, or until `control.stop` is set.
///
/// Notifies `control.done` on the way out, including when this task is dropped,
/// so the shell's exit path cannot wait forever on a panic.
pub async fn supervise<H: EngineHost>(
    host: H,
    shared: Arc<Shared>,
    launch: LaunchEnv,
    timing: Timing,
    mut control: Control,
) {
    let _done = DoneGuard(Arc::clone(&control.done));
    let mut clock = RestartClock::new();
    loop {
        if control.is_stopped() {
            return;
        }
        match attempt(&host, &shared, &launch, &timing, &mut control, &mut clock).await {
            Outcome::Stopped => return,
            Outcome::Retry(err) => {
                let Some(delay) = continue_after(&shared, &control, &timing, &mut clock, &err)
                else {
                    return;
                };
                if !sleep_controlled(delay, &mut control).await {
                    return;
                }
            }
        }
    }
}

/// Record the restart, or surface a fatal error.
///
/// `Some(delay)` is how long to wait before the next launch. The delay is taken
/// from `clock.streak` *before* `record` advances it, so the first retry waits 1s.
fn continue_after(
    shared: &Shared,
    control: &Control,
    timing: &Timing,
    clock: &mut RestartClock,
    err: &EngineError,
) -> Option<Duration> {
    if !err.is_retryable() {
        fail(shared, control, err);
        return None;
    }
    let now = clock.now_secs();
    if restart_budget_exhausted(
        &clock.times,
        now,
        timing.restart_window.as_secs(),
        timing.restart_limit,
    ) {
        fail(
            shared,
            control,
            &EngineError::RestartBudgetExhausted {
                restarts: timing.restart_limit,
                window_s: timing.restart_window.as_secs(),
            },
        );
        return None;
    }
    let delay = backoff_delay(clock.streak);
    clock.record(now);
    shared.set_restarts(u32::try_from(clock.times.len()).unwrap_or(u32::MAX));
    log::warn!(
        "engine restart in {}s after {} ({err})",
        delay.as_secs(),
        err.code()
    );
    shared.begin_attempt(EngineState::Restarting);
    emit_state(shared, control);
    Some(delay)
}

enum Outcome {
    Stopped,
    Retry(EngineError),
}

enum Handshake {
    Stopped,
    Ready(Result<super::ready::ReadyInfo, AwaitError>),
}

async fn attempt<H: EngineHost>(
    host: &H,
    shared: &Arc<Shared>,
    launch: &LaunchEnv,
    timing: &Timing,
    control: &mut Control,
    clock: &mut RestartClock,
) -> Outcome {
    if control.is_stopped() {
        return Outcome::Stopped;
    }
    let state = if clock.times.is_empty() {
        EngineState::Launching
    } else {
        EngineState::Restarting
    };
    shared.begin_attempt(state);
    emit_state(shared, control);

    let token = generate_token();
    shared.add_secret(&token);

    let command = match resolve_command(launch) {
        Ok(command) => command,
        Err(err) => return Outcome::Retry(err),
    };
    log::info!(
        "spawning engine ({:?}): {}",
        command.source,
        command.describe()
    );
    let request = SpawnRequest {
        command,
        env: child_env(&launch.paths, &token, &launch.log_level, launch.parent_pid),
    };
    let mut spawned = match host.spawn(&request) {
        Ok(spawned) => spawned,
        Err(source) => return Outcome::Retry(EngineError::SpawnFailed { source }),
    };

    // The stop arm must not borrow `spawned`: `read_ready` holds that borrow for
    // the whole select, and a cancelled handshake drops the pipe readers.
    let handshake = tokio::select! {
        biased;
        _ = control.stopped() => Handshake::Stopped,
        ready = read_ready(&mut spawned, shared, timing.ready_budget) => Handshake::Ready(ready),
    };
    let ready = match handshake {
        Handshake::Stopped => {
            start_drains(&mut spawned, shared);
            let code = teardown(host, None, &mut spawned, timing).await;
            shared.set_exit_code(code);
            return Outcome::Stopped;
        }
        Handshake::Ready(ready) => ready,
    };
    start_drains(&mut spawned, shared);

    let info = match ready {
        Ok(info) => info,
        Err(err) => {
            let code = teardown(host, None, &mut spawned, timing).await;
            shared.set_exit_code(code);
            return Outcome::Retry(ready_error(err, &token, code));
        }
    };

    let pid = if info.pid == 0 { spawned.pid } else { info.pid };
    let endpoint = EngineEndpoint::new(info.port, token);
    shared.publish(endpoint.clone(), pid, info.version);
    emit_state(shared, control);

    match watch_health(
        host,
        &endpoint,
        &spawned.proc,
        shared,
        timing,
        control,
        clock,
    )
    .await
    {
        HealthEnd::Stopped => {
            let code = teardown(host, Some(&endpoint), &mut spawned, timing).await;
            shared.set_exit_code(code);
            Outcome::Stopped
        }
        HealthEnd::Failed(err) => {
            let code = teardown(host, Some(&endpoint), &mut spawned, timing).await;
            shared.set_exit_code(code);
            Outcome::Retry(err)
        }
    }
}

fn resolve_command(launch: &LaunchEnv) -> Result<EngineCommand, EngineError> {
    let exists = |path: &Path| path.is_file();
    resolve(&Resolver {
        engine_cmd_env: launch.engine_cmd.as_deref(),
        resource_dir: launch.paths.resource_dir.as_deref(),
        dev_search_roots: &launch.dev_search_roots,
        exists: &exists,
    })
}

fn ready_error(err: AwaitError, token: &str, exit_code: Option<i32>) -> EngineError {
    match err {
        AwaitError::Timeout(budget) => EngineError::ReadyTimeout {
            timeout_s: budget.as_secs(),
        },
        AwaitError::Eof => EngineError::ExitedBeforeReady { code: exit_code },
        AwaitError::Malformed(source) => EngineError::ReadyMalformed {
            reason: redact(&source.to_string(), token).into_owned(),
        },
    }
}

enum HealthEnd {
    Stopped,
    Failed(EngineError),
}

async fn watch_health<H: EngineHost>(
    host: &H,
    endpoint: &EngineEndpoint,
    proc: &ProcHandle,
    shared: &Shared,
    timing: &Timing,
    control: &mut Control,
    clock: &mut RestartClock,
) -> HealthEnd {
    let mut consecutive = 0u32;
    loop {
        tokio::select! {
            biased;
            _ = control.stopped() => return HealthEnd::Stopped,
            code = proc.exited() => {
                return HealthEnd::Failed(EngineError::HealthUnreachable {
                    consecutive: consecutive.max(1),
                    reason: format!("process exited ({code:?})"),
                });
            }
            _ = tokio::time::sleep(timing.health_interval) => {
                match host.probe_health(endpoint).await {
                    Ok(status) => {
                        consecutive = 0;
                        clock.note_healthy();
                        shared.set_health(&status);
                    }
                    Err(reason) => {
                        consecutive = consecutive.saturating_add(1);
                        let reason = redact(&reason, &endpoint.token).into_owned();
                        log::warn!("engine health failed ({consecutive}): {reason}");
                        if consecutive >= timing.health_failures {
                            return HealthEnd::Failed(EngineError::HealthUnreachable {
                                consecutive,
                                reason,
                            });
                        }
                    }
                }
            }
        }
    }
}

async fn teardown<H: EngineHost>(
    host: &H,
    endpoint: Option<&EngineEndpoint>,
    spawned: &mut Spawned,
    timing: &Timing,
) -> Option<i32> {
    if let Some(endpoint) = endpoint {
        if let Err(err) = host.request_shutdown(endpoint).await {
            let reason = redact(&err, &endpoint.token);
            log::warn!("engine shutdown request failed: {reason}");
        }
    }
    if let Some(code) = spawned.proc.wait_timeout(timing.shutdown_wait).await {
        return code;
    }
    log::warn!(
        "engine did not exit after shutdown; terminating pid {}",
        spawned.pid
    );
    spawned.proc.terminate();
    if let Some(code) = spawned.proc.wait_timeout(timing.kill_grace).await {
        return code;
    }
    log::warn!("engine still alive; killing pid {}", spawned.pid);
    spawned.proc.kill();
    spawned.proc.wait_timeout(timing.kill_grace).await.flatten()
}

fn emit_state(shared: &Shared, control: &Control) {
    (control.sink)(SupervisorEvent::State(shared.status()));
}

fn fail(shared: &Shared, control: &Control, err: &EngineError) {
    log::error!("engine fatal {}: {err}", err.code());
    shared.fail(err);
    emit_state(shared, control);
    (control.sink)(SupervisorEvent::Failure(EngineFailure::from(err)));
}

async fn sleep_controlled(dur: Duration, control: &mut Control) -> bool {
    tokio::select! {
        biased;
        _ = control.stopped() => false,
        _ = tokio::time::sleep(dur) => true,
    }
}

struct DoneGuard(Arc<Notify>);

impl Drop for DoneGuard {
    fn drop(&mut self) {
        self.0.notify_one();
    }
}

struct RestartClock {
    base: tokio::time::Instant,
    times: Vec<u64>,
    /// Retries since the engine last answered a health check. Drives backoff.
    streak: u32,
}

impl RestartClock {
    fn new() -> Self {
        Self {
            base: tokio::time::Instant::now(),
            times: Vec::new(),
            streak: 0,
        }
    }

    fn now_secs(&self) -> u64 {
        self.base.elapsed().as_secs()
    }

    fn record(&mut self, now: u64) {
        self.times.push(now);
        self.streak = self.streak.saturating_add(1);
    }

    fn note_healthy(&mut self) {
        self.streak = 0;
    }
}

impl Control {
    fn is_stopped(&self) -> bool {
        *self.stop.borrow()
    }

    async fn stopped(&mut self) {
        loop {
            if self.is_stopped() {
                return;
            }
            if self.stop.changed().await.is_err() {
                return;
            }
        }
    }
}

/// A spawned engine: pipes plus a way to end it.
pub struct Spawned {
    pid: u32,
    stdout: Option<Box<dyn AsyncBufRead + Unpin + Send>>,
    stderr: Option<Box<dyn AsyncBufRead + Unpin + Send>>,
    proc: ProcHandle,
}

struct ProcHandle {
    exit: Arc<ExitSlot>,
    killer: Box<dyn Killer>,
}

trait Killer: Send + Sync {
    fn terminate(&self);
    fn kill(&self);
}

impl ProcHandle {
    fn terminate(&self) {
        self.killer.terminate();
    }

    fn kill(&self) {
        self.killer.kill();
    }

    async fn exited(&self) -> Option<i32> {
        self.exit.wait_forever().await
    }

    /// `Some` when the process has exited (the inner value is the code, if the
    /// platform reported one). `None` when `dur` elapsed first.
    async fn wait_timeout(&self, dur: Duration) -> Option<Option<i32>> {
        self.exit.wait_timeout(dur).await
    }
}

impl Drop for ProcHandle {
    fn drop(&mut self) {
        if !self.exit.is_set() {
            self.killer.kill();
        }
    }
}

struct ExitSlot {
    exited: AtomicBool,
    code: Mutex<Option<i32>>,
    notify: Notify,
}

impl ExitSlot {
    fn new() -> Self {
        Self {
            exited: AtomicBool::new(false),
            code: Mutex::new(None),
            notify: Notify::new(),
        }
    }

    fn signal(&self, code: Option<i32>) {
        if let Ok(mut slot) = self.code.lock() {
            if !self.exited.load(Ordering::SeqCst) {
                *slot = code;
            }
        }
        self.exited.store(true, Ordering::SeqCst);
        self.notify.notify_one();
    }

    fn is_set(&self) -> bool {
        self.exited.load(Ordering::SeqCst)
    }

    fn code(&self) -> Option<i32> {
        self.code.lock().ok().and_then(|guard| *guard)
    }

    async fn wait_forever(&self) -> Option<i32> {
        loop {
            if self.is_set() {
                return self.code();
            }
            self.notify.notified().await;
        }
    }

    async fn wait_timeout(&self, dur: Duration) -> Option<Option<i32>> {
        let sleep = tokio::time::sleep(dur);
        tokio::pin!(sleep);
        loop {
            if self.is_set() {
                return Some(self.code());
            }
            tokio::select! {
                _ = self.notify.notified() => {}
                _ = &mut sleep => {
                    return if self.is_set() { Some(self.code()) } else { None };
                }
            }
        }
    }
}

async fn read_ready(
    spawned: &mut Spawned,
    shared: &Arc<Shared>,
    budget: Duration,
) -> Result<super::ready::ReadyInfo, AwaitError> {
    // Take the readers so a cancelled select (shutdown during the handshake)
    // drops them with this future instead of leaving a borrowed pipe behind.
    // They are put back before we return; shutdown after that still has them.
    let mut stdout = spawned.stdout.take().ok_or(AwaitError::Eof)?;
    let mut stderr = spawned.stderr.take().ok_or(AwaitError::Eof)?;
    let mut sink = SharedSink(Arc::clone(shared));
    let result = await_ready(&mut stdout, &mut stderr, &mut sink, budget).await;
    spawned.stdout = Some(stdout);
    spawned.stderr = Some(stderr);
    result
}

fn start_drains(spawned: &mut Spawned, shared: &Arc<Shared>) {
    if let Some(reader) = spawned.stdout.take() {
        spawn_drain(reader, LogStream::Stdout, Arc::clone(shared));
    }
    if let Some(reader) = spawned.stderr.take() {
        spawn_drain(reader, LogStream::Stderr, Arc::clone(shared));
    }
}

fn spawn_drain(
    reader: Box<dyn AsyncBufRead + Unpin + Send>,
    stream: LogStream,
    shared: Arc<Shared>,
) {
    tokio::spawn(async move {
        let mut reader = reader;
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line).await {
                Ok(0) | Err(_) => break,
                Ok(_) => shared.record(stream, &line),
            }
        }
    });
}

fn http_client() -> Result<reqwest::Client, EngineError> {
    reqwest::Client::builder()
        .build()
        .map_err(|err| EngineError::HttpClient {
            detail: err.to_string(),
        })
}

async fn probe_health(
    client: &reqwest::Client,
    endpoint: &EngineEndpoint,
) -> Result<String, String> {
    let response = client
        .get(endpoint.url("/v1/health"))
        .header(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", endpoint.token),
        )
        .timeout(HEALTH_HTTP_TIMEOUT)
        .send()
        .await
        .map_err(|err| err.to_string())?;
    let status_code = response.status();
    if !status_code.is_success() {
        return Err(format!("HTTP {status_code}"));
    }
    let body: serde_json::Value = response.json().await.map_err(|err| err.to_string())?;
    match body.get("status").and_then(serde_json::Value::as_str) {
        Some(status @ ("ok" | "degraded")) => Ok(status.to_string()),
        Some(other) => Err(format!("health status {other}")),
        None => Err("health response has no status".to_string()),
    }
}

async fn request_shutdown(
    client: &reqwest::Client,
    endpoint: &EngineEndpoint,
) -> Result<(), String> {
    let response = client
        .post(endpoint.url("/v1/shutdown"))
        .header(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", endpoint.token),
        )
        .timeout(SHUTDOWN_HTTP_TIMEOUT)
        .send()
        .await
        .map_err(|err| err.to_string())?;
    if response.status().is_success() {
        Ok(())
    } else {
        Err(format!("HTTP {}", response.status()))
    }
}

/// Production host: a real process, Job Object / process group, and reqwest.
pub struct OsHost {
    client: reqwest::Client,
    #[cfg(windows)]
    job: crate::engine::job_object_win::JobObject,
}

impl OsHost {
    pub fn new() -> Result<Self, EngineError> {
        Ok(Self {
            client: http_client()?,
            #[cfg(windows)]
            job: crate::engine::job_object_win::JobObject::new()
                .map_err(|source| EngineError::SpawnFailed { source })?,
        })
    }
}

impl EngineHost for OsHost {
    fn spawn(&self, request: &SpawnRequest) -> Result<Spawned, std::io::Error> {
        #[cfg(windows)]
        {
            spawn_os(request, Some(&self.job))
        }
        #[cfg(not(windows))]
        {
            spawn_os(request, None)
        }
    }

    async fn probe_health(&self, endpoint: &EngineEndpoint) -> Result<String, String> {
        probe_health(&self.client, endpoint).await
    }

    async fn request_shutdown(&self, endpoint: &EngineEndpoint) -> Result<(), String> {
        request_shutdown(&self.client, endpoint).await
    }
}

#[cfg(windows)]
fn spawn_os(
    request: &SpawnRequest,
    job: Option<&crate::engine::job_object_win::JobObject>,
) -> Result<Spawned, std::io::Error> {
    let mut child = configure_command(request).spawn()?;
    let pid = child
        .id()
        .ok_or_else(|| std::io::Error::other("spawned engine has no pid"))?;
    if let Some(job) = job {
        let Some(raw) = child.raw_handle() else {
            let _ = child.start_kill();
            return Err(std::io::Error::other(
                "spawned engine has no process handle",
            ));
        };
        if let Err(err) = job.assign(raw) {
            let _ = child.start_kill();
            return Err(err);
        }
    }
    finish_spawn(pid, child)
}

#[cfg(not(windows))]
fn spawn_os(request: &SpawnRequest, _job: Option<()>) -> Result<Spawned, std::io::Error> {
    let child = configure_command(request).spawn()?;
    let pid = child
        .id()
        .ok_or_else(|| std::io::Error::other("spawned engine has no pid"))?;
    finish_spawn(pid, child)
}

fn configure_command(request: &SpawnRequest) -> tokio::process::Command {
    let mut command = tokio::process::Command::new(&request.command.program);
    command.args(&request.command.args);
    if let Some(cwd) = &request.command.cwd {
        command.current_dir(cwd);
    }
    // Inherited stdin would be the shell's console, and a read there blocks the
    // engine forever. stdout/stderr stay piped so the handshake can see them.
    command.stdin(std::process::Stdio::null());
    command.stdout(std::process::Stdio::piped());
    command.stderr(std::process::Stdio::piped());
    command.kill_on_drop(true);
    for (key, value) in &request.env {
        command.env(key, value);
    }
    #[cfg(windows)]
    {
        // The engine is a console subsystem binary. Without this, every launch
        // flashes a command window on the user's desktop.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(unix)]
    {
        crate::engine::pgroup_unix::detach(&mut command);
    }
    command
}

fn finish_spawn(pid: u32, mut child: tokio::process::Child) -> Result<Spawned, std::io::Error> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| std::io::Error::other("engine stdout was not piped"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| std::io::Error::other("engine stderr was not piped"))?;
    let proc = watch_child(pid, child);
    Ok(Spawned {
        pid,
        stdout: Some(Box::new(tokio::io::BufReader::new(stdout))),
        stderr: Some(Box::new(tokio::io::BufReader::new(stderr))),
        proc,
    })
}

fn watch_child(pid: u32, child: tokio::process::Child) -> ProcHandle {
    let exit = Arc::new(ExitSlot::new());
    let child = Arc::new(tokio::sync::Mutex::new(child));
    let poll_child = Arc::clone(&child);
    let poll_exit = Arc::clone(&exit);
    tokio::spawn(async move {
        loop {
            if poll_exit.is_set() {
                return;
            }
            let polled = {
                let mut guard = poll_child.lock().await;
                guard.try_wait()
            };
            match polled {
                Ok(Some(status)) => {
                    poll_exit.signal(status.code());
                    return;
                }
                Ok(None) => {}
                Err(_) => {
                    poll_exit.signal(None);
                    return;
                }
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    });
    ProcHandle {
        exit,
        killer: Box::new(OsKiller { pid }),
    }
}

struct OsKiller {
    pid: u32,
}

impl Killer for OsKiller {
    fn terminate(&self) {
        signal_term(self.pid);
    }

    fn kill(&self) {
        signal_kill(self.pid);
    }
}

fn signal_term(pid: u32) {
    #[cfg(unix)]
    {
        let _ = crate::engine::pgroup_unix::signal_group(pid, libc::SIGTERM);
    }
    #[cfg(windows)]
    {
        crate::engine::job_object_win::terminate_pid(pid);
    }
}

fn signal_kill(pid: u32) {
    #[cfg(unix)]
    {
        let _ = crate::engine::pgroup_unix::signal_group(pid, libc::SIGKILL);
    }
    #[cfg(windows)]
    {
        crate::engine::job_object_win::terminate_pid(pid);
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::sync::atomic::AtomicU32;

    use super::super::config::{CommandSource, ENV_DATA_DIR, ENV_PARENT_PID, ENV_TOKEN};
    use super::*;

    #[test]
    fn backoff_follows_the_plan_then_sticks_at_sixteen() {
        let expected = [1u64, 2, 4, 8, 16, 16, 16];
        for (prior, seconds) in expected.into_iter().enumerate() {
            assert_eq!(
                backoff_delay(u32::try_from(prior).unwrap()),
                Duration::from_secs(seconds),
                "restart {prior}"
            );
        }
    }

    #[test]
    fn five_restarts_inside_ten_minutes_block_the_next_one() {
        let window = RESTART_WINDOW.as_secs();
        let start = 10_000u64;
        let times: Vec<u64> = (0..5).map(|i| start + i * 30).collect();
        let now = times[4];
        assert!(restart_budget_exhausted(&times, now, window, RESTART_LIMIT));
        assert!(!restart_budget_exhausted(
            &times[..4],
            now,
            window,
            RESTART_LIMIT
        ));
    }

    #[test]
    fn a_restart_older_than_the_window_no_longer_counts() {
        let window = 600u64;
        let now = 10_000u64;
        let inside = now - window;
        let outside = now - window - 1;
        assert!(restart_budget_exhausted(&[inside], inside, window, 1));
        assert!(!restart_budget_exhausted(&[outside], now, window, 1));
        let old = now - window - 1;
        let recent: Vec<u64> = std::iter::once(old)
            .chain((0..4).map(|i| now - i))
            .collect();
        assert_eq!(recent.len(), 5);
        assert!(
            !restart_budget_exhausted(&recent, now, window, RESTART_LIMIT),
            "the stamp just outside the window leaves only four"
        );
    }

    #[test]
    fn production_timing_matches_the_plan() {
        let timing = Timing::production();
        assert_eq!(timing.ready_budget, Duration::from_secs(30));
        assert_eq!(timing.health_interval, Duration::from_secs(5));
        assert_eq!(timing.health_failures, 3);
        assert_eq!(timing.shutdown_wait, Duration::from_secs(10));
        assert_eq!(timing.kill_grace, Duration::from_secs(5));
        assert_eq!(timing.restart_window, Duration::from_secs(600));
        assert_eq!(timing.restart_limit, 5);
    }

    fn fast_timing() -> Timing {
        Timing {
            ready_budget: Duration::from_secs(2),
            health_interval: Duration::from_secs(1),
            health_failures: 3,
            shutdown_wait: Duration::from_secs(1),
            kill_grace: Duration::from_secs(1),
            restart_window: Duration::from_secs(600),
            restart_limit: 5,
        }
    }

    struct ScriptedHost {
        spawns: Arc<Mutex<Vec<SpawnRequest>>>,
        port: AtomicU32,
        health_calls: Arc<AtomicU32>,
        health: Arc<dyn Fn(u32) -> Result<String, String> + Send + Sync>,
        shutdowns: Arc<AtomicU32>,
        current_exit: Arc<Mutex<Option<Arc<ExitSlot>>>>,
        mode: ScriptMode,
        held: Arc<Mutex<Vec<tokio::io::DuplexStream>>>,
    }

    enum ScriptMode {
        Ready,
        Malformed,
        Silent,
    }

    struct Session {
        shared: Arc<Shared>,
        stop: tokio::sync::watch::Sender<bool>,
        done: Arc<Notify>,
        spawns: Arc<Mutex<Vec<SpawnRequest>>>,
        shutdowns: Arc<AtomicU32>,
    }

    impl ScriptedHost {
        fn new(
            mode: ScriptMode,
            health: impl Fn(u32) -> Result<String, String> + Send + Sync + 'static,
        ) -> Self {
            Self {
                spawns: Arc::new(Mutex::new(Vec::new())),
                port: AtomicU32::new(40_000),
                health_calls: Arc::new(AtomicU32::new(0)),
                health: Arc::new(health),
                shutdowns: Arc::new(AtomicU32::new(0)),
                current_exit: Arc::new(Mutex::new(None)),
                mode,
                held: Arc::new(Mutex::new(Vec::new())),
            }
        }
    }

    impl EngineHost for ScriptedHost {
        fn spawn(&self, request: &SpawnRequest) -> Result<Spawned, std::io::Error> {
            self.spawns.lock().unwrap().push(request.clone());
            let exit = Arc::new(ExitSlot::new());
            *self.current_exit.lock().unwrap() = Some(Arc::clone(&exit));
            let (stdout, stderr) = match self.mode {
                ScriptMode::Ready => {
                    let port = self.port.fetch_add(1, Ordering::SeqCst);
                    let token = env_value(&request.env, ENV_TOKEN);
                    let line = format!(
                        "PRAELECTOR_READY {{\"port\":{port},\"pid\":4242,\"version\":\"0.1.0\",\"schema\":1}}\n"
                    );
                    (
                        cursor(line.into_bytes()),
                        cursor(format!("token {token}\n").into_bytes()),
                    )
                }
                ScriptMode::Malformed => (
                    cursor(b"PRAELECTOR_READY {\"pid\":1}\n".to_vec()),
                    cursor(Vec::new()),
                ),
                ScriptMode::Silent => {
                    let (out_w, out_r) = tokio::io::duplex(64);
                    let (err_w, err_r) = tokio::io::duplex(64);
                    self.held.lock().unwrap().push(out_w);
                    self.held.lock().unwrap().push(err_w);
                    (
                        Box::new(tokio::io::BufReader::new(out_r))
                            as Box<dyn AsyncBufRead + Unpin + Send>,
                        Box::new(tokio::io::BufReader::new(err_r))
                            as Box<dyn AsyncBufRead + Unpin + Send>,
                    )
                }
            };
            let held = Arc::clone(&self.held);
            Ok(Spawned {
                pid: 4242,
                stdout: Some(stdout),
                stderr: Some(stderr),
                proc: ProcHandle {
                    exit: Arc::clone(&exit),
                    killer: Box::new(FakeKiller { exit, held }),
                },
            })
        }

        async fn probe_health(&self, _endpoint: &EngineEndpoint) -> Result<String, String> {
            let n = self.health_calls.fetch_add(1, Ordering::SeqCst) + 1;
            (self.health)(n)
        }

        async fn request_shutdown(&self, _endpoint: &EngineEndpoint) -> Result<(), String> {
            self.shutdowns.fetch_add(1, Ordering::SeqCst);
            if let Some(exit) = self.current_exit.lock().unwrap().clone() {
                exit.signal(Some(0));
            }
            Ok(())
        }
    }

    struct FakeKiller {
        exit: Arc<ExitSlot>,
        held: Arc<Mutex<Vec<tokio::io::DuplexStream>>>,
    }

    impl Killer for FakeKiller {
        fn terminate(&self) {
            self.held.lock().unwrap().clear();
            self.exit.signal(Some(1));
        }

        fn kill(&self) {
            self.held.lock().unwrap().clear();
            self.exit.signal(Some(9));
        }
    }

    fn cursor(bytes: Vec<u8>) -> Box<dyn AsyncBufRead + Unpin + Send> {
        Box::new(tokio::io::BufReader::new(std::io::Cursor::new(bytes)))
    }

    fn env_value(env: &[(String, String)], key: &str) -> String {
        env.iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.clone())
            .unwrap_or_default()
    }

    fn launch_env() -> LaunchEnv {
        LaunchEnv {
            paths: AppPaths {
                data_dir: PathBuf::from("data"),
                config_dir: PathBuf::from("config"),
                log_dir: PathBuf::from("logs"),
                projects_dir: PathBuf::from("projects"),
                resource_dir: None,
                // No dev root either: command resolution is overridden per test.
            },
            dev_search_roots: Vec::new(),
            log_level: "INFO".to_string(),
            parent_pid: 7,
            engine_cmd: Some("engine-test".to_string()),
        }
    }

    fn session(host: ScriptedHost, timing: Timing) -> Session {
        let spawns = Arc::clone(&host.spawns);
        let shutdowns = Arc::clone(&host.shutdowns);
        let shared = Shared::new();
        let (stop, stop_rx) = tokio::sync::watch::channel(false);
        let done = Arc::new(Notify::new());
        let done_task = Arc::clone(&done);
        let shared_task = Arc::clone(&shared);
        tokio::spawn(async move {
            supervise(
                host,
                shared_task,
                launch_env(),
                timing,
                Control {
                    stop: stop_rx,
                    done: done_task,
                    sink: Box::new(|_| {}),
                },
            )
            .await;
        });
        Session {
            shared,
            stop,
            done,
            spawns,
            shutdowns,
        }
    }

    async fn stop(session: &Session) {
        let _ = session.stop.send(true);
        session.done.notified().await;
    }

    #[tokio::test(start_paused = true)]
    async fn handshake_publishes_the_endpoint_and_redacts_the_token() {
        let host = ScriptedHost::new(ScriptMode::Ready, |_| Ok("ok".to_string()));
        let session = session(host, fast_timing());
        tokio::time::sleep(Duration::from_millis(50)).await;

        let status = session.shared.status();
        assert_eq!(status.state, EngineState::Ready);
        assert_eq!(status.engine_pid, Some(4242));
        assert_eq!(status.engine_version.as_deref(), Some("0.1.0"));
        let endpoint = session.shared.endpoint().expect("endpoint");
        assert_eq!(endpoint.base_url, "http://127.0.0.1:40000");

        {
            let spawns = session.spawns.lock().unwrap();
            let request = &spawns[0];
            assert_eq!(request.command.program, "engine-test");
            assert!(!request.command.describe().contains(&endpoint.token));
            assert!(!request
                .command
                .args
                .iter()
                .any(|arg| arg.contains(&endpoint.token)));
            assert_eq!(env_value(&request.env, ENV_TOKEN), endpoint.token);
            assert_eq!(env_value(&request.env, ENV_PARENT_PID), "7");
            assert_eq!(env_value(&request.env, ENV_DATA_DIR), "data");
        }

        let logs = session.shared.render_logs();
        assert!(
            !logs.contains(&endpoint.token),
            "token leaked into the log buffer: {logs}"
        );
        assert!(logs.contains(crate::logging::REDACTION));
        assert!(
            !logs.contains("PRAELECTOR_READY"),
            "the ready line is not a log line"
        );

        stop(&session).await;
        assert!(
            session.shutdowns.load(Ordering::SeqCst) >= 1,
            "shutdown posts before kill"
        );
    }

    #[tokio::test(start_paused = true)]
    async fn three_health_failures_restart_then_a_healthy_probe_sticks() {
        let host = ScriptedHost::new(ScriptMode::Ready, |n| {
            if n <= 3 {
                Err("connection refused".to_string())
            } else {
                Ok("ok".to_string())
            }
        });
        let session = session(host, fast_timing());
        for _ in 0..30 {
            let status = session.shared.status();
            if status.restarts >= 1 && status.state == EngineState::Ready {
                break;
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
        let status = session.shared.status();
        assert_eq!(status.state, EngineState::Ready, "{status:?}");
        assert_eq!(status.restarts, 1);
        assert_eq!(session.spawns.lock().unwrap().len(), 2);
        assert_eq!(status.base_url.as_deref(), Some("http://127.0.0.1:40001"));
        stop(&session).await;
    }

    #[tokio::test(start_paused = true)]
    async fn more_than_five_restarts_in_the_window_is_fatal() {
        let started = std::time::Instant::now();
        let host = ScriptedHost::new(ScriptMode::Ready, |_| Err("down".to_string()));
        let session = session(host, fast_timing());
        for _ in 0..80 {
            if session.shared.status().state == EngineState::Fatal {
                break;
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
        let status = session.shared.status();
        assert_eq!(status.state, EngineState::Fatal, "{status:?}");
        let code = status.error.as_ref().map(|err| err.code.as_str());
        assert_eq!(code, Some("engine.restart_budget_exhausted"));
        assert_eq!(
            session.spawns.lock().unwrap().len(),
            6,
            "initial launch plus five restarts"
        );
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "paused time must not sleep"
        );
        // Already finished; the permit is waiting.
        session.done.notified().await;
    }

    #[tokio::test(start_paused = true)]
    async fn a_missing_binary_is_fatal_without_a_restart() {
        let host = ScriptedHost::new(ScriptMode::Ready, |_| Ok("ok".to_string()));
        let spawns = Arc::clone(&host.spawns);
        let shared = Shared::new();
        let (stop, stop_rx) = tokio::sync::watch::channel(false);
        let done = Arc::new(Notify::new());
        let done_task = Arc::clone(&done);
        let shared_task = Arc::clone(&shared);
        let mut launch = launch_env();
        launch.engine_cmd = None;
        tokio::spawn(async move {
            supervise(
                host,
                shared_task,
                launch,
                fast_timing(),
                Control {
                    stop: stop_rx,
                    done: done_task,
                    sink: Box::new(|_| {}),
                },
            )
            .await;
        });
        tokio::time::sleep(Duration::from_secs(3)).await;
        let status = shared.status();
        assert_eq!(status.state, EngineState::Fatal);
        assert_eq!(
            status.error.as_ref().map(|err| err.code.as_str()),
            Some("engine.not_found")
        );
        assert!(spawns.lock().unwrap().is_empty());
        let _ = stop.send(true);
        done.notified().await;
    }

    #[tokio::test(start_paused = true)]
    async fn a_malformed_ready_line_is_not_retried() {
        let host = ScriptedHost::new(ScriptMode::Malformed, |_| Ok("ok".to_string()));
        let session = session(host, fast_timing());
        for _ in 0..20 {
            if session.shared.status().state == EngineState::Fatal {
                break;
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
        let status = session.shared.status();
        assert_eq!(status.state, EngineState::Fatal, "{status:?}");
        assert_eq!(
            status.error.as_ref().map(|err| err.code.as_str()),
            Some("engine.ready_malformed")
        );
        assert_eq!(session.spawns.lock().unwrap().len(), 1);
        session.done.notified().await;
    }

    #[tokio::test(start_paused = true)]
    async fn silence_past_the_ready_budget_restarts_then_stops() {
        let mut timing = fast_timing();
        timing.restart_limit = 1;
        let host = ScriptedHost::new(ScriptMode::Silent, |_| Ok("ok".to_string()));
        let session = session(host, timing);
        for _ in 0..40 {
            if session.shared.status().state == EngineState::Fatal {
                break;
            }
            tokio::time::sleep(Duration::from_secs(1)).await;
        }
        let status = session.shared.status();
        assert_eq!(status.state, EngineState::Fatal, "{status:?}");
        assert_eq!(
            status.error.as_ref().map(|err| err.code.as_str()),
            Some("engine.restart_budget_exhausted")
        );
        // Initial launch plus the one allowed restart. The next decision is fatal.
        assert_eq!(session.spawns.lock().unwrap().len(), 2);
        session.done.notified().await;
    }

    #[tokio::test]
    async fn health_probe_sends_a_bearer_token_and_no_origin() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let seen = Arc::new(Mutex::new(String::new()));
        let seen_task = Arc::clone(&seen);
        tokio::spawn(async move {
            let (mut sock, _) = listener.accept().await.unwrap();
            let headers = read_headers(&mut sock).await;
            *seen_task.lock().unwrap() = headers;
            let body =
                r#"{"status":"ok","uptime_s":0.1,"project_open":false,"active_job_id":null}"#;
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                body.len()
            );
            use tokio::io::AsyncWriteExt;
            let _ = sock.write_all(response.as_bytes()).await;
        });

        let client = http_client().unwrap();
        let endpoint = EngineEndpoint::new(port, "tok-test");
        let status = probe_health(&client, &endpoint).await.unwrap();
        assert_eq!(status, "ok");
        let raw = seen.lock().unwrap().clone();
        let lower = raw.to_ascii_lowercase();
        assert!(lower.contains("authorization: bearer tok-test"), "{raw}");
        assert!(
            !lower.contains("\r\norigin:"),
            "supervisor must not send Origin: {raw}"
        );
    }

    #[tokio::test]
    async fn shutdown_is_a_post_with_the_same_header_rules() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let seen = Arc::new(Mutex::new(String::new()));
        let seen_task = Arc::clone(&seen);
        tokio::spawn(async move {
            let (mut sock, _) = listener.accept().await.unwrap();
            let headers = read_headers(&mut sock).await;
            *seen_task.lock().unwrap() = headers;
            let body = r#"{"accepted":true,"server_signalled":true}"#;
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                body.len()
            );
            use tokio::io::AsyncWriteExt;
            let _ = sock.write_all(response.as_bytes()).await;
        });
        let client = http_client().unwrap();
        let endpoint = EngineEndpoint::new(port, "tok-shut");
        request_shutdown(&client, &endpoint).await.unwrap();
        let raw = seen.lock().unwrap().clone();
        let lower = raw.to_ascii_lowercase();
        assert!(lower.starts_with("post /v1/shutdown "), "{raw}");
        assert!(lower.contains("authorization: bearer tok-shut"), "{raw}");
        assert!(!lower.contains("\r\norigin:"), "{raw}");
    }

    async fn read_headers(sock: &mut tokio::net::TcpStream) -> String {
        use tokio::io::AsyncReadExt;
        let mut buf = Vec::new();
        let mut tmp = [0u8; 1024];
        loop {
            let n = sock.read(&mut tmp).await.unwrap_or(0);
            if n == 0 {
                break;
            }
            buf.extend_from_slice(&tmp[..n]);
            if buf.windows(4).any(|window| window == b"\r\n\r\n") || buf.len() > 8192 {
                break;
            }
        }
        String::from_utf8_lossy(&buf).into_owned()
    }

    #[tokio::test]
    async fn a_trivial_child_is_assigned_and_reaped() {
        let (program, args) = trivial_child();
        let request = SpawnRequest {
            command: EngineCommand {
                program,
                args,
                cwd: None,
                source: CommandSource::Dev,
            },
            env: vec![("PRAELECTOR_TEST".to_string(), "1".to_string())],
        };
        let host = OsHost::new().expect("os host");
        let spawned = host.spawn(&request).expect("spawn");
        // Drop the pipes so a chatty child cannot block on a full buffer.
        drop(spawned.stdout);
        drop(spawned.stderr);
        spawned.proc.terminate();
        let _code = tokio::time::timeout(Duration::from_secs(10), spawned.proc.exited())
            .await
            .expect("child did not exit");
    }

    fn trivial_child() -> (String, Vec<String>) {
        if cfg!(windows) {
            (
                "ping".to_string(),
                vec!["127.0.0.1".to_string(), "-n".to_string(), "5".to_string()],
            )
        } else {
            ("sleep".to_string(), vec!["5".to_string()])
        }
    }
}
