"""Tolerant models for the Frigate 0.17 MQTT payloads used by the adapter."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LifecycleType = Literal["new", "update", "end"]


class ReviewData(BaseModel):
    model_config = ConfigDict(extra="allow")

    detections: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    sub_labels: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    audio: list[str] = Field(default_factory=list)
    thumb_time: float | None = None


class ReviewState(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    camera: str
    start_time: float
    end_time: float | None = None
    severity: str | None = None
    thumb_path: str | None = None
    data: ReviewData = Field(default_factory=ReviewData)


class ReviewMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: LifecycleType
    before: ReviewState | None = None
    after: ReviewState


class ObjectState(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    camera: str
    start_time: float
    end_time: float | None = None
    frame_time: float | None = None
    label: str
    sub_label: str | list[str] | None = None
    score: float | None = None
    stationary: bool | None = None
    motionless_count: int | None = None
    current_zones: list[str] = Field(default_factory=list)
    entered_zones: list[str] = Field(default_factory=list)
    has_snapshot: bool | None = None
    has_clip: bool | None = None


class ObjectMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: LifecycleType
    before: ObjectState | None = None
    after: ObjectState


class TrackedObjectUpdate(BaseModel):
    """The update topic evolves quickly, so only stable identity fields are required."""

    model_config = ConfigDict(extra="allow")

    type: str
    id: str
    camera: str | None = None
    timestamp: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    name: str | None = None
    plate: str | None = None
    score: float | None = None
    model: str | None = None
    sub_label: str | None = None
    attribute: str | None = None
