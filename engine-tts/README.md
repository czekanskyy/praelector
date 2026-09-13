# praelector-tts

TTS runtime worker for Praelector.

- Communicates with `praelector-engine` via **JSONL over stdio**
- Runs as an isolated worker process (one per parallel TTS slot)
- Isolates `torch` CUDA/ROCm execution and deterministic VRAM reclamation
- Includes built-in `fake` backend for torch-free integration testing and documentation.
