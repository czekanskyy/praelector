// SPDX-License-Identifier: Apache-2.0
#[cfg(unix)]
pub mod unix {
    use std::os::unix::process::CommandExt;
    use std::process::Command;

    pub fn set_process_group(cmd: &mut Command) {
        cmd.process_group(0);
    }
}
