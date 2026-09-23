# SPDX-License-Identifier: Apache-2.0
"""Tests for the JSONL stdio loop: a full session, and the ways it can go wrong."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from praelector_tts.backends import UnknownBackendError, available_backend_ids, describe_all
from praelector_tts.backends.fake import FakeBackend
from praelector_tts.worker import Worker


def run_session(lines: list[str]) -> list[dict[str, object]]:
    stdout = StringIO()
    worker = Worker(FakeBackend(), stdin=StringIO("\n".join(lines) + "\n"), stdout=stdout)
    assert worker.serve() == 0
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def test_the_ready_event_comes_first() -> None:
    frames = run_session([])
    assert frames[0]["event"] == "ready"
    assert frames[0]["backend"] == "fake"
    assert frames[0]["pid"]


def test_describe_answers_with_the_full_descriptor() -> None:
    frames = run_session(['{"id":1,"op":"describe"}'])
    reply = frames[1]
    assert reply["id"] == 1
    assert reply["ok"] is True
    assert reply["result"]["id"] == "fake"
    assert "pl" in reply["result"]["capabilities"]["languages"]


def test_load_then_synthesize_writes_the_part_file(tmp_path: Path) -> None:
    out = tmp_path / "chunks" / "ab" / "rk.wav"
    frames = run_session(
        [
            json.dumps({"id": 1, "op": "load", "params": {"models_dir": str(tmp_path)}}),
            json.dumps({"id": 2, "op": "synthesize", "text": "Ala ma kota.", "out_path": str(out)}),
        ]
    )
    assert frames[1]["result"]["loaded"] is True
    result = frames[2]["result"]
    assert result["duration_s"] == pytest.approx(len("Ala ma kota.") / 14.0, abs=1e-4)
    assert Path(str(result["out_path"])).exists()
    assert str(result["out_path"]).endswith(".part")


def test_synthesize_before_load_reports_the_error_without_killing_the_worker(
    tmp_path: Path,
) -> None:
    frames = run_session(
        [
            json.dumps(
                {"id": 1, "op": "synthesize", "text": "Ala.", "out_path": str(tmp_path / "a.wav")}
            ),
            '{"id":2,"op":"describe"}',
        ]
    )
    assert frames[1]["ok"] is False
    assert frames[1]["error"]["code"] == "tts.load_failed"
    # The session continued: the next request was still answered.
    assert frames[2]["ok"] is True


def test_probe_vram_and_unload() -> None:
    frames = run_session(
        [
            '{"id":1,"op":"load","params":{"models_dir":"/m"}}',
            '{"id":2,"op":"probe_vram"}',
            '{"id":3,"op":"unload"}',
        ]
    )
    assert frames[2]["result"]["peak_mib"] is not None
    assert frames[3]["result"] == {"unloaded": True}


def test_shutdown_ends_the_session() -> None:
    frames = run_session(['{"id":1,"op":"shutdown"}', '{"id":2,"op":"describe"}'])
    assert frames[1]["result"] == {"shutdown": True}
    assert len(frames) == 2, "no request after shutdown may be answered"


def test_a_malformed_line_gets_an_error_with_no_id() -> None:
    frames = run_session(["{not json at all}", '{"id":7,"op":"describe"}'])
    assert frames[1]["ok"] is False
    # `id` is absent rather than null: frames are serialised with exclude_none so
    # the engine can treat a reply without an id as unsolicited.
    assert frames[1].get("id") is None
    assert frames[1]["error"]["code"] == "tts.internal"
    assert frames[2]["id"] == 7


def test_an_unknown_op_gets_an_error() -> None:
    frames = run_session(['{"id":4,"op":"teleport"}'])
    assert frames[1]["ok"] is False
    assert frames[1]["error"]["code"] == "tts.internal"


def test_blank_lines_are_ignored() -> None:
    frames = run_session(["", '{"id":1,"op":"describe"}', "   "])
    assert len(frames) == 2


def test_every_frame_is_one_line_of_json() -> None:
    stdout = StringIO()
    worker = Worker(FakeBackend(), stdin=StringIO('{"id":1,"op":"describe"}\n'), stdout=stdout)
    worker.serve()
    for line in stdout.getvalue().splitlines():
        assert line.strip() == line
        json.loads(line)


def test_the_registry_lists_and_describes_without_instantiating() -> None:
    assert "fake" in available_backend_ids()
    descriptors = describe_all()
    assert [d.id for d in descriptors] == available_backend_ids()


def test_an_unknown_backend_is_reported_with_the_known_ids() -> None:
    from praelector_tts.backends import create_backend

    with pytest.raises(UnknownBackendError) as excinfo:
        create_backend("omnivoice")
    assert excinfo.value.known == ["fake"]
