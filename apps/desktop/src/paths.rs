// SPDX-License-Identifier: Apache-2.0
//! Where this installation keeps things (PLAN.md §1.7).
//!
//! The shell resolves the same directories the engine does, from the same
//! environment variables, so the two processes can never disagree about where
//! projects or logs live. The values are handed to the engine explicitly rather
//! than left to its own defaults — see [`child_env`](crate::engine::config::child_env).

use std::io;
use std::path::{Path, PathBuf};

use serde::Serialize;

/// Engine-side overrides honoured here too, so a tester can point both processes
/// at a scratch directory with one variable (`engine/src/praelector/config.py`).
pub const ENV_DATA_DIR: &str = "PRAELECTOR_DATA_DIR";
pub const ENV_CONFIG_DIR: &str = "PRAELECTOR_CONFIG_DIR";
pub const ENV_LOG_DIR: &str = "PRAELECTOR_LOG_DIR";
pub const ENV_PROJECTS_DIR: &str = "PRAELECTOR_PROJECTS_DIR";

/// Windows directories are capitalised and Linux ones are lowercase, exactly as
/// in the §1.7 table. Windows is case-insensitive so the constant is the only
/// thing that has to differ.
const APP_DIR_NAME: &str = if cfg!(windows) {
    "Praelector"
} else {
    "praelector"
};

/// `~/Praelector/projects` on every platform (PRD §5.2) — deliberately outside the
/// app data dir, because it holds the user's books and finished audiobooks.
const PROJECTS_ROOT_NAME: &str = "Praelector";

/// Every directory the shell needs, already resolved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppPaths {
    pub data_dir: PathBuf,
    pub config_dir: PathBuf,
    pub log_dir: PathBuf,
    pub projects_dir: PathBuf,
    /// `None` when the executable cannot locate its own resources, which is the
    /// normal case for `cargo test` and the dev fallback in
    /// [`resolve`](crate::engine::config::resolve).
    pub resource_dir: Option<PathBuf>,
}

impl AppPaths {
    /// Resolve from the real process environment.
    pub fn from_process_env() -> Self {
        resolve(&|key| std::env::var(key).ok(), None)
    }

    pub fn with_resource_dir(mut self, resource_dir: Option<PathBuf>) -> Self {
        self.resource_dir = resource_dir;
        self
    }

    /// Create the directories the shell owns. `projects_dir` is not created here:
    /// the engine makes it when a project is created, and an empty `~/Praelector`
    /// on first launch would look like a bug to the user.
    pub fn ensure_dirs(&self) -> io::Result<()> {
        for dir in [&self.data_dir, &self.config_dir, &self.log_dir] {
            std::fs::create_dir_all(dir)?;
        }
        Ok(())
    }

    /// The file `tauri-plugin-log` writes to.
    pub fn desktop_log_file(&self) -> PathBuf {
        self.log_dir.join("desktop.log")
    }
}

/// Resolve every directory, honouring the `PRAELECTOR_*` overrides.
///
/// `var` is a lookup rather than a direct `std::env::var` call so the whole table
/// in PLAN.md §1.7 is unit-testable on any host.
pub fn resolve(var: &dyn Fn(&str) -> Option<String>, resource_dir: Option<PathBuf>) -> AppPaths {
    let (data_default, config_default, log_default) = platform_defaults(var);
    let home = home_dir(var);

    let data_dir = override_or(var, ENV_DATA_DIR, data_default);
    let config_dir = override_or(var, ENV_CONFIG_DIR, config_default);
    let log_dir = override_or(var, ENV_LOG_DIR, log_default);
    let projects_dir = override_or(
        var,
        ENV_PROJECTS_DIR,
        home.join(PROJECTS_ROOT_NAME).join("projects"),
    );

    AppPaths {
        data_dir,
        config_dir,
        log_dir,
        projects_dir,
        resource_dir,
    }
}

fn override_or(var: &dyn Fn(&str) -> Option<String>, key: &str, default: PathBuf) -> PathBuf {
    match var(key) {
        Some(raw) if !raw.trim().is_empty() => expand_user(PathBuf::from(raw.trim())),
        _ => default,
    }
}

/// Per-OS defaults, mirroring `platformdirs` on the engine side so both processes
/// land on the same directory without either one importing the other's table.
fn platform_defaults(var: &dyn Fn(&str) -> Option<String>) -> (PathBuf, PathBuf, PathBuf) {
    if cfg!(windows) {
        let home = home_dir(var);
        let local = var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData").join("Local"));
        let roaming = var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join("AppData").join("Roaming"));
        let data = local.join(APP_DIR_NAME);
        // Windows keeps logs next to the data dir; Linux uses XDG_STATE_HOME.
        let logs = data.join("logs");
        (data, roaming.join(APP_DIR_NAME), logs)
    } else {
        let home = home_dir(var);
        let data = xdg(var, "XDG_DATA_HOME", home.join(".local").join("share")).join(APP_DIR_NAME);
        let config = xdg(var, "XDG_CONFIG_HOME", home.join(".config")).join(APP_DIR_NAME);
        let logs = xdg(var, "XDG_STATE_HOME", home.join(".local").join("state"))
            .join(APP_DIR_NAME)
            .join("logs");
        (data, config, logs)
    }
}

