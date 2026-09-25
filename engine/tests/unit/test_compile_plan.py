# SPDX-License-Identifier: Apache-2.0
"""Compiling a plan writes the items the render pass will read."""

from __future__ import annotations

from pathlib import Path

from praelector.domain.enums import VoiceMode, VoiceSlot
from praelector.jobs.compile import compile_plan
from praelector.jobs.planfile import read_plan
from praelector.jobs.planner import SourceBlock
from praelector.text.apply import AppliedSpan


def test_a_pause_becomes_silence_in_the_written_plan(tmp_path: Path) -> None:
    path = tmp_path / "plan.jsonl"
    items, warnings = compile_plan(
        path,
        [
            SourceBlock(
                "chp_1",
                "Cisza potem.",
                (AppliedSpan("pause", 5, 6),),
            )
        ],
        mode=VoiceMode.SINGLE,
        filled={VoiceSlot.NARRATOR},
        profiles={VoiceSlot.NARRATOR: ("vpr_n", "hash_n")},
        max_input_chars=400,
        backend_id="fake",
        adapter_version="1",
        model_revision="0",
    )
    assert warnings == []
    assert [item.kind for item in items] == ["tts", "silence", "tts"]
    assert [item.spoken_text for item in items] == ["Cisza", "", "potem."]
    assert read_plan(path) == items
    assert items[0].ordinal == 0
    assert items[2].ordinal == 2
