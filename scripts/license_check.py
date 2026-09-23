#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dependency license policy (NF-03, CI_AND_RELEASE.md §5) and NOTICE generation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from email.parser import BytesParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOW_IDS = frozenset(
    {
        "apache-2.0",
        "mit",
        "bsd-2-clause",
        "bsd-3-clause",
        "isc",
        "psf-2.0",
        "mpl-2.0",
        "unlicense",
        "cc0-1.0",
    }
)

REVIEW_IDS = frozenset(
    {
        "lgpl-2.1",
        "lgpl-2.1-only",
        "lgpl-2.1-or-later",
        "lgpl-3.0",
        "lgpl-3.0-only",
        "lgpl-3.0-or-later",
        "epl-2.0",
    }
)

AGPL_HINT = (
    "AGPL-3.0 is denied; see docs/plan/PLAN.md D-01 (EbookLib was rejected for this reason)."
)

# Spoken forms that package metadata still emits instead of an SPDX id. Everything
# here normalises into ALLOW_IDS or REVIEW_IDS; anything unrecognised stays unknown
# and therefore lands in review, because guessing permissive is how a copyleft
# dependency slips into a release.
LICENSE_ALIASES: dict[str, str] = {
    "apache-2.0": "apache-2.0",
    "apache 2.0": "apache-2.0",
    "apache-2": "apache-2.0",
    "apache2": "apache-2.0",
    "apache software license": "apache-2.0",
    "apache license 2.0": "apache-2.0",
    "apache license, version 2.0": "apache-2.0",
    "asl 2.0": "apache-2.0",
    "mit": "mit",
    "mit license": "mit",
    "the mit license": "mit",
    "mit/x11": "mit",
    "expat": "mit",
    "x11": "mit",
    "bsd": "bsd-3-clause",
    "bsd-3": "bsd-3-clause",
    "bsd-3-clause": "bsd-3-clause",
    "new bsd license": "bsd-3-clause",
    "revised bsd": "bsd-3-clause",
    "bsd license": "bsd-3-clause",
    "bsd-2": "bsd-2-clause",
    "bsd-2-clause": "bsd-2-clause",
    "simplified bsd": "bsd-2-clause",
    "isc": "isc",
    "isc license": "isc",
    "isc license (iscl)": "isc",
    "psf-2.0": "psf-2.0",
    "psf": "psf-2.0",
    "python-2.0": "psf-2.0",
    "python software foundation": "psf-2.0",
    "python software foundation license": "psf-2.0",
    "mpl-2.0": "mpl-2.0",
    "mpl 2.0": "mpl-2.0",
    "mozilla public license": "mpl-2.0",
    "mozilla public license 2.0": "mpl-2.0",
    "unlicense": "unlicense",
    "the unlicense": "unlicense",
    "public domain": "unlicense",
    "cc0-1.0": "cc0-1.0",
    "cc0": "cc0-1.0",
    "creative commons zero": "cc0-1.0",
    "lgpl-2.1": "lgpl-2.1",
    "lgpl-2.1-only": "lgpl-2.1-only",
    "lgpl-2.1-or-later": "lgpl-2.1-or-later",
    "lgpl-2.1+": "lgpl-2.1-or-later",
    "lgplv2.1": "lgpl-2.1",
    "lgplv2": "lgpl-2.1",
    "lgpl-3.0": "lgpl-3.0",
    "lgpl-3.0-only": "lgpl-3.0-only",
    "lgpl-3.0-or-later": "lgpl-3.0-or-later",
    "lgpl-3.0+": "lgpl-3.0-or-later",
    "lgplv3": "lgpl-3.0",
    "lgpl": "lgpl-2.1",
    "epl-2.0": "epl-2.0",
    "epl 2.0": "epl-2.0",
    "eclipse public license 2.0": "epl-2.0",
}

# SPDX operators are always whitespace-separated, so splitting on bare `\bor\b`
# would shred ids like `LGPL-2.1-or-later`.
OPERATOR_RE = re.compile(r"\s+(?:and|or|with)\s+|\s*[(),]\s*")
WEAK_COPYLEFT_PREFIXES = ("lgpl", "epl-", "epl1", "epl2")