fn xdg(var: &dyn Fn(&str) -> Option<String>, key: &str, fallback: PathBuf) -> PathBuf {
    match var(key) {
        // XDG says a *relative* value must be ignored, not joined onto $HOME.
        Some(raw) if !raw.trim().is_empty() && Path::new(raw.trim()).is_absolute() => {
            PathBuf::from(raw.trim())
        }
        _ => fallback,
    }
}

fn home_dir(var: &dyn Fn(&str) -> Option<String>) -> PathBuf {
    let key = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    var(key)
        .filter(|raw| !raw.trim().is_empty())
        .map(|raw| PathBuf::from(raw.trim()))
        // A missing HOME means something is already badly wrong; a scratch dir
        // beats writing into the working directory of a bundled app.
        .unwrap_or_else(std::env::temp_dir)
}

fn expand_user(path: PathBuf) -> PathBuf {
    match path.to_str() {
        Some("~") => home_dir(&|key| std::env::var(key).ok()),
        Some(s) if s.starts_with("~/") || s.starts_with("~\\") => {
            home_dir(&|key| std::env::var(key).ok()).join(&s[2..])
        }
        _ => path,
    }
}

/// Serialise a path for the WebView: POSIX-style with the drive prefix preserved,
/// the same wire form the engine uses (`config.to_posix`), so the UI never has to
/// branch on the host OS.
pub fn to_wire(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

/// Inverse of [`to_wire`]. Accepts both separators so a path the user pasted or
/// that came from an older build still resolves.
pub fn from_wire(value: &str) -> PathBuf {
    if cfg!(windows) {
        PathBuf::from(value.replace('/', "\\"))
    } else {
        PathBuf::from(value)
    }
}

/// Wire form of [`AppPaths`] for the `app_paths` command.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppPathsDto {
    pub data_dir: String,
    pub config_dir: String,
    pub log_dir: String,
    pub projects_dir: String,
    pub resource_dir: Option<String>,
    pub desktop_log_file: String,
}

