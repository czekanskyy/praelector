// SPDX-License-Identifier: Apache-2.0
//! The rolling engine-output buffer behind the fatal panel (PLAN.md §1.6 step 4).
//!
//! When the engine fails to start or stops answering, the last 200 lines of its
//! stdout and stderr are the only evidence the user can send us. This buffer is
//! the whole diagnostics story, so it has to be cheap enough to fill on every
//! line and safe to render while the supervisor is still writing.

use std::collections::VecDeque;

use serde::Serialize;

use crate::logging::redact;

/// PLAN.md §1.6: "a fatal panel with the last 200 lines".
pub const DEFAULT_CAPACITY: usize = 200;

/// A single pathological line (a traceback with a base64 blob in it) must not be
/// able to blow up the buffer just because it is one of 200.
pub const MAX_LINE_LEN: usize = 4_000;

const TRUNCATION_MARK: &str = "…[truncated]";

/// Which pipe a line came from. The engine puts JSON logs on stderr and exactly
/// one readiness line on stdout, so the label carries real information.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum LogStream {
    Stdout,
    Stderr,
}

impl LogStream {
    pub fn label(self) -> &'static str {
        match self {
            Self::Stdout => "out",
            Self::Stderr => "err",
        }
    }
}

/// One buffered line. `seq` is monotonically increasing across the whole app
/// lifetime, so a restart is visible as a gap rather than as a silent reset.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LogLine {
    pub seq: u64,
    pub stream: LogStream,
    pub text: String,
}

/// Anything that can absorb an engine output line. Implemented by [`LogBuffer`]
/// for unit tests and by the shared handle in the supervisor for production.
///
/// The method is named `record` rather than `push` so the blanket impl below
/// cannot be mistaken for — or accidentally become — infinite recursion.
pub trait LogSink: Send {
    fn record(&mut self, stream: LogStream, line: &str);
}

impl LogSink for LogBuffer {
    fn record(&mut self, stream: LogStream, line: &str) {
        self.push(stream, line);
    }
}

/// A fixed-capacity ring of engine output lines.
pub struct LogBuffer {
    capacity: usize,
    lines: VecDeque<LogLine>,
    /// Running total of `text.len()` plus the per-line prefix, kept so [`render`]
    /// can allocate exactly once instead of growing a `String` 200 times.
    bytes: usize,
    next_seq: u64,
    /// The launch token. Held here so redaction cannot be forgotten by a caller.
    /// Every launch token this process has handed out. Newest last.
    secrets: Vec<String>,
}

impl std::fmt::Debug for LogBuffer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("LogBuffer")
            .field("capacity", &self.capacity)
            .field("len", &self.lines.len())
            .field("bytes", &self.bytes)
            .field("secrets", &self.secrets.len())
            .finish()
    }
}

impl LogBuffer {
    pub fn new(capacity: usize) -> Self {
        Self {
            // A zero capacity would make every push a no-op and hide the very
            // evidence the fatal panel exists to show.
            capacity: capacity.max(1),
            lines: VecDeque::with_capacity(capacity.max(1)),
            bytes: 0,
            next_seq: 0,
            secrets: Vec::new(),
        }
    }

    /// Replace the remembered secrets with `secret`. An empty string clears them:
    /// redacting against `""` would blank every line.
    pub fn set_secret(&mut self, secret: impl Into<String>) {
        self.secrets.clear();
        self.add_secret(secret);
    }

    /// Remember another secret without forgetting the previous ones.
    ///
    /// The supervisor rotates the launch token on every restart, and a line from
    /// the process that is being killed can arrive after the new token is current.
    pub fn add_secret(&mut self, secret: impl Into<String>) {
        let secret = secret.into();
        if secret.is_empty() || self.secrets.iter().any(|existing| existing == &secret) {
            return;
        }
        self.secrets.push(secret);
    }

    pub fn len(&self) -> usize {
        self.lines.len()
    }

    pub fn is_empty(&self) -> bool {
        self.lines.is_empty()
    }

    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Append one line, evicting the oldest when full.
    pub fn push(&mut self, stream: LogStream, line: &str) {
        let text = self.scrub(line);
        if self.lines.len() == self.capacity {
            if let Some(evicted) = self.lines.pop_front() {
                self.bytes = self.bytes.saturating_sub(entry_len(&evicted));
            }
        }
        let entry = LogLine {
            seq: self.next_seq,
            stream,
            text,
        };
        self.next_seq = self.next_seq.wrapping_add(1);
        self.bytes = self.bytes.saturating_add(entry_len(&entry));
        self.lines.push_back(entry);
    }

    /// Flatten to the single string the `engine_logs` command returns, oldest
    /// line first. One allocation, no re-splitting.
    pub fn render(&self) -> String {
        let mut out = String::with_capacity(self.bytes);
        for line in &self.lines {
            out.push_str(line.stream.label());
            out.push(' ');
            out.push_str(&line.text);
            out.push('\n');
        }
        out
    }

    pub fn clear(&mut self) {
        self.lines.clear();
        self.bytes = 0;
    }

    fn scrub(&self, line: &str) -> String {
        let without_newline = line.trim_end_matches(['\r', '\n']);
        let mut redacted = std::borrow::Cow::Borrowed(without_newline);
        for secret in &self.secrets {
            if let std::borrow::Cow::Owned(replaced) = redact(&redacted, secret) {
                redacted = std::borrow::Cow::Owned(replaced);
            }
        }
        // Char-safe truncation: slicing a UTF-8 str at a byte offset would panic
        // on the first Polish diacritic that happened to straddle the boundary.
        if redacted.len() > MAX_LINE_LEN {
            let mut end = MAX_LINE_LEN;
            while !redacted.is_char_boundary(end) {
                end -= 1;
            }
            format!("{}{}", &redacted[..end], TRUNCATION_MARK)
        } else {
            redacted.into_owned()
        }
    }
}

