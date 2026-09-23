// SPDX-License-Identifier: Apache-2.0
//! Finding the engine and building the environment it is launched with
//! (PLAN.md §1.6 step 1–2, §1.7).

use std::path::{Path, PathBuf};

use base64::Engine as _;
use serde::Serialize;

use super::EngineError;
use crate::paths::AppPaths;

/// Every variable the shell sets, named exactly as `engine/src/praelector/config.py`
/// reads them. Duplicated as constants rather than parsed out of the Python file
/// because the two sides are a wire contract, and a typo here has to fail a test
/// rather than silently start an engine with default paths.
pub const ENV_TOKEN: &str = "PRAELECTOR_TOKEN";
pub const ENV_DATA_DIR: &str = "PRAELECTOR_DATA_DIR";
pub const ENV_CONFIG_DIR: &str = "PRAELECTOR_CONFIG_DIR";
pub const ENV_LOG_DIR: &str = "PRAELECTOR_LOG_DIR";
pub const ENV_PROJECTS_DIR: &str = "PRAELECTOR_PROJECTS_DIR";
pub const ENV_LOG_LEVEL: &str = "PRAELECTOR_LOG_LEVEL";
pub const ENV_PARENT_PID: &str = "PRAELECTOR_PARENT_PID";
pub const ENV_ENGINE_CMD: &str = "PRAELECTOR_ENGINE_CMD";

/// Bytes of entropy in the launch token. Matches `security.generate_token(32)`.
pub const TOKEN_BYTES: usize = 32;

const ENGINE_STEM: &str = "praelector-engine";

/// How the command line was decided — kept for `desktop.log`, because "which engine
/// did this build actually run?" is the first question in every bug report.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum CommandSource {
    /// `PRAELECTOR_ENGINE_CMD`, for debugging.
    EnvOverride,
    /// `<resourceDir>/engine/praelector-engine[.exe]` — the release path.
    Bundled,
    /// `uv run --project engine praelector-engine` — a source checkout.
    Dev,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineCommand {
    pub program: String,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub source: CommandSource,
}

impl EngineCommand {
    /// One-line form for logs. Never contains the token: the command line carries
    /// no secrets precisely so that it is safe to log (PLAN.md §1.5).
    pub fn describe(&self) -> String {
        let mut parts = vec![self.program.clone()];
        parts.extend(self.args.iter().cloned());
        let mut line = parts.join(" ");
        if let Some(cwd) = &self.cwd {
            line.push_str(&format!("  [cwd {}]", cwd.display()));
        }
        line
    }
}

/// Inputs to [`resolve`]. `exists` is injected so the whole §1.7 precedence order is
/// testable without touching the filesystem.
pub struct Resolver<'a> {
    pub engine_cmd_env: Option<&'a str>,
    pub resource_dir: Option<&'a Path>,
    /// Directories whose ancestors are searched for `engine/pyproject.toml`.
    pub dev_search_roots: &'a [PathBuf],
    pub exists: &'a dyn Fn(&Path) -> bool,
}

