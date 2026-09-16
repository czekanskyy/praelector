# Praelector — Repository Layout

Monorepo (PRD §8). Node workspaces via `pnpm-workspace.yaml`, Python via two `uv` projects, Rust via one crate. Task entry points live in `justfile`.

Conventions:

- Python packages use `src/` layout.
- Every source file carries an SPDX header: `# SPDX-License-Identifier: Apache-2.0` (checked in CI).
- No generated artifact is committed except lockfiles, `packages/schemas/src/generated/**` and small text fixtures.

---

## 1. Top level

```
praelector/
├── .github/                  # CI, templates, automation policy
├── apps/
│   ├── desktop/              # Tauri 2 shell (Rust) — the shipped executable
│   └── ui/                   # React 19 + TS front end
├── engine/                   # Python 3.12 sidecar, torch-free  (praelector)
├── engine-tts/               # Python TTS worker, torch-dependent (praelector_tts)
├── packages/
│   └── schemas/              # JSON Schemas + generated TS types (shared contract)
├── docs/                     # English documentation (NF-10)
├── fixtures/                 # cross-language sample inputs
├── scripts/                  # build, codegen, license and i18n tooling
├── LICENSE                   # Apache-2.0
├── NOTICE                    # third-party attributions (NF-03)
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md              # managed by release-please
├── justfile                  # dev, test, lint, build, package
├── package.json              # workspace root scripts only
├── pnpm-workspace.yaml
├── release-please-config.json
├── .release-please-manifest.json
├── .editorconfig
├── .gitignore
└── .gitattributes            # keep fixture EPUB/PDF/WAV binary, LF for text
```

| Path | Responsibility |
| --- | --- |
| `apps/desktop` | Owns process lifecycle, window, native dialogs, resource resolution. Contains no product logic. |
| `apps/ui` | Owns all user-facing strings and all presentation. Talks only to the engine HTTP/WS API. |
| `engine` | Owns all product logic that does not need `torch`. Single writer of the project directory. |
| `engine-tts` | Owns model loading and synthesis. Knows nothing about projects, SQLite or HTTP. |
| `packages/schemas` | The only place where the UI/engine contract is defined. |

---

## 2. `.github/`

```
.github/
├── workflows/
│   ├── ci-engine.yml         # ruff, mypy, pytest on ubuntu + windows
│   ├── ci-ui.yml             # eslint, tsc, vitest, i18n parity, schema staleness
│   ├── ci-desktop.yml        # cargo fmt/clippy, tauri build --no-bundle (+ macOS best-effort)
│   ├── licenses.yml          # dependency license policy, NOTICE freshness, SPDX headers
│   ├── pr-title.yml          # Conventional Commits on PR titles
│   ├── gitleaks.yml          # secret scan (LM-03)
│   ├── codeql.yml            # python + javascript
│   ├── release-please.yml    # version + changelog + tag PR
│   └── release.yml           # tag -> Windows NSIS + zip, Linux AppImage + tar.gz, SHA256SUMS
├── ISSUE_TEMPLATE/
│   ├── bug_report.yml        # requires OS, GPU, backend, engine version
│   ├── feature_request.yml
│   ├── tts_backend_request.yml
│   └── config.yml
├── PULL_REQUEST_TEMPLATE.md  # requirement IDs touched, tests, docs, license impact
├── CODEOWNERS
├── dependabot.yml            # pip, npm, cargo, github-actions
└── labeler.yml               # area:engine, area:ui, area:desktop, area:docs
```

---

## 3. `apps/desktop/` — Tauri 2 shell