impl From<&AppPaths> for AppPathsDto {
    fn from(paths: &AppPaths) -> Self {
        Self {
            data_dir: to_wire(&paths.data_dir),
            config_dir: to_wire(&paths.config_dir),
            log_dir: to_wire(&paths.log_dir),
            projects_dir: to_wire(&paths.projects_dir),
            resource_dir: paths.resource_dir.as_ref().map(|p| to_wire(p)),
            desktop_log_file: to_wire(&paths.desktop_log_file()),
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::collections::HashMap;

    use super::*;

    fn lookup(pairs: &[(&str, &str)]) -> impl Fn(&str) -> Option<String> {
        let map: HashMap<String, String> = pairs
            .iter()
            .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
            .collect();
        move |key: &str| map.get(key).cloned()
    }

    #[test]
    fn windows_defaults_match_the_plan_table() {
        if !cfg!(windows) {
            return;
        }
        let var = lookup(&[
            ("LOCALAPPDATA", r"C:\Users\al\AppData\Local"),
            ("APPDATA", r"C:\Users\al\AppData\Roaming"),
            ("USERPROFILE", r"C:\Users\al"),
        ]);
        let paths = resolve(&var, None);
        assert_eq!(
            paths.data_dir,
            PathBuf::from(r"C:\Users\al\AppData\Local\Praelector")
        );
        assert_eq!(
            paths.config_dir,
            PathBuf::from(r"C:\Users\al\AppData\Roaming\Praelector")
        );
        assert_eq!(
            paths.log_dir,
            PathBuf::from(r"C:\Users\al\AppData\Local\Praelector\logs")
        );
        assert_eq!(
            paths.projects_dir,
            PathBuf::from(r"C:\Users\al\Praelector\projects")
        );
    }

    #[test]
    fn unix_defaults_use_xdg_when_set() {
        if cfg!(windows) {
            return;
        }
        let var = lookup(&[
            ("HOME", "/home/al"),
            ("XDG_DATA_HOME", "/mnt/data"),
            ("XDG_CONFIG_HOME", "/mnt/conf"),
            ("XDG_STATE_HOME", "/mnt/state"),
        ]);
        let paths = resolve(&var, None);
        assert_eq!(paths.data_dir, PathBuf::from("/mnt/data/praelector"));
        assert_eq!(paths.config_dir, PathBuf::from("/mnt/conf/praelector"));
        assert_eq!(paths.log_dir, PathBuf::from("/mnt/state/praelector/logs"));
        assert_eq!(
            paths.projects_dir,
            PathBuf::from("/home/al/Praelector/projects")
        );
    }

    #[test]
    fn unix_defaults_fall_back_to_home() {
        if cfg!(windows) {
            return;
        }
        let var = lookup(&[("HOME", "/home/al")]);
        let paths = resolve(&var, None);
        assert_eq!(
            paths.data_dir,
            PathBuf::from("/home/al/.local/share/praelector")
        );
        assert_eq!(
            paths.config_dir,
            PathBuf::from("/home/al/.config/praelector")
        );
        assert_eq!(
            paths.log_dir,
            PathBuf::from("/home/al/.local/state/praelector/logs")
        );
    }

    #[test]
    fn a_relative_xdg_value_is_ignored_not_joined() {
        if cfg!(windows) {
            return;
        }
        let var = lookup(&[("HOME", "/home/al"), ("XDG_DATA_HOME", "relative/nope")]);
        let paths = resolve(&var, None);
        assert_eq!(
            paths.data_dir,
            PathBuf::from("/home/al/.local/share/praelector")
        );
    }

    #[test]
    fn praelector_overrides_win_over_every_default() {
        let var = lookup(&[
            ("USERPROFILE", r"C:\Users\al"),
            ("HOME", "/home/al"),
            (
                ENV_DATA_DIR,
                if cfg!(windows) {
                    r"D:\scratch\data"
                } else {
                    "/scratch/data"
                },
            ),
            (
                ENV_LOG_DIR,
                if cfg!(windows) {
                    r"D:\scratch\logs"
                } else {
                    "/scratch/logs"
                },
            ),
            (
                ENV_PROJECTS_DIR,
                if cfg!(windows) { r"D:\books" } else { "/books" },
            ),
        ]);
        let paths = resolve(&var, None);
        assert_eq!(
            paths.data_dir,
            PathBuf::from(if cfg!(windows) {
                r"D:\scratch\data"
            } else {
                "/scratch/data"
            })
        );
        assert_eq!(
            paths.log_dir,
            PathBuf::from(if cfg!(windows) {
                r"D:\scratch\logs"
            } else {
                "/scratch/logs"
            })
        );
        assert_eq!(
            paths.projects_dir,
            PathBuf::from(if cfg!(windows) { r"D:\books" } else { "/books" })
        );
        // config_dir was not overridden, so it keeps its platform default.
        assert!(!paths.config_dir.starts_with(if cfg!(windows) {
            r"D:\scratch"
        } else {
            "/scratch"
        }));
    }

    #[test]
    fn a_blank_override_is_treated_as_absent() {
        let var = lookup(&[
            ("USERPROFILE", r"C:\Users\al"),
            ("HOME", "/home/al"),
            (ENV_DATA_DIR, "   "),
        ]);
        let paths = resolve(&var, None);
        assert!(!paths.data_dir.to_string_lossy().contains("   "));
    }

    #[test]
    fn wire_paths_are_posix_style_and_round_trip() {
        if cfg!(windows) {
            let path = Path::new(r"C:\Users\al\Praelector\projects\prj_01");
            assert_eq!(to_wire(path), "C:/Users/al/Praelector/projects/prj_01");
            assert_eq!(from_wire(&to_wire(path)), path.to_path_buf());
        } else {
            let path = Path::new("/home/al/Praelector/projects/prj_01");
            assert_eq!(to_wire(path), "/home/al/Praelector/projects/prj_01");
            assert_eq!(from_wire(&to_wire(path)), path.to_path_buf());
        }
    }

    #[test]
    fn from_wire_accepts_the_other_separator() {
        if !cfg!(windows) {
            return;
        }
        assert_eq!(
            from_wire("C:/books/a.epub"),
            PathBuf::from(r"C:\books\a.epub")
        );
    }

    #[test]
    fn ensure_dirs_creates_the_shell_owned_directories_only() {
        let root = std::env::temp_dir().join(format!("praelector-paths-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let paths = AppPaths {
            data_dir: root.join("data"),
            config_dir: root.join("config"),
            log_dir: root.join("logs"),
            projects_dir: root.join("projects"),
            resource_dir: None,
        };
        paths
            .ensure_dirs()
            .expect("directories should be creatable");
        assert!(paths.data_dir.is_dir());
        assert!(paths.config_dir.is_dir());
        assert!(paths.log_dir.is_dir());
        assert!(!paths.projects_dir.exists(), "the engine owns projects_dir");
        assert_eq!(paths.desktop_log_file().file_name().unwrap(), "desktop.log");
        std::fs::remove_dir_all(&root).ok();
    }
}
