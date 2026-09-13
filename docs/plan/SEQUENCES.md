# Praelector — Sequence Diagrams

Flows referenced by [PLAN.md](PLAN.md). Participants: **UI** (React), **Shell** (Tauri/Rust), **Engine** (FastAPI core), **Worker** (TTS process), **ffmpeg**, **LLM** (Ollama/LM Studio/cloud), **Calibre** (`ebook-convert`).

---

## 1. Startup and sidecar handshake

```mermaid
sequenceDiagram
    autonumber
    participant Shell
    participant Engine
    participant UI

    Shell->>Shell: generate 32-byte token
    Shell->>Engine: spawn (env PRAELECTOR_TOKEN, DATA_DIR, PARENT_PID), stdout piped
    Note over Shell: Windows: assign to kill-on-close Job Object<br/>Linux: own process group
    Engine->>Engine: bind 127.0.0.1:0, run migrations for app-level config
    Engine-->>Shell: stdout "PRAELECTOR_READY {port, pid, version, schema}"
    Shell->>UI: load WebView
    UI->>Shell: invoke engine_endpoint()
    Shell-->>UI: {base_url, token}
    UI->>Engine: GET /v1/health (Bearer)
    Engine-->>UI: {status:"ok", project_open:false}
    UI->>Engine: GET /v1/capabilities
    Engine-->>UI: {ffmpeg, calibre, keyring, runtime}
    loop every 5 s
        Shell->>Engine: GET /v1/health
    end
```

Failure branches: no READY line within 30 s, or three consecutive failed health polls, ⇒ kill, backoff, restart; more than five restarts in ten minutes ⇒ fatal panel with the last 200 log lines (PLAN §1.6).

---

## 2. Ingest (EB-01…EB-08)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant Calibre

    UI->>Engine: POST /v1/projects {name}
    Engine->>Engine: create project dir, project.json, project.db, acquire project.lock
    Engine-->>UI: {project_id}

    UI->>Engine: POST /v1/projects/{pid}/ingest/probe {path}
    Engine->>Engine: magic bytes + extension
    alt EPUB with DRM (EB-01, EB-02)
        Engine->>Engine: inspect META-INF/encryption.xml, sinf.xml
        Engine-->>UI: 422 ebook.drm_detected
    else PDF without a text layer (EB-04)
        Engine->>Engine: pypdf probe, first 5 pages
        Engine-->>UI: 422 ebook.no_text_layer
    else needs conversion (EB-03)
        Engine-->>UI: {needs_conversion:true, converter:"calibre", available:true|false}
    else EPUB, clean
        Engine-->>UI: {format:"epub", metadata_preview}
    end

    UI->>Engine: POST /v1/projects/{pid}/ingest {path, convert}
    Engine->>Engine: copy to source/original.<ext> (never mutated, EB-06)
    opt conversion requested
        Engine->>Calibre: ebook-convert original.pdf tmp/working.epub
        Calibre-->>Engine: exit code + stderr
    end
    Engine->>Engine: parse OPF/spine/TOC, extract metadata + cover (EB-05, EB-07)
    Engine->>Engine: XHTML -> blocks with source_ref (D-08)
    Engine->>Engine: fail closed if spine>3 and text<200 chars (EB-02)
    Engine->>Engine: front-matter heuristics -> skip spans (EB-08)
    Engine->>Engine: write source/working.epub, revision 0
    Engine-->>UI: {chapters:[…], warnings:[…]}
