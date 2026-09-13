# Product Requirements Document

**Product:** Praelector  
**Version:** 1.0 (target MVP / v1)  
**Status:** Draft for implementation planning  
**License (application code):** Apache License 2.0  
**Primary docs language:** English  
**UI languages in v1:** English (default) + complete Polish

Related documents:

- `00_ZAMYSL_Praelector.md` — product concept (Polish)
- `CODING_AGENT_PROMPT.md` — prompt for a coding agent to produce an implementation plan

This PRD is the source of truth for v1 scope. If a coding plan disagrees with this file, this file wins until the maintainer amends it.

---

## 1. Summary

Praelector is a local-first desktop application (Windows and Linux, macOS best-effort) that turns a DRM-free ebook into a chapterized M4B audiobook. The differentiator is a **lector preparation workshop**: pronunciation rewrites for Polish narration, dialogue segmentation (including mid-paragraph), speaker-gender classification, human review of every AI change, GPU-aware parallel TTS with pause/resume, and M4B assembly from complete or partial recordings.

v1 is optimized for Polish books and a Polish narrator, with three first-party TTS backends (OmniVoice default, Chatterbox, Qwen3-TTS) and pluggable later backends.

## 2. Goals and non-goals

### 2.1 Goals

- G1. Import DRM-free EPUB; import PDF (text layer only) and MOBI via optional Calibre CLI; use EPUB as the working and export format.
- G2. Provide a purpose-built lector editor (chapters, spans, suggestions), not a general Sigil clone.
- G3. Run an AI preparation pipeline whose outputs are listed, categorized, and manually editable.
- G4. Detect dialogues at paragraph start **and** mid-paragraph; classify speaker gender from local context.
- G5. Support three voice modes: single; narrator+dialogue; narrator+male+female.
- G6. Run local OSS TTS with voice-sample ingest (trim, loudness, resample) and per-model parameters.
- G7. Detect NVIDIA CUDA and AMD ROCm VRAM; schedule workers under a hard memory ceiling.
- G8. Show live job metrics (stage, fragment, remaining work, RTF, ETA, VRAM).
- G9. Pause / stop / resume without redoing finished chunks.
- G10. Mux M4B with chapters and editable metadata (cover, title, author, narrator, …), including mux-from-partial.
- G11. Export the lector-prepared book as EPUB.
- G12. Talk to user-started Ollama / LM Studio and to cloud LLM APIs; never ship secrets.
- G13. Ship as Apache-2.0 open source on GitHub with English docs, CI, and review-gated automated PRs.

### 2.2 Non-goals (v1)

- OCR for scanned PDFs.
- DRM removal or circumvention.
- Installing or managing chat-LLM runtimes (Ollama/LM Studio are user-owned).
- Multi-book queue.
- Cloud project sync.
- Per-named-character voice casting (gender + narrator only).
- Guaranteed macOS quality (no maintainer Mac).
- Fine-tuning TTS models.
- Using ChatGPT / Claude / Gemini / Grok / Cursor **subscriptions** as API backends (they are not APIs).

## 3. Users and environments

### 3.1 Primary user

Polish power user producing personal audiobooks from legally obtained, DRM-free ebooks. Already able to generate single-voice audiobooks; v1 must exceed that.

### 3.2 Reference hardware

| Machine | OS             | GPU                    | Role                |
| ------- | -------------- | ---------------------- | ------------------- |
| A       | Windows 11     | RTX 4070 Ti 12 GB VRAM | Primary CUDA target |
| B       | CachyOS (Arch) | RX 9060 XT 16 GB VRAM  | Primary ROCm target |

Minimum viable inference: 8 GB VRAM, 1 worker, or CPU with an explicit slow-path warning. Comfortable: 12–16 GB and 2+ workers when the backend allows.

### 3.3 Platforms