NO_ASSERTION = frozenset({"", "noassertion", "none", "unknown", "unspecified"})

# This repository's own distributions are Apache-2.0 by definition and would only
# add self-referential rows to the report. Editable installs are skipped separately,
# which is what actually catches them: names here are a belt-and-braces fallback.
OWN_PACKAGES = frozenset(
    {
        "praelector",
        "praelector-engine",
        "praelector_engine",
        "praelector-tts",
        "praelector_tts",
        "praelector-tts-engine",
        "@praelector/schemas",
        "ui",
        "desktop",
    }
)

CC_NC_RE = re.compile(r"cc[-_ ]?by[-_ ]?nc", re.IGNORECASE)
# The leading `[^a-z]` keeps `lgpl-2.1` out of the GPL match: LGPL is review class.
GPL_RE = re.compile(r"(?:^|[^a-z])gpl(?:[-_ ]?[23])?", re.IGNORECASE)
AGPL_RE = re.compile(r"agpl|affero", re.IGNORECASE)
DENY_SUBSTRINGS = ("sspl", "busl", "business source", "server side public license")
CLASSIFIER_RE = re.compile(r"^License\s*::\s*(.+)$", re.IGNORECASE)
# One pinned line of `uv export` output: name, optional extras, `==`, version with an
# optional local segment (`torch==2.12.0+rocm7.14.1`).
EXPORTED_REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9][A-Za-z0-9.+!_-]*)"
)
EXPORTED_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


class UsageError(RuntimeError):
    """A missing or unreadable input; reported as exit code 2."""


@dataclass(frozen=True)
class Component:
    project: str
    kind: str  # "python" | "node"
    name: str
    version: str
    license: str
    origin: str
    scope: str = (
        "runtime"  # "runtime" ships and reaches NOTICE; "dev" must still pass the deny list
    )


@dataclass(frozen=True)
class Assessment:
    klass: str  # "allow" | "review" | "deny"
    reason: str
    hint: str = ""
    allowlisted: bool = False
    justification: str = ""


@dataclass(frozen=True)
class AllowlistEntry:
    name: str
    license: str
    reason: str
    added: str


@dataclass(frozen=True)
class ProjectReport:
    label: str
    kind: str
    origin: str
    components: list[Component]


def canonical(license_id: str) -> str:
    key = " ".join(license_id.split()).strip().lower()
    return LICENSE_ALIASES.get(key, key)


