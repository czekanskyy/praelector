# Praelector

**Prepare the page. Cast the voice.**

Praelector turns a DRM-free ebook into a chapterized M4B audiobook on your own
machine. The differentiator is a **lector preparation workshop**: Polish
pronunciation rewrites, dialogue segmentation (including mid-paragraph),
speaker-gender classification, and human review of every AI-proposed change —
then GPU-aware parallel TTS with pause/resume and M4B assembly from complete or
partial recordings.

v1 is optimised for Polish books and a Polish narrator, with three first-party
TTS backends (OmniVoice by default, Chatterbox, Qwen3-TTS).

## Status

Pre-release. Development follows the milestone plan in
[`docs/plan/PLAN.md`](docs/plan/PLAN.md); scope is defined by
[`docs/PRD.md`](docs/PRD.md).

## Platform support

| Platform | Status |
| --- | --- |
| Windows 11 x64 | Supported |
| Linux x64 (Arch and derivatives first, generic glibc ≥ 2.35) | Supported |
| macOS (Apple Silicon / Intel) | Built in CI, **not** supported — no maintainer hardware |

Reference hardware: RTX 4070 Ti 12 GB (CUDA) and RX 9060 XT 16 GB (ROCm).
Minimum viable inference is 8 GB VRAM with one worker, or CPU with an explicit
slow-path warning.

## What Praelector will never do

- **Remove or circumvent DRM.** DRM-locked files are detected and refused. This
  is policy, not a missing feature, and it will not change.
- **OCR scanned PDFs.** A PDF without a text layer is rejected.
- **Send your book anywhere.** No telemetry, no analytics, no crash reporting.
  Book text leaves the machine only if you explicitly enable a cloud LLM
  provider for the project.
- **Bundle ffmpeg or Calibre.** Both are external processes resolved from your
  settings or `PATH`; Calibre is optional and only used for PDF/MOBI conversion.

## Unsigned binaries

v1 ships unsigned — no code-signing certificate is in place yet. Windows
SmartScreen and macOS Gatekeeper will warn on first run. Every release publishes
`SHA256SUMS`, which is the verification path. See
[`SECURITY.md`](SECURITY.md) and [`docs/plan/PLAN.md`](docs/plan/PLAN.md) (D-24).

## Development

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node 22+ with `pnpm`, Rust
stable, [`just`](https://github.com/casey/just). Optional: `ffmpeg` (audio work),
Calibre (PDF/MOBI ingest).

```sh
just setup      # Python 3.12 + engine env + pnpm workspace
just dev        # engine on 127.0.0.1:8787 + UI on http://localhost:1420
just dev-desktop  # the real Tauri app, engine supervised by the shell
just check      # everything the blocking CI workflows run
```

Full instructions for Windows 11 and Arch/CachyOS:
[`docs/dev-setup.md`](docs/dev-setup.md). Contributing rules, commit
conventions and the license policy: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `apps/desktop` | Tauri 2 shell (Rust): window, engine supervision, native dialogs. No product logic. |
| `apps/ui` | React 19 + TypeScript front end. Owns every user-facing string. |
| `engine` | Python 3.12 sidecar, **torch-free**: all product logic, SQLite, HTTP/WS API. |
| `engine-tts` | Python TTS worker with mutually exclusive `cpu` / `cuda` / `rocm` extras. |
| `packages/schemas` | The generated UI/engine contract (JSON Schema + TypeScript). |
| `docs` | English documentation. `docs/plan/` holds the implementation plan. |
| `fixtures` | Cross-language sample inputs for tests. |
| `scripts` | Build, codegen, license and i18n tooling. |

Three process tiers exist because they have three dependency footprints: the
installer ships the torch-free core (~120 MB), and the app provisions the GPU
runtime (2.5–4 GB of `torch` plus a backend) into its data directory on first
use. Rationale: [`docs/plan/PLAN.md`](docs/plan/PLAN.md) D-04.

## Architecture

```
Tauri shell (Rust)  ──spawn/stdio/health──▶  engine (FastAPI on 127.0.0.1)
       │                                            │
       └── WebView: React UI ──HTTP + WS, bearer──▶ │
                                                    ├──▶ TTS workers (torch, JSONL over stdio)
                                                    ├──▶ ffmpeg, ebook-convert
                                                    └──▶ Ollama / LM Studio / cloud LLMs
```

Details, the trust boundary and the ready handshake:
[`docs/architecture.md`](docs/architecture.md).

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Third-party model
weights have their own licenses, shown in-app before any download; the current
dependency and model license posture is summarised in
[`docs/plan/PLAN.md`](docs/plan/PLAN.md) §11.