| Platform                                              | v1 commitment                               |
| ----------------------------------------------------- | ------------------------------------------- |
| Windows 11 x64                                        | Supported                                   |
| Linux x64 (Arch and derivatives first; generic glibc) | Supported                                   |
| macOS (Apple Silicon / Intel)                         | Build in CI if cheap; unmarked as supported |

## 4. Product principles

1. **No silent mutation.** AI writes suggestions; the user commits them.
2. **Resume is a data-model feature**, not an afterthought.
3. **VRAM is a budget**, not a best-effort hope.
4. **Local-first.** Cloud LLMs are optional. Book text must not leave the machine unless the user enables a cloud provider.
5. **Licenses are visible.** Model weight licenses are shown before download.
6. **One book, one project, one job at a time.**

## 5. Information architecture

### 5.1 App surfaces

1. **Library / Home** — recent projects, new project, settings entry.
2. **Project workspace**
   - Source & structure (chapters)
   - Lector editor
   - Suggestion review
   - Voices
   - Record / job monitor
   - Metadata & export
3. **Settings** — LLM providers, TTS backends, GPU policy, paths, language (en/pl).

### 5.2 Project directory (default `~/Praelector/projects/<project_id>/`)

```
project.json              # ids, paths, voice mode, backend
source/                   # original upload + normalized working.epub
reader/                   # lector EPUB export snapshots
book/                     # parsed chapter JSON + span model
suggestions/              # suggestion store (jsonl or sqlite)
voices/                   # processed references + profiles
jobs/<job_id>/
  job.json                # state machine + offsets
  chunks/<nnnnn>.wav
  chunks/<nnnnn>.json     # text, voice slot, hashes
  logs/
output/
  book.m4b
  cover.jpg
cache/                    # model files may live in a global cache instead
```

Exact on-disk schema is an implementation choice; the fields above are required in spirit.

## 6. Functional requirements

Requirements use MoSCoW. **M** = v1 must. **S** = v1 should. **C** = nice if cheap. **W** = not v1.

### 6.1 Ebook ingest and conversion

| ID    | Pri | Requirement                                                                                                                                                         |
| ----- | --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EB-01 | M   | Open EPUB 2/3 without DRM. Reject DRM with a clear error. Never attempt circumvention.                                                                              |
| EB-02 | M   | Detect DRM-ish failure modes (empty text, encrypted encryption.xml) and fail closed.                                                                                |
| EB-03 | M   | Optional conversion PDF→EPUB and MOBI/AZW3→EPUB by invoking a user-configured `ebook-convert` binary. If missing, show install instructions. Do not vendor Calibre. |
| EB-04 | M   | PDF without a text layer: fail with “no OCR in v1”.                                                                                                                 |
| EB-05 | M   | Extract title, authors, language, cover, TOC/spine into the project.                                                                                                |
| EB-06 | M   | Normalize to a working EPUB stored in the project (never mutate the user’s original file).                                                                          |
| EB-07 | S   | Preserve images that are the cover; ignore full-page decorative images for TTS.                                                                                     |
| EB-08 | S   | Heuristic drop of front-matter candidates (TOC pages, copyright blocks) flagged as `skip` spans, user-overridable.                                                  |
| EB-09 | C   | AZW if Calibre handles it.                                                                                                                                          |

### 6.2 Lector editor

| ID    | Pri | Requirement                                                                                              |
| ----- | --- | -------------------------------------------------------------------------------------------------------- |
| ED-01 | M   | Chapter tree from spine/TOC: rename, reorder, merge, split at caret, include/exclude from narration.     |
| ED-02 | M   | Edit chapter plain text and commit back into the span model.                                             |
| ED-03 | M   | Render spans with distinct styling: narration, dialogue, pronunciation (display vs spoken), skip, pause. |
| ED-04 | M   | Insert/edit pronunciation pairs: display form stays in reader EPUB; spoken form is what TTS sees.        |
| ED-05 | M   | Find / replace in the current chapter and across the book.                                               |
| ED-06 | M   | Side-by-side or toggle: “print text” vs “spoken text”.                                                   |
| ED-07 | M   | Autosave project state; crash-safe.                                                                      |
| ED-08 | S   | Jump from a suggestion to its span.                                                                      |
| ED-09 | S   | Manual mark of a range as dialogue / skip / pause.                                                       |
| ED-10 | W   | Full CSS / XHTML visual layout editor.                                                                   |

