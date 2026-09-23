# Security Policy

## 1. Supported versions

Praelector has not shipped v1 yet. There is a single line of development and no long-term-support channel.

| Version | Branch | Support |
| --- | --- | --- |
| v1 pre-release | `main` | Best effort. Security reports are accepted and fixed forward on `main`. |
| Published `v*` tags | — | Best effort. No backports and no patch releases for a superseded tag; the fix lands in the next release. |
| Anything else | — | Unsupported. |

There is no LTS, no version matrix, and no commitment to maintain an older release. When you report, report against the current `main` commit or the newest published tag.

## 2. Reporting a vulnerability

Use GitHub's **private vulnerability reporting** on this repository:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability** (GitHub private security advisory).
3. Describe the issue and include your OS, GPU and driver, TTS backend, and the engine version from the About screen or `GET /v1/version`.

Private reporting is enabled on this repository, so a report is visible only to the maintainer until you both agree to disclose it.

**Do not open a public issue for a security report**, and do not file one as a feature request or a bug report. Public disclosure before a fix exists puts every user of the pre-release build at risk.

There is no security email address for this project. The GitHub mechanism and the maintainer's account, [@czekanskyy](https://github.com/czekanskyy), are the only channels.

**Response target:** best effort, within 14 days of the report. There is no bug bounty, no SLA, and no guaranteed remediation timeline. This is a single-maintainer project.

## 3. Threat model