/// Bytes an entry contributes to [`LogBuffer::render`]: label, space, text, newline.
fn entry_len(line: &LogLine) -> usize {
    line.stream.label().len() + 1 + line.text.len() + 1
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn it_caps_at_two_hundred_lines() {
        let mut buf = LogBuffer::new(DEFAULT_CAPACITY);
        for i in 0..500 {
            buf.push(LogStream::Stderr, &format!("line {i}"));
        }
        assert_eq!(buf.len(), 200);
        assert_eq!(buf.capacity(), DEFAULT_CAPACITY);
        let rendered = buf.render();
        let lines: Vec<&str> = rendered.lines().collect();
        assert_eq!(lines.len(), 200);
        assert_eq!(
            *lines.first().unwrap(),
            "err line 300",
            "the oldest lines are evicted"
        );
        assert_eq!(*lines.last().unwrap(), "err line 499");
    }

    #[test]
    fn it_preserves_order_and_stream_labels() {
        let mut buf = LogBuffer::new(8);
        buf.push(LogStream::Stdout, "first");
        buf.push(LogStream::Stderr, "second");
        buf.push(LogStream::Stdout, "third");
        assert_eq!(buf.render(), "out first\nerr second\nout third\n");
        assert_eq!(
            buf.lines.iter().map(|l| l.seq).collect::<Vec<_>>(),
            vec![0, 1, 2]
        );
    }

    #[test]
    fn sequence_numbers_keep_counting_across_eviction() {
        let mut buf = LogBuffer::new(2);
        buf.push(LogStream::Stderr, "a");
        buf.push(LogStream::Stderr, "b");
        buf.push(LogStream::Stderr, "c");
        let seqs: Vec<u64> = buf.lines.iter().map(|l| l.seq).collect();
        assert_eq!(seqs, vec![1, 2]);
    }

    #[test]
    fn render_allocates_once_and_reports_the_exact_size() {
        let mut buf = LogBuffer::new(DEFAULT_CAPACITY);
        for i in 0..DEFAULT_CAPACITY {
            buf.push(LogStream::Stderr, &format!("padded line {i:04}"));
        }
        // `bytes` must equal the rendered length, otherwise the capacity hint in
        // `render` is a lie and the string reallocates while growing.
        assert_eq!(buf.render().len(), buf.bytes);
        assert_eq!(buf.render().capacity(), buf.bytes);
    }

    #[test]
    fn it_strips_the_launch_token_from_every_line() {
        let mut buf = LogBuffer::new(4);
        // Low entropy on purpose: the buffer strips an exact secret, and
        // gitleaks' generic-api-key rule ignores a token of all one character.
        buf.set_secret("aaaaaaaaaaaaaaaa");
        buf.push(
            LogStream::Stderr,
            r#"{"event":"ws","url":"ws://x/v1/ws?token=aaaaaaaaaaaaaaaa"}"#,
        );
        buf.push(LogStream::Stdout, "nothing secret here");
        let rendered = buf.render();
        assert!(!rendered.contains("aaaaaaaaaaaaaaaa"));
        assert!(rendered.contains(crate::logging::REDACTION));
        assert!(rendered.contains("nothing secret here"));
    }

    #[test]
    fn overlong_lines_are_truncated_on_a_char_boundary() {
        let mut buf = LogBuffer::new(4);
        let long = "zażółć gęślą jaźń".repeat(400);
        buf.push(LogStream::Stderr, &long);
        assert_eq!(buf.len(), 1);
        let rendered = buf.render();
        assert!(rendered.ends_with(&format!("{TRUNCATION_MARK}\n")));
        assert!(
            rendered.len() < long.len(),
            "the buffer must not retain the whole blob"
        );
    }

    #[test]
    fn trailing_newlines_are_stripped_so_render_stays_one_line_per_entry() {
        let mut buf = LogBuffer::new(4);
        buf.push(LogStream::Stderr, "alpha\r\n");
        buf.push(LogStream::Stderr, "beta\n");
        assert_eq!(buf.render(), "err alpha\nerr beta\n");
    }

    #[test]
    fn a_zero_capacity_buffer_still_keeps_the_newest_line() {
        let mut buf = LogBuffer::new(0);
        buf.push(LogStream::Stderr, "only");
        buf.push(LogStream::Stderr, "newest");
        assert_eq!(buf.render(), "err newest\n");
    }

    #[test]
    fn every_remembered_token_is_stripped() {
        let mut buf = LogBuffer::new(4);
        buf.add_secret("alpha-token");
        buf.add_secret("beta-token");
        buf.add_secret("alpha-token");
        buf.push(LogStream::Stderr, "alpha-token then beta-token");
        let rendered = buf.render();
        assert!(!rendered.contains("alpha-token"));
        assert!(!rendered.contains("beta-token"));
        assert!(rendered.contains(crate::logging::REDACTION));
    }

    #[test]
    fn clear_empties_without_losing_the_secret() {
        let mut buf = LogBuffer::new(4);
        buf.set_secret("s3cret");
        buf.push(LogStream::Stderr, "s3cret leaked");
        buf.clear();
        assert!(buf.is_empty());
        buf.push(LogStream::Stderr, "s3cret again");
        assert!(!buf.render().contains("s3cret"));
    }
}
