# praelector-tts

The TTS worker process. It loads a model, synthesises audio, and talks JSONL over
stdio. It knows nothing about projects, SQLite or HTTP — that is the engine's
job (PLAN.md D-05).

```sh
uv sync --project engine-tts --extra cpu --group dev   # or --extra cuda / rocm
uv run --project engine-tts praelector-tts-worker --backend fake
```

## Why a separate process

1. VRAM is released deterministically when the worker exits, which is what makes
   GPU admission control honest (GPU-05).
2. A CUDA/HIP OOM or driver fault kills one worker, not the app or the job.
3. The engine core stays torch-free, so CI can exercise the whole job engine
   with the `fake` backend.
4. Worker count is the scheduler's only knob (GPU-04).

## The extras

`cpu`, `cuda` and `rocm` are **mutually exclusive** (`[tool.uv] conflicts`). One
environment serves exactly one vendor; there is no union and no fat wheel. AMD's
device extras (`torch[device-gfx1200]`) are appended by the provisioner after it
detects the gfx target, so a gfx1201 user is not forced onto gfx1200 kernels.
`rocm` is Linux-only: PyTorch publishes no ROCm wheels for Windows (D-20).

Importing `praelector_tts` with **no** extra installed must succeed and expose the
`fake` backend. `tests/unit/test_no_torch.py` enforces that.

## Protocol

Wire format: `docs/plan/PLAN.md` §6.2. Typed models: `src/praelector_tts/protocol.py`.
One request in flight per worker; audio is written to disk by the worker and only
paths and metrics cross the pipe.

The protocol is frozen at the end of M3, before backends 2 and 3 are written.
Changing it after that is a breaking change and must be marked as one.
