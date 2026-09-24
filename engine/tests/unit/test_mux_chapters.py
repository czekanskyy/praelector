# SPDX-License-Identifier: Apache-2.0
"""Partial mux keeps chapter numbers. Silence sits only between speech."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from praelector.errors import AppError, ErrorCode
from praelector.jobs.chunker import PlanItem
from praelector.mux.chapters import (
    ChapterAudio,
    chapter_marks,
    concat_list,
    select_for_mux,
    write_partial_report,
)


def _item(ordinal: int, chapter_id: str, kind: str = "tts", key: str = "k") -> PlanItem:
    return PlanItem(ordinal, chapter_id, "narrator", "a", kind, key)


def _chapter(number: int, *items: PlanItem) -> ChapterAudio:
    return ChapterAudio(f"chp_{number}", number, f"Rozdział {number}", tuple(items))


def test_partial_drops_an_incomplete_chapter_and_keeps_its_number() -> None:
    chapters = [
        _chapter(1, _item(0, "chp_1", key="a")),
        _chapter(2, _item(1, "chp_2", key="missing")),
        _chapter(3, _item(2, "chp_3", key="c")),
    ]
    plan = select_for_mux(
        chapters,
        present=lambda item: item.render_key != "missing",
        mode="partial",
    )
    assert [chapter.number for chapter in plan.included] == [1, 3]
    assert plan.omitted == (
        {
            "chapter_id": "chp_2",
            "number": 2,
            "title": "Rozdział 2",
            "reason": "incomplete",
        },
    )


def test_full_export_refuses_a_missing_chunk() -> None:
    chapters = [_chapter(1, _item(0, "chp_1", key="missing"))]
    with pytest.raises(AppError) as caught:
        select_for_mux(chapters, present=lambda _item: False, mode="full")
    assert caught.value.code is ErrorCode.EXPORT_INCOMPLETE
    assert caught.value.detail["missing_chapters"] == [1]


def test_silence_is_inserted_only_between_speech(tmp_path: Path) -> None:
    items = [
        _item(0, "chp_1", key="a"),
        _item(1, "chp_1", "silence", key=""),
        _item(2, "chp_1", key="b"),
        _item(3, "chp_1", key="c"),
    ]
    silence = tmp_path / "gap.wav"
    text = concat_list(
        items,
        wav_for=lambda item: tmp_path / f"{item.render_key or 'pause'}.wav",
        silence_wav=silence,
        gap_ms=300,
    )
    lines = text.strip().splitlines()
    assert lines == [
        f"file '{(tmp_path / 'a.wav').as_posix()}'",
        f"file '{(tmp_path / 'pause.wav').as_posix()}'",
        f"file '{(tmp_path / 'b.wav').as_posix()}'",
        f"file '{silence.as_posix()}'",
        f"file '{(tmp_path / 'c.wav').as_posix()}'",
    ]


def test_the_report_records_the_omitted_chapter_number(tmp_path: Path) -> None:
    chapters = [
        _chapter(1, _item(0, "chp_1", key="a")),
        _chapter(8, _item(1, "chp_8", key="missing")),
    ]
    plan = select_for_mux(
        chapters, present=lambda item: item.render_key != "missing", mode="partial"
    )
    path = tmp_path / "partial_report.json"
    write_partial_report(path, plan)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["omitted"][0]["number"] == 8
    assert saved["omitted"][0]["reason"] == "incomplete"


def test_chapter_marks_follow_the_included_order() -> None:
    chapters = [_chapter(1, _item(0, "chp_1")), _chapter(8, _item(1, "chp_8"))]
    marks = chapter_marks(chapters, [1.5, 0.25])
    assert [(mark.title, mark.start_ms, mark.end_ms) for mark in marks] == [
        ("Rozdział 1", 0, 1500),
        ("Rozdział 8", 1500, 1750),
    ]


def test_a_zero_gap_does_not_insert_silence(tmp_path: Path) -> None:
    items = [_item(0, "chp_1", key="a"), _item(1, "chp_1", key="b")]
    text = concat_list(
        items,
        wav_for=lambda item: tmp_path / f"{item.render_key}.wav",
        silence_wav=tmp_path / "gap.wav",
        gap_ms=0,
    )
    assert text.count("gap.wav") == 0
    assert text.count("file ") == 2