```

---

## 3. Preparation pipeline: heuristics then LLM (AI-01…AI-03, DG-01…DG-05)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant LLM

    UI->>Engine: POST /v1/projects/{pid}/jobs {kind:"prep"}
    Engine->>Engine: acquire the global job slot (D-14), state queued -> running, stage=plan
    Engine-->>UI: WS job.state {running, stage:"plan"}

    loop per chapter, per block
        Engine->>Engine: normalise (NFC, whitespace, soft hyphens, hyphenation joins)
        Engine->>Engine: dialogue state machine (paragraph-initial + mid-paragraph) DG-01/DG-02
        Engine->>Engine: gender ladder: verb suffix -> name lexicon -> pronouns -> speaker map DG-04
        Engine->>Engine: numerals, ordinals, acronyms, foreign tokens, toponyms, lexicon
        Engine-->>UI: WS suggestion.created (batched 10/s)
    end
    Engine-->>UI: WS prep.progress {stage:"heuristic", blocks_done, suggestions}

    Engine->>Engine: collect low-confidence items (split < 0.75, gender < 0.70)
    alt cloud profile required but project toggle off (LM-05, NF-02)
        Engine-->>UI: WS job.warning llm.cloud_disabled, continue local-only
    else
        loop per item, bounded context = block ± 1, cap 1200 chars/side (AI-03)
            Engine->>LLM: chat completion, JSON schema response format
            LLM-->>Engine: JSON
            alt schema valid
                Engine->>Engine: suggestion detector="llm"
            else invalid
                Engine->>LLM: retry once with the validation error
                LLM-->>Engine: JSON
                Engine->>Engine: still invalid -> status="failed", error_code (D-15)
            end
            opt 429 / 5xx
                Engine-->>UI: WS job.warning llm.provider_unavailable {local_profile_available:true}
            end
        end
    end
    Engine->>Engine: state -> done, release the job slot
    Engine-->>UI: WS job.state {done}
```

---

## 4. Review and apply (AI-04…AI-07, EX-01)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine

    UI->>Engine: GET /v1/projects/{pid}/suggestions?category=dialogue_split&status=pending
    Engine-->>UI: page of suggestions with context windows
    UI->>Engine: PATCH /v1/suggestions/{sid} {status:"edited", proposed:"Łoker"}
    UI->>Engine: POST /v1/projects/{pid}/suggestions/bulk {filter:{category:"numeral"}, action:"accept"}
    Engine-->>UI: {batch_id, affected: 214}

    UI->>Engine: POST /v1/projects/{pid}/suggestions/apply
    Engine->>Engine: open revision R+1
    loop per block, suggestions sorted by start DESC
        Engine->>Engine: original still matches? else -> conflicts[]
        Engine->>Engine: pronunciation -> new span; artifact -> rewrite block.text + remap
        Engine->>Engine: dialogue_split -> retile spans; speaker_gender -> set gender
    end
    Engine->>Engine: close old block/span versions at R, insert new at R+1 (SCD-2)
    Engine->>Engine: project.current_revision = R+1
    Engine-->>UI: {revision:R+1, applied:214, conflicts:[]}
    Engine-->>UI: WS project.revision {revision:R+1}

    opt undo (AI-06)
        UI->>Engine: POST /v1/projects/{pid}/suggestions/undo {batch_id}
        Engine->>Engine: restore current_revision = R, mark batch reverted
    end

    UI->>Engine: POST /v1/projects/{pid}/export/epub {variant:"reader"}
    Engine->>Engine: write data-prl-* spans + prl-spans.json companion (EX-01)
    Engine-->>UI: {path:"reader/reader-2026-09-13.epub"}