```
apps/desktop/
├── src/
│   ├── main.rs               # entry, plugin registration, run loop
│   ├── lib.rs
│   ├── engine/
│   │   ├── mod.rs            # EngineHandle { base_url, token } in tauri::State
│   │   ├── supervisor.rs     # spawn, ready handshake, health poll, backoff, teardown
│   │   ├── ready.rs          # parse "PRAELECTOR_READY {json}" from stdout
│   │   ├── logbuf.rs         # rolling 200-line buffer for the fatal panel
│   │   ├── job_object_win.rs # #[cfg(windows)] kill-on-close Job Object
│   │   └── pgroup_unix.rs    # #[cfg(unix)] process group + SIGTERM/SIGKILL
│   ├── commands.rs           # engine_endpoint, open_path, pick_file, app_paths, engine_logs
│   ├── paths.rs              # resourceDir / dataDir / configDir resolution per OS
│   └── logging.rs            # tauri-plugin-log wiring
├── capabilities/
│   └── default.json          # least-privilege plugin permissions and fs scopes
├── icons/
├── resources/                # populated at build time, not committed
│   ├── engine/               # PyInstaller onedir output
│   └── bin/                  # bundled uv
├── build.rs
├── Cargo.toml
└── tauri.conf.json           # CSP, bundle targets (nsis, appimage), resources globs
```

Responsibilities and non-responsibilities:

- **Does**: resolve paths, start/stop/restart the engine, guarantee no orphan processes, enforce single instance, host the WebView, provide native file pickers.
- **Does not**: read project files, call the LLM, know about chapters or jobs. If the shell needs data, it asks the engine over HTTP like the UI does.

---

## 4. `apps/ui/` — front end

```
apps/ui/
├── src/
│   ├── main.tsx
│   ├── App.tsx                     # router + engine-connection gate
│   ├── routes.tsx
│   ├── features/
│   │   ├── library/                # recent projects, new/open (PRD §5.1)
│   │   ├── ingest/                 # file pick, DRM + Calibre error states
│   │   ├── chapters/               # tree, rename/reorder/merge/split, include flags
│   │   ├── editor/
│   │   │   ├── ChapterEditor.tsx   # CodeMirror 6 host
│   │   │   ├── spanDecorations.ts  # span kind -> Decoration (ED-03)
│   │   │   ├── spokenView.tsx      # print vs spoken (ED-06)
│   │   │   ├── FindReplace.tsx     # ED-05
│   │   │   └── PronunciationDialog.tsx
│   │   ├── suggestions/            # queue, filters, accept/reject/edit, bulk + undo
│   │   ├── voices/                 # sample upload, waveform, slots, params panel
│   │   ├── job/                    # stage, fragment, counts, RTF, ETA, VRAM, controls
│   │   ├── metadata/               # metadata form, cover, M4B + EPUB export
│   │   └── settings/               # llm, tts backends + licenses, gpu, runtime, paths, language
│   ├── components/ui/              # shadcn-style primitives (button, dialog, table, ...)
│   ├── lib/
│   │   ├── api/                    # typed fetch client generated against packages/schemas
│   │   ├── ws/                     # WS client, seq tracking, gap-fill via /events?since=
│   │   ├── errors/                 # error code -> i18n key mapping (D-16)
│   │   ├── schemaForm/             # JSON Schema + x-prl-ui -> form (TTS-05)
│   │   ├── hooks/
│   │   └── format/                 # duration, bytes, RTF, ETA formatting (locale-aware)
│   ├── i18n/
│   │   ├── index.ts
│   │   └── locales/
│   │       ├── en/{common,library,ingest,chapters,editor,suggestions,voices,job,metadata,settings,errors}.json
│   │       └── pl/{...same keys...}
│   └── styles/
├── tests/                          # vitest unit + component tests
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── eslint.config.js                # flat config; no-literal-string on src/**/*.tsx (IX-02)
└── vitest.config.ts
```

Rules:

- No string literal reaches the screen without going through `i18next` (enforced by lint).
- `lib/api` is the only module allowed to call `fetch`.
- Feature folders never import from each other; shared code moves to `components/` or `lib/`.

---

## 5. `engine/` — Python sidecar (core)

