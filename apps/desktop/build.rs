// SPDX-License-Identifier: Apache-2.0
//! Embeds the Tauri context (config, CSP, icons, capabilities) into the binary.
//!
//! `cargo test` compiles the shell before `beforeBuildCommand` runs, so the stub
//! frontend and the empty resource directories have to be created here too. A
//! real `apps/ui` package is left alone — building it is the frontend script's job.

use std::fs;
use std::path::Path;

const STUB_HTML: &str = "<!doctype html><html><head><meta charset=\"utf-8\"><title>Praelector</title></head><body></body></html>\n";

fn main() {
    let manifest_dir = Path::new(env!("CARGO_MANIFEST_DIR"));
    println!("cargo:rerun-if-changed=../ui/package.json");
    ensure_frontend_stub(manifest_dir);
    let _ = fs::create_dir_all(manifest_dir.join("resources").join("engine"));
    let _ = fs::create_dir_all(manifest_dir.join("resources").join("bin"));
    // Command permissions are not inferred from `generate_handler!` at this
    // point; listing them here is what emits `allow-<command>` for the capability.
    let manifest = tauri_build::AppManifest::new().commands(&[
        "engine_endpoint",
        "engine_status",
        "engine_logs",
        "copy_engine_logs",
        "open_path",
        "pick_file",
        "app_paths",
    ]);
    if let Err(error) =
        tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
    {
        println!("cargo:warning={error:#}");
        std::process::exit(1);
    }
    // `tauri-winres` links the Common Controls v6 manifest only into bins.
    // Unit-test harnesses are not bins and do not receive `rustc-link-arg-tests`
    // (cargo#10937). They import `TaskDialogIndirect`; without the manifest the
    // loader binds comctl32 v5 and exits before any test. An unscoped link arg
    // would also hit the bin, and a second RT_MANIFEST fails the MSVC link.
    link_manifest_into_tests();
}

fn link_manifest_into_tests() {
    let Ok(target_os) = std::env::var("CARGO_CFG_TARGET_OS") else {
        return;
    };
    if target_os != "windows" {
        return;
    }
    let Ok(out_dir) = std::env::var("OUT_DIR") else {
        println!("cargo:warning=OUT_DIR unset; cannot embed the test manifest");
        std::process::exit(1);
    };
    let file_name = if std::env::var("CARGO_CFG_TARGET_ENV").ok().as_deref() == Some("msvc") {
        "resource.lib"
    } else {
        "libresource.a"
    };
    let resource = Path::new(&out_dir).join(file_name);
    if !resource.is_file() {
        println!(
            "cargo:warning=Windows resource {} was not produced; test binaries would fail to start",
            resource.display()
        );
        std::process::exit(1);
    }
    // Integration tests are real test targets, so this does not touch the bin.
    println!("cargo:rustc-link-arg-tests={}", resource.display());
    if std::env::var("CARGO_CFG_TARGET_ENV").ok().as_deref() == Some("msvc") {
        // The .res above is not a COFF object, so the unit-test harness (which
        // ignores `rustc-link-arg-tests`) gets the dependency from a referenced
        // symbol instead. Unreferenced artifacts drop the member.
        let source = Path::new(&out_dir).join("test_manifest_anchor.c");
        let c_source = r#"
#pragma comment(linker, "/manifestdependency:\"type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'\"")
void praelector_test_manifest_anchor(void) {}
"#;
        if fs::write(&source, c_source).is_err() {
            println!("cargo:warning=could not write {}", source.display());
            std::process::exit(1);
        }
        cc::Build::new()
            .file(&source)
            .compile("praelector_test_manifest");
        return;
    }
    let bytes = match fs::read(&resource) {
        Ok(bytes) => bytes,
        Err(error) => {
            println!("cargo:warning=reading {}: {error}", resource.display());
            std::process::exit(1);
        }
    };
    let Some(with_symbol) = add_coff_anchor(&bytes) else {
        println!("cargo:warning=resource object has no COFF symbol table; cannot anchor the test manifest");
        std::process::exit(1);
    };
    let archive = Path::new(&out_dir).join("libpraelector_test_manifest.a");
    if fs::write(&archive, gnu_archive("anchor.o", &with_symbol)).is_err() {
        println!("cargo:warning=could not write {}", archive.display());
        std::process::exit(1);
    }
    println!("cargo:rustc-link-search=native={out_dir}");
    // Pulled into the unit-test harness by `windows_test_manifest`. Bins do not
    // reference the anchor, so the linker leaves this member out.
    println!("cargo:rustc-link-lib=static=praelector_test_manifest");
}

