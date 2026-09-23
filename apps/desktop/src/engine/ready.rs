// SPDX-License-Identifier: Apache-2.0
//! The ready handshake (PLAN.md §1.6 step 3–4).
//!
//! stdout carries **exactly one line, ever**:
//! `PRAELECTOR_READY {"port":54321,"pid":12345,"version":"0.1.0","schema":1}`.
//! Everything else the engine emits — all of its JSON logs — is on stderr. Both
//! streams are drained here so a chatty engine can never block on a full pipe
//! while the shell waits for a line it has already consumed.

use std::future::poll_fn;
use std::pin::Pin;
use std::task::Poll;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::io::AsyncBufRead;
use tokio::io::AsyncBufReadExt;

use super::logbuf::{LogSink, LogStream};

/// Must match `praelector.__main__.READY_PREFIX`, including the trailing space.
pub const READY_PREFIX: &str = "PRAELECTOR_READY ";

/// PLAN.md §1.6: a 30 s budget for the prefix, then the child is killed.
pub const READY_BUDGET: Duration = Duration::from_secs(30);

/// What the engine announced. `port` is the only field the shell needs to talk to
/// it; the rest is surfaced in diagnostics.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReadyInfo {
    pub port: u16,
    #[serde(default)]
    pub pid: u32,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub schema: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum ReadyParseError {
    #[error("line does not start with the ready prefix")]
    NotReady,
    #[error("the ready payload is not a JSON object: {payload}")]
    MalformedJson { payload: String },
    #[error("the ready payload carries no usable port: {payload}")]
    MissingPort { payload: String },
}

