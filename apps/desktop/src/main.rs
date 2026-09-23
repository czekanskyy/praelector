// SPDX-License-Identifier: Apache-2.0
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // `run` failing means the process cannot show a window at all. Every later
    // failure is reported through the supervisor instead of aborting here.
    #[allow(clippy::expect_used)]
    praelector_desktop_lib::run().expect("praelector desktop failed to start");
}