The full reasoning is in [`docs/plan/PLAN.md` §1.5](docs/plan/PLAN.md#15-transport-and-trust-boundary), [§1.6](docs/plan/PLAN.md#16-sidecar-launch-and-supervision) and [D-10](docs/plan/PLAN.md#d-10-bearer-token--origin-check-on-the-loopback-api). The summary a reporter needs:

**The engine is a local process, not a service.** The Python engine is a FastAPI process spawned by the Tauri shell, bound to `127.0.0.1` on an OS-assigned port (`0`) — `NF-01`. It has no listening interface reachable from another machine and no inbound firewall rule.

**Every request is authenticated.** The Tauri shell generates 32 random bytes per launch and passes them to the engine through the **environment** as `PRAELECTOR_TOKEN` — never through `argv`, because command lines are world-readable in process listings on both Windows and Linux. Every HTTP request and the WebSocket handshake must carry `Authorization: Bearer <token>`.

**The `Origin` allow-list is what stops the browser.** Requests that carry an `Origin` header are rejected unless the origin is exactly `tauri://localhost` or `http://localhost:1420`. Binding to loopback alone is not sufficient: without this check, any web page the user visits could drive the engine (a DNS-rebinding / CSRF-style attack against a localhost service). A cross-origin request from a real website fails here even if it somehow obtained the token.

**The WebView cannot reach anywhere else.** The Tauri CSP allows `connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*` and nothing else. There is no `script-src` allowance for remote origins and no remote content is loaded into the shell.

**No orphan processes.** On Windows the engine child is assigned to a Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`; on POSIX it gets its own process group and receives SIGTERM when the shell exits, then SIGKILL. As a portable backstop the engine polls `PRAELECTOR_PARENT_PID` every 5 s and exits if the parent is gone and no job is running. TTS worker processes are children of the engine and are torn down by the same logic one level down. A crash therefore cannot leave an unauthenticated listener behind — and the token dies with the process regardless, since it is regenerated on every launch.

**One instance, one project, one job.** `tauri-plugin-single-instance` prevents a second app instance, which is what makes "one project / one job at a time" enforceable (`JB-06`). Belt and braces: the engine takes an exclusive lock on `<project_dir>/project.lock` recording its pid, so a second engine cannot write the same project directory.

**The engine returns codes, not prose.** Error responses are `{"error": {"code": "...", "detail": {...}, "retryable": bool}}` ([D-16](docs/plan/PLAN.md#d-16-engine-returns-error-codes-not-prose)), which keeps filesystem paths, stack traces and internal state out of the response body by default.

## 4. Data handling and privacy

- **No telemetry, no crash reporting, no analytics** (`NF-05`, product principle 4). The application makes no outbound call except to: a user-configured LLM endpoint, a TTS model download the user explicitly initiated, and the guided LGPL `ffmpeg` fetch.
- **Book text never leaves the machine unless the user enables a cloud LLM provider.** Cloud calls require an explicit per-project toggle (`LM-05`, `NF-02`); the default is local-only when a local profile exists. Context sent to an LLM is bounded to the target block plus its immediate neighbours (`AI-03`), not the whole book.
- **Secrets** (LLM API keys) go to the OS keyring, with an encrypted local store as fallback (`LM-03`). They are never written to `argv`, never committed, and never logged — the JSON log has a secret-redaction filter (`engine/src/praelector/logging.py`). `.env` files with keys are scanned for by `gitleaks.yml` on every PR.
- **The original ebook file is never mutated** (`EB-06`). Work happens on a normalised copy inside the project directory, which lives under the user's own home (`~/Praelector/projects/<project_id>/`).
- **Project data stays local.** There is no cloud project sync and no account system; a project directory is ordinary files and a SQLite database on the user's disk.
- Logs are written to `%LOCALAPPDATA%\Praelector\logs\` on Windows and `${XDG_STATE_HOME:-~/.local/state}/praelector/logs/` on Linux, and are under the user's control.

## 5. Out of scope / will not fix

These are deliberate design decisions, not vulnerabilities. Reports asking for them will be closed.

- **DRM circumvention of any kind.** Praelector refuses DRM-locked files and fails closed (`EB-01`, `EB-02`). Removing, weakening, or working around that refusal — including a "user-supplied key" path or a pointer to an external tool — will never be implemented, and a report requesting it is out of scope. This is policy, not a bug.
- **OCR of scanned PDFs.** A PDF without a text layer fails with `ebook.no_text_layer` (`EB-04`). OCR is a v1 non-goal ([PRD §2.2](docs/PRD.md#22-non-goals-v1)).
- **Anything that requires a signed binary in v1.** **v1 ships unsigned** ([D-24](docs/plan/PLAN.md#d-24-unsigned-binaries-in-v1)). Windows SmartScreen will warn on first run, and macOS Gatekeeper has no notarised artifact to accept. The verification path is the `SHA256SUMS` file published alongside every release. Code signing (Azure Trusted Signing for the NSIS installer) is an explicit post-v1 item; no code depends on being signed, so enabling it later is a `release.yml` change only. "The installer is not signed" is therefore a known, accepted, documented condition — please do not report it.
- **macOS.** macOS is CI-only ([D-23](docs/plan/PLAN.md#d-23-macos-is-ci-only)): the `macos-14` job runs with `continue-on-error: true` and produces no release artifact. macOS-specific reports are out of scope for v1.
- **Reports that require local code execution or a malicious user account on the same machine.** The token model defends against other processes and web pages opportunistically; it is not a sandbox against an attacker who already runs arbitrary code as the same user.
- **Third-party runtime behaviour.** Bugs in `torch`, a TTS model, `ffmpeg`, or Calibre are upstream issues. Report them upstream; report to us only if Praelector invokes them unsafely.

## 6. Known-risk notes

Stated here so they are on the record rather than discovered later.

| Component | License | Handling |
| --- | --- | --- |
| PyInstaller bootloader | GPL-2.0 with bootloader exception | Build-time only. The exception explicitly permits shipping a non-GPL frozen application. The engine is frozen `onedir`, not `onefile`, which also avoids the re-extraction behaviour that trips Windows AV heuristics ([D-04](docs/plan/PLAN.md#d-04-two-tier-packaging-frozen-core--provisioned-tts-runtime)). |
| `ffmpeg` / `ffprobe` | LGPL-2.1+ (or GPL, depending on the build) | **Never bundled** in the installer ([D-06](docs/plan/PLAN.md#d-06-ffmpeg-for-all-audio-io-not-bundled)). Resolved from `settings.ffmpeg_path`, then `PATH`, then an in-app guided fetch of an **LGPL** build into `<dataDir>/bin`, shown with its checksum and license (`MX-04`). |
| Calibre (`ebook-convert`) | GPLv3 | Optional, user-installed, invoked as a subprocess only, never vendored or bundled (`NF-04`, `EB-03`). |
| `uv` | Apache-2.0 / MIT | Bundled as a resource binary and used to provision the TTS runtime. |
| TTS runtime (`torch` + backend) | BSD-3 and per-backend | **Provisioned on first use** into `<dataDir>/runtimes/<flavour>-<lockhash>/` from the committed `engine-tts/uv.lock`, so installs are locked and reproducible ([D-04](docs/plan/PLAN.md#d-04-two-tier-packaging-frozen-core--provisioned-tts-runtime)). |
| Model weights | per descriptor | Downloaded only on explicit user action, pinned by repo + revision + `sha256`, with the license shown and acknowledged before the download starts (`TTS-02`, `NF-03`). A failed checksum is a hard error, not a silent retry. |

Full license posture, including the libraries rejected for license reasons: [PLAN.md §11](docs/plan/PLAN.md#11-third-party-libraries-and-license-posture) and [`docs/licenses.md`](docs/licenses.md).

## 7. Responsible disclosure expectations

Report privately through the GitHub Security tab, give us a reasonable chance to fix it, and do not publish details until a release containing the fix is available or you have agreed otherwise with the maintainer.

We will credit reporters in the release notes for the version that contains the fix, unless you ask not to be named. There is no bounty, but the credit is real and the acknowledgement is permanent.
