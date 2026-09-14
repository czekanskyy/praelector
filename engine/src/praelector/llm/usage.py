# SPDX-License-Identifier: Apache-2.0
"""Token and usage tracking for LLM operations per project (LM-07)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from praelector.llm.protocol import LlmUsage
from praelector.store.atomic import atomic_write


class LlmUsageTracker:
    """Best-effort usage counter tracking token counts per project and profile (LM-07)."""

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.storage_dir / "llm_usage.json"
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.file_path.is_file():
            return {}
        try:
            content = json.loads(self.file_path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                return content
            return {}
        except Exception:
            return {}

    def _save(self) -> None:
        atomic_write(self.file_path, json.dumps(self._data, indent=2))

    def record(
        self,
        project_id: str,
        profile_id: str,
        task: str,
        usage: LlmUsage,
    ) -> None:
        """Record a completed LLM invocation's token usage."""
        if project_id not in self._data:
            self._data[project_id] = {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
                "by_profile": {},
                "by_task": {},
            }

        proj = self._data[project_id]
        proj["total_prompt_tokens"] += usage.prompt_tokens
        proj["total_completion_tokens"] += usage.completion_tokens
        proj["total_tokens"] += usage.total_tokens
        proj["call_count"] += 1

        # Track by profile
        prof_dict = proj["by_profile"].setdefault(
            profile_id, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
        )
        prof_dict["prompt_tokens"] += usage.prompt_tokens
        prof_dict["completion_tokens"] += usage.completion_tokens
        prof_dict["total_tokens"] += usage.total_tokens
        prof_dict["calls"] += 1

        # Track by task
        task_dict = proj["by_task"].setdefault(
            task, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
        )
        task_dict["prompt_tokens"] += usage.prompt_tokens
        task_dict["completion_tokens"] += usage.completion_tokens
        task_dict["total_tokens"] += usage.total_tokens
        task_dict["calls"] += 1

        self._save()

    def get_project_usage(self, project_id: str) -> dict[str, Any]:
        """Return usage summary for a project."""
        return self._data.get(
            project_id,
            {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "call_count": 0,
                "by_profile": {},
                "by_task": {},
            },
        )

    def get_global_usage(self) -> dict[str, Any]:
        """Return aggregated usage across all projects."""
        total_prompt = sum(p.get("total_prompt_tokens", 0) for p in self._data.values())
        total_comp = sum(p.get("total_completion_tokens", 0) for p in self._data.values())
        total_tokens = sum(p.get("total_tokens", 0) for p in self._data.values())
        calls = sum(p.get("call_count", 0) for p in self._data.values())
        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_comp,
            "total_tokens": total_tokens,
            "call_count": calls,
            "projects_tracked": len(self._data),
        }
