# Contributing to Praelector

Thank you for contributing to Praelector!

Praelector is an Apache-2.0 local-first desktop app that turns DRM-free ebooks into multi-voice M4B audiobooks with a Polish lector-preparation workshop.

---

## 1. Governance and Workflow

- **Branch Protection:** All changes go through pull requests against `main`. Direct pushes to `main` are blocked.
- **Review & CI:** Every PR requires at least one human review and passing CI before merging.
- **Merge Strategy:** `main` allows **squash merge only** to preserve a clean, linear git history.
- **Commit Format:** Conventional Commits are required for PR titles and commit messages:
  - Format: `<type>(<scope>): <subject>`
  - Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`
  - Scopes: `engine`, `engine-tts`, `ui`, `desktop`, `ebook`, `text`, `llm`, `tts`, `gpu`, `jobs`, `mux`, `store`, `docs`, `ci`, `deps`
  - Breaking changes must include `!` (e.g. `feat(engine)!: change render_key`) and explain the impact in the description.

---

## 2. Monorepo Structure

| Directory | Language | Description |
| --------- | -------- | ----------- |
| `apps/desktop` | Rust (Tauri 2) | Desktop shell: windowing, sidecar lifecycle, native dialogs. |
| `apps/ui` | TypeScript, React 19 | Frontend: CodeMirror editor, suggestions queue, job controls. |
| `engine` | Python 3.12 (uv) | Engine core: ebook ingestion, text processing, LLM router, job orchestration. Torch-free! |
| `engine-tts` | Python 3.12 (uv) | TTS runtime worker: torch, model loading, audio synthesis. |
| `packages/schemas` | TypeScript, JSON Schema | Shared schemas and generated TypeScript contracts. |
| `scripts` | Python, Node.js | Tooling for codegen, license checking, packaging. |
| `docs` | Markdown | Architecture, developer setup, GPU guides, plugin docs. |

---

## 3. Development Setup

### Prerequisites

- **Rust:** Stable toolchain (`rustup default stable`, `rustfmt`, `clippy`)
- **Node.js:** v22+ and `pnpm` (v10+)
- **Python:** 3.12 managed via `uv` (`uv python install 3.12`)
- **Just:** Command runner (`cargo install just`)
- **External Binaries:** `ffmpeg` / `ffprobe` (6.0+ recommended)

### Quick Start

```bash
# Install Node dependencies
pnpm install

# Setup Python environments
uv sync --project engine --group dev
uv sync --project engine-tts --extra cpu --group dev

# Verify everything builds and passes checks
just test
just lint

# Start development mode
just dev
```

---

## 4. `justfile` Recipes

| Recipe | Description |
| ------ | ----------- |
| `just dev` | Start engine, UI Vite dev server, and Tauri window |
| `just test` | Run tests across engine, UI, and desktop |
| `just lint` | Run linters (ruff, eslint, clippy, cargo fmt) |
| `just check` | Typecheck engine (mypy) and UI (tsc) |
| `just codegen` | Regenerate TypeScript interfaces from Pydantic schemas |
| `just licenses` | Run license policy check and verify NOTICE freshness |

---

## 5. Licensing & SPDX Headers

- All first-party source code in Praelector is licensed under **Apache-2.0**.
- Every source file must start with the SPDX identifier:
  ```python
  # SPDX-License-Identifier: Apache-2.0
  ```
  or
  ```typescript
  // SPDX-License-Identifier: Apache-2.0
  ```
- Third-party dependencies must comply with the license policy:
  - **Allowed:** Apache-2.0, MIT, BSD-2/3, ISC, MPL-2.0, Unlicense, CC0.
  - **Review:** LGPL-2.1/3.0 with static/dynamic linking justification.
  - **Denied:** GPL-2/3, AGPL-3, commercial/non-commercial restricted licenses.

---

## 6. Adding a TTS Backend

TTS backends in Praelector run in separate worker processes implementing the plugin protocol over JSONL stdio. To add or inspect backend implementations, see `docs/plugins.md`.

---

## 7. Internationalization (i18n)

- Praelector is bilingual: English (`en`) and Polish (`pl`).
- All user-facing strings must be localized via `i18next`.
- Key parity between `en` and `pl` is enforced in CI.