/// Append an external symbol to a MinGW resource object so a `#[used]` static
/// can pull the `.rsrc` section into the unit-test executable.
fn add_coff_anchor(coff: &[u8]) -> Option<Vec<u8>> {
    if coff.len() < 20 {
        return None;
    }
    let symptr = read_u32(coff, 8)?;
    let nsym = read_u32(coff, 12)?;
    if symptr == 0 || nsym == 0 {
        return None;
    }
    let sym_end = symptr as usize + nsym as usize * 18;
    if sym_end > coff.len() {
        return None;
    }
    let name = b"praelector_test_manifest_anchor";
    let (old_strings, keep_through) = match read_u32(coff, sym_end) {
        Some(size) if size >= 4 && sym_end + size as usize <= coff.len() => {
            (coff[sym_end + 4..sym_end + size as usize].to_vec(), sym_end)
        }
        _ => (Vec::new(), sym_end),
    };
    let offset = 4 + old_strings.len() as u32;
    let mut strings = old_strings;
    strings.extend_from_slice(name);
    strings.push(0);
    let mut out = coff[..keep_through].to_vec();
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&offset.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out.push(2);
    out.push(0);
    let str_size = (4 + strings.len()) as u32;
    out.extend_from_slice(&str_size.to_le_bytes());
    out.extend_from_slice(&strings);
    out[12..16].copy_from_slice(&(nsym + 1).to_le_bytes());
    Some(out)
}

fn gnu_archive(member: &str, bytes: &[u8]) -> Vec<u8> {
    let symbol = b"praelector_test_manifest_anchor\0";
    let index_raw = 8 + symbol.len();
    let index_len = index_raw + index_raw % 2;
    let member_off = 8 + 60 + index_len;
    let mut index = Vec::with_capacity(index_len);
    index.extend_from_slice(&1u32.to_be_bytes());
    index.extend_from_slice(&(member_off as u32).to_be_bytes());
    index.extend_from_slice(symbol);
    if index.len() % 2 == 1 {
        index.push(b'\n');
    }
    let mut out = Vec::with_capacity(member_off + 60 + bytes.len() + 1);
    out.extend_from_slice(b"!<arch>\n");
    out.extend_from_slice(&ar_header("/", index.len()));
    out.extend_from_slice(&index);
    out.extend_from_slice(&ar_header(member, bytes.len()));
    out.extend_from_slice(bytes);
    if bytes.len() % 2 == 1 {
        out.push(b'\n');
    }
    out
}

fn ar_header(name: &str, size: usize) -> [u8; 60] {
    let mut header = [b' '; 60];
    // The archive symbol index is the member whose name is exactly `/`.
    // Anything else is a file member and keeps the trailing slash GNU ar expects.
    let labeled = if name == "/" {
        "/".to_string()
    } else {
        format!("{name}/")
    };
    let label = labeled.as_bytes();
    let n = label.len().min(16);
    header[..n].copy_from_slice(&label[..n]);
    header[16..28].copy_from_slice(b"0           ");
    header[28..34].copy_from_slice(b"0     ");
    header[34..40].copy_from_slice(b"0     ");
    header[40..48].copy_from_slice(b"100644  ");
    let size_field = format!("{size:<10}");
    header[48..58].copy_from_slice(size_field.as_bytes());
    header[58..60].copy_from_slice(b"`\n");
    header
}

fn read_u32(bytes: &[u8], offset: usize) -> Option<u32> {
    let end = offset.checked_add(4)?;
    let raw = bytes.get(offset..end)?;
    let mut buf = [0u8; 4];
    buf.copy_from_slice(raw);
    Some(u32::from_le_bytes(buf))
}

fn ensure_frontend_stub(manifest_dir: &Path) {
    if manifest_dir.join("../ui/package.json").exists() {
        return;
    }
    let dist = manifest_dir.join("../ui/dist");
    let index = dist.join("index.html");
    if index.is_file() {
        return;
    }
    if fs::create_dir_all(&dist).is_ok() {
        let _ = fs::write(index, STUB_HTML);
    }
}
