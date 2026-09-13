# Praelector

> _Prepare the page. Cast the voice._

Praelector is an Apache-2.0 local-first desktop application that turns DRM-free ebooks into multi-voice M4B audiobooks with a Polish lector-preparation workshop.

---

## Features

- **Local-First & Private:** Audio synthesis and text processing run on your hardware. No telemetry, no cloud lock-in.
- **Polish Lector Workshop:** Interactive review queue for dialogue segmentation, speaker gender detection, numeral expansion, foreign token pronunciation, and punctuation cleanup.
- **Multi-Voice Casting:** Support for single narrator, narrator + dialogue, and narrator + male/female dialogue casting.
- **TTS Backends:** OmniVoice (default high-quality multilingual), Chatterbox Multilingual (permissive MIT), and Qwen3-TTS.
- **GPU-Aware Engine:** Native support for NVIDIA CUDA and AMD ROCm with VRAM admission control, chunk checkpointing, and resume on crash/power loss.
- **M4B Audiobook Output:** M4B assembly with embedded cover art, chapter markers, and rich audiobook metadata via ffmpeg.

---

## Platform Support

| Platform | Architecture | Status | Notes |
| -------- | ------------ | ------ | ----- |
| **Windows 11** | x86_64 | **Supported** | First-class CUDA support; AMD ROCm on Windows is experimental / CPU fallback |
| **Linux** (e.g. CachyOS, Arch, Ubuntu) | x86_64 | **Supported** | First-class CUDA and ROCm support (e.g. RX 9060 XT gfx1200); AppImage & tarball |
| **macOS** | Apple Silicon / Intel | *Best-effort* | CI build validation only; not officially supported in v1 |

> [!NOTE]
> **Code Signing & SmartScreen:** Binaries in v1 are unsigned. Windows SmartScreen may display an "Unknown Publisher" warning on first launch. Verify release integrity against the published `SHA256SUMS`. Official signing is planned post-v1.

---

## Important Constraints

- **No DRM Circumvention:** Praelector strictly requires DRM-free ebooks. Files containing DRM encryption (`encryption.xml`, `sinf.xml`, etc.) will fail closed with an informative error.
- **No OCR:** Scanned PDF documents without extractable digital text layers are refused. Praelector is a lector workshop and synthesis tool, not an OCR engine.
- **Subscriptions are Not APIs:** ChatGPT Plus, Claude Pro, Gemini Advanced, and Cursor subscriptions do not grant API access. For cloud LLM suggestions, configure a supported API key (e.g. Groq, Google AI Studio, OpenRouter free tiers, OpenAI, Anthropic) or use a local LLM runner (Ollama, LM Studio).

---

## Quick Start for Developers

```bash
# Clone the repository
git clone https://github.com/czekanskyy/praelector.git
cd praelector

# Install frontend dependencies
pnpm install

# Setup Python virtual environments
uv sync --project engine --group dev
uv sync --project engine-tts --extra cpu --group dev

# Run test suites and linters
just test
just lint

# Start dev environment
just dev
```

For full setup guides and architecture documentation, see:
- [Development Setup](docs/dev-setup.md)
- [Architecture Overview](docs/architecture.md)
- [Architecture & Design Plan](docs/plan/PLAN.md)
- [Repository Layout](docs/plan/REPO_LAYOUT.md)
- [Data Model](docs/plan/DATA_MODEL.md)

---

## License

Praelector is licensed under the [Apache License, Version 2.0](LICENSE).
Third-party component attributions and licenses are listed in [NOTICE](NOTICE).
