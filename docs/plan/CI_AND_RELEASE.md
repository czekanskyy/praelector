# Praelector — CI, Branch Rules and Release

Implements PRD §9 and NF-09/NF-10/NF-11. Workflow: **an agent opens a PR → a human reviews → merge when CI is green**. Nothing force-pushes `main`, nothing merges red, nothing commits secrets.

---

## 1. Workflow inventory

| File | Trigger | Runners | Blocking | Purpose |
| --- | --- | --- | --- | --- |
| `ci-engine.yml` | PR, push `main` | `ubuntu-latest`, `windows-latest` | yes | Python lint, types, tests |
| `ci-ui.yml` | PR, push `main` | `ubuntu-latest` | yes | ESLint, `tsc`, Vitest, i18n parity, schema staleness |
| `ci-desktop.yml` | PR, push `main` | `ubuntu-22.04`, `windows-latest`, `macos-14` | yes except macOS | `cargo fmt`/`clippy`, `tauri build --no-bundle` |
| `licenses.yml` | PR, push `main`, weekly | `ubuntu-latest` | yes | dependency license policy, `NOTICE` freshness, SPDX headers |
| `pr-title.yml` | `pull_request_target` (title events) | `ubuntu-latest` | yes | Conventional Commits on the PR title |
| `gitleaks.yml` | PR, push `main` | `ubuntu-latest` | yes | secret scan (LM-03) |
| `codeql.yml` | PR, weekly | `ubuntu-latest` | no | `python`, `javascript-typescript` |
| `release-please.yml` | push `main` | `ubuntu-latest` | n/a | maintains the release PR, tags on merge |
| `release.yml` | tag `v*` | matrix | n/a | builds installers, publishes a draft release |
| `nightly-fixture.yml` | schedule (daily) | `ubuntu-latest` | no | full-book fixture job with the `fake` backend |

All workflows set `permissions: contents: read` by default and elevate per job. Concurrency: `group: ${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true` for PR workflows only.

---

## 2. `ci-engine.yml`

```yaml
name: engine
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with: { enable-cache: true }
      - run: uv python install 3.12
      - run: uv sync --project engine --group dev --frozen
      - run: uv sync --project engine-tts --extra cpu --group dev --frozen
      - run: uv run --project engine ruff check .
      - run: uv run --project engine ruff format --check .
      - run: uv run --project engine mypy --strict src
      - name: no torch in the core lock
        run: uv run python scripts/assert_no_torch.py engine/uv.lock
      - uses: FedericoCarboni/setup-ffmpeg@v3      # real ffmpeg for mux tests
      - run: uv run --project engine pytest -m "not gpu" --cov=praelector --cov-report=xml
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: engine-test-output-${{ matrix.os }}, path: engine/.pytest_cache }
```

Rules:

- `--frozen` everywhere: a lockfile that needs updating is a failing build, not a silent resolve.
- `pytest -m "not gpu"`: GPU-marked tests exist for local runs on the two reference machines only; CI has no GPU.
- Coverage gates: ≥ 90 % on `praelector/text/**` and `praelector/jobs/**`, ≥ 80 % on `praelector/gpu/**` and `praelector/ebook/**` (these are the NF-08 modules). No global gate.
- `engine-tts` is installed with `--extra cpu` so the `fake` backend and worker protocol are exercised, but no CUDA/ROCm wheel is ever downloaded in CI.

---

## 3. `ci-ui.yml`

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm -F ui lint
      - run: pnpm -F ui typecheck            # tsc --noEmit
      - run: pnpm -F ui test -- --run        # vitest
      - run: node scripts/i18n_check.mjs     # IX-01 / IX-02
      - name: schemas are not stale
        run: uv run python scripts/gen_ts_types.py && git diff --exit-code packages/schemas
