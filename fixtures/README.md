# Fixtures

Cross-language sample inputs, referenced by engine tests, UI tests and the
nightly fixture run. Inventory and purpose: `docs/plan/REPO_LAYOUT.md` §9,
`docs/plan/PLAN.md` §10.

Anything that can be generated is generated — review the generator, not the
artifact:

```sh
uv run --no-project python scripts/make_fixtures.py          # write missing fixtures
uv run --no-project python scripts/make_fixtures.py --force  # rewrite everything
```

Generation is byte-deterministic (fixed zip ordering, fixed timestamps, fixed
seed) so regenerated fixtures never show up as spurious diffs.

## What is committed vs generated

| Path | Status |
| --- | --- |
| `books/epub2_minimal.epub`, `books/epub3_minimal.epub`, `books/epub3_polish_novel.epub` | committed copies, so tests run offline without a generation step |
| `books/drm_encrypted.epub`, `books/font_obfuscated.epub`, `books/empty_text.epub` | generated |
| `books/no_text_layer.pdf`, `books/text_layer.pdf` | committed binaries produced by an external tool; not generated |
| `audio/voice_sample.*`, `audio/voice_sample_silence_padded.wav` | generated (WAV via stdlib `wave`; the compressed variants need ffmpeg) |
| `text/pl_chapter_01.txt`, `text/pl_chapter_01.expected.json` | committed; the golden chapter from `PLAN.md` §10.1 |

`drm_encrypted.epub` must be refused (EB-01, EB-02). `font_obfuscated.epub` uses
IDPF font obfuscation and must **not** be refused — legitimate font obfuscation
is not DRM.