/// Resolve the engine command, in PLAN.md §1.7 order:
/// `PRAELECTOR_ENGINE_CMD` → `<resourceDir>/engine/praelector-engine[.exe]` → dev `uv run`.
///
/// The dev fallback is not a guess about where a source checkout might be: it only
/// applies when `engine/pyproject.toml` is actually found above one of the search
/// roots. A bundled app always satisfies step two, so a release build that reaches
/// step three is a packaging bug and is reported as [`EngineError::NotFound`].
pub fn resolve(resolver: &Resolver<'_>) -> Result<EngineCommand, EngineError> {
    if let Some(raw) = resolver.engine_cmd_env {
        if !raw.trim().is_empty() {
            let mut parts = split_command(raw);
            if !parts.is_empty() {
                let program = parts.remove(0);
                return Ok(EngineCommand {
                    program,
                    args: parts,
                    // `uv run --project engine …` resolves `engine` against the cwd,
                    // so an override in a source checkout still needs the repo root.
                    cwd: find_dev_root(resolver.dev_search_roots, resolver.exists),
                    source: CommandSource::EnvOverride,
                });
            }
        }
    }

    let mut searched = Vec::new();
    if let Some(resource_dir) = resolver.resource_dir {
        let bundled = bundled_engine_path(resource_dir);
        searched.push(bundled.display().to_string());
        if (resolver.exists)(&bundled) {
            return Ok(EngineCommand {
                program: bundled.display().to_string(),
                args: Vec::new(),
                // PyInstaller onedir finds `_internal` next to the executable, so
                // the cwd only matters for relative paths in a user's config.
                cwd: bundled.parent().map(Path::to_path_buf),
                source: CommandSource::Bundled,
            });
        }
    }

    if let Some(root) = find_dev_root(resolver.dev_search_roots, resolver.exists) {
        searched.push(root.join("engine").display().to_string());
        return Ok(EngineCommand {
            program: "uv".to_string(),
            args: vec![
                "run".to_string(),
                "--project".to_string(),
                "engine".to_string(),
                ENGINE_STEM.to_string(),
            ],
            cwd: Some(root),
            source: CommandSource::Dev,
        });
    }

    Err(EngineError::NotFound { searched })
}

fn bundled_engine_path(resource_dir: &Path) -> PathBuf {
    let name = if cfg!(windows) {
        format!("{ENGINE_STEM}.exe")
    } else {
        ENGINE_STEM.to_string()
    };
    resource_dir.join("engine").join(name)
}

/// Walk up from each root looking for `engine/pyproject.toml`.
fn find_dev_root(roots: &[PathBuf], exists: &dyn Fn(&Path) -> bool) -> Option<PathBuf> {
    roots
        .iter()
        .find_map(|root| {
            root.ancestors()
                .find(|candidate| exists(&candidate.join("engine").join("pyproject.toml")))
        })
        .map(Path::to_path_buf)
}

/// Split a command line on whitespace, honouring double quotes.
///
/// PLAN.md §1.7 says "split on whitespace", but `PRAELECTOR_ENGINE_CMD` pointing at
/// `C:\Program Files\Praelector\…` is a realistic debugging case, and a plain
/// `split_whitespace` would turn that into two nonsense tokens. Quotes are the
/// minimum that makes the override usable; anything unquoted behaves identically to
/// a whitespace split.
pub fn split_command(line: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    let mut started = false;

    for ch in line.chars() {
        match ch {
            '"' => {
                quoted = !quoted;
                started = true;
            }
            c if c.is_whitespace() && !quoted => {
                if started {
                    parts.push(std::mem::take(&mut current));
                    started = false;
                }
            }
            c => {
                current.push(c);
                started = true;
            }
        }
    }
    if started {
        parts.push(current);
    }
    parts
}

/// A per-launch bearer token: 32 random bytes, URL-safe base64 without padding —
/// byte-for-byte the alphabet `secrets.token_urlsafe(32)` produces on the engine
/// side. URL-safe matters beyond cosmetics: the UI passes the token as a WebSocket
/// query parameter (`security.websocket_token`), where `+` and `/` would have to be
/// escaped and a mistake there is a silent 401.
pub fn generate_token() -> String {
    let bytes: [u8; TOKEN_BYTES] = rand::random();
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(bytes)
}