### 6.3 AI preparation pipeline

| ID    | Pri | Requirement                                                                                                                                                                                              |
| ----- | --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AI-01 | M   | Pipeline is a job with progress, cancel, and partial results.                                                                                                                                            |
| AI-02 | M   | Deterministic pre-pass before any LLM: dialogue dash patterns, English-lexicon hits, numerals, acronyms, hyphenation artifacts, repeated whitespace.                                                     |
| AI-03 | M   | LLM pass receives bounded context (target paragraph ± neighbors) and must return schema-validated JSON. Invalid JSON is retried once then recorded as a failed suggestion.                               |
| AI-04 | M   | Suggestion object: id, category, chapter_id, span range, original, proposed, rationale (short), confidence, detector (`heuristic`\|`llm`\|`dict`), status (`pending`\|`accepted`\|`rejected`\|`edited`). |
| AI-05 | M   | Categories listed in §6.3.1.                                                                                                                                                                             |
| AI-06 | M   | Review UI: filter by category/status/chapter, accept, reject, edit proposed text, accept-all-in-filter with undo.                                                                                        |
| AI-07 | M   | Applying suggestions is explicit and produces a new book revision.                                                                                                                                       |
| AI-08 | M   | Target spoken language in v1 is Polish. English tokens are rewritten into Polish readout forms.                                                                                                          |
| AI-09 | S   | User-editable pronunciation lexicon (global + per project) applied before LLM and after.                                                                                                                 |
| AI-10 | S   | Provider failover: if cloud 429/5xx, offer local profile.                                                                                                                                                |
| AI-11 | C   | Diff statistics: counts per category.                                                                                                                                                                    |

#### 6.3.1 Suggestion categories (v1)

`foreign_word`, `acronym`, `toponym`, `numeral`, `ordinal_heading`, `dialogue_split`, `speaker_gender`, `conversion_artifact`, `dict_hit`.

Examples the pipeline must be able to propose (user remains final editor):

- Walker → „Łoker”
- IT → „aj ti”
- Washington DC → „Łoszynkton di si”
- 238 → „dwieście trzydzieści osiem”
- Rozdział 8 → „rozdział ósmy”

#### 6.3.2 Dialogue and gender (v1 blocker)

| ID    | Pri | Requirement                                                                                                                                                              |
| ----- | --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| DG-01 | M   | Detect Polish dialogue openings: em dash / en dash / hyphen at paragraph start, including quotes variants.                                                               |
| DG-02 | M   | Detect mid-paragraph dialogue (dash or quotation after narration in the same paragraph) and split into narration + dialogue spans.                                       |
| DG-03 | M   | Attach `gender` = male \| female \| unknown to each dialogue span.                                                                                                       |
| DG-04 | M   | Gender signals: speech tags („powiedział X”, „zapytała Y”), given-name lexicons, pronouns in adjacent sentences. LLM used when heuristics disagree or confidence is low. |
| DG-05 | M   | Unknown gender falls back according to voice mode (dialogue voice or narrator) and is listed for review.                                                                 |
| DG-06 | S   | Optional speaker_id string when a name is explicit, used only as a label in UI in v1 (not a fourth voice).                                                               |

This block is **in scope for v1**. A single-voice converter without DG-\* does not satisfy v1.

### 6.4 LLM integration

