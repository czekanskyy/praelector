# SPDX-License-Identifier: Apache-2.0
"""Version information endpoint."""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter
from pydantic import BaseModel, Field

import praelector

router = APIRouter(tags=["System"])

SCHEMA_VERSION = 1


class VersionResponse(BaseModel):
    """Engine version details."""

    model_config = {"populate_by_name": True}

    app: str = Field(default="0.1.0", description="Praelector application version")
    engine: str = Field(default=praelector.__version__, description="Engine core version")
    schema_version: int = Field(
        default=SCHEMA_VERSION, alias="schema", description="Project schema version"
    )
    python: str = Field(
        default_factory=lambda: (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        description="Python runtime version",
    )
    platform: str = Field(default_factory=platform.platform, description="Host operating system")


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    """Returns engine and schema version information."""
    return VersionResponse()
