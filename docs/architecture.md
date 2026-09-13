<!-- SPDX-License-Identifier: Apache-2.0 -->
# Praelector Architecture Overview

Praelector is an open-source, local-first desktop application designed to convert DRM-free ebooks into multi-voice audiobooks with professional Polish lector workshop rules.

---

## 1. Process Topology

```
┌────────────────────────────────────────────────────────┐
│               Tauri 2 Desktop Shell (Rust)             │
│  - WebView (React 19 + TypeScript + i18next)           │
│  - EngineSupervisor (spawn, ready handshake, watchdog) │
└──────────────────────────┬─────────────────────────────┘
                           │ Loopback HTTP + WS
                           │ (Bearer Token, 127.0.0.1:ephemeral)
┌──────────────────────────▼─────────────────────────────┐
│             praelector-engine (Python 3.12)            │
│  - FastAPI REST API & WebSocket event hub             │
│  - Ebook parsing (zipfile + lxml, no AGPL EbookLib)    │
│  - Polish linguistic pipeline & LLM assistance         │
│  - SQLite storage (project.db in WAL mode)             │
│  - Single writer of project directories               │
└──────────────────────────┬─────────────────────────────┘
                           │ JSONL over stdio
┌──────────────────────────▼─────────────────────────────┐
│          TTS Worker Processes (engine-tts)             │
│  - Short-lived worker pool (1 per parallel slot)       │
│  - PyTorch + model backends (OmniVoice, Chatterbox)   │
│  - Full VRAM release on process termination            │
└────────────────────────────────────────────────────────┘
```

---

## 2. Storage Architecture

Each Praelector project is an autonomous directory on the local filesystem:

```
<project_dir>/
├── project.json          # Manifest for quick Library listing without DB access
├── project.db            # SQLite database with Alembic migrations
├── project.lock          # Exclusive OS file lock (msvcrt / fcntl)
├── source/               # Original and working EPUBs
├── voices/               # Processed 24 kHz mono reference audio samples
├── audio/
│   ├── chunks/           # Content-addressed audio chunks (<rk[0:2]>/<render_key>.wav + .json)
│   └── quarantine/       # Corrupted / torn write chunk quarantine
├── jobs/                 # Crash-resilient job state & recovery records
└── output/               # Exported M4B audiobooks, covers, and reports
```

### Storage Principles
- **SQLite with WAL Mode**: Enables concurrent reader access and fast writes with `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;`.
- **Alembic Forward Migrations**: Programmatically applied whenever a project is opened to guarantee schema correctness.
- **Content-Addressable Audio**: Chunks are hashed using blake2s over text, voice profile, backend parameters, and model revisions.
- **Strict Single Writer**: An exclusive lock (`project.lock`) guarantees that only one process writes to `project.db` at any time.

---

## 3. Security Boundary & Privacy

- **Loopback Enforcement**: The engine sidecar binds exclusively to `127.0.0.1` on an OS-assigned ephemeral port.
- **Bearer Token Auth**: Tauri generates a 32-byte cryptographically secure random token passed via environment variable `PRAELECTOR_TOKEN`.
- **Origin Validation**: Loopback requests must originate from `tauri://localhost` or `http://localhost:1420`.
- **Secret Redaction (LM-03)**: API keys for LLM providers are stored in the OS credential manager (`keyring`) or encrypted local fallback and are never echoed over the API.
