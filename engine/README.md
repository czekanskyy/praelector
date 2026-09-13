# praelector-engine

Core sidecar process for Praelector.

- **FastAPI + Uvicorn** running on `127.0.0.1:<ephemeral>`
- Authenticated via `Authorization: Bearer <PRAELECTOR_TOKEN>`
- Origin-checked against `{tauri://localhost, http://localhost:1420}`
- **Strictly torch-free**: all torch / heavy neural inference dependencies live in `engine-tts` worker processes.
