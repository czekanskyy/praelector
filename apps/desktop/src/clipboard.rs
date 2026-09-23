// SPDX-License-Identifier: Apache-2.0
//! Copy redacted diagnostics without adding a clipboard crate.
//!
//! The fatal dialog cannot grow a localised "Copy" button (that string would
//! belong to the UI catalogues). Putting the already-redacted buffer on the
//! clipboard, and returning it from `copy_engine_logs`, is the shell-side half.

/// `CF_UNICODETEXT` from the Win32 clipboard. Kept numeric so this module does
/// not pull in the whole OLE feature set for one constant.
#[cfg(windows)]
const CF_UNICODETEXT: u32 = 13;

/// Returns whether the text reached the system clipboard. Failure is not fatal:
/// the same text is still written to `engine-diagnostics.txt` and returned to
/// the caller.
pub fn copy_text(text: &str) -> bool {
    #[cfg(windows)]
    {
        copy_windows(text)
    }
    #[cfg(not(windows))]
    {
        copy_unix(text)
    }
}

#[cfg(windows)]
fn copy_windows(text: &str) -> bool {
    use windows::Win32::Foundation::{GlobalFree, HANDLE, HGLOBAL};
    use windows::Win32::System::DataExchange::{
        CloseClipboard, EmptyClipboard, OpenClipboard, SetClipboardData,
    };
    use windows::Win32::System::Memory::{GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE};

    let wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
    let bytes = wide.len().saturating_mul(std::mem::size_of::<u16>());
    // SAFETY: a moveable allocation of exactly the UTF-16 payload, including the
    // terminating NUL, is what `SetClipboardData(CF_UNICODETEXT)` takes ownership
    // of. On the failure paths the allocation is released with `GlobalFree`.
    unsafe {
        let Ok(memory) = GlobalAlloc(GMEM_MOVEABLE, bytes) else {
            return false;
        };
        let ptr = GlobalLock(memory);
        if ptr.is_null() {
            let _ = GlobalFree(Some(memory));
            return false;
        }
        std::ptr::copy_nonoverlapping(wide.as_ptr(), ptr.cast::<u16>(), wide.len());
        // FALSE here usually means the lock count hit zero, which is success
        // for a single `GlobalLock`. `GetLastError` distinguishes the real
        // failure, and a stuck lock is not worth aborting the copy for.
        let _ = GlobalUnlock(memory);
        if OpenClipboard(None).is_err() {
            let _ = GlobalFree(Some(memory));
            return false;
        }
        if EmptyClipboard().is_err() {
            let _ = CloseClipboard();
            let _ = GlobalFree(Some(memory));
            return false;
        }
        let copied = SetClipboardData(CF_UNICODETEXT, Some(HANDLE(memory.0))).is_ok();
        let _ = CloseClipboard();
        if !copied {
            // `SetClipboardData` did not take ownership.
            let _ = GlobalFree(Some(HGLOBAL(memory.0)));
        }
        copied
    }
}

#[cfg(not(windows))]
fn copy_unix(text: &str) -> bool {
    // First tool that exists wins. None of these are required: the diagnostics
    // file is the portable copy path.
    pipe_to("wl-copy", &[], text)
        || pipe_to("xclip", &["-selection", "clipboard"], text)
        || pipe_to("pbcopy", &[], text)
}

#[cfg(not(windows))]
fn pipe_to(program: &str, args: &[&str], text: &str) -> bool {
    use std::io::Write;
    use std::process::{Command, Stdio};

    let mut child = match Command::new(program)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(_) => return false,
    };
    let Some(mut stdin) = child.stdin.take() else {
        return false;
    };
    if stdin.write_all(text.as_bytes()).is_err() {
        return false;
    }
    drop(stdin);
    matches!(child.wait(), Ok(status) if status.success())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use super::*;

    #[test]
    fn copy_text_does_not_panic() {
        // A headless session may refuse the clipboard. That is still success
        // for this test: the call has to return, not abort the shell.
        let _ = copy_text("praelector");
    }
}
