# Praelector task runner. `just --list` prints the inventory.
# SPDX-License-Identifier: Apache-2.0
#
# Recipes stay shell-agnostic on purpose: CI runs them under bash on Linux and
# developers run them under cmd.exe on Windows, so each line is a single command
# invocation and anything needing real logic lives in scripts/*.py.

uv_py := "uv run --no-project python"
tts_extra := env_var_or_default("PRL_TTS_EXTRA", "cpu")
host_os := if os_family() == "windows" { "windows-x64" } else { "linux-x64" }

[private]
default:
    @just --list

# Install Python 3.12, the engine project, and the pnpm workspace.
setup:
    uv python install 3.12
    uv sync --project engine --group dev
    pnpm install --frozen-lockfile

# Install the TTS worker environment. Set PRL_TTS_EXTRA=rocm on Linux/AMD or
# =cuda for NVIDIA; the three extras are mutually exclusive (PLAN.md D-03).
setup-tts:
    uv sync --project engine-tts --extra {{tts_extra}} --group dev

# Engine + UI for browser-based development at http://localhost:1420.
dev:
    {{uv_py}} scripts/dev.py

# The full desktop app; Tauri spawns the engine itself.
dev-desktop:
    {{uv_py}} scripts/dev.py --desktop

# Only the engine sidecar; prints the PRAELECTOR_READY line and keeps serving.
dev-engine:
    {{uv_py}} scripts/dev.py --engine-only

test: test-engine test-ui

test-engine:
    cd engine && uv run pytest -m "not gpu"

test-ui:
    pnpm -F ui test -- --run

test-desktop:
    cargo test --manifest-path apps/desktop/Cargo.toml

lint:
    uv run --project engine ruff check .
    pnpm -F ui lint
    cargo fmt --manifest-path apps/desktop/Cargo.toml --check
    cargo clippy --manifest-path apps/desktop/Cargo.toml --all-targets -- -D warnings

format:
    uv run --project engine ruff format .
    uv run --project engine ruff check --fix .
    pnpm -F ui format
    cargo fmt --manifest-path apps/desktop/Cargo.toml

typecheck:
    cd engine && uv run mypy --strict src
    pnpm -F ui typecheck

codegen:
    uv run --project engine python scripts/gen_ts_types.py

codegen-check:
    uv run --project engine python scripts/gen_ts_types.py --check

# Regenerate the contract and fail if the committed copy was stale.
codegen-diff:
    uv run --project engine python scripts/gen_ts_types.py
    git diff --exit-code packages/schemas

i18n-check:
    node scripts/i18n_check.mjs

spdx-check:
    {{uv_py}} scripts/spdx_headers.py --check

spdx-fix:
    {{uv_py}} scripts/spdx_headers.py --fix

license-check:
    {{uv_py}} scripts/license_check.py --python engine --python engine-tts --node apps/ui

notice:
    {{uv_py}} scripts/license_check.py --python engine --python engine-tts --node apps/ui --write-notice

# The engine core lockfile must never resolve torch (PLAN.md D-03).
no-torch-check:
    {{uv_py}} scripts/assert_no_torch.py engine/uv.lock

fixtures:
    {{uv_py}} scripts/make_fixtures.py

# Everything the blocking CI workflows run, in one pass.
check: lint typecheck test spdx-check license-check no-torch-check i18n-check codegen-diff

build:
    pnpm -F ui build

# Compile and link the desktop app without producing installers.
build-desktop:
    {{uv_py}} scripts/build_engine.py --onedir
    pnpm tauri build --no-bundle

# Host-platform installers plus SHA256SUMS; release.yml does this per matrix target.
package:
    {{uv_py}} scripts/build_engine.py --onedir
    {{uv_py}} scripts/fetch_uv.py --verify
    pnpm tauri build
    {{uv_py}} scripts/make_portable.py --os {{host_os}}
    {{uv_py}} scripts/checksums.py dist

# Full-book pipeline with the fake backend; runs nightly (CI_AND_RELEASE.md §11).
nightly-fixture:
    cd engine && uv run pytest -m "full_book and not gpu"