```

---

## 5. Voice ingest and preview (TTS-04, TTS-09)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant ffmpeg
    participant Worker

    UI->>Engine: POST /v1/projects/{pid}/voices (multipart: sample.m4a, ref_text, slot)
    Engine->>ffmpeg: decode -> PCM16 mono
    Engine->>ffmpeg: silenceremove (trim)
    Engine->>ffmpeg: loudnorm pass 1 (measure) then pass 2 (apply target LUFS)
    Engine->>ffmpeg: resample to backend native rate, clamp to [min,max] seconds
    Engine->>Engine: write voices/<id>.wav, peaks json, content_hash
    Engine-->>UI: VoiceProfile

    UI->>Engine: POST /v1/projects/{pid}/tts/preview {block_id, slot}
    Engine->>Engine: check runtime provisioned, assets present, license acknowledged
    Engine->>Worker: spawn (runtime python, env device pin)
    Worker-->>Engine: {"event":"ready", device:"cuda:0", torch:"2.13.0+cu130"}
    Engine->>Worker: {"op":"load", device, precision, models_dir}
    Worker-->>Engine: {ok:true, load_ms}
    Engine->>Worker: {"op":"synthesize", text, language:"pl", voice{ref_audio, ref_text}, out_path}
    Worker->>Worker: write <out>.part
    Worker-->>Engine: {ok:true, duration_s, rtf, peak_vram_mib}
    Engine->>Engine: validate, rename to final
    Engine->>Worker: {"op":"shutdown"}
    Engine-->>UI: {audio_url, metrics}
```

---

## 6. Recording job with admission control, pause and resume (JB-01…JB-07, GPU-04, GPU-05)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant GPU as GPU probe
    participant W1 as Worker 1
    participant W2 as Worker 2

    UI->>Engine: POST /v1/projects/{pid}/jobs {kind:"record", options}
    Engine->>Engine: preflight: voices resolved, language in backend.capabilities.languages (D-17),<br/>runtime ready, ffmpeg present
    Engine->>Engine: plan: blocks -> spans -> sentences -> chunks, compute render_key each
    Engine->>Engine: write plan.jsonl; mark items whose chunk already exists as reused (JB-05)
    Engine->>GPU: sample total/free VRAM
    GPU-->>Engine: total 12288, free 11000
    Engine->>Engine: reserve = max(ceil(0.2*12288),1536) = 2458<br/>max_workers = max(1, floor((11000-2458)/3500)) = 2
    Engine-->>UI: WS job.state {running, stage:"synth"}, budget snapshot

    par worker 1
        Engine->>W1: spawn + load + synthesize(ordinal 403)
        W1-->>Engine: {duration_s, rtf, peak_vram_mib}
        Engine->>Engine: atomic rename + sidecar, append events.jsonl
        Engine-->>UI: WS job.chunk, job.progress (<= 4 Hz)
    and worker 2
        Engine->>W2: spawn + load + synthesize(ordinal 404)
        W2-->>Engine: {duration_s, rtf}
    end

    loop every 1 s
        Engine->>GPU: sample free VRAM
        Engine-->>UI: WS gpu.sample {vram_used, workers_active}
        alt free_now - reserve < peak_worker
            Engine->>Engine: admissions_paused = true (GPU-05), running workers finish
        else headroom restored for 3 samples
            Engine->>Engine: admissions_paused = false
        end
    end

    UI->>Engine: POST /v1/jobs/{jid}/pause
    Engine->>Engine: stop admitting; pause_mode=finish_current
    W1-->>Engine: final chunk result
    Engine->>W2: shutdown (discard .part)
    Engine->>Engine: write job.json atomically, state=paused (JB-03)

    Note over Engine: process killed / power loss
    Engine->>Engine: on open: job.state in {running,muxing} -> paused,<br/>paused_reason="crash_recovery" (JB-07)
    Engine->>Engine: reconcile chunk index from sidecars (D-02)

    UI->>Engine: POST /v1/jobs/{jid}/resume
    Engine->>Engine: re-plan at the current revision; reuse every matching render_key
    Engine-->>UI: WS job.progress {chunks_reused: 402}
```

Chunk invalidation on resume, illustrated:

```mermaid
flowchart LR
    edit["User edits one sentence<br/>in chapter 8"] --> rev["New revision R+1"]
    rev --> replan["Re-plan at R+1"]
    replan --> cmp{"render_key<br/>in chunk store?"}
    cmp -->|"yes, WAV + sidecar valid"| reuse["Reuse, no GPU work"]
    cmp -->|"no"| render["Synthesize"]
    cmp -->|"sidecar/size mismatch"| quarantine["Quarantine file, re-synthesize"]
