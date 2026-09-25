# SPDX-License-Identifier: Apache-2.0
"""Plan pages mark silence as not reusable and speech only when the chunk matches."""

from __future__ import annotations

from praelector.jobs.chunker import PlanItem
from praelector.jobs.plan_view import annotate_plan


def test_silence_is_not_probed_and_the_page_is_a_slice() -> None:
    speech = PlanItem(0, "chp_1", "narrator", "a", "tts", "rk1")
    quiet = PlanItem(1, "chp_1", "narrator", "", "silence", "rk2")
    seen: list[str] = []

    def reusable(item: PlanItem) -> bool:
        seen.append(item.render_key)
        return item.render_key == "rk1"

    page = annotate_plan((speech, quiet), reusable=reusable, offset=0, limit=1)
    assert page["total"] == 2
    assert page["items"][0]["reusable"] is True
    assert seen == ["rk1"]

    rest = annotate_plan((speech, quiet), reusable=reusable, offset=1, limit=10)
    assert rest["items"][0]["kind"] == "silence"
    assert rest["items"][0]["reusable"] is False
    assert seen == ["rk1"]
