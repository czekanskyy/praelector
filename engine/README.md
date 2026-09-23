# praelector-engine

The Praelector sidecar: all product logic that does not need `torch`.

Frozen into the installer with PyInstaller (onedir) and launched by the Tauri
shell, which passes a per-launch bearer token through the environment and reads
the `PRAELECTOR_READY` line from stdout. See
[`../docs/architecture.md`](../docs/architecture.md).

```sh
uv sync --group dev          # from the repo root: uv sync --project engine --group dev
uv run pytest                # from this directory
uv run praelector-engine     # bind 127.0.0.1:0, print the ready line, serve
```

## Hard rules

- **No `torch`.** Not here, not transitively. `scripts/assert_no_torch.py` fails
  CI if the lockfile resolves it. Model inference belongs in `../engine-tts`.
- `api/` holds no logic beyond validation and delegation.
- `store/` is the only layer that touches disk or SQLite.
- `text/` is pure: text in, spans and suggestions out. No I/O, no network — that
  is what makes the golden tests cheap.
- `tts/` describes and supervises backends; it never imports one.
- Errors leave this process as **codes**, never as prose. User-facing strings
  live in `apps/ui/src/i18n/locales/**` (PLAN.md D-16).
- Logs go to **stderr**. stdout carries exactly one line: the ready handshake.
- Secrets are registered with the redaction filter in `logging.py` before use
  and are never logged (LM-03).

## Layout

`../docs/plan/REPO_LAYOUT.md` §5 is the authoritative module map.
