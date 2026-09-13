# Prompt for a coding agent — produce the Praelector implementation plan

Copy everything below the line into a planning agent (Claude, Codex, Cursor Plan, Devin, etc.). Attach `PRD.md` and `00_ZAMYSL_Praelector.md` as context. The agent must **not** start implementing the application in the same step. Its deliverable is a plan the maintainer can approve, then slice into PRs.

---

You are the principal engineer planning **Praelector**, an Apache-2.0 local-first desktop app that turns DRM-free ebooks into multi-voice M4B audiobooks with a Polish lector-preparation workshop.

## Your job

Produce an **implementation plan** only:

1. `PLAN.md` — architecture, module map, data model, milestone task breakdown, risks, first 10 PRs.
2. `REPO_LAYOUT.md` — exact monorepo tree with responsibilities per folder.
3. `OPENAPI_SKETCH.md` — sidecar HTTP/WS endpoints needed for v1 (sketch, not generated code).
4. `DATA_MODEL.md` — JSON/SQLite entities: Project, Chapter, Span, Suggestion, VoiceProfile, Job, Chunk, GpuBudget.
5. `CI_AND_RELEASE.md` — GitHub workflow list and branch rules matching the PRD.
6. Optional: sequence diagrams in Mermaid for ingest → suggestions → TTS → mux.

Do **not** write application source yet. Do **not** invent features outside `PRD.md`. If the PRD is silent, pick the simplest option and record the decision in `PLAN.md` under “Decisions”.

## Binding constraints (do not reopen)

- Name: **Praelector**. Tagline: _Prepare the page. Cast the voice._
- App license: Apache-2.0. Calibre only as optional external `ebook-convert`.
- UI: Tauri 2 + React + TypeScript. Engine: Python 3.12 FastAPI sidecar on `127.0.0.1`.
- Platforms: Windows 11 x64 and Linux x64 supported. macOS CI best-effort, not a v1 promise.
- i18n: English default + complete Polish in v1.
- One project / one recording job at a time. Local project dir.
- TTS backends in v1: **OmniVoice (default)**, **Chatterbox Multilingual**, **Qwen3-TTS**, behind one plugin protocol.
- Voice modes: `single` | `narrator_dialogue` | `narrator_male_female`.
- Dialogue split (paragraph-initial **and** mid-paragraph) + speaker gender are **v1 blockers**.
- AI never silently overwrites the book; suggestions are reviewed.
- GPU: NVIDIA CUDA and AMD ROCm first-class; VRAM admission control; pause/resume with chunk checkpoints.
- LLM: Ollama and LM Studio as user-owned processes; plus OpenAI, Anthropic, Gemini, xAI, generic OpenAI-compatible. No installer for Ollama.
- ChatGPT / Claude / Grok / Gemini / Cursor **subscriptions are not APIs**. Document Groq, Google AI Studio, OpenRouter `:free` as cheap cloud on-ramps.
- Docs in English. Conventional Commits. Agents open PRs; humans merge when CI is green.
- No OCR. No DRM circumvention. No multi-book queue.

Read `PRD.md` as the source of truth. Requirements IDs (EB-01, DG-02, GPU-04, …) must appear in the plan next to the tasks that implement them.

## Quality bar for the plan

- Each milestone M0–M6 from the PRD becomes a checklist of concrete tasks (file-level when useful).
- Call out Windows vs Linux differences (ROCm wheels, ffmpeg, path conventions, code signing later).
- Specify how Tauri launches and supervises the sidecar, and how a release build finds Python/models.
- Specify the TTS plugin Protocol (methods, capability flags, parameter schema, license metadata).
- Specify the job state machine and chunk invalidation by text hash.
- Specify GPU budget math exactly as GPU-04 unless you must change it — if so, justify.
- List fixture tests: at least one Polish sample chapter with dashes, mid-paragraph speech, names, numerals, English tokens.
- Identify third-party libraries with licenses (ebooklib, beautifulsoup, pydantic, ffmpeg-python, soundfile, torch, etc.) and flag GPL risk.
- Propose pinning strategy for torch CUDA and torch ROCm as **separate extras**, not one fat wheel.

## Suggested stack choices (use these unless you have a documented better option)

| Area       | Choice                                                                                         |
| ---------- | ---------------------------------------------------------------------------------------------- |
| Frontend   | Vite + React 19 + TypeScript + Tailwind + shadcn-style components                              |
| i18n       | i18next                                                                                        |
| Desktop    | Tauri 2                                                                                        |
| Engine     | uv or poetry for Python deps; FastAPI + Uvicorn                                                |
| Validation | Pydantic v2                                                                                    |
| Persist    | SQLite via SQLAlchemy or sqlmodel + JSON files for chunk sidecars                              |
| EPUB       | ebooklib + lxml; Calibre CLI optional                                                          |
| Audio      | soundfile, numpy, pyloudnorm or ffmpeg loudnorm, pydub only if needed                          |
| Mux        | ffmpeg CLI                                                                                     |
| LLM        | official SDKs where useful + one OpenAI-compatible client for Ollama/LM Studio/Groq/OpenRouter |
| Tests      | pytest, ruff, mypy (engine); vitest + eslint (UI)                                              |
| Release    | Release Please + GitHub Actions                                                                |

## Hardware to plan against

- RTX 4070 Ti 12 GB, Windows 11
- RX 9060 XT 16 GB, CachyOS (Arch), ROCm

If a library does not support one of these, the plan must say so and pick an alternative path.

## Output style

Write the plan files in **English**, in Markdown, ready to commit under `/docs/plan/`. Be specific. No marketing language. No “maybe we could also”. v1 only.

When you are done, also print a short **PR sequence** (10–15 PRs) a maintainer can open in order, each small enough to review.

## What “done” means for you

The maintainer can hand `PLAN.md` to an implementation agent and get a compiling skeleton in M0 without asking you clarifying questions about stack, folders, or v1 scope.