| ID    | Pri | Requirement                                                                                                                                                                                          |
| ----- | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LM-01 | M   | Pluggable providers: Ollama, LM Studio (OpenAI-compatible), generic OpenAI-compatible, OpenAI, Anthropic, Gemini, xAI.                                                                               |
| LM-02 | M   | Connection test button per profile.                                                                                                                                                                  |
| LM-03 | M   | Secrets in OS keyring / encrypted local store. Never log secrets. Never commit `.env` with keys.                                                                                                     |
| LM-04 | M   | Per-task model routing: “cheap classify” vs “hard dialogue” profiles.                                                                                                                                |
| LM-05 | M   | Cloud calls require an explicit user-enabled toggle. Default is local-only if a local profile exists.                                                                                                |
| LM-06 | S   | Document in Settings how to get **free/cheap** keys: Groq, Google AI Studio Gemini Flash, OpenRouter `:free`. State clearly that ChatGPT Plus / Claude Pro / Grok / Cursor seats are not API access. |
| LM-07 | S   | Token/usage counters per project (best-effort).                                                                                                                                                      |
| LM-08 | W   | Bundle or install Ollama.                                                                                                                                                                            |

### 6.5 Voices and TTS

| ID     | Pri | Requirement                                                                                                                                                                        |
| ------ | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| TTS-01 | M   | Backend plugin interface with feature flags (clone, language list, emotion, design).                                                                                               |
| TTS-02 | M   | Ship adapters for OmniVoice (default), Chatterbox Multilingual, Qwen3-TTS. First-run download of weights into a global cache with progress, checksum, and license acknowledgement. |
| TTS-03 | M   | Voice modes: `single` \| `narrator_dialogue` \| `narrator_male_female`.                                                                                                            |
| TTS-04 | M   | Sample ingest: WAV/FLAC/MP3/M4A/OGG → VAD trim, LUFS normalize, resample, length clamp, preview playback, save profile.                                                            |
| TTS-05 | M   | Global audio settings and per-backend parameter panels (exposed from plugin schema).                                                                                               |
| TTS-06 | M   | Missing sample for a required slot: warn and fall back to narrator; do not fail the whole book silently.                                                                           |
| TTS-07 | M   | Sentence/utterance chunking that does not split inside a word; respects dialogue spans as atomic when short enough.                                                                |
| TTS-08 | S   | Crossfade / configurable inter-sentence silence.                                                                                                                                   |
| TTS-09 | S   | Short preview synthesize of the current paragraph.                                                                                                                                 |
| TTS-10 | C   | Extra backends (CosyVoice, IndexTTS) as plugins after the interface is stable.                                                                                                     |

**Default backend:** OmniVoice. License UI must flag non-commercial weight constraints when the selected checkpoint is NC.

### 6.6 GPU scheduler

| ID     | Pri | Requirement                                                                                                                |
| ------ | --- | -------------------------------------------------------------------------------------------------------------------------- |
| GPU-01 | M   | Detect CUDA devices (nvidia-smi / NVML) and ROCm devices (rocm-smi / amd-smi) plus CPU.                                    |
| GPU-02 | M   | Record total and free VRAM before a job and on a timer during a job.                                                       |
| GPU-03 | M   | Maintain a per-backend peak-VRAM table (measured or conservative defaults). Allow user override.                           |
| GPU-04 | M   | `max_workers = max(1, floor((free - reserve) / peak_worker))` with reserve = max(20% total, 1.5 GB) unless user overrides. |
| GPU-05 | M   | Refuse to start a worker that would exceed the ceiling. If memory climbs, pause admissions.                                |
| GPU-06 | M   | Surface GPU name, VRAM, worker count, and backend device in the job UI.                                                    |
| GPU-07 | S   | Separate CUDA vs ROCm install extras documented; app detects a missing stack and explains it.                              |
| GPU-08 | S   | CPU-only mode with a modal “this will be much slower than realtime”.                                                       |

### 6.7 Recording job, pause, resume