```

`scripts/i18n_check.mjs` fails when:

1. any key exists in `en` but not in `pl`, or vice versa (IX-01 demands 100 % Polish);
2. any key is unused across `apps/ui/src` (dead strings rot);
3. `i18next-parser` finds a translatable literal outside the catalogues. The ESLint rule `no-literal-string` on `src/**/*.tsx` is the first line of defence (IX-02).

---

## 4. `ci-desktop.yml`

```yaml
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - { os: ubuntu-22.04,   required: true }
          - { os: windows-latest, required: true }
          - { os: macos-14,       required: false }   # D-23, best effort
    runs-on: ${{ matrix.os }}
    continue-on-error: ${{ !matrix.required }}
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with: { components: rustfmt, clippy }
      - uses: swatinem/rust-cache@v2
      - name: linux webkit deps
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: cargo fmt --manifest-path apps/desktop/Cargo.toml --check
      - run: cargo clippy --manifest-path apps/desktop/Cargo.toml -- -D warnings
      - run: pnpm tauri build --no-bundle       # compile + link only; bundling happens in release.yml
```

`ubuntu-22.04` is pinned deliberately: it fixes the glibc floor at 2.35 for the AppImage, which is what makes the artifact usable on CachyOS and on older distros. macOS is `continue-on-error` and produces no artifact.

---

## 5. `licenses.yml` (NF-03)

```yaml
jobs:
  policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --project engine --frozen
      - run: uv run python scripts/license_check.py --python engine --python engine-tts --node apps/ui
      - run: uv run python scripts/spdx_headers.py --check
      - name: NOTICE is current
        run: uv run python scripts/license_check.py --write-notice && git diff --exit-code NOTICE
```

`scripts/license_check.py` policy:

| Class | SPDX examples | Action |
| --- | --- | --- |
| allow | `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `PSF-2.0`, `MPL-2.0`, `Unlicense`, `CC0-1.0` | pass |
| review | `LGPL-2.1`, `LGPL-3.0`, `EPL-2.0`, unknown/missing metadata | fail unless the package is in `scripts/license_allowlist.toml` with a written justification |
| deny | `GPL-2.0`, `GPL-3.0`, **`AGPL-3.0`**, `SSPL`, `BUSL`, `CC-BY-NC-*`, "commercial" | fail, no allowlist |

