# Contributing to Praelector

## 1. What Praelector is

Praelector is a local-first desktop application for Windows 11 and Linux that turns a DRM-free ebook into a chapterised M4B audiobook. What separates it from a plain converter is the lector preparation workshop: Polish pronunciation rewrites, dialogue segmentation (including mid-paragraph), speaker-gender classification, human review of every AI-proposed change, GPU-aware parallel TTS with pause and resume, and M4B assembly from complete or partial recordings. v1 is optimised for Polish books and a Polish narrator.

**Prepare the page. Cast the voice.**

[`docs/PRD.md`](docs/PRD.md) is the source of truth for scope. If this file, an implementation plan, or a pull request disagrees with the PRD, the PRD wins until the maintainer amends it. Requirement IDs (`EB-01`, `DG-02`, `LM-03`, `NF-05`, …) are defined in [PRD §6](docs/PRD.md#6-functional-requirements) and [PRD §7](docs/PRD.md#7-non-functional-requirements); cite the ones your change touches in the PR description.

## 2. Hard scope rules

These are not preferences. A PR that violates one of them is closed regardless of code quality.

- **No DRM removal or circumvention, ever.** Praelector refuses DRM-locked files and fails closed (`EB-01`, `EB-02`). Do not add a bypass, a "user-supplied key" path, or a pointer to one. This is policy, not a bug — see [SECURITY.md](SECURITY.md).
- **No OCR.** A PDF without a text layer is rejected with `ebook.no_text_layer` (`EB-04`). OCR is a v1 non-goal ([PRD §2.2](docs/PRD.md#22-non-goals-v1)).
- **Never mutate the user's original ebook file.** The upload lands at `source/original.<ext>` and all editing happens on `source/working.epub` (`EB-06`).
- **No telemetry.** No analytics, no crash reporting, no phone-home (`NF-05`). The only network calls are to user-configured LLM endpoints, TTS model downloads, and the guided LGPL ffmpeg fetch.
- **The AI never silently mutates text.** Every detector emits a `Suggestion`; the user accepts, edits, or rejects it, and applying creates a new book revision (`AI-04`, `AI-06`, `AI-07`). Product principle 1, [PRD §4](docs/PRD.md#4-product-principles).
- **One project, one job at a time.** `JB-06` plus [D-14](docs/plan/PLAN.md#d-14-one-active-job-of-any-kind-per-app-instance): starting a second job returns `job.already_active`. Multi-book queues are a non-goal.

## 3. Development environment

The long version, including troubleshooting and GPU stacks, is [`docs/dev-setup.md`](docs/dev-setup.md). This section is the short path.

### Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| `uv` | 0.12.x | Manages both Python projects and fetches the interpreter. |
| Python | 3.12, pinned | Installed by `uv python install 3.12`. Your system Python may be newer; that is fine and irrelevant — `uv` resolves the pinned one. |
| Node.js | 22 or newer | — |
| `pnpm` | 11.x | — |
| Rust | stable, via `rustup` | Needed only for `apps/desktop`. |
| `just` | 1.5x | Task runner. Every command below has a `just` equivalent. |
| `ffmpeg` | ≥ 6.0 with `aac`, `loudnorm`, `silenceremove` | **Not bundled.** Resolved from `settings.ffmpeg_path`, then `PATH`, then the in-app guided fetch of an LGPL build ([D-06](docs/plan/PLAN.md#d-06-ffmpeg-for-all-audio-io-not-bundled)). Required for any audio work. |
| `ebook-convert` (Calibre) | any | **Optional and never bundled** (`NF-04`). Only needed to exercise PDF/MOBI ingest (`EB-03`). |

### Windows 11

```powershell
winget install --id Git.Git -e
winget install --id Rustlang.Rustup -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Casey.Just -e
winget install --id Gyan.FFmpeg -e
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

Open a **new** shell so the PATH changes take effect, then:

```powershell
rustup default stable
corepack enable
uv python install 3.12
uv sync --project engine --group dev --frozen
uv sync --project engine-tts --extra cpu --group dev --frozen
pnpm install --frozen-lockfile
just dev
```

The WebView2 runtime ships with Windows 11. ROCm is Linux-only ([D-20](docs/plan/PLAN.md#d-20-windows--amd-rocm-is-best-effort)); on Windows with an AMD card use `--extra cpu`.

### Arch / CachyOS Linux

```bash
sudo pacman -S --needed base-devel git curl wget file patchelf \
  rustup nodejs pnpm just python-uv ffmpeg \
  gtk3 webkit2gtk-4.1 libappindicator-gtk3 librsvg
```

If your mirror's `python-uv` is older than 0.12.x, use the upstream installer instead: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

```bash
rustup default stable
uv python install 3.12
uv sync --project engine --group dev --frozen
uv sync --project engine-tts --extra cpu --group dev --frozen
pnpm install --frozen-lockfile
just dev
```

For GPU work install your distro's vendor stack so `nvidia-smi` (NVIDIA: `nvidia`, `nvidia-utils`) or `rocm-smi` / `amd-smi` (AMD: the `rocm-*` packages) is on `PATH`. Tested torch/ROCm tuples per reference machine are in [`docs/gpu.md`](docs/gpu.md).

### Choosing the `engine-tts` extra

There are two Python projects: `engine` (torch-free, always installed) and `engine-tts` (the TTS worker). `engine-tts` declares **mutually exclusive** `cpu` / `cuda` / `rocm` extras via `[tool.uv] conflicts`, so you must select exactly one — passing two is an error, not a union ([D-03](docs/plan/PLAN.md#d-03-uv-with-mutually-exclusive-cuda--rocm--cpu-extras)).

```bash
uv sync --project engine-tts --extra cpu  --group dev --frozen   # CI and non-GPU work; enables the `fake` backend
uv sync --project engine-tts --extra cuda --group dev --frozen   # NVIDIA
uv sync --project engine-tts --extra rocm --group dev --frozen   # AMD, Linux only (marker: sys_platform == "linux")
```

The engine core's own lockfile must never resolve `torch`; CI asserts this with `scripts/assert_no_torch.py engine/uv.lock`.

## 4. Repository layout and layering

Full detail in [`docs/plan/REPO_LAYOUT.md`](docs/plan/REPO_LAYOUT.md#1-top-level).

| Path | Responsibility |
| --- | --- |
| `apps/desktop` | Tauri 2 shell (Rust). Process lifecycle, window, native dialogs, resource resolution. Contains no product logic. |
| `apps/ui` | React 19 + TS front end. Owns every user-facing string and all presentation. Talks only to the engine HTTP/WS API. |
| `engine` | Python 3.12 sidecar (`praelector`), torch-free. All product logic that does not need `torch`. Single writer of the project directory. |
| `engine-tts` | Python TTS worker (`praelector_tts`). Model loading and synthesis only. Knows nothing about projects, SQLite or HTTP. |
| `packages/schemas` | The only place where the UI/engine contract is defined. Generated — run `just codegen`. |
| `docs` | English documentation (`NF-10`). |
| `fixtures` | Cross-language sample inputs (`books/`, `audio/`, `text/`). |
| `scripts` | Build, codegen, license and i18n tooling. |

Layering rules, all enforced in review and partly in CI:

- Python packages use a `src/` layout.
- `apps/desktop` never reads project files, never calls an LLM, never learns about chapters or jobs. If the shell needs data, it asks the engine over HTTP the same way the UI does.
- In `apps/ui`, `lib/api` is the only module allowed to call `fetch`, and feature folders never import from each other — shared code moves to `components/` or `lib/`.
- `engine/src/praelector/api/v1/` contains no logic beyond validation and delegation.
- `engine/src/praelector/store/` is the only layer that touches disk or SQLite.
- `engine/src/praelector/text/` is pure: functions take text and return spans or suggestions, with no I/O and no network. This is what keeps the golden tests cheap.
- `engine/src/praelector/tts/` never imports `torch`. Neither does anything else in `engine` — the core lockfile is asserted torch-free.
- `engine-tts` communicates over newline-delimited JSON on stdin/stdout only ([D-05](docs/plan/PLAN.md#d-05-tts-backends-run-in-worker-processes-over-jsonl-stdio)). Importing `praelector_tts` with no extra installed must succeed and expose the `fake` backend.
- No generated artifact is committed except lockfiles, `packages/schemas/src/generated/**`, and small text fixtures.

## 5. Running tasks with `just`

| Target | What it does |
| --- | --- |
| `just setup` | Installs both `uv` projects (`engine`, `engine-tts`) and all `pnpm` workspace dependencies. |
| `just dev` | Runs the engine, the Vite dev server and the Tauri window together. |
| `just test` | Runs the whole suite: engine `pytest` plus UI `vitest`. |
| `just test-engine` | Engine tests only: `pytest -m "not gpu"`. |
| `just test-ui` | UI tests only: `pnpm -F ui test`. |
| `just lint` | `ruff check`, ESLint, `cargo fmt --check`, `cargo clippy -D warnings`, SPDX header check. |
| `just format` | `ruff format`, Prettier `--write`, `cargo fmt`. |
| `just typecheck` | `mypy --strict` on the engine plus `tsc --noEmit` on the UI. |
| `just codegen` | Regenerates JSON Schemas and the TypeScript types in `packages/schemas`. |
| `just build` | Compiles all three workspaces (`tauri build --no-bundle`). |
| `just package` | Freezes the engine with PyInstaller and produces installers plus `SHA256SUMS`. |
| `just nightly-fixture` | Runs the full-book fixture pipeline headless against the `fake` backend. |

Run `just --list` for the complete set, which also includes `license-check` (see §10).

## 6. Commits and pull requests

Conventional Commits (`NF-09`), linted on the **PR title** by `pr-title.yml` — see [`docs/plan/CI_AND_RELEASE.md` §6](docs/plan/CI_AND_RELEASE.md#6-pr-titleyml-and-commit-conventions-nf-09).

- **Types:** `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`
- **Scopes:** `engine`, `engine-tts`, `ui`, `desktop`, `ebook`, `text`, `llm`, `tts`, `gpu`, `jobs`, `mux`, `store`, `docs`, `ci`, `deps`

A scope is recommended but not required (`requireScope: false`).

Examples: `feat(text): detect mid-paragraph dialogue after a colon`, `fix(jobs): keep finished chunks when a record job is cancelled`, `docs(plugins)!: freeze the backend descriptor schema`.

Subject rules, enforced by `subjectPattern: ^(?![A-Z]).+[^.]$`:

- the subject **must not** start with a capital letter;
- the subject **must not** end with a period.

`main` allows **squash merge only**, so the PR title becomes the single commit message and therefore the changelog entry that release-please reads. Write it as the sentence you want in `CHANGELOG.md`.

**Breaking changes** use a `!` after the type/scope *and* a `BREAKING CHANGE:` footer in the PR description. Marking a PR breaking is **mandatory** — not a judgement call — when it changes any of:

- the inputs to `render_key` ([PLAN.md §8.3](docs/plan/PLAN.md#83-chunk-identity-and-invalidation-jb-02-jb-05)), because that silently invalidates every chunk a user has already rendered;
- the TTS plugin protocol or `BackendDescriptor`;
- the project directory schema or `project.json` `schema_version`.

The PR template checklist must be filled in: requirement IDs touched, tests added or updated, docs updated (or `n/a`), dependency license impact, breaking-change declaration, and i18n catalogue parity.

## 7. Branch protection on `main`

A maintainer applies these in **Settings → Branches → Add rule** for `main` (source: [`CI_AND_RELEASE.md` §7](docs/plan/CI_AND_RELEASE.md#7-branch-protection-on-main)). There is **no administrator bypass during v1** — the maintainer follows the same rules as everyone else.

- [ ] Require a pull request before merging.
- [ ] Require **1** approving review.
- [ ] Dismiss stale pull request approvals when new commits are pushed.
- [ ] Require status checks to pass before merging.
- [ ] Require branches to be up to date before merging (strict).
- [ ] Required status checks: `engine (ubuntu-latest)`, `engine (windows-latest)`, `ui`, `desktop (ubuntu-22.04)`, `desktop (windows-latest)`, `licenses`, `pr-title`, `gitleaks`.
- [ ] **Not** required: `desktop (macos-14)` and `codeql` ([D-23](docs/plan/PLAN.md#d-23-macos-is-ci-only)).
- [ ] Require conversation resolution before merging.
- [ ] Require linear history.
- [ ] Allow **squash merging** only; disable merge commits and rebase merging.
- [ ] Do not allow force pushes.
- [ ] Do not allow deletions.
- [ ] Do **not** enable "Allow administrators to bypass the above settings".
- [ ] Automation tokens (`GITHUB_TOKEN`, agent PATs) hold `contents: write` on feature branches only, never on `main`.

Allowed automation: coding agents pushing feature branches and opening PRs, `release-please`, `dependabot`, `labeler`. Forbidden: force-pushing `main`, merging with red CI, committing secrets, auto-merging any PR.

## 8. Testing

```bash
uv run --project engine pytest                     # everything, including gpu-marked tests
uv run --project engine pytest -m "not gpu"        # what CI runs
pnpm -F ui test                                    # vitest
pnpm -F ui test -- --run                           # vitest, no watch (CI form)
```

- **The `gpu` marker.** Tests that need a real CUDA or ROCm device are marked `@pytest.mark.gpu` and are excluded from CI, which has no GPU. They are run by hand on the two reference machines only — Windows 11 with an RTX 4070 Ti (CUDA) and CachyOS with an RX 9060 XT (ROCm), [PRD §3.2](docs/PRD.md#32-reference-hardware). Never make a `gpu` test a merge requirement.
- **The `fake` backend.** `engine-tts` ships a deterministic sine-wave backend that imports no `torch`. The job engine, resume logic and muxer are all testable through it, and one integration test drives a full job over the API.
- **Golden fixtures.** `engine/tests/golden/` holds the expected output for the Polish golden chapter (`pl_chapter_01`): ordinals, mid-paragraph dialogue splits, gender from verb suffixes, the `-a` male name exceptions, toponyms, acronyms, hyphenation and soft-hyphen artifacts. Repo-root `fixtures/` holds the cross-language inputs — `books/` (EPUB 2/3, DRM-encrypted, font-obfuscated, PDF with and without a text layer), `audio/` (voice samples in five containers), `text/`. Fixtures that can be regenerated are produced by `scripts/make_fixtures.py`; only the generator is reviewed in depth.
- **Coverage gates** ([`CI_AND_RELEASE.md` §2](docs/plan/CI_AND_RELEASE.md#2-ci-engineyml)): ≥ 90 % on `praelector/text/**` and `praelector/jobs/**`, ≥ 80 % on `praelector/gpu/**` and `praelector/ebook/**`. There is deliberately **no global gate** — these four trees are the `NF-08` modules (span/dialogue heuristics and resume logic) and they are where bugs hurt.
- **Lockfiles are frozen.** `--frozen` everywhere. A lockfile that needs updating is a failing build, not a silent resolve.
- **UI.** Vitest only; browser end-to-end tests are post-v1 ([D-19](docs/plan/PLAN.md#d-19-no-browser-e2e-tests-in-v1)).

## 9. Internationalisation

The UI ships English (default) and a complete Polish catalogue (`IX-01`, `IX-02`).

- No string literal reaches the screen except through `i18next`. The ESLint `no-literal-string` rule on `apps/ui/src/**/*.tsx` is the first line of defence.
- Both `en` and `pl` catalogues under `apps/ui/src/i18n/locales/` **must be updated in the same PR**. A key present in one and missing in the other fails CI. Machine-translating the `pl` value and flagging it for review is acceptable; leaving it out is not.
- `node scripts/i18n_check.mjs` enforces key parity between `en` and `pl`, fails on any key that is unused across `apps/ui/src` (dead strings rot), and fails when `i18next-parser` finds a translatable literal outside the catalogues.
- The engine returns **error codes, never prose** ([D-16](docs/plan/PLAN.md#d-16-engine-returns-error-codes-not-prose)) — `ebook.drm_detected`, `tts.language_unsupported`, `job.already_active`. All user-facing text lives in the UI catalogues, including the `errors.json` namespace. This is what makes `IX-02` mechanically checkable.

## 10. Licenses and dependencies

Application code is Apache-2.0 (`NF-03`). `scripts/license_check.py` runs on every PR and classifies each dependency in `engine`, `engine-tts` and `apps/ui`:

| Class | SPDX examples | Action |
| --- | --- | --- |
| allow | `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `PSF-2.0`, `MPL-2.0`, `Unlicense`, `CC0-1.0` | pass |
| review | `LGPL-2.1`, `LGPL-3.0`, `EPL-2.0`, unknown or missing metadata | fails unless the package is listed in `scripts/license_allowlist.toml` with a written justification |
| deny | `GPL-2.0`, `GPL-3.0`, `AGPL-3.0`, `SSPL`, `BUSL`, `CC-BY-NC-*`, "commercial" | fails, no allowlist |

**`AGPL-*`, `GPL-*`, `SSPL`, `BUSL` and `CC-BY-NC-*` are denied outright. There is no allowlist for the deny class, no override flag, and no exception process.** Copyleft would relicense the whole distributed application.

Worked example: **EbookLib is banned.** It is AGPL-3.0-or-later, and importing it into an Apache-2.0 desktop app whose binaries we distribute would put the whole work under AGPL. Praelector therefore uses a hand-rolled EPUB reader/writer built on `zipfile` (stdlib), `lxml` (BSD-3) and `beautifulsoup4` (MIT) — see [D-01](docs/plan/PLAN.md#d-01-no-ebooklib-hand-rolled-epub-readerwriter). The deny list exists precisely so a well-meaning contributor or agent cannot reintroduce it. Other libraries rejected for license reasons are tabulated in [PLAN.md §11.4](docs/plan/PLAN.md#114-rejected-for-license-reasons).

**Adding any dependency:**

1. Check its SPDX id against the table above before opening the PR.
2. Commit the updated lockfile (`--frozen` means CI will not resolve it for you).
3. Regenerate `NOTICE`: `just license-check`, or `uv run python scripts/license_check.py --write-notice`. Commit the result in the same PR; `licenses.yml` fails on a diff.
4. Tick the dependency box in the PR template.

**Model weights are a different mechanism.** Weight licenses are *not* dependency metadata and are not checked by `license_check.py`. They live in each TTS backend's `BackendDescriptor.licenses[]` array, are surfaced in the Backends screen before any download, and gate the download behind an acknowledgement where required (`TTS-02`, `NF-03`, product principle 5). A unit test asserts every descriptor carries a complete `licenses[]` with a valid SPDX id or an explicit `LicenseRef-` id.

External binaries are never linked, only invoked as subprocesses (`NF-04`): Calibre's `ebook-convert` is GPLv3 and user-installed; `ffmpeg` is LGPL in the build we fetch and is never bundled. PyInstaller's GPL-2.0-with-bootloader-exception applies at build time only. Details in [PLAN.md §11.5](docs/plan/PLAN.md#115-external-processes-never-linked) and [`docs/licenses.md`](docs/licenses.md).

## 11. Adding a TTS backend

Full guide: [`docs/plugins.md`](docs/plugins.md). The short version:

1. Implement the `TtsBackend` protocol in `engine-tts/src/praelector_tts/backends/`: `describe()`, `load()`, `synthesize()`, `probe_vram()`, `unload()`, plus the `id` and `adapter_version` class attributes. `adapter_version` is an input to `render_key`, so bump it whenever output changes.
2. Return a complete `BackendDescriptor` from `describe()`. It must include `licenses[]` — one entry per component (code, weights, tokenizer), each with an SPDX id or `LicenseRef-` id, a URL, and the `acknowledgement_required` / `commercial_use` flags — and `capabilities.languages`.
3. **`pl` must appear in `capabilities.languages` for the backend to be usable by v1's primary audience.** The language list is the capability gate from `TTS-01`: `POST /v1/jobs` refuses to start with `tts.language_unsupported` when the project language is outside it. Qwen3-TTS ships without `pl` for exactly this reason ([D-17](docs/plan/PLAN.md#d-17-qwen3-tts-ships-but-cannot-narrate-polish)). Declare the truth; do not pad the list.
4. Set the remaining capability flags honestly — `clone`, `voice_design`, `emotion`, `streaming`, `batching`, `deterministic_with_seed`, `watermark`, `native_sample_rate`, `max_input_chars`, `reference_audio`. Chatterbox sets `watermark: true` because it embeds a PerTh watermark in every clip ([D-22](docs/plan/PLAN.md#d-22-chatterbox-output-watermarking-is-disclosed)).
5. Expose tunables through `params_schema` with `x-prl-ui` hints; the Voices screen renders the panel from the schema, so no backend-specific UI code is allowed (`TTS-05`).
6. **Never import `torch` in the engine core.** Model loading happens inside the worker process (`engine-tts`); `engine/src/praelector/tts/` only speaks the JSONL protocol and manages the model cache.

Add a test that the descriptor validates, and note the backend in `docs/gpu.md` with a measured `peak_mib` once you have run it on real hardware (`GPU-03`).

## 12. Milestones

Detail and per-milestone task lists: [`docs/plan/PLAN.md` §9](docs/plan/PLAN.md#9-milestones).

| Milestone | Name | One line |
| --- | --- | --- |
| M0 | Skeleton | Monorepo scaffold, Tauri window, sidecar health handshake, i18n `en`/`pl` stub, settings shell, project create and open. |
| M1 | Ebook core | EPUB ingest, chapter tree, lector editor, working EPUB save, optional Calibre convert, DRM refusal. |
| M2 | Suggestions, dialogue, gender | Deterministic pre-pass, LLM router, review UI, apply, reader EPUB export. **Do not skip.** |
| M3 | Voices and one backend | Voice sample ingest, OmniVoice adapter, preview playback, GPU detection, TTS plugin protocol frozen. |
| M4 | Job engine | Chunker, checkpointing, pause/resume, progress metrics, Chatterbox and Qwen3-TTS adapters. |
| M5 | M4B | Metadata editor, full and partial mux, ffmpeg packaging. |
| M6 | Hardening and v1 release | ROCm path on Arch, Windows installer, docs, CI releases, license screens, full-book fixture tests. |

Issues carrying the `blocker:v1` label are the dialogue and speaker-gender work — `DG-01` through `DG-06`. That block is the reason v1 exists: a single-voice converter without mid-paragraph dialogue detection and gender classification does not satisfy the PRD. **`blocker:v1` work must not be skipped, descoped, or deferred to a post-v1 milestone**, and a PR that weakens it (for example by auto-applying a low-confidence split) will not be merged.

## 13. Code style

**SPDX header on every source file** — `scripts/spdx_headers.py --check` runs in CI on every PR:

- Python: `# SPDX-License-Identifier: Apache-2.0`
- TypeScript / TSX / JavaScript: `// SPDX-License-Identifier: Apache-2.0`
- Rust: `// SPDX-License-Identifier: Apache-2.0`

Do not add the header to Markdown, JSON, TOML or YAML.

| Language | Formatter | Linter | Types |
| --- | --- | --- | --- |
| Python | `ruff format` | `ruff check` | `mypy --strict` — no untyped defs, no `Any` without a reason |
| TypeScript | `prettier` | ESLint, flat config (`eslint.config.js`) | `tsc --noEmit` |
| Rust | `cargo fmt` | `cargo clippy -- -D warnings` | — |

Beyond the tooling:

- **Comments explain *why*, never *what*.** The code states what it does; a comment earns its place when it records a constraint, a rejected alternative, or a reference (`# DG-02: a dash that closes a narration insertion re-opens dialogue`, not `# increment i`). Link a decision ID (`D-07`) or requirement ID (`JB-05`) rather than restating a plan.
- Errors are codes plus machine-readable detail, mapped to HTTP in `engine/src/praelector/errors.py`. Never return user-facing prose from the engine.
- All engine paths are `pathlib.Path`, serialised as POSIX-style strings with a drive prefix. Nothing inside a project directory may exceed 240 characters.
- Writes to the project directory go through `store/atomic.py` (temp file plus rename). Never write a project file in place.
- Keep `engine` importable and testable without a GPU, without `torch`, and without network access.