def classify(raw: str) -> Assessment:
    """Return the policy class for one license string, failing closed."""
    text = " ".join(raw.split()).strip()
    if text.lower() in NO_ASSERTION:
        return Assessment("review", "no license metadata")

    lowered = text.lower()
    if "commercial" in lowered:
        return Assessment(
            "deny",
            "license text mentions a commercial restriction",
            "commercial terms are incompatible with an Apache-2.0 distribution",
        )
    if CC_NC_RE.search(lowered):
        return Assessment("deny", "CC-BY-NC non-commercial license")
    if any(marker in lowered for marker in DENY_SUBSTRINGS):
        return Assessment("deny", "SSPL / BUSL source-available license")
    if AGPL_RE.search(lowered):
        return Assessment("deny", "AGPL network copyleft", AGPL_HINT)
    if "gnu general public license" in lowered or GPL_RE.search(lowered):
        return Assessment("deny", "GPL copyleft")

    # A single id in prose form ("ISC License (ISCL)", "Apache Software License")
    # has to be matched whole before it is split into operands.
    whole = canonical(lowered)
    if whole in ALLOW_IDS:
        return Assessment("allow", "permissive license")

    operands = [part.strip() for part in OPERATOR_RE.split(lowered) if part.strip()]
    resolved = [canonical(part) for part in operands]

    review = sorted(
        {item for item in resolved if item in REVIEW_IDS or item.startswith(WEAK_COPYLEFT_PREFIXES)}
    )
    if review:
        return Assessment("review", f"weak copyleft: {', '.join(review)}")

    unknown = sorted({item for item in resolved if item not in ALLOW_IDS})
    if unknown:
        return Assessment("review", f"unrecognised license id: {', '.join(unknown)}")

    return Assessment("allow", "permissive license")


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    if not path.is_file():
        return []
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        raise UsageError(f"cannot read allowlist {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"cannot parse allowlist {path}: {exc}") from exc

    entries: list[AllowlistEntry] = []
    for index, raw in enumerate(data.get("allow", []), start=1):
        if not isinstance(raw, dict):
            raise UsageError(f"{path}: [[allow]] entry {index} is not a table")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise UsageError(f"{path}: [[allow]] entry {index} has no 'name'")
        missing = [key for key in ("license", "reason", "added") if not raw.get(key)]
        if missing:
            raise UsageError(f"{path}: entry {name!r} is missing {', '.join(missing)}")
        entries.append(
            AllowlistEntry(
                name=name,
                license=str(raw["license"]),
                reason=str(raw["reason"]),
                added=str(raw["added"]),
            )
        )
    return entries


def apply_allowlist(
    component: Component, assessment: Assessment, entries: Sequence[AllowlistEntry]
) -> Assessment:
    if assessment.klass != "review":
        return assessment

    resolved = canonical(component.license)
    for entry in entries:
        if entry.name.casefold() != component.name.casefold():
            continue
        pinned = canonical(entry.license)
        # A justification written for LGPL-2.1 must not silently cover an upgrade to
        # LGPL-3.0, so the license the reviewer recorded has to still be the one we
        # resolved.
        if pinned and pinned != resolved:
            print(
                f"warning: allowlist entry for {component.name} records "
                f"{entry.license!r} but the resolved license is "
                f"{component.license or 'unknown'!r}; update the entry",
                file=sys.stderr,
            )
            continue
        return replace(
            assessment,
            allowlisted=True,
            justification=entry.reason,
            hint=f"allowlisted {entry.added}: {entry.reason}",
        )

    return replace(
        assessment,
        hint=(
            "add an [[allow]] entry with a written justification to "
            "scripts/license_allowlist.toml, or replace the dependency"
        ),
    )


def _fold(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def classifier_license(segment: str) -> str:
    """Map the tail of a `Classifier: License ::` value onto an SPDX id."""
    tail = segment.strip().rsplit("::", 1)[-1].strip().lower()
    if "affero" in tail:
        return "AGPL-3.0"
    if "lesser general public license v2.1" in tail or "lgplv2.1" in tail:
        return "LGPL-2.1"
    if "lesser general public license v3" in tail or "lgplv3" in tail:
        return "LGPL-3.0"
    if "lesser general public license v2" in tail or "lgplv2" in tail:
        return "LGPL-2.1"
    if "lesser general public" in tail:
        return "LGPL-2.1"
    if "general public" in tail:
        return "GPL-3.0"
    if "eclipse" in tail:
        return "EPL-2.0"
    if "apache" in tail:
        return "Apache-2.0"
    if tail in {"mit license", "mit", "the mit license"}:
        return "MIT"
    if tail in {"isc license (iscl)", "isc license", "isc"}:
        return "ISC"
    if "python software foundation" in tail or tail == "psf":
        return "PSF-2.0"
    if "mozilla" in tail:
        return "MPL-2.0"
    if "bsd" in tail:
        return "BSD-3-Clause"
    if "public domain" in tail:
        return "Unlicense"
    if "cc0" in tail or "zero" in tail:
        return "CC0-1.0"
    if tail in {"zlib license", "zlib"}:
        return "Zlib"
    return ""


def parse_metadata(path: Path) -> tuple[str, str, str] | None:
    """Return (name, version, license) from a PEP 566 METADATA / PKG-INFO file."""
    try:
        with path.open("rb") as handle:
            message = BytesParser().parse(handle)
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return None

    name = _fold(message.get("Name"))
    version = _fold(message.get("Version"))
    if not name:
        return None

    expression = _fold(message.get("License-Expression"))
    if expression and expression.lower() not in NO_ASSERTION:
        return name, version, expression

    mapped: list[str] = []
    for value in message.get_all("Classifier") or []:
        match = CLASSIFIER_RE.match(_fold(value))
        if match is None:
            continue
        spdx = classifier_license(match.group(1))
        if spdx and spdx not in mapped:
            mapped.append(spdx)
    if mapped:
        # Several license classifiers mean dual licensing; "OR" is the honest reading
        # and both branches still have to pass the policy.
        return name, version, " OR ".join(mapped)

    declared = _fold(message.get("License"))
    # A pasted license body is not an identifier; reporting it as unknown beats
    # putting a paragraph into NOTICE.
    if declared and len(declared) <= 80:
        return name, version, declared
    return name, version, ""


def site_packages_dirs(project_dir: Path) -> list[Path]:
    found: list[Path] = []
    windows = project_dir / ".venv" / "Lib" / "site-packages"
    if windows.is_dir():
        found.append(windows)
    posix_lib = project_dir / ".venv" / "lib"
    if posix_lib.is_dir():
        found.extend(
            sorted(
                child / "site-packages"
                for child in posix_lib.glob("python3.*")
                if (child / "site-packages").is_dir()
            )
        )
    return found


def is_editable_install(dist_info: Path) -> bool:
    """True for a locally installed project, i.e. our own code rather than a dependency."""
    marker = dist_info / "direct_url.json"
    if not marker.is_file():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    directory = data.get("dir_info") if isinstance(data, dict) else None
    return bool(isinstance(directory, dict) and directory.get("editable"))


def normalize_name(name: str) -> str:
    """PEP 503 normalisation: `pydantic_core` and `pydantic-core` are one package."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def venv_metadata_map(project_dir: Path) -> dict[str, tuple[str, str, str]]:
    """normalised name -> (display name, version, license) for every installed dist."""
    own = {normalize_name(name) for name in OWN_PACKAGES}
    found: dict[str, tuple[str, str, str]] = {}
    for directory in site_packages_dirs(project_dir):
        for metadata in sorted(directory.glob("*.dist-info/METADATA")):
            if is_editable_install(metadata.parent):
                continue
            parsed = parse_metadata(metadata)
            if parsed is None:
                continue
            name, version, license_id = parsed
            key = normalize_name(name)
            if key in own or key in found:
                continue
            found[key] = (name, version, license_id)
    return found


def lock_license_map(project_dir: Path) -> dict[str, str]:
    """normalised name -> license from uv.lock. Usually empty: uv writes no license field."""
    lock = project_dir / "uv.lock"
    if not lock.is_file():
        return {}
    try:
        with lock.open("rb") as handle:
            data = tomllib.load(handle)
    except OSError as exc:
        print(f"warning: cannot read {lock}: {exc}", file=sys.stderr)
        return {}
    except tomllib.TOMLDecodeError as exc:
        print(f"warning: cannot parse {lock}: {exc}", file=sys.stderr)
        return {}

    licenses: dict[str, str] = {}
    for entry in data.get("package", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        license_id = entry.get("license")
        if isinstance(name, str) and isinstance(license_id, str) and license_id:
            licenses.setdefault(normalize_name(name), license_id)
    return licenses


def require_uv() -> str:
    uv = shutil.which("uv")
    if uv is None:
        raise UsageError(
            "uv is not on PATH. The shipped dependency set comes from `uv export`; "
            "this script refuses to derive it from an installed virtualenv instead, "
            "because a dev-synced .venv would attribute pytest and mypy to the product "
            "and omit the provisioned torch stack."
        )
    return uv


def run_uv_export(uv: str, root: Path, project_dir: Path, extra: str | None) -> str:
    relative = (
        project_dir.relative_to(root).as_posix()
        if project_dir.is_relative_to(root)
        else str(project_dir)
    )
    command = [
        uv,
        "export",
        "--project",
        relative,
        "--no-dev",
        "--no-emit-project",
        "--format",
        "requirements-txt",
        "--frozen",
    ]
    if extra:
        command += ["--extra", extra]
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise UsageError(
            f"`{' '.join(command[1:])}` failed with exit code {result.returncode}:\n  {detail}"
        )
    return result.stdout


def parse_requirements(text: str) -> list[tuple[str, str]]:
    """Parse `uv export` requirements-txt output into (name, version) pairs."""
    pairs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        # Continuation lines carry only --hash= arguments and "# via" annotations.
        if raw[:1].isspace():
            continue
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        line = line.split(";", 1)[0].strip().rstrip("\\").strip()
        match = EXPORTED_REQUIREMENT_RE.match(line)
        if match is not None:
            pairs.append((match.group(1), match.group(2)))
            continue
        # A direct-URL requirement (`name @ https://…`) still ships, so keep the name
        # with an unknown version rather than dropping it from NOTICE.
        named = EXPORTED_NAME_RE.match(line)
        if named is not None:
            pairs.append((named.group(1), ""))
    return pairs


def project_extras(project_dir: Path) -> list[str]:
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        # `uv export` runs first and would already have failed on a broken pyproject.
        return []
    extras = (data.get("project") or {}).get("optional-dependencies")
    if not isinstance(extras, dict):
        return []
    return sorted(key for key in extras if isinstance(key, str))


def runtime_requirements(
    uv: str, root: Path, project_dir: Path
) -> tuple[list[tuple[str, str]], list[str]]:
    """The shipped set: the base export unioned with one export per extra.

    A user can be provisioned with any flavour (D-03), so NOTICE has to attribute all
    of them; the same package pinned differently per extra legitimately appears once
    per version.
    """
    extras = project_extras(project_dir)
    pairs = parse_requirements(run_uv_export(uv, root, project_dir, None))
    for extra in extras:
        pairs.extend(parse_requirements(run_uv_export(uv, root, project_dir, extra)))

    unique: dict[tuple[str, str], str] = {}
    for name, version in pairs:
        unique.setdefault((normalize_name(name), version), name)
    ordered = sorted(unique.items(), key=lambda item: (item[0][0], item[1]))
    return [(display, version) for (_, version), display in ordered], extras


def collect_python(root: Path, project_dir: Path, label: str, require_venv: bool) -> ProjectReport:
    uv = require_uv()
    runtime, extras = runtime_requirements(uv, root, project_dir)
    installed = venv_metadata_map(project_dir)
    if require_venv and not installed:
        raise UsageError(
            f"--json-metadata was requested but {project_dir} has no installed packages; "
            f"run `uv sync --project {label}` first"
        )
    locked = lock_license_map(project_dir)

    components: list[Component] = []
    runtime_keys: set[str] = set()
    unresolved: list[str] = []
    for name, version in runtime:
        key = normalize_name(name)
        runtime_keys.add(key)
        meta = installed.get(key)
        if meta is not None and meta[2]:
            license_id, source = meta[2], ".venv METADATA"
        elif locked.get(key):
            license_id, source = locked[key], "uv.lock"
        else:
            license_id, source = "", "unresolved"
            unresolved.append(f"{name}=={version}" if version else name)
        components.append(
            Component(
                project=label,
                kind="python",
                name=name,
                version=version,
                license=license_id,
                origin=f"uv export; license: {source}",
                scope="runtime",
            )
        )

    # Dev-group packages are not shipped, so they never reach NOTICE, but a GPL dev
    # tool is still a policy problem and has to pass the deny list.
    for key, (name, version, license_id) in sorted(installed.items()):
        if key in runtime_keys:
            continue
        components.append(
            Component(
                project=label,
                kind="python",
                name=name,
                version=version,
                license=license_id,
                origin=".venv METADATA",
                scope="dev",
            )
        )

    if unresolved:
        print(
            f"warning: {label}: no license metadata for {len(unresolved)} shipped "
            f"package(s) — they are review class: {', '.join(unresolved[:8])}"
            + (" …" if len(unresolved) > 8 else "")
            + f". Sync the runtime environment (`uv sync --project {label}"
            + (f" --extra {extras[0]}" if extras else "")
            + "`) to resolve them.",
            file=sys.stderr,
        )

    flavour = f" +{len(extras)} extra(s)" if extras else ""
    return ProjectReport(label, "python", f"uv export --no-dev{flavour}", components)


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"warning: cannot parse {path}: {exc}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def resolve_node_package(name: str, project_dir: Path, root: Path) -> dict[str, object] | None:
    for candidate in (
        project_dir / "node_modules" / name / "package.json",
        root / "node_modules" / name / "package.json",
    ):
        data = _read_json(candidate)
        if data is not None:
            return data

    # pnpm stores the real payload under .pnpm and symlinks it into node_modules.
    encoded = name.replace("/", "+")
    store = root / "node_modules" / ".pnpm"
    if store.is_dir():
        for candidate in sorted(store.glob(f"{encoded}@*/node_modules/{name}/package.json")):
            data = _read_json(candidate)
            if data is not None:
                return data
    return None


def license_field(data: dict[str, object]) -> str:
    value = data.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        kind = value.get("type")
        return kind if isinstance(kind, str) else ""
    if isinstance(value, list):
        parts = [item for item in value if isinstance(item, str)]
        return " OR ".join(parts)
    return ""


def collect_node(project_dir: Path, label: str, root: Path) -> ProjectReport:
    manifest_path = project_dir / "package.json"
    manifest = _read_json(manifest_path)
    if manifest is None:
        print(
            f"warning: {manifest_path} is missing or unreadable; no components resolved",
            file=sys.stderr,
        )
        return ProjectReport(label, "node", "no metadata found", [])

    own = {name.casefold() for name in OWN_PACKAGES}
    # A package listed in both blocks ships, so "dependencies" is scanned first and
    # setdefault keeps the runtime scope.
    dependencies: dict[str, tuple[str, str]] = {}
    for field, scope in (("dependencies", "runtime"), ("devDependencies", "dev")):
        block = manifest.get(field)
        if isinstance(block, dict):
            for name, spec in block.items():
                dependencies.setdefault(name, (spec if isinstance(spec, str) else "", scope))

    components: list[Component] = []
    for name, (spec, scope) in dependencies.items():
        if name.casefold() in own or spec.startswith("workspace:"):
            continue
        installed = resolve_node_package(name, project_dir, root)
        if installed is None:
            # Not installed: the declared range is all we have, and the license is
            # unknown, which the policy treats as review.
            components.append(
                Component(label, "node", name, spec, "", "package.json (not installed)", scope)
            )
            continue
        raw_version = installed.get("version")
        components.append(
            Component(
                project=label,
                kind="node",
                name=name,
                version=raw_version if isinstance(raw_version, str) else spec,
                license=license_field(installed),
                origin="node_modules",
                scope=scope,
            )
        )
    return ProjectReport(label, "node", "package.json + node_modules", components)


def project_label(project_dir: Path, root: Path) -> str:
    try:
        return project_dir.resolve().relative_to(root).as_posix()
    except ValueError:
        return project_dir.name


def verdict_of(assessment: Assessment) -> str:
    if assessment.klass == "deny":
        return "DENY"
    if assessment.klass == "review":
        return "allowlisted" if assessment.allowlisted else "REVIEW"
    return "ok"


def render_scope_block(subset: Sequence[tuple[Component, Assessment]], indent: str) -> list[str]:
    name_w = max(len("PACKAGE"), *(len(c.name) for c, _ in subset))
    ver_w = max(len("VERSION"), *(len(c.version or "-") for c, _ in subset))
    lic_w = max(len("LICENSE"), *(len(c.license or "unknown") for c, _ in subset))
    lines = [
        f"{indent}{'PACKAGE'.ljust(name_w)}  {'VERSION'.ljust(ver_w)}  "
        f"{'LICENSE'.ljust(lic_w)}  CLASS   VERDICT"
    ]
    for component, assessment in subset:
        lines.append(
            f"{indent}{component.name.ljust(name_w)}  {(component.version or '-').ljust(ver_w)}  "
            f"{(component.license or 'unknown').ljust(lic_w)}  "
            f"{assessment.klass.ljust(6)}  {verdict_of(assessment)}"
        )
    return lines


def render_table(
    reports: Sequence[ProjectReport], rows: Sequence[tuple[Component, Assessment]]
) -> str:
    lines: list[str] = []
    for report in reports:
        lines.append(f"{report.label} ({report.kind}) — source: {report.origin}")
        subset = [(component, a) for component, a in rows if component.project == report.label]
        if not subset:
            lines.append("  (no third-party components resolved)")
            lines.append("")
            continue

        runtime = [(c, a) for c, a in subset if c.scope == "runtime"]
        dev = [(c, a) for c, a in subset if c.scope != "runtime"]
        lines.append(f"  runtime — {len(runtime)} shipped component(s)")
        lines.extend(render_scope_block(runtime, "    ") if runtime else ["    (none)"])
        if dev:
            lines.append(f"  dev — {len(dev)} installed component(s), not shipped")
            lines.extend(render_scope_block(dev, "    "))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def render_failures(rows: Iterable[tuple[Component, Assessment]]) -> list[str]:
    lines: list[str] = []
    for component, assessment in rows:
        scope = "" if component.scope == "runtime" else f" [{component.scope}]"
        lines.append(
            f"  {assessment.klass:6} {component.project}: {component.name} "
            f"{component.version or '-'} — {component.license or 'unknown'} "
            f"({assessment.reason}){scope}"
        )
        if assessment.hint:
            lines.append(f"         {assessment.hint}")
    return lines


def notice_body(reports: Sequence[ProjectReport]) -> str:
    header = (
        "Praelector\n"
        "Copyright 2026 The Praelector Authors\n"
        "\n"
        "This application is licensed under the Apache License, Version 2.0 (see\n"
        "LICENSE). The third-party components listed below are distributed with it\n"
        "and remain under their own licenses.\n"
        "\n"
        "Generated by `scripts/license_check.py --write-notice`; do not edit by hand.\n"
    )

    # Only what ships: dev-group packages are build tools and attributing them here
    # would misdescribe the product (and churn NOTICE on every dev dependency bump).
    shipped = {
        report.label: [c for c in report.components if c.scope == "runtime"] for report in reports
    }
    if not any(shipped.values()):
        return header + "\nNo third-party components resolved yet.\n"

    parts: list[str] = [header]
    for report in reports:
        components = shipped[report.label]
        if not components:
            continue
        heading = "Node" if report.kind == "node" else "Python"
        parts.append(f"\n## {heading} ({report.label})\n\n")
        for component in sorted(components, key=lambda c: (c.name.lower(), c.version)):
            parts.append(
                f"  {component.name} {component.version or 'unversioned'} "
                f"— {component.license or 'unknown'}\n"
            )
    return "".join(parts)


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="license_check.py",
        description=(
            "Apply the dependency license policy (allow / review / deny) and keep "
            "NOTICE in sync with the resolved dependency graph."
        ),
        epilog=(
            "exit codes: 0 policy satisfied, 1 deny or un-allowlisted review, "
            "2 usage or unreadable input. A project directory that does not exist "
            "yet is a warning, not a failure, so the job stays green from PR 1."
        ),
    )
    parser.add_argument(
        "--python",
        action="append",
        default=[],
        metavar="DIR",
        help="Python (uv) project directory to inspect; repeatable",
    )
    parser.add_argument(
        "--node",
        action="append",
        default=[],
        metavar="DIR",
        help="Node workspace package directory to inspect; repeatable",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: the parent of scripts/)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help="review-class allowlist (default: <root>/scripts/license_allowlist.toml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as JSON instead of a table",
    )
    parser.add_argument(
        "--json-metadata",
        action="store_true",
        help=(
            "require license metadata from <dir>/.venv/**/METADATA and fail if the "
            "virtual environment has not been synced. The component set always comes "
            "from `uv export --no-dev`; this flag only makes license resolution strict, "
            "since uv.lock carries no license field."
        ),
    )
    parser.add_argument(
        "--write-notice",
        action="store_true",
        help="regenerate NOTICE at the repository root (byte-stable output)",
    )
    parser.add_argument(
        "--notice",
        type=Path,
        default=None,
        help="NOTICE destination (default: <root>/NOTICE)",
    )
    return parser.parse_args(argv)


def collect_reports(args: argparse.Namespace, root: Path) -> list[ProjectReport]:
    requested: list[tuple[str, str]] = [(raw, "python") for raw in args.python] + [
        (raw, "node") for raw in args.node
    ]

    reports: list[ProjectReport] = []
    for raw, kind in requested:
        project_dir = Path(raw)
        if not project_dir.is_absolute():
            project_dir = root / project_dir
        label = project_label(project_dir, root)
        if not project_dir.is_dir():
            print(f"warning: {raw} does not exist yet; no components resolved", file=sys.stderr)
            reports.append(ProjectReport(label, kind, "project missing", []))
            continue
        if kind == "python":
            reports.append(collect_python(root, project_dir, label, args.json_metadata))
        else:
            reports.append(collect_node(project_dir, label, root))
    return reports


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2
    if not args.python and not args.node and not args.write_notice:
        print(
            "error: nothing to do; pass --python DIR, --node DIR or --write-notice",
            file=sys.stderr,
        )
        return 2

    allow_path: Path = (args.allowlist or (root / "scripts" / "license_allowlist.toml")).resolve()

    try:
        allowlist = load_allowlist(allow_path)
        reports = collect_reports(args, root)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rows: list[tuple[Component, Assessment]] = [
        (component, apply_allowlist(component, classify(component.license), allowlist))
        for report in reports
        for component in report.components
    ]
    failures = [
        (component, assessment)
        for component, assessment in rows
        if assessment.klass == "deny"
        or (assessment.klass == "review" and not assessment.allowlisted)
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "policy": {
                        "allow": sorted(ALLOW_IDS),
                        "review": sorted(REVIEW_IDS),
                        "deny": "GPL-2.0/3.0, AGPL-3.0, SSPL, BUSL, CC-BY-NC-*, commercial terms",
                    },
                    "projects": [
                        {
                            "name": report.label,
                            "kind": report.kind,
                            "origin": report.origin,
                            "components": len(report.components),
                            "runtime": sum(1 for c in report.components if c.scope == "runtime"),
                            "dev": sum(1 for c in report.components if c.scope != "runtime"),
                        }
                        for report in reports
                    ],
                    "components": [
                        {
                            "project": component.project,
                            "kind": component.kind,
                            "name": component.name,
                            "version": component.version,
                            "license": component.license,
                            "origin": component.origin,
                            "scope": component.scope,
                            "in_notice": component.scope == "runtime",
                            "class": assessment.klass,
                            "reason": assessment.reason,
                            "allowlisted": assessment.allowlisted,
                            "justification": assessment.justification,
                            "passed": verdict_of(assessment) in {"ok", "allowlisted"},
                        }
                        for component, assessment in rows
                    ],
                    "failures": [
                        {
                            "project": component.project,
                            "name": component.name,
                            "version": component.version,
                            "license": component.license,
                            "scope": component.scope,
                            "class": assessment.klass,
                            "reason": assessment.reason,
                            "hint": assessment.hint,
                        }
                        for component, assessment in failures
                    ],
                    "summary": {
                        "total": len(rows),
                        "runtime": sum(1 for c, _ in rows if c.scope == "runtime"),
                        "dev": sum(1 for c, _ in rows if c.scope != "runtime"),
                        "allow": sum(1 for _, a in rows if a.klass == "allow"),
                        "review": sum(1 for _, a in rows if a.klass == "review"),
                        "deny": sum(1 for _, a in rows if a.klass == "deny"),
                        "failures": len(failures),
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render_table(reports, rows), end="")
        counts = {
            klass: sum(1 for _, assessment in rows if assessment.klass == klass)
            for klass in ("allow", "review", "deny")
        }
        shipped = sum(1 for component, _ in rows if component.scope == "runtime")
        print(
            f"components: {len(rows)} ({shipped} shipped, {len(rows) - shipped} dev) — "
            f"allow {counts['allow']}, review {counts['review']}, deny {counts['deny']}"
        )

    if args.write_notice:
        notice_path: Path = (args.notice or (root / "NOTICE")).resolve()
        notice_path.write_text(notice_body(reports), encoding="utf-8", newline="\n")
        print(f"wrote {notice_path}", file=sys.stderr if args.json else sys.stdout)

    if failures:
        print(f"FAIL: {len(failures)} component(s) violate the license policy", file=sys.stderr)
        for line in render_failures(failures):
            print(line, file=sys.stderr)
        return 1

    # --json must leave stdout parseable, so the human summary goes to stderr there.
    print(
        "ok: every resolved component satisfies the license policy",
        file=sys.stderr if args.json else sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