/// The child environment for one launch.
///
/// `PRAELECTOR_HOST` and `PRAELECTOR_PORT` are deliberately **not** set: leaving
/// them absent means the engine binds `127.0.0.1` and asks the OS for a port, so
/// the endpoint is unpredictable from outside (NF-01, PLAN.md D-10). Setting a fixed
/// port here would undo that.
pub fn child_env(
    paths: &AppPaths,
    token: &str,
    log_level: &str,
    parent_pid: u32,
) -> Vec<(String, String)> {
    vec![
        (ENV_TOKEN.to_string(), token.to_string()),
        (
            ENV_DATA_DIR.to_string(),
            paths.data_dir.display().to_string(),
        ),
        (
            ENV_CONFIG_DIR.to_string(),
            paths.config_dir.display().to_string(),
        ),
        (ENV_LOG_DIR.to_string(), paths.log_dir.display().to_string()),
        (
            ENV_PROJECTS_DIR.to_string(),
            paths.projects_dir.display().to_string(),
        ),
        (ENV_LOG_LEVEL.to_string(), log_level.to_string()),
        // The portable orphan backstop. It is the *last* line of defence, not the
        // first: the engine's watchdog refuses to exit while a job is running, so
        // the Job Object / process group is what actually guarantees no orphans.
        (ENV_PARENT_PID.to_string(), parent_pid.to_string()),
    ]
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used, clippy::expect_used)]

    use std::collections::HashSet;
    use std::path::PathBuf;

    use super::*;

    /// A pretend tree: `/repo` holds `engine/pyproject.toml`, `/app` holds the
    /// bundled binary. Compared as `Path`s, never as strings, because Windows
    /// renders the same path with backslashes.
    fn fake_fs(paths: &[PathBuf]) -> impl Fn(&Path) -> bool {
        let set: HashSet<PathBuf> = paths.iter().cloned().collect();
        move |path: &Path| set.contains(path)
    }

    fn bundled_name() -> &'static str {
        if cfg!(windows) {
            "praelector-engine.exe"
        } else {
            "praelector-engine"
        }
    }

    fn bundled_path(resource_dir: &str) -> PathBuf {
        Path::new(resource_dir).join("engine").join(bundled_name())
    }

    fn resolver<'a>(
        env: Option<&'a str>,
        resource_dir: Option<&'a Path>,
        roots: &'a [PathBuf],
        exists: &'a dyn Fn(&Path) -> bool,
    ) -> Resolver<'a> {
        Resolver {
            engine_cmd_env: env,
            resource_dir,
            dev_search_roots: roots,
            exists,
        }
    }

    #[test]
    fn the_env_override_beats_everything_else() {
        let exists = fake_fs(&[
            bundled_path("/app"),
            PathBuf::from("/repo/engine/pyproject.toml"),
        ]);
        let roots = [PathBuf::from("/repo/apps/desktop/target/debug")];
        let got = resolve(&resolver(
            Some("/opt/engine/praelector-engine --log-level DEBUG"),
            Some(Path::new("/app")),
            &roots,
            &exists,
        ))
        .expect("an override always resolves");
        assert_eq!(got.source, CommandSource::EnvOverride);
        assert_eq!(got.program, "/opt/engine/praelector-engine");
        assert_eq!(got.args, ["--log-level", "DEBUG"]);
    }

    #[test]
    fn a_blank_override_is_ignored() {
        let exists = fake_fs(&[bundled_path("/app")]);
        let got = resolve(&resolver(
            Some("   "),
            Some(Path::new("/app")),
            &[],
            &exists,
        ))
        .unwrap();
        assert_eq!(got.source, CommandSource::Bundled);
    }

    #[test]
    fn the_bundled_binary_wins_over_the_dev_fallback() {
        let exists = fake_fs(&[
            bundled_path("/app"),
            PathBuf::from("/repo/engine/pyproject.toml"),
        ]);
        let roots = [PathBuf::from("/repo/apps/desktop/target/debug")];
        let got = resolve(&resolver(None, Some(Path::new("/app")), &roots, &exists)).unwrap();
        assert_eq!(got.source, CommandSource::Bundled);
        assert_eq!(Path::new(&got.program), bundled_path("/app"));
        assert_eq!(got.cwd.as_deref(), Some(Path::new("/app/engine")));
        assert!(got.args.is_empty());
    }

    #[test]
    fn the_dev_fallback_runs_uv_from_the_repo_root() {
        let exists = fake_fs(&[PathBuf::from("/repo/engine/pyproject.toml")]);
        // The executable lives in target/debug, so the root is two levels up.
        let roots = [PathBuf::from("/repo/apps/desktop/target/debug")];
        let got = resolve(&resolver(None, Some(Path::new("/app")), &roots, &exists)).unwrap();
        assert_eq!(got.source, CommandSource::Dev);
        assert_eq!(got.program, "uv");
        assert_eq!(
            got.args,
            ["run", "--project", "engine", "praelector-engine"],
            "--project is relative, so the cwd has to be the repo root"
        );
        assert_eq!(got.cwd.as_deref(), Some(Path::new("/repo")));
    }

    #[test]
    fn a_bundled_app_with_no_engine_is_a_hard_error_not_a_guess() {
        let exists = fake_fs(&[]);
        let err = resolve(&resolver(None, Some(Path::new("/app")), &[], &exists)).unwrap_err();
        match &err {
            EngineError::NotFound { searched } => {
                assert_eq!(searched.len(), 1);
                assert_eq!(Path::new(&searched[0]), bundled_path("/app"));
            }
            other => panic!("expected NotFound, got {other:?}"),
        }
        assert_eq!(err.code(), "engine.not_found");
        assert!(!err.is_retryable());
    }

    #[test]
    fn a_dev_root_is_only_accepted_when_the_marker_file_is_there() {
        // A directory that merely looks like a checkout must not be treated as one.
        let exists = fake_fs(&[PathBuf::from("/repo/engine/README.md")]);
        let roots = [PathBuf::from("/repo/apps/desktop")];
        let err = resolve(&resolver(None, None, &roots, &exists)).unwrap_err();
        assert!(matches!(err, EngineError::NotFound { .. }));
    }

    #[test]
    fn command_splitting_honours_quotes_and_collapses_whitespace() {
        assert_eq!(split_command("a b  c"), ["a", "b", "c"]);
        assert_eq!(split_command("  "), Vec::<String>::new());
        assert_eq!(
            split_command(r#""C:\Program Files\Praelector\engine.exe" --flag"#),
            [r"C:\Program Files\Praelector\engine.exe", "--flag"]
        );
        assert_eq!(split_command(r#""only quoted""#), ["only quoted"]);
        assert_eq!(
            split_command("uv run --project engine praelector-engine").len(),
            5
        );
    }

    #[test]
    fn the_token_is_url_safe_unpadded_and_unique() {
        let mut seen = HashSet::new();
        for _ in 0..64 {
            let token = generate_token();
            // 32 bytes -> ceil(32 * 4 / 3) = 43 characters, no padding.
            assert_eq!(token.len(), 43, "{token}");
            assert!(
                token
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_'),
                "{token} is not URL-safe"
            );
            assert!(seen.insert(token), "tokens must not repeat");
        }
    }

    #[test]
    fn the_child_environment_matches_what_the_engine_reads() {
        let paths = AppPaths {
            data_dir: PathBuf::from(if cfg!(windows) {
                r"C:\d\data"
            } else {
                "/d/data"
            }),
            config_dir: PathBuf::from(if cfg!(windows) {
                r"C:\d\conf"
            } else {
                "/d/conf"
            }),
            log_dir: PathBuf::from(if cfg!(windows) {
                r"C:\d\logs"
            } else {
                "/d/logs"
            }),
            projects_dir: PathBuf::from(if cfg!(windows) {
                r"C:\d\books"
            } else {
                "/d/books"
            }),
            resource_dir: None,
        };
        let env = child_env(&paths, "tok", "INFO", 4321);
        let map: std::collections::HashMap<_, _> = env.iter().cloned().collect();

        assert_eq!(map[ENV_TOKEN], "tok");
        assert_eq!(map[ENV_LOG_LEVEL], "INFO");
        assert_eq!(map[ENV_PARENT_PID], "4321");
        assert_eq!(map[ENV_DATA_DIR], paths.data_dir.display().to_string());
        assert_eq!(
            map[ENV_PROJECTS_DIR],
            paths.projects_dir.display().to_string()
        );
        // NF-01 / D-10: a predictable port would defeat the point of the token.
        assert!(!map.contains_key("PRAELECTOR_HOST"));
        assert!(!map.contains_key("PRAELECTOR_PORT"));
    }

    #[test]
    fn describe_never_includes_a_secret_and_shows_the_cwd() {
        let cmd = EngineCommand {
            program: "uv".to_string(),
            args: vec!["run".to_string(), "praelector-engine".to_string()],
            cwd: Some(PathBuf::from("/repo")),
            source: CommandSource::Dev,
        };
        assert_eq!(cmd.describe(), "uv run praelector-engine  [cwd /repo]");
    }
}
