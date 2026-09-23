// SPDX-License-Identifier: Apache-2.0
//! Own process group for the engine (PLAN.md §1.6).
//!
//! Signalling the group, not the pid, is what takes TTS workers down with the
//! engine. A pid of 0 must never reach `kill`: `kill(0, sig)` delivers the
//! signal to the caller's own group, which is the shell.

use std::io;

/// Put the child in a new process group whose id is the child's pid.
pub fn detach(command: &mut tokio::process::Command) {
    command.process_group(0);
}

/// Send `signal` to the process group led by `pid`.
pub fn signal_group(pid: u32, signal: i32) -> io::Result<()> {
    let Some(pgid) = pid_to_group(pid) else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "refusing to signal process group 0",
        ));
    };
    // SAFETY: `pgid` is non-zero and negative, so this targets that group only.
    let rc = unsafe { libc::kill(pgid, signal) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

/// Negative group id, or `None` when the pid cannot be negated safely.
fn pid_to_group(pid: u32) -> Option<i32> {
    let pid = i32::try_from(pid).ok()?;
    if pid <= 0 {
        return None;
    }
    pid.checked_neg()
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn signalling_group_zero_is_refused() {
        let err = signal_group(0, libc::SIGTERM).expect_err("pid 0 must not be signalled");
        assert_eq!(err.kind(), io::ErrorKind::InvalidInput);
    }

    #[test]
    fn a_pid_that_does_not_fit_in_i32_is_refused() {
        let err = signal_group(u32::MAX, libc::SIGTERM).expect_err("unrepresentable pid");
        assert_eq!(err.kind(), io::ErrorKind::InvalidInput);
    }
}
