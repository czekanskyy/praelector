// SPDX-License-Identifier: Apache-2.0
//! Kill-on-close Job Object (PLAN.md §1.6).
//!
//! The engine and every process it later spawns are assigned here. Closing the
//! handle — including when the OS reaps it because the shell was killed — kills
//! those processes. That is the path `Drop` does not get to run.

use std::io;

use windows::core::PCWSTR;
use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows::Win32::System::Threading::{OpenProcess, TerminateProcess, PROCESS_TERMINATE};

/// An owned job. Dropping it closes the handle and, because of
/// `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, kills every process still in the job.
pub struct JobObject {
    handle: HANDLE,
}

// SAFETY: the job handle is exclusively owned. The Win32 calls used here take
// the raw handle by value and are thread-safe; the pointer is never turned
// into a Rust reference.
unsafe impl Send for JobObject {}
unsafe impl Sync for JobObject {}

impl JobObject {
    /// Create an anonymous job that dies with this handle.
    ///
    /// The shell process itself is never assigned: putting the parent in the job
    /// would make closing it a suicide pact with the window.
    pub fn new() -> io::Result<Self> {
        // SAFETY: a nameless job and a null security descriptor are the documented
        // way to create a private job owned by this process.
        let handle = unsafe { CreateJobObjectW(None, PCWSTR::null()) }.map_err(io_err)?;
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let len = u32::try_from(std::mem::size_of_val(&info)).unwrap_or(u32::MAX);
        // SAFETY: `handle` is an open job and `info` matches the information class
        // and the length passed in.
        let set = unsafe {
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                std::ptr::from_ref(&info).cast(),
                len,
            )
        };
        if let Err(err) = set {
            // SAFETY: `handle` came from CreateJobObjectW and has not been closed.
            unsafe {
                let _ = CloseHandle(handle);
            }
            return Err(io_err(err));
        }
        Ok(Self { handle })
    }

    /// Put `process` in this job. The caller keeps ownership of `process`;
    /// assignment does not close it.
    pub fn assign(&self, process: std::os::windows::io::RawHandle) -> io::Result<()> {
        // SAFETY: `process` is a live process handle owned by the caller for the
        // duration of the call, and `self.handle` is an open job.
        unsafe { AssignProcessToJobObject(self.handle, HANDLE(process)) }.map_err(io_err)
    }
}

impl Drop for JobObject {
    fn drop(&mut self) {
        // SAFETY: `handle` is exclusively owned and closed exactly once.
        unsafe {
            let _ = CloseHandle(self.handle);
        }
    }
}

/// `TerminateProcess` on `pid`. Used for the post-shutdown step; the job object
/// is what covers a shell crash, where this function never runs.
///
/// A pid of 0 is refused: `OpenProcess` would not mean "this process", but it is
/// not a pid we ever spawned either, and guessing here is how a supervisor kills
/// the wrong thing.
pub(crate) fn terminate_pid(pid: u32) {
    if pid == 0 {
        return;
    }
    // SAFETY: the pid was returned by `CreateProcess` for a child we spawned.
    // `OpenProcess` failing means it is already gone, which is the outcome we want.
    unsafe {
        let Ok(handle) = OpenProcess(PROCESS_TERMINATE, false, pid) else {
            return;
        };
        let _ = TerminateProcess(handle, 1);
        let _ = CloseHandle(handle);
    }
}

fn io_err(err: windows::core::Error) -> io::Error {
    io::Error::other(err.to_string())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn constructing_a_job_object_does_not_panic() {
        let job = JobObject::new().expect("CreateJobObjectW");
        drop(job);
    }

    #[test]
    fn terminate_refuses_pid_zero() {
        // Must return rather than signal the system idle process.
        terminate_pid(0);
    }
}
