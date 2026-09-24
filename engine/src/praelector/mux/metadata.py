# SPDX-License-Identifier: Apache-2.0
"""ffmetadata for an audiobook (MX-02).

Artist and album artist are the authors. Composer is the narrator.
Genre is always Audiobook. An ISBN is appended to the description.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChapterMark:
    """One chapter span. Times are milliseconds."""

    title: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class AudiobookTags:
    """Tags that become atoms. ``date`` is a year or an ISO date."""

    title: str
    authors: tuple[str, ...]
    narrator: str
    album: str
    date: str
    language: str = "pol"
    description: str = ""
    isbn: str = ""


def ffmetadata(tags: AudiobookTags, chapters: list[ChapterMark]) -> str:
    """The ffmetadata document, including a header line."""
    description = tags.description
    if tags.isbn:
        suffix = f"ISBN {tags.isbn}"
        description = f"{description}\n{suffix}".strip()
    authors = ", ".join(tags.authors)
    lines = [
        ";FFMETADATA1",
        f"title={_escape(tags.title)}",
        f"artist={_escape(authors)}",
        f"album_artist={_escape(authors)}",
        f"composer={_escape(tags.narrator)}",
        f"album={_escape(tags.album)}",
        f"date={_escape(tags.date)}",
        "genre=Audiobook",
        f"language={_escape(tags.language)}",
        f"description={_escape(description)}",
        f"comment={_escape(description)}",
    ]
    for chapter in chapters:
        lines.extend(
            [
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={chapter.start_ms}",
                f"END={chapter.end_ms}",
                f"title={_escape(chapter.title)}",
            ]
        )
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    """ffmetadata treats ``= ; # \\`` and newlines as syntax."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
    )
