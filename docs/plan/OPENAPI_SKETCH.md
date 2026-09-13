# Praelector — Sidecar API Sketch (v1)

Sketch, not generated code. The real spec is produced by FastAPI from the Pydantic models in `engine/src/praelector/domain/models.py` and served at `/v1/openapi.json`.

- Base URL: `http://127.0.0.1:<ephemeral>/v1` — NF-01
- Auth: `Authorization: Bearer <PRAELECTOR_TOKEN>` on every request including the WS handshake — [D-10](PLAN.md#d-10-bearer-token--origin-check-on-the-loopback-api)
- `Origin`, when present, must be `tauri://localhost` or `http://localhost:1420`
- Content type `application/json` except uploads (`multipart/form-data`) and audio downloads (`audio/wav`, `audio/mp4`)
- All timestamps are RFC 3339 UTC. All ids are prefixed ULIDs (`prj_…`, `chp_…`, `blk_…`, `spn_…`, `sug_…`, `vpr_…`, `job_…`)
- One project may be open at a time; project-scoped routes accept the id explicitly anyway so the UI never depends on hidden server state

## Error envelope

```jsonc
// HTTP 4xx/5xx
{
  "error": {
    "code": "ebook.drm_detected",       // stable, localised by the UI (D-16)
    "detail": { "encrypted_items": ["OEBPS/ch01.xhtml"] },
    "retryable": false,
    "trace_id": "01J8…"
  }
}
```

Code families: `auth.*`, `project.*`, `ebook.*`, `text.*`, `llm.*`, `voice.*`, `tts.*`, `runtime.*`, `gpu.*`, `job.*`, `audio.*`, `export.*`, `internal.*`.

Notable codes: `ebook.drm_detected` (EB-01), `ebook.no_text_layer` (EB-04), `ebook.calibre_missing` (EB-03), `ebook.empty_text` (EB-02), `llm.invalid_json` (AI-03), `llm.cloud_disabled` (LM-05/NF-02), `tts.language_unsupported` ([D-17](PLAN.md#d-17-qwen3-tts-ships-but-cannot-narrate-polish)), `tts.license_not_acknowledged` (TTS-02), `tts.voice_slot_missing` (TTS-06), `tts.oom`, `runtime.not_provisioned` (GPU-07), `gpu.insufficient_vram` (GPU-05), `job.already_active` ([D-14](PLAN.md#d-14-one-active-job-of-any-kind-per-app-instance)), `audio.ffmpeg_missing` (MX-04).

---

## 1. System

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/health` | `{status, uptime_s, project_open, active_job_id}`; polled by the supervisor every 5 s | §1.6 |
| GET | `/version` | `{app, engine, schema, python, platform}` | — |
| GET | `/capabilities` | probe results: `{ffmpeg:{path,version,filters_ok}, calibre:{path,version}, keyring:{backend}, runtime:{flavour,ready}}` | MX-04, EB-03 |
| POST | `/shutdown` | graceful: pause any job, checkpoint, close SQLite, exit 0 | §1.6 |

---

## 2. Settings

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/settings` | full settings tree, secrets replaced by `{"set": true}` | LM-03 |
| PUT | `/settings` | partial update (JSON merge patch semantics) | — |
| GET | `/settings/llm-profiles` | list profiles | LM-01 |
| POST | `/settings/llm-profiles` | create | LM-01 |
| PATCH | `/settings/llm-profiles/{id}` | update; `api_key` writes go to the keyring and are never echoed | LM-03 |
| DELETE | `/settings/llm-profiles/{id}` | — | — |
| POST | `/settings/llm-profiles/{id}/test` | `{ok, latency_ms, models:[…], error?}` | LM-02 |
| GET | `/settings/task-routing` | `{classify_cheap, dialogue_hard, pronounce} → profile_id` | LM-04 |
| PUT | `/settings/task-routing` | — | LM-04 |
| PUT | `/settings/gpu-policy` | `{device_index, reserve_mib?, peak_worker_mib_overrides{}, worker_cap, allow_cpu}` | GPU-03, GPU-04 |
| PUT | `/settings/audio` | `{output_sample_rate, output_bitrate_kbps, target_lufs, inter_sentence_silence_ms, crossfade_ms}` | TTS-05, TTS-08 |

`LlmProfile`:

```jsonc
{
  "id": "llm_local_ollama",
  "kind": "openai_compatible",         // openai_compatible | openai | anthropic | gemini
  "preset": "ollama",                  // ollama | lmstudio | openai | anthropic | gemini | xai | groq | openrouter | generic
  "base_url": "http://127.0.0.1:11434/v1",
  "model": "qwen2.5:14b-instruct",
  "is_cloud": false,                   // cloud requires the per-project toggle (LM-05, NF-02)
  "supports_json_schema": true,
  "timeout_s": 120,
  "max_tokens": 1024,
  "api_key": { "set": false }
}
```

---

## 3. Projects

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/projects` | scan `projects_dir` for `project.json` manifests | PRD §5.1 |
| POST | `/projects` | `{name, dir?}` → create directory + db; does not ingest | §5.2 |
| GET | `/projects/{pid}` | manifest + counts + `current_revision` + `active_job_id` | — |
| PATCH | `/projects/{pid}` | `{name?, voice_mode?, backend_id?, spoken_language?, cloud_llm_enabled?}` | TTS-03, LM-05 |
| POST | `/projects/{pid}/open` | acquire `project.lock`, run migrations, reconcile jobs | JB-07 |
| POST | `/projects/{pid}/close` | release lock | — |
| DELETE | `/projects/{pid}` | `?delete_files=true\|false` | — |
| GET | `/projects/{pid}/stats` | per-category suggestion counts, chapter/word/chunk totals | AI-11 |

---

## 4. Ingest and conversion

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| POST | `/projects/{pid}/ingest/probe` | `{path}` → `{format, needs_conversion, drm:{detected,reason?}, has_text_layer, metadata_preview}` — cheap, no writes | EB-01, EB-02, EB-04 |
| POST | `/projects/{pid}/ingest` | `{path, convert:{enabled, engine:"calibre"}}` → starts a short synchronous ingest (or a `prep`-kind job for large books); copies the original, converts, normalises, parses blocks, extracts cover/TOC, runs front-matter heuristics | EB-01…EB-08 |
| GET | `/projects/{pid}/source` | `{original_path, working_epub_path, imported_at, converter}` | EB-06 |

Refusals are HTTP 422 with `ebook.drm_detected` / `ebook.no_text_layer` / `ebook.empty_text`; `ebook.calibre_missing` carries `detail.install_hint_key` so the UI shows the right localised instructions per OS (EB-03).

---

## 5. Chapters, blocks, spans

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/chapters` | tree: `{id, ordinal, title, included, block_count, char_count, est_audio_s}` | ED-01 |
| PATCH | `/chapters/{cid}` | `{title?, included?}` | ED-01 |
| POST | `/projects/{pid}/chapters/reorder` | `{order:[cid,…]}` | ED-01 |
| POST | `/chapters/{cid}/split` | `{block_id, offset}` → two chapters | ED-01 |
| POST | `/projects/{pid}/chapters/merge` | `{ids:[cid,…]}` | ED-01 |
| GET | `/chapters/{cid}/text` | `?view=display\|spoken` → `{view, blocks:[{id, ordinal, kind, text}], text}` | ED-02, ED-06 |
| PUT | `/chapters/{cid}/text` | `{text, base_revision}` → re-splits blocks, re-associates identities, remaps spans, returns `{revision, orphaned_span_ids}` | ED-02, ED-07 |
| GET | `/chapters/{cid}/spans` | spans at the current revision | ED-03 |
| POST | `/chapters/{cid}/spans` | manual span: `{block_id, start, end, kind, gender?, speaker_id?, spoken?, pause_ms?}` | ED-04, ED-09 |
| PATCH | `/spans/{sid}` | — | ED-04, ED-09 |
| DELETE | `/spans/{sid}` | — | ED-09 |
| POST | `/projects/{pid}/search` | `{query, regex?, case_sensitive?, scope:"chapter"\|"book", chapter_id?}` → hits with block + offsets | ED-05 |
| POST | `/projects/{pid}/replace` | `{…search…, replacement, dry_run}` → `{count, preview[], revision?}` | ED-05 |

---

## 6. Suggestions, lexicon, revisions

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/suggestions` | filters `category[]`, `status[]`, `chapter_id`, `detector[]`, `min_confidence`, `q`; cursor pagination | AI-06 |
| GET | `/suggestions/{sid}` | one suggestion with its context window | AI-04 |
| PATCH | `/suggestions/{sid}` | `{status:"accepted"\|"rejected"\|"edited", proposed?}` — `edited` requires `proposed` | AI-06 |
| POST | `/projects/{pid}/suggestions/bulk` | `{filter:{…}, action:"accept"\|"reject", limit?}` → `{batch_id, affected}` | AI-06 |
| POST | `/projects/{pid}/suggestions/undo` | `{batch_id}` → reverts statuses (and the revision if already applied) | AI-06 |
| POST | `/projects/{pid}/suggestions/apply` | `{filter?}` → applies accepted/edited suggestions, creates a new revision: `{revision, applied, skipped, conflicts[]}` | AI-07 |
| GET | `/projects/{pid}/revisions` | revision list with labels and batch ids | AI-07 |
| POST | `/projects/{pid}/revisions/{n}/restore` | set `current_revision` back (no data loss; SCD-2) | AI-06, AI-07 |
| GET | `/lexicon` · PUT `/lexicon` | global pronunciation lexicon | AI-09 |
| GET | `/projects/{pid}/lexicon` · PUT | project lexicon (overrides global) | AI-09 |

`Suggestion`:

```jsonc
{
  "id": "sug_01J8…",
  "category": "dialogue_split",       // 9 categories, PRD §6.3.1
  "chapter_id": "chp_…",
  "block_id": "blk_…",
  "range": { "start": 42, "end": 71 },
  "original": "Walker wzruszył ramionami. — A jednak spróbujemy — mruknął",
  "proposed": null,                    // null for structural suggestions; payload carries the split
  "payload": { "segments": [ {"kind":"narration","start":0,"end":26},
                             {"kind":"dialogue","start":29,"end":50,"gender":"male"},
                             {"kind":"narration","start":53,"end":61} ] },
  "rationale": "dash followed by verb of saying",
  "confidence": 0.9,
  "detector": "heuristic",             // heuristic | llm | dict
  "status": "pending",                 // pending | accepted | rejected | edited | failed (D-15)
  "error_code": null,
  "prompt_version": null,
  "created_at": "2026-09-13T11:00:00Z",
  "applied_in_revision": null
}
```

---

## 7. Voices and TTS backends

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/tts/backends` | descriptors for all registered backends (capabilities, params schema, licenses, assets, vram profile) | TTS-01, TTS-05 |
| GET | `/tts/backends/{bid}` | one descriptor | TTS-01 |
| POST | `/tts/backends/{bid}/license-ack` | `{components:["weights"], accepted:true}` — required before download when `acknowledgement_required` | TTS-02, NF-03 |
| POST | `/tts/backends/{bid}/assets/download` | starts an asset download job; progress on WS `download.progress`; sha256 verified | TTS-02 |
| GET | `/tts/backends/{bid}/assets` | per-asset `{present, bytes, sha256_ok}` | TTS-02 |
| POST | `/projects/{pid}/voices` | multipart upload → runs the ingest chain → `VoiceProfile` | TTS-04 |
| GET | `/projects/{pid}/voices` | list | TTS-04 |
| PATCH | `/voices/{vpr}` | `{name?, slot?, ref_text?, trim?, target_lufs?}`; re-runs the chain and bumps `content_hash` | TTS-04, JB-05 |
| DELETE | `/voices/{vpr}` | — | — |
| GET | `/voices/{vpr}/audio` | `audio/wav` processed reference | TTS-04 |
| GET | `/voices/{vpr}/peaks` | waveform peaks for the preview widget | TTS-04 |
| PUT | `/projects/{pid}/voice-assignment` | `{mode, slots:{narrator:vpr, male:vpr, female:vpr}, params:{…}}` → `{warnings:["slot_missing_female"]}` | TTS-03, TTS-06 |
| POST | `/projects/{pid}/tts/preview` | `{text?, block_id?, slot, backend_id?, params?}` → spawns one worker, returns `{audio_url, metrics}` | TTS-09 |

---

## 8. Runtime and GPU

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/runtime/status` | `{flavour, ready, python, torch, lock_hash, gfx_target, mismatch_reason?}` | GPU-07 |
| GET | `/runtime/flavours` | `[{id:"cuda", recommended:true, download_mib:2600, reason:"NVIDIA GPU detected"}, {id:"rocm", available:false, reason:"rocm_not_available_on_windows"}, {id:"cpu", …}]` | GPU-07, GPU-08, [D-20](PLAN.md#d-20-windows--amd-rocm-is-best-effort) |
| POST | `/runtime/provision` | `{flavour}` → starts the locked `uv` install; progress on WS `runtime.progress` | [D-04](PLAN.md#d-04-two-tier-packaging-frozen-core--provisioned-tts-runtime) |
| DELETE | `/runtime/{flavour}` | remove a provisioned runtime | — |
| GET | `/gpu/devices` | `[{index, vendor, name, driver, memory_total_mib, memory_free_mib, available, reason?}]` plus a `cpu` pseudo-device | GPU-01, GPU-02, GPU-06 |
| GET | `/gpu/budget` | `?backend_id=&precision=&device_index=` → the full `GpuBudget` object (see [DATA_MODEL.md](DATA_MODEL.md)) | GPU-03, GPU-04 |
| GET | `/gpu/vram-table` · PUT | per-backend peak table with `measured` flags and user overrides | GPU-03 |

---

## 9. Jobs

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| POST | `/projects/{pid}/jobs` | `{kind:"prep"\|"record", options:{…}}` → 201 `Job`, or 409 `job.already_active` | AI-01, JB-06, D-14 |
| GET | `/projects/{pid}/jobs` | history, newest first | JB-04 |
| GET | `/jobs/{jid}` | full job: state, stage, counts, metrics, budget, warnings | UI-01…UI-06 |
| GET | `/jobs/{jid}/plan` | paginated plan items with reuse flags | JB-05 |
| GET | `/jobs/{jid}/events?since=<seq>` | replay for WS gap-fill | §8.1 |
| POST | `/jobs/{jid}/pause` | JB-03 |
| POST | `/jobs/{jid}/resume` | re-plans, reuses matching chunks | JB-05 |
| POST | `/jobs/{jid}/cancel` | keeps finished chunks | JB-04 |
| POST | `/jobs/{jid}/reset` | `{delete_audio:false}` — deleting audio requires an explicit `true` | JB-04 |
| GET | `/jobs/{jid}/logs?tail=500` | text log tail | — |

`POST /projects/{pid}/jobs` record options:

```jsonc
{
  "kind": "record",
  "options": {
    "chapter_ids": null,                    // null = all included chapters
    "backend_id": "omnivoice",
    "precision": "fp16",
    "device_index": 0,
    "auto_mux": true,
    "apply_high_confidence_structure": false,  // dialogue splits >= 0.75 only (PLAN §5.2)
    "pause_mode": "finish_current"          // finish_current | discard_current (JB-03)
  }
}
```

`Job` response (abridged):

```jsonc
{
  "id": "job_01J8…",
  "kind": "record",
  "state": "running",                       // JB-01 set exactly
  "stage": "synth",                         // plan | synth | mux (UI-01)
  "paused_reason": null,                    // e.g. "crash_recovery" (JB-07)
  "counts": { "chunks_total": 4180, "chunks_done": 1655, "chunks_reused": 402,
              "chunks_failed": 0, "chapters_total": 34, "chapters_done": 12 },
  "current": { "chapter_id": "chp_…", "chapter_title": "Rozdział 8",
               "chunk_ordinal": 1656, "text_prefix": "Nie zdążymy…" },   // UI-02
  "metrics": { "rtf_instant": 0.31, "rtf_smoothed": 0.34, "throughput_audio_s_per_s": 2.9,
               "chars_per_audio_s": 13.8, "eta_s": 5230, "elapsed_s": 4120 },  // UI-04, UI-05
  "budget": { "device_index": 0, "workers_active": 2, "workers_max": 2,
              "vram_used_mib": 7100, "vram_budget_mib": 8542, "admissions_paused": false },  // UI-06
  "warnings": [ { "code": "tts.voice_slot_fallback", "detail": { "slot": "female" } } ]      // TTS-06
}
```

---

## 10. Export

| Method | Path | Purpose | Req |
| --- | --- | --- | --- |
| GET | `/projects/{pid}/metadata` · PUT | title, authors[], narrator, year, description, language, publisher, isbn, series | MX-02 |
| POST | `/projects/{pid}/cover` | multipart image → `output/cover.jpg` (re-encoded, max 2000 px) | MX-02 |
| GET | `/projects/{pid}/cover` | image bytes | MX-02 |
| POST | `/projects/{pid}/export/epub` | `{variant:"reader"\|"clean", path?}` → `{path}` | EX-01, EX-02, EX-03 |
| POST | `/projects/{pid}/export/m4b` | `{mode:"full"\|"partial", job_id?, keep_chapter_files?}` → starts a `mux`-stage job; 422 `export.incomplete` if `full` and chunks are missing | MX-01, MX-03, MX-05 |
| GET | `/projects/{pid}/export/m4b/report` | `partial_report.json` — omitted chapters and why | MX-03 |

---

## 11. WebSocket

`GET /v1/ws` (bearer token in the handshake header). One connection per app. Server → client only, except `{"op":"subscribe","topics":[…]}` and `{"op":"ping"}`.

Envelope:

```jsonc
{ "v": 1, "seq": 10432, "ts": "2026-09-13T11:02:03.123Z",
  "type": "job.progress", "job_id": "job_…", "payload": { … } }
```

`seq` is monotonic per job event log; on reconnect the client calls `GET /jobs/{jid}/events?since=<last_seq>` and replays, so no event is lost (§8.1).

| Type | Payload | Rate | Req |
| --- | --- | --- | --- |
| `job.state` | `{state, stage, paused_reason?}` | on change | JB-01, UI-01 |
| `job.progress` | counts + current + metrics (same shape as `Job`) | ≤ 4 Hz | UI-02…UI-05 |
| `job.chunk` | `{ordinal, render_key, reused, duration_s, rtf, worker_id}` | per chunk | UI-03 |
| `job.warning` | `{code, detail}` | on occurrence | TTS-06 |
| `job.log` | `{level, message_code, detail}` | throttled | — |
| `gpu.sample` | `{device_index, vram_used_mib, vram_free_mib, workers_active, admissions_paused}` | 1 Hz | GPU-02, UI-06 |
| `suggestion.created` | `{suggestion_id, category, chapter_id}` | batched 10/s | AI-01 |
| `prep.progress` | `{stage:"heuristic"\|"llm", blocks_done, blocks_total, suggestions}` | ≤ 4 Hz | AI-01 |
| `download.progress` | `{backend_id, asset, bytes, total, sha256_ok?}` | ≤ 2 Hz | TTS-02 |
| `runtime.progress` | `{flavour, phase, bytes?, total?, log_line?}` | ≤ 2 Hz | D-04 |
| `project.revision` | `{revision, reason}` | on change | AI-07 |
| `error` | the standard error envelope | on occurrence | D-16 |

---

## 12. Route-to-requirement coverage

| Requirement block | Routes |
| --- | --- |
| EB-01…EB-09 | `/ingest/probe`, `/ingest`, `/source` |
| ED-01…ED-09 | `/chapters*`, `/chapters/{cid}/text`, `/spans*`, `/search`, `/replace` |
| AI-01…AI-11 | `/jobs` (kind=prep), `/suggestions*`, `/revisions*`, `/lexicon*`, `/stats` |
| DG-01…DG-06 | produced by the prep job; consumed via `/suggestions` (`dialogue_split`, `speaker_gender`) and `/spans` |
| LM-01…LM-07 | `/settings/llm-profiles*`, `/settings/task-routing` |
| TTS-01…TTS-09 | `/tts/backends*`, `/voices*`, `/voice-assignment`, `/tts/preview` |
| GPU-01…GPU-08 | `/gpu/*`, `/runtime/*` |
| JB-01…JB-07 | `/jobs/*` |
| UI-01…UI-07 | `GET /jobs/{jid}` + WS `job.*`, `gpu.sample` |
| MX-01…MX-05 | `/metadata`, `/cover`, `/export/m4b`, `/export/m4b/report` |
| EX-01…EX-03 | `/export/epub` |
| NF-01, NF-02 | bearer token + Origin check; `cloud_llm_enabled` on the project |
