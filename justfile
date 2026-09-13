# Praelector Justfile
# Cross-platform development recipes

set shell := ["bash", "-c"]
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

# Start development mode (engine + UI + desktop)
dev:
    uv run python scripts/dev.py

# Run all test suites
test: test-engine test-tts test-ui

test-engine:
    uv run --project engine pytest -m "not gpu"

test-tts:
    uv run --project engine-tts pytest engine-tts/tests

test-ui:
    pnpm -F ui test -- --run

# Run all linters and code formatters
lint: lint-engine lint-tts lint-ui lint-desktop licenses

lint-engine:
    uv run --project engine ruff check .
    uv run --project engine ruff format --check .

lint-tts:
    uv run --project engine-tts ruff check .
    uv run --project engine-tts ruff format --check .

lint-ui:
    pnpm -F ui lint

lint-desktop:
    cargo fmt --manifest-path apps/desktop/Cargo.toml --check
    cargo clippy --manifest-path apps/desktop/Cargo.toml -- -D warnings

# Static type checking
check: check-engine check-ui

check-engine:
    uv run --project engine mypy --strict engine/src

check-ui:
    pnpm -F ui typecheck

# Code formatting
fmt:
    uv run --project engine ruff format .
    uv run --project engine ruff check --fix .
    pnpm -F ui lint --fix
    cargo fmt --manifest-path apps/desktop/Cargo.toml

# Codegen (Pydantic -> JSON Schema -> TypeScript)
codegen:
    uv run --project engine python scripts/gen_ts_types.py

# Dependency license policy check & NOTICE verification
licenses:
    uv run python scripts/license_check.py --python engine --python engine-tts --node apps/ui
    uv run python scripts/spdx_headers.py --check

# Build application
build: build-engine build-ui build-desktop

build-engine:
    uv run python scripts/build_engine.py --onedir

build-ui:
    pnpm -F ui build

build-desktop:
    pnpm tauri build --no-bundle