| ID    | Pri | Requirement                                                                                                     |
| ----- | --- | --------------------------------------------------------------------------------------------------------------- |
| JB-01 | M   | Job state machine: `queued → running → paused → running → muxing → done` and `failed` / `cancelled`.            |
| JB-02 | M   | Each chunk written atomically (temp + rename) with sidecar JSON (text hash, voice slot, backend, duration).     |
| JB-03 | M   | Pause: stop admitting new chunks; current chunk either finishes or is discarded; state persisted.               |
| JB-04 | M   | Stop/cancel: persist finished chunks; do not delete them unless user confirms “reset job”.                      |
| JB-05 | M   | Resume skips chunks whose text hash and voice slot still match. If text changed, only invalidated chunks rerun. |
| JB-06 | M   | One active recording job per app instance.                                                                      |
| JB-07 | S   | Recover after app kill / power loss from `job.json`.                                                            |

### 6.8 Progress UI

| ID    | Pri | Requirement                                                       |
| ----- | --- | ----------------------------------------------------------------- |
| UI-01 | M   | Current stage and human label.                                    |
| UI-02 | M   | Current fragment: chapter title, chunk index, text prefix.        |
| UI-03 | M   | Counts: finished / remaining chunks and stages.                   |
| UI-04 | M   | Instantaneous and smoothed RTF (audio-seconds / wall-seconds).    |
| UI-05 | M   | ETA from smoothed RTF and remaining characters or audio estimate. |
| UI-06 | M   | VRAM used vs budget; worker count.                                |
| UI-07 | M   | Pause, resume, stop controls always reachable during a job.       |

### 6.9 M4B and metadata

| ID    | Pri | Requirement                                                                                                        |
| ----- | --- | ------------------------------------------------------------------------------------------------------------------ |
| MX-01 | M   | Export M4B (AAC in MPEG-4) with chapter markers aligned to included chapters.                                      |
| MX-02 | M   | Editable metadata: title, authors, narrator, year, description, language, publisher, ISBN (optional), cover image. |
| MX-03 | M   | Mux available finished chunks into a partial M4B (missing chapters omitted or marked).                             |
| MX-04 | M   | Depend on a system or bundled ffmpeg; document the dependency.                                                     |
| MX-05 | S   | Keep per-chapter audio files as an advanced export.                                                                |

### 6.10 Reader EPUB export

| ID    | Pri | Requirement                                                                                                                                                                                    |
| ----- | --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EX-01 | M   | Export an EPUB that reflects accepted lector changes. Spoken-only rewrites should remain encoded so a future import can recover them (e.g. custom attributes or a companion JSON in the EPUB). |
| EX-02 | M   | Do not lose chapter structure or cover.                                                                                                                                                        |
| EX-03 | S   | Option: “clean reader” EPUB without internal span markup, display forms only.                                                                                                                  |

### 6.11 i18n, a11y, UX

| ID    | Pri | Requirement                                                 |
| ----- | --- | ----------------------------------------------------------- |
| IX-01 | M   | UI default English; Polish translation 100% for v1 strings. |
| IX-02 | M   | Extractable string catalog (not hardcoded Polish).          |
| IX-03 | S   | Keyboard shortcuts for accept/reject suggestion.            |
| IX-04 | S   | Respect OS dark/light.                                      |

## 7. Non-functional requirements

| ID    | Requirement                                                                                        |
| ----- | -------------------------------------------------------------------------------------------------- |
| NF-01 | Sidecar binds `127.0.0.1` only.                                                                    |
| NF-02 | Book text is sent to a cloud LLM only when that provider is enabled for the job.                   |
| NF-03 | App code Apache-2.0. Third-party notices file required. Model licenses acknowledged in UI.         |
| NF-04 | Calibre used only as an external process.                                                          |
| NF-05 | No telemetry by default. If added later, opt-in.                                                   |
| NF-06 | Warm start to UI < 5 s on reference hardware excluding model load.                                 |
| NF-07 | Model load and first chunk may be slow; UI must stay responsive.                                   |
| NF-08 | Unit tests for span/dialogue heuristics and job resume logic.                                      |
| NF-09 | Conventional Commits; CI red blocks merge.                                                         |
| NF-10 | Docs in English: README, architecture, user guide, plugin guide, contributing, security.           |
| NF-11 | Releases include Windows installer or portable zip + Linux AppImage or equivalent, plus changelog. |

