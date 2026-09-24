# SPDX-License-Identifier: Apache-2.0
"""ffmetadata atoms and the M4B ffmpeg argument list."""

from __future__ import annotations

from pathlib import Path

from praelector.mux.m4b import m4b_args
from praelector.mux.metadata import AudiobookTags, ChapterMark, ffmetadata


def test_tags_follow_the_audiobook_convention() -> None:
    text = ffmetadata(
        AudiobookTags(
            title="Tytuł=1",
            authors=("Anna", "Bartek"),
            narrator="Lektor",
            album="Tytuł",
            date="2026",
            description="Opis",
            isbn="978-0-00",
        ),
        [ChapterMark("Rozdział 1", 0, 12000), ChapterMark("Rozdział 2", 12000, 30000)],
    )
    assert text.startswith(";FFMETADATA1\n")
    assert "title=Tytuł\\=1\n" in text
    assert "artist=Anna, Bartek\n" in text
    assert "album_artist=Anna, Bartek\n" in text
    assert "composer=Lektor\n" in text
    assert "genre=Audiobook\n" in text
    assert "description=Opis\\nISBN 978-0-00\n" in text
    assert "TIMEBASE=1/1000\nSTART=0\nEND=12000\ntitle=Rozdział 1\n" in text
    assert "START=12000\nEND=30000\n" in text


def test_m4b_args_pin_the_encode_and_an_optional_cover(tmp_path: Path) -> None:
    args = m4b_args(
        ffmpeg=tmp_path / "ffmpeg",
        concat_list=tmp_path / "list.txt",
        metadata=tmp_path / "meta.txt",
        output=tmp_path / "book.m4b",
        cover=tmp_path / "cover.jpg",
    )
    assert args[0].endswith("ffmpeg")
    assert args[1:7] == ["-y", "-f", "concat", "-safe", "0", "-i"]
    assert "ffmetadata" in args
    assert args[args.index("-c:a") + 1] == "aac"
    assert args[args.index("-b:a") + 1] == "64k"
    assert args[args.index("-ar") + 1] == "44100"
    assert args[args.index("-ac") + 1] == "1"
    assert args[args.index("-movflags") + 1] == "+faststart"
    assert args[args.index("-disposition:v") + 1] == "attached_pic"
    assert args[-1].endswith("book.m4b")


def test_m4b_args_omit_the_cover_when_there_is_none(tmp_path: Path) -> None:
    args = m4b_args(
        ffmpeg=tmp_path / "ffmpeg",
        concat_list=tmp_path / "list.txt",
        metadata=tmp_path / "meta.txt",
        output=tmp_path / "book.m4b",
    )
    assert "attached_pic" not in args
    assert "-map" in args