The deny list is what stops EbookLib (AGPL-3.0) from being reintroduced by a well-meaning agent ([D-01](PLAN.md#d-01-no-ebooklib-hand-rolled-epub-readerwriter)). Model weight licenses are **not** dependency metadata; they live in backend descriptors and are checked by a separate unit test asserting every descriptor has a complete `licenses[]` array with a valid SPDX id or an explicit `LicenseRef-` id.

---

## 6. `pr-title.yml` and commit conventions (NF-09)

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: amannn/action-semantic-pull-request@v5
        env: { GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
        with:
          types: feat,fix,perf,refactor,docs,test,build,ci,chore,revert
          scopes: engine,engine-tts,ui,desktop,ebook,text,llm,tts,gpu,jobs,mux,store,docs,ci,deps
          requireScope: false
          subjectPattern: ^(?![A-Z]).+[^.]$
```

Because `main` allows squash-merge only, the PR title becomes the commit message, which is what release-please reads. Breaking changes use `!` plus a `BREAKING CHANGE:` footer. A PR that changes `render_key` inputs, the TTS plugin protocol or the project directory schema **must** be marked breaking (see [DATA_MODEL.md §14](DATA_MODEL.md#14-schema-versioning-and-migrations)).

PR template checklist:

```markdown
- [ ] Requirement IDs implemented or touched: <!-- e.g. DG-02, JB-05 -->
- [ ] Tests added or updated (unit / golden / integration)
- [ ] Docs updated (docs/**, or "n/a")
- [ ] No new dependency, or: license is on the allow list and NOTICE regenerated
- [ ] No change to render_key inputs / plugin protocol / project schema, or marked breaking
- [ ] Strings go through i18next and both en and pl catalogues are updated
```

---

## 7. Branch protection on `main`

Documented settings (PRD §9: "no direct push to `main`"):

- Require a pull request before merging; **1 approving review**; dismiss stale approvals on new commits.
- Required status checks (strict, branch must be up to date):
  `engine (ubuntu-latest)`, `engine (windows-latest)`, `ui`, `desktop (ubuntu-22.04)`, `desktop (windows-latest)`, `licenses`, `pr-title`, `gitleaks`.
  `desktop (macos-14)` and `codeql` are **not** required.
- Require conversation resolution before merging.
- Require linear history; allow **squash merge only** (merge commits and rebase merges disabled).
- Block force pushes and deletions. No bypass for administrators during v1.
- Automation tokens (`GITHUB_TOKEN`, agent PATs) get `contents: write` on branches only, never on `main`.

Allowed automation: coding agents pushing feature branches and opening PRs, `release-please`, `dependabot`, `labeler`.
Forbidden: force-pushing `main`, merging without CI, committing secrets, auto-merging any PR.

---

## 8. Versioning and changelog

Single product version across all three workspaces, kept in step by `release-please`'s linked-versions plugin:

```jsonc
// release-please-config.json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "simple",
  "include-component-in-tag": false,
  "changelog-sections": [
    { "type": "feat",     "section": "Features" },
    { "type": "fix",      "section": "Bug Fixes" },
    { "type": "perf",     "section": "Performance" },
    { "type": "refactor", "section": "Refactoring" },
    { "type": "docs",     "section": "Documentation" },
    { "type": "build",    "section": "Build and Packaging" },
    { "type": "deps",     "section": "Dependencies" }
  ],
  "packages": {
    ".":                { "release-type": "simple",  "changelog-path": "CHANGELOG.md" },
    "apps/ui":          { "release-type": "node",    "skip-github-release": true },
    "apps/desktop":     { "release-type": "rust",    "skip-github-release": true },
    "engine":           { "release-type": "python",  "skip-github-release": true },
    "engine-tts":       { "release-type": "python",  "skip-github-release": true }
  },
  "plugins": [{ "type": "linked-versions", "groupName": "praelector", "components":
                ["apps/ui", "apps/desktop", "engine", "engine-tts"] }]
}
```

`apps/desktop/tauri.conf.json` reads its version from `Cargo.toml`, so the installer, the UI About box and `GET /v1/version` always agree. Merging the release PR creates tag `vX.Y.Z`, which triggers `release.yml`.

---

## 9. `release.yml` (NF-11)

```yaml
name: release
on:
  push:
    tags: ['v*']
permissions:
  contents: write
jobs:
  bundle:
    strategy:
      fail-fast: false
      matrix:
        include:
          - { os: windows-latest, targets: 'nsis',     artifact: windows-x64 }
          - { os: ubuntu-22.04,   targets: 'appimage', artifact: linux-x64 }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: dtolnay/rust-toolchain@stable
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: freeze the engine            # PyInstaller onedir -> apps/desktop/resources/engine
        run: uv run python scripts/build_engine.py --onedir
      - name: bundle uv
        run: uv run python scripts/fetch_uv.py --verify
      - run: pnpm tauri build --bundles ${{ matrix.targets }}
      - name: portable archive
        run: uv run python scripts/make_portable.py --os ${{ matrix.artifact }}
      - name: checksums
        run: uv run python scripts/checksums.py dist/ > dist/SHA256SUMS.${{ matrix.artifact }}
      - uses: actions/upload-artifact@v4
        with: { name: ${{ matrix.artifact }}, path: dist/* }

  publish:
    needs: bundle
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
      - run: cat */SHA256SUMS.* > SHA256SUMS
      - uses: softprops/action-gh-release@v2
        with:
          draft: true                       # a human presses publish
          generate_release_notes: false     # release-please owns the notes
          files: |
            windows-x64/*
            linux-x64/*
            SHA256SUMS
```

Artifacts per release:

| Platform | Artifacts |
| --- | --- |
| Windows 11 x64 | `Praelector_X.Y.Z_x64-setup.exe` (NSIS), `Praelector_X.Y.Z_windows-x64_portable.zip` |
| Linux x64 | `Praelector_X.Y.Z_amd64.AppImage`, `Praelector_X.Y.Z_linux-x64.tar.gz` |
| both | `SHA256SUMS`, `CHANGELOG.md` excerpt in the release body |

What is **not** in the artifacts, and why:

- `torch` and the TTS runtime — provisioned on first use ([D-04](PLAN.md#d-04-two-tier-packaging-frozen-core--provisioned-tts-runtime)); keeps installers around 150 MB instead of 3+ GB and avoids shipping a vendor-exclusive stack.
- Model weights — downloaded with checksum and license acknowledgement (TTS-02).
- `ffmpeg` — resolved or fetched as an LGPL build ([D-06](PLAN.md#d-06-ffmpeg-for-all-audio-io-not-bundled)); avoids putting a GPL binary inside an Apache-2.0 installer.
- Calibre — never (NF-04).
- macOS anything ([D-23](PLAN.md#d-23-macos-is-ci-only)).

Signing ([D-24](PLAN.md#d-24-unsigned-binaries-in-v1)): v1 ships unsigned. The release body and README state that Windows SmartScreen will warn on first run and that `SHA256SUMS` is the verification path. Post-v1: Azure Trusted Signing for the NSIS installer; the Linux AppImage stays checksum-verified. No code depends on being signed, so enabling it later is a `release.yml` change only.

---

## 10. Dependabot and labels

```yaml
# .github/dependabot.yml
version: 2
updates:
  - { package-ecosystem: pip,            directory: /engine,       schedule: { interval: weekly }, open-pull-requests-limit: 5 }
  - { package-ecosystem: pip,            directory: /engine-tts,   schedule: { interval: monthly }, open-pull-requests-limit: 2 }
  - { package-ecosystem: npm,            directory: /,             schedule: { interval: weekly } }
  - { package-ecosystem: cargo,          directory: /apps/desktop, schedule: { interval: weekly } }
  - { package-ecosystem: github-actions, directory: /,             schedule: { interval: monthly } }
```

`engine-tts` is monthly and limited to 2 open PRs because every `torch` bump needs manual verification on both reference GPUs; those PRs are labelled `needs-gpu-verification` and are never merged from CI alone ([D-03](PLAN.md#d-03-uv-with-mutually-exclusive-cuda--rocm--cpu-extras)).

Labels: `area:engine`, `area:ui`, `area:desktop`, `area:docs`, `area:ci`, `milestone:M0`…`M6`, `blocker:v1`, `needs-gpu-verification`, `license-review`, `good-first-issue`.

---

## 11. Nightly fixture run

`nightly-fixture.yml` runs the whole pipeline headless on `epub3_polish_novel.epub` with the `fake` backend: ingest → heuristic prep (no LLM) → apply → plan → synthesize 300 chunks → pause → restart the engine → resume → partial mux → full mux → export reader EPUB. It asserts chunk reuse ≥ 95 % after resume and that `ffprobe` reports the expected chapter count and duration. Failures open an issue via `actions/github-script` rather than blocking PRs, so flakiness never wedges development but never goes unnoticed either.

---

## 12. Day-one repository checklist (PRD §9)

- [ ] `LICENSE` — Apache-2.0, unmodified
- [ ] `NOTICE` — generated, non-empty
- [ ] `CONTRIBUTING.md` — Conventional Commits, `just` targets, how to run both Python projects, how to add a TTS backend (links `docs/plugins.md`)
- [ ] `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1
- [ ] `SECURITY.md` — loopback-only threat model, token scheme, "no DRM circumvention", private reporting via GitHub Security Advisories, no telemetry (NF-05)
- [ ] `.github/ISSUE_TEMPLATE/*` and `PULL_REQUEST_TEMPLATE.md`
- [ ] `CHANGELOG.md` seeded, release-please config + manifest committed
- [ ] All nine workflows present, even if some jobs are stubs in PR 1
- [ ] Branch protection configured per §7 (manual, documented in `CONTRIBUTING.md`)
- [ ] `README.md` — name, tagline, the platform support table, "no DRM circumvention, no OCR", and the unsigned-binary note