/// Why the handshake did not produce a port.
#[derive(Debug, Error)]
pub enum AwaitError {
    #[error("no ready line within the {0:?} budget")]
    Timeout(Duration),
    #[error("the engine closed its output before announcing readiness")]
    Eof,
    #[error(transparent)]
    Malformed(#[from] ReadyParseError),
}

/// Parse one stdout line. Returns [`ReadyParseError::NotReady`] for anything that
/// is not a ready line, which is the normal case for pre-announcement noise and
/// must not be confused with a malformed announcement.
pub fn parse_ready_line(line: &str) -> Result<ReadyInfo, ReadyParseError> {
    let trimmed = line.trim_end_matches(['\r', '\n']);
    match trimmed.strip_prefix(READY_PREFIX) {
        Some(payload) => parse_ready_payload(payload),
        None => Err(ReadyParseError::NotReady),
    }
}

/// Parse the JSON half of the ready line.
///
/// Parsed through [`serde_json::Value`] rather than straight into [`ReadyInfo`] so
/// a missing `port` reports as `MissingPort` instead of a generic deserialisation
/// failure — the fatal panel shows a different message for "the engine is not ours"
/// than for "the engine is broken".
pub fn parse_ready_payload(payload: &str) -> Result<ReadyInfo, ReadyParseError> {
    let value: serde_json::Value =
        serde_json::from_str(payload.trim()).map_err(|_| ReadyParseError::MalformedJson {
            payload: payload.to_string(),
        })?;

    if !value.is_object() {
        return Err(ReadyParseError::MalformedJson {
            payload: payload.to_string(),
        });
    }

    let port = value
        .get("port")
        .and_then(serde_json::Value::as_u64)
        .filter(|port| (1..=u64::from(u16::MAX)).contains(port));
    let Some(port) = port else {
        return Err(ReadyParseError::MissingPort {
            payload: payload.to_string(),
        });
    };

    Ok(ReadyInfo {
        port: port as u16,
        pid: value
            .get("pid")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or(0) as u32,
        version: value
            .get("version")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default()
            .to_string(),
        schema: value
            .get("schema")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or(0) as u32,
    })
}

/// Read both streams until the ready line appears, both close, or `budget` runs out.
///
/// `budget` is applied with [`tokio::time::timeout`], which is the injectable
/// clock: tests run it under `#[tokio::test(start_paused = true)]` so the 30 s
/// timeout path is exercised in zero wall-clock time instead of by sleeping.
pub async fn await_ready<O, E, S>(
    stdout: &mut O,
    stderr: &mut E,
    sink: &mut S,
    budget: Duration,
) -> Result<ReadyInfo, AwaitError>
where
    O: AsyncBufRead + Unpin,
    E: AsyncBufRead + Unpin,
    S: LogSink + ?Sized,
{
    let mut out_buf = String::new();
    let mut err_buf = String::new();
    let mut out_open = true;
    let mut err_open = true;

    let outcome = tokio::time::timeout(budget, async {
        loop {
            // A closed stream will never deliver the newline that terminates its
            // last line, so add it: otherwise a flushed-but-unterminated ready
            // line would sit in the buffer and be reported as EOF.
            terminate_tail(&mut out_buf, out_open);
            terminate_tail(&mut err_buf, err_open);

            if let Some(info) = drain_lines(&mut out_buf, LogStream::Stdout, sink, true)? {
                // Stdout is preferred, so the ready line returns before `select`
                // has read stderr. Bytes already in that pipe still belong in
                // the log; a read that would block is left for the later drain.
                if err_open {
                    err_open = take_available(stderr, &mut err_buf).await;
                    terminate_tail(&mut err_buf, err_open);
                    drain_lines(&mut err_buf, LogStream::Stderr, sink, false)?;
                }
                return Ok(info);
            }
            // stderr never carries the ready line, so it is only buffered.
            drain_lines(&mut err_buf, LogStream::Stderr, sink, false)?;

            if !out_open && !err_open {
                return Err(AwaitError::Eof);
            }

            tokio::select! {
                biased;
                read = stdout.read_line(&mut out_buf), if out_open => {
                    // EOF and a read error mean the same thing here: no more lines.
                    out_open = matches!(read, Ok(n) if n > 0);
                }
                read = stderr.read_line(&mut err_buf), if err_open => {
                    err_open = matches!(read, Ok(n) if n > 0);
                }
            }
        }
    })
    .await;

    match outcome {
        Ok(inner) => inner,
        Err(_elapsed) => Err(AwaitError::Timeout(budget)),
    }
}

/// Append bytes `poll_fill_buf` can return without waiting. `false` means the
/// stream has closed or failed.
async fn take_available<R>(reader: &mut R, buf: &mut String) -> bool
where
    R: AsyncBufRead + Unpin,
{
    poll_fn(|cx| loop {
        let mut pinned = Pin::new(&mut *reader);
        match pinned.as_mut().poll_fill_buf(cx) {
            Poll::Ready(Ok(data)) if !data.is_empty() => {
                let n = data.len();
                let chunk = String::from_utf8_lossy(data).into_owned();
                pinned.as_mut().consume(n);
                buf.push_str(&chunk);
            }
            Poll::Ready(Ok(_)) | Poll::Ready(Err(_)) => return Poll::Ready(false),
            Poll::Pending => return Poll::Ready(true),
        }
    })
    .await
}

fn terminate_tail(buf: &mut String, stream_open: bool) {
    if !stream_open && !buf.is_empty() && !buf.ends_with('\n') {
        buf.push('\n');
    }
}

/// Move every complete line out of `buf`, keeping the partial tail for the next
/// read. Splitting here rather than trusting one `read_line` per iteration is what
/// makes the loop safe under `select!` cancellation: bytes already appended to
/// `buf` are never lost, only re-scanned.
fn drain_lines<S>(
    buf: &mut String,
    stream: LogStream,
    sink: &mut S,
    look_for_ready: bool,
) -> Result<Option<ReadyInfo>, AwaitError>
where
    S: LogSink + ?Sized,
{
    while let Some(idx) = buf.find('\n') {
        let line: String = buf.drain(..=idx).collect();
        let line = line.trim_end_matches(['\r', '\n']);
        if line.is_empty() {
            continue;
        }
        match parse_ready_line(line) {
            Ok(info) if look_for_ready => return Ok(Some(info)),
            Ok(_) => sink.record(stream, line),
            Err(ReadyParseError::NotReady) => sink.record(stream, line),
            Err(err) => return Err(err.into()),
        }
    }
    Ok(None)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::io;
    use std::pin::Pin;
    use std::task::{Context, Poll};

    use super::super::logbuf::LogBuffer;
    use super::*;

    const GOOD: &str =
        r#"PRAELECTOR_READY {"port":54321,"pid":12345,"version":"0.1.0","schema":1}"#;

    /// A reader that never produces anything, so the timeout path can be reached
    /// without a stream ever closing.
    struct PendingReader;

    impl tokio::io::AsyncRead for PendingReader {
        fn poll_read(
            self: Pin<&mut Self>,
            _cx: &mut Context<'_>,
            _buf: &mut tokio::io::ReadBuf<'_>,
        ) -> Poll<io::Result<()>> {
            Poll::Pending
        }
    }

    impl tokio::io::AsyncBufRead for PendingReader {
        fn poll_fill_buf(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<io::Result<&[u8]>> {
            Poll::Pending
        }

        fn consume(self: Pin<&mut Self>, _amt: usize) {}
    }

    fn reader(text: &str) -> tokio::io::BufReader<&[u8]> {
        tokio::io::BufReader::new(text.as_bytes())
    }

    #[test]
    fn parses_the_exact_line_the_engine_writes() {
        let info = parse_ready_line(GOOD).expect("the canonical line must parse");
        assert_eq!(
            info,
            ReadyInfo {
                port: 54321,
                pid: 12345,
                version: "0.1.0".to_string(),
                schema: 1,
            }
        );
    }

    #[test]
    fn tolerates_a_trailing_carriage_return() {
        let info = parse_ready_line(&format!("{GOOD}\r\n")).expect("CRLF must parse");
        assert_eq!(info.port, 54321);
    }

    #[test]
    fn garbage_before_the_ready_line_is_not_ready() {
        for line in [
            "",
            "PRAELECTOR_READY",
            "PRAELECTOR_READYX {}",
            "praelector_ready {\"port\":1}",
            "warning: something on stdout",
            " PRAELECTOR_READY {\"port\":1}",
        ] {
            assert_eq!(
                parse_ready_line(line),
                Err(ReadyParseError::NotReady),
                "{line:?} must not be mistaken for the announcement"
            );
        }
    }

    #[test]
    fn a_prefix_with_invalid_json_is_malformed() {
        let err = parse_ready_line("PRAELECTOR_READY {not json").unwrap_err();
        assert!(
            matches!(err, ReadyParseError::MalformedJson { .. }),
            "got {err:?}"
        );
    }

    #[test]
    fn a_json_array_is_malformed_not_missing_port() {
        let err = parse_ready_line("PRAELECTOR_READY [1,2,3]").unwrap_err();
        assert!(
            matches!(err, ReadyParseError::MalformedJson { .. }),
            "got {err:?}"
        );
    }

    #[test]
    fn a_missing_or_unusable_port_is_its_own_error() {
        for payload in [
            r#"PRAELECTOR_READY {"pid":1,"version":"0.1.0","schema":1}"#,
            r#"PRAELECTOR_READY {"port":null}"#,
            r#"PRAELECTOR_READY {"port":"54321"}"#,
            r#"PRAELECTOR_READY {"port":0}"#,
            r#"PRAELECTOR_READY {"port":70000}"#,
            r#"PRAELECTOR_READY {"port":-1}"#,
        ] {
            let err = parse_ready_line(payload).unwrap_err();
            assert!(
                matches!(err, ReadyParseError::MissingPort { .. }),
                "{payload:?} gave {err:?}"
            );
        }
    }

    #[test]
    fn optional_fields_default_instead_of_failing() {
        let info =
            parse_ready_line(r#"PRAELECTOR_READY {"port":40000}"#).expect("port alone is enough");
        assert_eq!(info.pid, 0);
        assert_eq!(info.version, "");
        assert_eq!(info.schema, 0);
    }

    #[tokio::test]
    async fn the_ready_line_is_found_after_unrelated_stdout_noise() {
        let stdout_text = format!("compiling praelector...\nwarning: something\n{GOOD}\n");
        let stderr_text = r#"{"level":"info","event":"listening"}"#;
        let mut stdout = reader(&stdout_text);
        let mut stderr = reader(stderr_text);
        let mut sink = LogBuffer::new(64);

        let info = await_ready(&mut stdout, &mut stderr, &mut sink, Duration::from_secs(30))
            .await
            .expect("handshake should succeed");
        assert_eq!(info.port, 54321);
        assert_eq!(
            sink.render(),
            "out compiling praelector...\nout warning: something\nerr {\"level\":\"info\",\"event\":\"listening\"}\n"
        );
    }

    #[tokio::test]
    async fn a_line_without_a_trailing_newline_is_still_honoured() {
        let mut stdout = reader(GOOD);
        let mut stderr = reader("");
        let mut sink = LogBuffer::new(64);
        let info = await_ready(&mut stdout, &mut stderr, &mut sink, Duration::from_secs(30))
            .await
            .expect("a flushed line without a newline must still parse");
        assert_eq!(info.port, 54321);
    }

    #[tokio::test]
    async fn both_streams_closing_without_an_announcement_is_eof() {
        let mut stdout = reader("praelector-engine: PRAELECTOR_TOKEN is required\n");
        let mut stderr = reader("praelector-engine: PRAELECTOR_TOKEN is required\n");
        let mut sink = LogBuffer::new(64);
        let err = await_ready(&mut stdout, &mut stderr, &mut sink, Duration::from_secs(30))
            .await
            .expect_err("no announcement means failure");
        assert!(matches!(err, AwaitError::Eof), "got {err:?}");
        assert!(
            sink.render().contains("PRAELECTOR_TOKEN"),
            "the reason must reach the panel"
        );
    }

    #[tokio::test]
    async fn a_malformed_announcement_is_reported_immediately() {
        let mut stdout = reader("PRAELECTOR_READY {\"pid\":1}\n");
        let mut stderr = PendingReader;
        let mut sink = LogBuffer::new(64);
        let err = await_ready(&mut stdout, &mut stderr, &mut sink, Duration::from_secs(30))
            .await
            .expect_err("a missing port is fatal");
        assert!(
            matches!(
                err,
                AwaitError::Malformed(ReadyParseError::MissingPort { .. })
            ),
            "got {err:?}"
        );
    }

    /// `start_paused = true` puts tokio on a virtual clock that jumps straight to
    /// the next timer, so the production 30 s budget is asserted without waiting.
    #[tokio::test(start_paused = true)]
    async fn a_silent_engine_hits_the_budget_not_the_wall_clock() {
        let mut stdout = PendingReader;
        let mut stderr = PendingReader;
        let mut sink = LogBuffer::new(64);

        let started = std::time::Instant::now();
        let err = await_ready(&mut stdout, &mut stderr, &mut sink, READY_BUDGET)
            .await
            .expect_err("silence must time out");
        assert!(
            matches!(err, AwaitError::Timeout(d) if d == READY_BUDGET),
            "got {err:?}"
        );
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "the virtual clock must not sleep"
        );
    }

    #[tokio::test(start_paused = true)]
    async fn a_slow_but_eventually_ready_engine_still_wins() {
        let (mut tx, rx) = tokio::io::duplex(1024);
        let mut stdout = tokio::io::BufReader::new(rx);
        let mut stderr = PendingReader;
        let mut sink = LogBuffer::new(64);

        tokio::spawn(async move {
            use tokio::io::AsyncWriteExt;
            tokio::time::sleep(Duration::from_secs(29)).await;
            tx.write_all(format!("{GOOD}\n").as_bytes())
                .await
                .expect("write");
        });

        let info = await_ready(&mut stdout, &mut stderr, &mut sink, READY_BUDGET)
            .await
            .expect("29 s is inside the 30 s budget");
        assert_eq!(info.port, 54321);
    }

    #[tokio::test(start_paused = true)]
    async fn arriving_one_second_after_the_budget_is_too_late() {
        let (mut tx, rx) = tokio::io::duplex(1024);
        let mut stdout = tokio::io::BufReader::new(rx);
        let mut stderr = PendingReader;
        let mut sink = LogBuffer::new(64);

        tokio::spawn(async move {
            use tokio::io::AsyncWriteExt;
            tokio::time::sleep(Duration::from_secs(31)).await;
            let _ = tx.write_all(format!("{GOOD}\n").as_bytes()).await;
        });

        let err = await_ready(&mut stdout, &mut stderr, &mut sink, READY_BUDGET)
            .await
            .expect_err("31 s exceeds the budget");
        assert!(matches!(err, AwaitError::Timeout(_)), "got {err:?}");
    }
}
