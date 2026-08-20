"""Tolerant response models for the read-only Frigate HTTP API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrigateEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str
    camera: str
    start_time: float
    end_time: float | None = None
    sub_label: str | list[Any] | None = None
    false_positive: bool | None = None
    zones: list[str] = Field(default_factory=list)
    has_clip: bool = False
    has_snapshot: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class FrigateReview(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    camera: str
    start_time: float | datetime
    end_time: float | datetime | None = None
    has_been_reviewed: bool = False
    severity: str
    thumb_path: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class MediaResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    content: bytes
    content_type: str
    frame_time: str | None = None