```

---

## 7. Mux to M4B, full and partial (MX-01…MX-04)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant ffmpeg

    UI->>Engine: POST /v1/projects/{pid}/export/m4b {mode:"partial", job_id}
    Engine->>Engine: state -> muxing, stage=mux
    Engine->>Engine: for each included chapter, is every plan item rendered?
    alt mode=full and items missing
        Engine-->>UI: 422 export.incomplete {missing_chapters:[…]}
    else
        Engine->>Engine: omit incomplete chapters, write output/partial_report.json (MX-03)
    end

    loop per complete chapter
        Engine->>Engine: build a concat list: chunk WAVs + inter-sentence silence + pause spans
        Engine->>ffmpeg: concat demuxer -> output/chapters/<nnn>.wav (optional keep, MX-05)
        ffmpeg-->>Engine: ok
    end
    Engine->>Engine: build ffmetadata: [CHAPTER] TIMEBASE=1/1000 START/END title
    Engine->>ffmpeg: concat chapters + ffmetadata + cover<br/>-c:a aac -b:a 64k -ar 44100 -ac 1 -movflags +faststart
    ffmpeg-->>Engine: output/book.m4b
    Engine->>ffmpeg: ffprobe verification (duration, chapter count)
    Engine->>Engine: state -> done
    Engine-->>UI: WS job.state {done}, {path, duration_s, chapters}
```

---

## 8. TTS runtime provisioning (D-04, GPU-07)

```mermaid
sequenceDiagram
    autonumber
    participant UI
    participant Engine
    participant GPU as GPU probe
    participant uv as bundled uv
    participant HF as weights host

    UI->>Engine: GET /v1/runtime/flavours
    Engine->>GPU: detect vendors and driver
    GPU-->>Engine: nvidia present / amd present / none
    Engine-->>UI: [{cuda, recommended, download_mib}, {rocm, available:false, reason:"rocm_not_available_on_windows"}, {cpu}]

    UI->>Engine: POST /v1/runtime/provision {flavour:"rocm"}
    Engine->>Engine: resolve gfx target (gfx1200 for RX 9060 XT) -> device extra
    Engine->>uv: sync engine-tts --extra rocm --frozen into <dataDir>/runtimes/rocm-<lockhash>
    uv-->>Engine: progress lines
    Engine-->>UI: WS runtime.progress {phase:"download", bytes, total}
    Engine->>Engine: write runtime.json {flavour, torch, lock_hash, gfx_target}
    Engine-->>UI: WS runtime.progress {phase:"done"}

    UI->>Engine: POST /v1/tts/backends/omnivoice/license-ack {components:["weights"]}
    UI->>Engine: POST /v1/tts/backends/omnivoice/assets/download
    Engine->>HF: snapshot download, allow_patterns from the descriptor
    HF-->>Engine: files
    Engine->>Engine: verify sha256 per asset, write manifest.json
    Engine-->>UI: WS download.progress {sha256_ok:true}
```

---

## 9. End-to-end book flow

```mermaid
flowchart TB
    A["PDF* / MOBI / EPUB"] -->|"ebook-convert if needed"| B["working.epub"]
    B --> C["chapters + blocks + spans"]
    C --> D["heuristic pre-pass"]
    D --> E["LLM pass, bounded context"]
    E --> F["suggestion review: accept / reject / edit"]
    F --> G["apply -> new revision"]
    G --> H["reader.epub export"]
    G --> I["plan: sentences -> chunks -> render_key"]
    I --> J["scheduler under the VRAM budget"]
    J --> K["content-addressed chunk store"]
    K --> L["per-chapter concat"]
    L --> M["M4B + chapters + metadata + cover"]
    K -.->|"partial"| M
    style A stroke-dasharray: 4 4
```

`*` PDF only with a text layer; no OCR in v1 (EB-04).
