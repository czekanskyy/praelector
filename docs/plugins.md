# TTS plugins

The engine core never imports `torch`. A backend runs in `engine-tts`, one
worker process per admission slot. The engine speaks newline-delimited JSON on
the worker's stdin and stdout. Audio is a WAV on disk. The pipe carries paths
and metrics, not samples.

Stdout is the protocol. Logs go to stderr.

## Worker

```text
python -m praelector_tts --backend fake
```

The engine spawns this. `--backend` defaults to `fake`. The ids that resolve
today are `fake` and `omnivoice` (`praelector_tts.backends`).

Ops, in `praelector.tts.protocol`: `describe`, `load`, `synthesize`,
`probe_vram`, `unload`, `shutdown`. `describe` is the gate: languages, sample
rate, whether reference audio is required, and the params schema.

## Fake backend

`praelector_tts.backends.fake.FakeBackend` is the CI backend. It writes a sine
whose length is `len(text) / 14` seconds at 24 kHz. The same text is
byte-stable. No model, no network, no GPU.

The chunk tests drive it. A third-party backend is not required to exercise
pause, reuse, or mux.

## Adding a backend

1. Implement `TtsBackend` in `engine-tts/src/praelector_tts/backends/<id>.py`.
2. Add one `"<id>": "praelector_tts.backends.<id>:<Class>"` line to `_REGISTRY`
   in `backends/__init__.py`. Import the module only from that line, so
   `import praelector_tts` stays torch-free.
3. Keep `describe().capabilities.languages` honest. A project language that is
   not listed is refused before a worker starts.

Chatterbox and Qwen3-TTS are not registered yet.