## 8. Architecture constraints (binding)

- Desktop shell: **Tauri 2 + React + TypeScript**.
- Engine: **Python 3.12 FastAPI sidecar** started by Tauri.
- IPC: HTTP + WebSocket on localhost; shared JSON schemas.
- State: SQLite and/or JSON files under the project dir (choose one primary store and document it).
- Packaging: sidecar bundled or isolated venv documented for dev; production must not require the user to hand-assemble Python if a release build exists.
- GPU extras: optional dependency groups `cuda` and `rocm`.
- Monorepo.

## 9. GitHub and automation

Maintainer workflow: **open PR from automation → human reviews → merge if CI green**.

Must exist on day one of the public repo:

- `LICENSE` Apache-2.0
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Issue and PR templates
- `CHANGELOG.md` or Release Please
- CI: Python lint/test, frontend lint/test, license header or NOTICE check
- Release workflow for tags
- Branch protection assumption: no direct push to `main` in the documented workflow

Allowed automation: coding agents create branches and PRs, labelers, release-please, dependabot.

Forbidden automation: force-push to `main`, merging without CI, committing secrets.

## 10. Milestones

### M0 — Skeleton (week 1–2)

Repo, Tauri window, sidecar health, i18n en/pl stub, settings shell, project folder create/open.

### M1 — Ebook core

EPUB ingest, chapter tree, editor, working EPUB save, Calibre optional convert, DRM refusal.

### M2 — Suggestions + dialogue + gender

Heuristics, LLM router, review UI, apply/export reader EPUB. **Exit criterion:** a Polish novel chapter yields reviewable dialogue splits and gender tags.

### M3 — Voices + one backend

Voice ingest, OmniVoice adapter, preview play, GPU detect.

### M4 — Job engine

Chunker, checkpoint, pause/resume, progress metrics, Chatterbox + Qwen3-TTS adapters.

### M5 — M4B

Metadata editor, mux full and partial, ffmpeg packaging.

### M6 — Hardening and v1 release

ROCm path on Arch, Windows installer, docs, CI releases, license screens, sample book fixture tests.

Do not skip M2. Dialogue/gender is the reason v1 exists.

## 11. Risks

| Risk                           | Mitigation                                                                                                      |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| OmniVoice weights NC           | Default can stay OmniVoice for personal use; UI license gate; Chatterbox/Qwen as fully permissive alternatives. |
| Mid-paragraph dialogue quality | Heuristic-first + human review; never auto-apply low-confidence splits.                                         |
| ROCm fragility                 | Document tested PyTorch/ROCm pins; CPU fallback.                                                                |
| VRAM tables wrong              | Conservative defaults + user override + admission control.                                                      |
| Calibre GPL                    | External binary only.                                                                                           |
| Cloud cost / privacy           | Local default; explicit enable; chunked context.                                                                |
| Plugin API churn               | Freeze a tiny Protocol in M3 before adding backend 2 and 3.                                                     |

## 12. Success metrics (qualitative v1)

- Maintainer completes one full Polish novel on both reference PCs with mode `narrator_male_female`.
- Killing the app at 40% and restarting does not redo finished audio.
- A reviewer can reject a bad “Łoker” without re-running TTS for accepted chapters.
- A new contributor can add a TTS backend using only `docs/plugins.md`.

## 13. Glossary

- **Working EPUB** — normalized project copy.
- **Reader EPUB** — export after accepted suggestions.
- **Span** — tagged substring (narration, dialogue, …).
- **Suggestion** — proposed edit awaiting review.
- **Chunk** — unit of TTS audio.
- **RTF** — real-time factor; `< 1` means faster than playback.
- **Voice slot** — narrator / dialogue / male / female depending on mode.
