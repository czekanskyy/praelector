# SPDX-License-Identifier: Apache-2.0
"""The engine core must never pull in torch, and the worker must run without it.

Two invariants, both load-bearing:

* ``engine`` resolving torch would put a 3 GB wheel in the installer (D-03/D-04).
* ``praelector_tts`` importing torch at module scope would break CI, which
  exercises the whole job engine through the ``fake`` backend with no extra
  installed (REPO_LAYOUT.md §6).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

_PROBE = """
import sys, json, tempfile, pathlib
from praelector_tts.backends import create_backend
from praelector_tts.worker import Worker
from praelector_tts.protocol import LoadContext, SynthesisRequest

backend = create_backend("fake")
backend.load(LoadContext(models_dir=tempfile.gettempdir()))
out = pathlib.Path(tempfile.mkdtemp()) / "rk.wav"
backend.synthesize(SynthesisRequest(text="Ala ma kota.", out_path=str(out)))
print(json.dumps({"torch_imported": "torch" in sys.modules}))
"""


def test_using_the_fake_backend_never_imports_torch() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    import json

    assert json.loads(result.stdout.strip().splitlines()[-1])["torch_imported"] is False


@pytest.mark.parametrize("lockfile", [REPO_ROOT / "engine" / "uv.lock"])
def test_the_core_lockfile_has_no_torch(lockfile: Path) -> None:
    """The same assertion CI makes through scripts/assert_no_torch.py."""
    if not lockfile.exists():
        pytest.skip(f"{lockfile} is not generated yet")
    import tomllib

    with lockfile.open("rb") as handle:
        data = tomllib.load(handle)
    names = {package.get("name", "") for package in data.get("package", [])}
    forbidden = {"torch", "torchvision", "torchaudio", "pytorch-triton", "pytorch-triton-rocm"}
    assert not (names & forbidden), f"the core lock resolved: {sorted(names & forbidden)}"
