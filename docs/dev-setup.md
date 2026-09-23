# Development setup

Everything below is for working on Praelector itself. End-user installation is
documented in [`user-guide.md`](user-guide.md).

Two shapes of development exist:

| Shape | Command | What it exercises |
| --- | --- | --- |
| Browser mode | `just dev` | Engine sidecar on a fixed port + Vite dev server. No Rust toolchain needed for the rebuild loop. |
| Desktop mode | `just dev-desktop` | The real Tauri app: the Rust `EngineSupervisor` spawns the engine, does the ready handshake, health-polls it and tears it down. This is the only mode that tests process supervision. |

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| [`uv`](https://docs.astral.sh/uv/) | 0.12+ | both Python projects; also installs Python 3.12 for you |
| Node.js | 22 LTS+ | `apps/ui` |
| pnpm | 11+ | the JS workspace (`corepack enable` after installing Node) |
| Rust | stable (rustup) | `apps/desktop` |
| [`just`](https://github.com/casey/just) | 1.30+ | task runner |
| ffmpeg | 6.0+ with `aac`, `loudnorm`, `silenceremove` | audio ingest and muxing only; **never bundled** |
| Calibre (`ebook-convert`) | any recent | PDF/MOBI ingest only; **never bundled** |

Python is pinned to **3.12** (`engine/.python-version`). Do not develop against a
newer interpreter: `torch` wheels for the TTS runtime are cp312.

## Windows 11

```powershell
winget install --id Rustlang.Rustup        # then: rustup default stable
winget install --id OpenJS.NodeJS.LTS
winget install --id astral-sh.uv
winget install --id Casey.Just
corepack enable                            # provides pnpm

# optional
winget install --id Gyan.FFmpeg
winget install --id calibre.calibre
```

The Tauri WebView on Windows is WebView2, which ships with Windows 11. If you
target Windows 10 as well, install the Evergreen Bootstrapper.

Long paths: the NSIS installer manifest enables them, but for development
enable them once so deep `audio/chunks/**` trees cannot fail:

```powershell
# requires an elevated shell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
```

## Arch / CachyOS

```sh
sudo pacman -S --needed base-devel rustup nodejs pnpm just git ffmpeg calibre
rustup default stable
sudo pacman -S --needed webkit2gtk-4.1 libappindicator librsvg patchelf   # Tauri
# uv: from the AUR (paru -S uv) or the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`ubuntu-22.04` is the CI floor for glibc (2.35), so an Arch-built binary may not
run on older distros. Build release artifacts in CI, not locally.

## First run

```sh
git clone <repo> && cd praelector
just setup        # Python 3.12, engine env, pnpm workspace
just dev          # engine on 127.0.0.1:8787, UI on http://localhost:1420
```

`just setup` does **not** install the TTS runtime — it is 250 MB (CPU) to 4 GB
(CUDA/ROCm) and most work does not need it. When you do:

```sh
just setup-tts                       # cpu flavour (default)
PRL_TTS_EXTRA=cuda just setup-tts    # NVIDIA
PRL_TTS_EXTRA=rocm just setup-tts    # AMD, Linux only (PLAN.md D-20)
```

The `cpu`, `cuda` and `rocm` extras are mutually exclusive (PLAN.md D-03); one
environment serves exactly one vendor. Never union them.

## Verifying the engine by hand

Browser mode writes a fixed dev token to `apps/ui/.env.local` (gitignored). The
engine requires it on every request:

```sh
curl -H "Authorization: Bearer praelector-dev-token-not-a-secret" \
  http://127.0.0.1:8787/v1/health
```

A request without the header, or with a disallowed `Origin`, must be rejected —
that is the trust boundary from PLAN.md §1.5, and it is worth checking after any
change to `engine/src/praelector/security.py`.

## Everyday commands

```sh
just test           # engine pytest (no GPU markers) + UI vitest
just lint           # ruff, eslint, cargo fmt --check, clippy -D warnings
just typecheck      # mypy --strict on engine/src, tsc --noEmit
just check          # all of the above + SPDX, licenses, i18n parity, codegen drift
just codegen        # regenerate packages/schemas from the Pydantic models
just fixtures       # regenerate deterministic test fixtures
just format         # ruff format, prettier, cargo fmt
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `just dev` says `engine/pyproject.toml does not exist` | You are on a branch that predates the engine. Check out `feat/engine-skeleton` or later. |
| Port 8787 already in use | A previous `just dev` did not die. Find and kill it (`Get-NetTCPConnection -LocalPort 8787` on Windows, `ss -lptn 'sport = :8787'` on Linux), or set `PRAELECTOR_PORT`. |
| `uv sync` resolves `torch` into `engine` | A regression — the core lockfile must stay torch-free. `just no-torch-check` reproduces the CI failure. |
| `cargo clippy` fails on Linux with missing webkit | Install `webkit2gtk-4.1`, `librsvg2-dev`, `patchelf` (see above). |
| Engine starts but the UI shows "engine unreachable" | `apps/ui/.env.local` is stale, or the engine bound a different port. Delete the file and restart `just dev`. |
| Audio features report `audio.ffmpeg_missing` | Install ffmpeg ≥ 6.0 or set `ffmpeg_path` in settings. The app will not bundle it (PLAN.md D-06). |
| `mypy` passes locally, fails in CI | CI runs `mypy --strict src` from inside `engine/`. Run `just typecheck`, not a bare `mypy .`. |

## Where state lives during development

| Path | Contents |
| --- | --- |
| `.dev/data/` | dev-only engine data dir (models, runtimes, logs). Gitignored, safe to delete. |
| `apps/ui/.env.local` | dev engine URL + token, rewritten by `scripts/dev.py`. Gitignored. |
| `~/Praelector/projects/` | real projects, in dev and in production alike. Never deleted by the app. |