```
engine/
├── src/praelector/
│   ├── __main__.py            # argv/env parsing, uvicorn bootstrap, READY line, parent watchdog
│   ├── app.py                 # FastAPI factory, middleware, router mounting, lifespan
│   ├── config.py              # Settings (pydantic-settings), path resolution, feature probes
│   ├── security.py            # bearer token, Origin allow-list (D-10)
│   ├── logging.py             # JSON logs + secret redaction filter (LM-03)
│   ├── errors.py              # error codes, AppError -> HTTP mapping (D-16)
│   ├── events.py              # in-process event bus -> WS hub
│   │
│   ├── api/v1/
│   │   ├── health.py  settings.py  projects.py  ingest.py
│   │   ├── chapters.py  spans.py  search.py
│   │   ├── suggestions.py  lexicon.py  revisions.py
│   │   ├── voices.py  tts.py  runtime.py  gpu.py
│   │   ├── jobs.py  export.py  metadata.py
│   │   └── ws.py              # /v1/ws hub, seq, replay
│   │
│   ├── domain/
│   │   ├── ids.py             # prefixed ULIDs: prj_, chp_, blk_, spn_, sug_, vpr_, job_
│   │   ├── enums.py           # SpanKind, VoiceMode, VoiceSlot, JobState, JobStage, ...
│   │   ├── models.py          # Pydantic entities (source of packages/schemas)
│   │   ├── hashing.py         # text_hash, params_hash, render_key (JB-05)
│   │   └── revisions.py       # SCD-2 helpers, offset remap after edits (D-08)
│   │
│   ├── store/
│   │   ├── db.py              # engine, WAL, session scope
│   │   ├── migrations/        # alembic
│   │   ├── project_dir.py     # directory layout, create/open/validate
│   │   ├── manifest.py        # project.json
│   │   ├── atomic.py          # temp+rename writers (JB-02)
│   │   ├── locks.py           # project.lock, global job slot (D-14)
│   │   ├── reconcile.py       # rebuild chunk index from sidecars (JB-07, D-02)
│   │   └── repositories/      # project, chapter, block, span, suggestion, voice, job, chunk, lexicon
│   │
│   ├── ebook/
│   │   ├── detect.py          # magic bytes + extension
│   │   ├── drm.py             # encryption.xml / sinf.xml analysis, fail closed (EB-01, EB-02)
│   │   ├── epub_read.py       # container -> OPF -> manifest/spine -> NCX|nav
│   │   ├── epub_write.py      # deterministic EPUB 3 writer (EB-06, EX-01..EX-03)
│   │   ├── opf.py  ncx.py  nav.py
│   │   ├── blocks.py          # XHTML -> Block[] with source_ref (D-08)
│   │   ├── cover.py           # cover detection + extraction (EB-05, EB-07)
│   │   ├── frontmatter.py     # skip-span heuristics (EB-08)
│   │   ├── calibre.py         # ebook-convert discovery + invocation (EB-03, EB-09)
│   │   └── pdf.py             # pypdf text-layer probe (EB-04)
│   │
│   ├── text/
│   │   ├── normalize.py  artifacts.py  segment.py
│   │   ├── dialogue.py        # DG-01, DG-02 state machine
│   │   ├── gender.py          # DG-03..DG-06 signal ladder
│   │   ├── numerals_pl.py     # D-11
│   │   ├── acronyms.py  foreign.py  toponyms.py
│   │   ├── lexicon.py         # AI-09
│   │   ├── pipeline.py        # heuristic pass -> llm pass -> suggestions
│   │   ├── prompts/           # versioned prompt templates per task key
│   │   └── data/
│   │       ├── speech_verbs_pl.txt
│   │       ├── given_names_pl.tsv       # incl. -a male exceptions
│   │       ├── abbreviations_pl.txt
│   │       ├── toponyms_pl.tsv
│   │       └── en_words.txt             # public-domain EN list (D-12)
│   │
│   ├── llm/
│   │   ├── protocol.py  router.py  schemas.py  usage.py  secrets.py
│   │   └── providers/{openai_compat.py, anthropic.py, gemini.py}
│   │
│   ├── voices/{ingest.py, profiles.py, preview.py, waveform.py}
│   ├── audio/{ffmpeg.py, probe.py, wavio.py, loudness.py, silence.py, concat.py}
│   ├── tts/{protocol.py, descriptor.py, registry.py, worker_client.py, models_cache.py, licenses.py}
│   ├── gpu/{detect.py, budget.py, monitor.py, vram_table.py}
│   ├── jobs/{manager.py, state.py, planner.py, chunker.py, scheduler.py,
│   │         checkpoint.py, metrics.py, prep_job.py, record_job.py, eventlog.py}
│   ├── mux/{chapters.py, metadata.py, m4b.py, partial.py}
│   └── runtime/{provision.py, uv_runner.py, flavour.py, requirements/}
│
├── tests/
│   ├── unit/                  # one module per source module
│   ├── golden/                # pl_chapter_01 and friends
│   ├── integration/           # ingest->export, job->resume->mux (fake backend)
│   ├── fixtures/              # see PLAN.md §10
│   └── conftest.py
├── pyproject.toml
├── uv.lock                    # CI asserts: contains no torch
└── README.md
```

