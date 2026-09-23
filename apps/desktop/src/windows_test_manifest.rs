// SPDX-License-Identifier: Apache-2.0
//! Pulls the Common Controls v6 manifest into this unit-test executable.
//!
//! `build.rs` archives the Tauri resource object (GNU) or a
//! `/manifestdependency` object (MSVC) under the name below. The reference has
//! to live in the harness itself: `cargo test --lib` does not apply
//! `rustc-link-arg-tests`, and the bin must not link the resource a second time.

#[link(name = "praelector_test_manifest", kind = "static")]
unsafe extern "C" {
    static praelector_test_manifest_anchor: u8;
}

#[used]
static KEEP_TEST_MANIFEST: &u8 = unsafe { &praelector_test_manifest_anchor };
