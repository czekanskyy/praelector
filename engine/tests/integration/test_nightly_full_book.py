# SPDX-License-Identifier: Apache-2.0
"""Placeholder for the nightly full-book run (CI_AND_RELEASE.md §11).

The real test lands in M4, once the planner, scheduler and muxer exist: ingest
``epub3_polish_novel.epub`` → heuristic prep → apply → plan → synthesise ~300
chunks with the ``fake`` backend → pause → restart the engine → resume → partial
mux → full mux → reader EPUB export, asserting ≥95 % chunk reuse after resume and
the ``ffprobe`` chapter count and duration.

Until then it skips, so ``nightly-fixture.yml`` is inert rather than red — pytest
exits non-zero when a marker selects nothing, which would file an issue daily.
"""

from __future__ import annotations

import pytest


@pytest.mark.full_book
@pytest.mark.skip(reason="lands in M4: needs the planner, scheduler and muxer")
def test_full_book_pipeline_with_the_fake_backend() -> None:
    raise NotImplementedError