Rules:

- `api/` contains no logic beyond validation and delegation.
- `store/` is the only layer that touches disk or SQLite.
- `text/` is pure: functions take text and return spans/suggestions; no I/O, no network. This is what makes the golden tests cheap.
- `tts/` never imports `torch`.

---

## 6. `engine-tts/` — TTS worker

```
engine-tts/
├── src/praelector_tts/
│   ├── __main__.py            # JSONL stdio loop, one request in flight
│   ├── protocol.py            # request/response models mirrored from engine/tts/protocol.py
│   ├── worker.py              # dispatch, error mapping, ready event
│   ├── device.py              # cuda/hip/cpu selection, CUDA_VISIBLE_DEVICES pin (D-13)
│   ├── vram.py                # torch.cuda.max_memory_allocated reporting (GPU-03)
│   ├── audio.py               # tensor -> PCM16 WAV (.part then reported)
│   └── backends/
│       ├── base.py            # shared descriptor helpers
│       ├── fake.py            # deterministic sine; no torch import (CI + docs/plugins.md)
│       ├── omnivoice.py       # default (TTS-02)
│       ├── chatterbox.py      # MIT alternative, watermark flag (D-22)
│       └── qwen3.py           # Apache-2.0, languages exclude pl (D-17)
├── pyproject.toml             # cpu/cuda/rocm conflicting extras (D-03)
├── uv.lock
└── README.md
```

The worker is intentionally dependency-light outside its extras: importing `praelector_tts` without any extra must succeed and expose the `fake` backend, so CI can exercise the entire job engine without `torch`.

---

## 7. `packages/schemas/`

```
packages/schemas/
├── src/
│   ├── json/                  # generated from Pydantic: entities, ws events, errors, descriptors
│   └── generated/             # generated TS types consumed by apps/ui
├── package.json
└── README.md                  # "generated; run `just codegen`"
```

`scripts/gen_ts_types.py` runs Pydantic `model_json_schema()` then `json-schema-to-typescript`. `ci-ui.yml` regenerates and fails on a diff, so the UI can never drift from the engine contract.

---

## 8. `docs/`

```
docs/
├── plan/
│   ├── PLAN.md  REPO_LAYOUT.md  OPENAPI_SKETCH.md
│   ├── DATA_MODEL.md  CI_AND_RELEASE.md  SEQUENCES.md
├── architecture.md            # process topology, trust boundary, data flow
├── dev-setup.md               # Windows and Arch/CachyOS from zero
├── packaging.md               # PyInstaller, resources, runtime provisioning, installers
├── gpu.md                     # tested CUDA/ROCm tuples, budget math, troubleshooting
├── plugins.md                 # how to add a TTS backend (success metric, PRD §12)
├── llm-providers.md           # 7 profiles, free/cheap on-ramps, "subscriptions are not APIs"
├── user-guide.md              # ingest -> review -> voices -> record -> export
├── licenses.md                # dependency and model license tables
├── security.md -> ../SECURITY.md
└── troubleshooting.md
```

---

## 9. `scripts/` and `fixtures/`

```
scripts/
├── build_engine.py            # PyInstaller onedir -> apps/desktop/resources/engine
├── fetch_uv.py                # download + verify the bundled uv binary
├── gen_ts_types.py            # Pydantic -> JSON Schema -> TS
├── license_check.py           # dependency license policy + NOTICE freshness
├── spdx_headers.py            # SPDX header presence check/fix
├── i18n_check.mjs             # en/pl key parity + unused/missing keys (IX-01)
├── make_fixtures.py           # generate EPUB/PDF/WAV fixtures deterministically
└── dev.py                     # run engine + vite + tauri together

fixtures/
├── books/                     # epub2_minimal, epub3_minimal, epub3_polish_novel, drm_encrypted,
│                              # font_obfuscated, empty_text, no_text_layer.pdf, text_layer.pdf
├── audio/                     # voice_sample.{wav,mp3,flac,m4a,ogg}, silence-padded variant
└── text/                      # pl_chapter_01.txt + pl_chapter_01.expected.json
```

Fixtures that can be generated are generated by `make_fixtures.py` and only the generator is reviewed; a small committed copy exists for the three EPUBs so tests run offline without a build step.

---

## 10. Project directory on the user's disk

Created and owned by `engine/store/project_dir.py`. Matches PRD §5.2 with the two documented deviations ([D-02](PLAN.md#d-02-sqlite-is-the-primary-store), [D-07](PLAN.md#d-07-chunk-audio-is-content-addressed-at-project-level)).

```
~/Praelector/projects/<project_id>/
├── project.json              # manifest: schema_version, id, name, voice_mode, backend_id
├── project.db                # SQLite: chapters, blocks, spans, suggestions, voices, jobs, index
├── project.lock              # exclusive lock + owning pid
├── source/
│   ├── original.<ext>        # untouched user upload (EB-06)
│   └── working.epub          # normalised working copy
├── reader/                   # exported lector EPUB snapshots (EX-01, EX-03)
├── voices/
│   ├── <voice_profile_id>.wav      # processed reference
│   └── <voice_profile_id>.peaks.json
├── audio/chunks/<rk[0:2]>/<render_key>.wav   # content-addressed, immutable (D-07)
│                            .json            # sidecar: text, slot, hashes, backend, duration
├── jobs/<job_id>/
│   ├── job.json              # state machine + offsets + warnings (JB-01, JB-03)
│   ├── plan.jsonl            # ordinal -> render_key -> text prefix
│   ├── events.jsonl          # append-only, monotonic seq (WS replay)
│   └── logs/
├── output/
│   ├── book.m4b
│   ├── cover.jpg
│   ├── chapters/             # optional per-chapter audio (MX-05)
│   └── partial_report.json   # which chapters were omitted (MX-03)
└── cache/                    # per-project scratch; models live in the global cache instead
```

Global (outside the project), per §1.7 of [PLAN.md](PLAN.md):

```
<dataDir>/
├── models/<backend>/<repo>/<revision>/   # weights + manifest.json with sha256 per file
├── runtimes/<flavour>-<lockhash>/        # provisioned TTS venv + runtime.json
├── bin/                                  # fetched ffmpeg/ffprobe (LGPL build)
└── logs/
<configDir>/config.json                   # settings; secrets go to the OS keyring
```
