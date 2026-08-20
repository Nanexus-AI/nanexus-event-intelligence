from datetime import datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.api.dependencies import get_session
from nanexus_event_intelligence.persistence.models import (
    Action,
    AuditRecord,
    Camera,
    Decision,
    Evidence,
    Feedback,
    Notification,
    Observation,
    ObservedObject,
    RawSourceMessage,
    SourceInstance,
)

router = APIRouter(prefix="/events", tags=["events"])


class EventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    event_kind: str
    lifecycle: str
    labels: list[str]
    zones: list[str]
    partial_history: bool
    source_name: str
    camera_name: str | None
    feedback_verdict: str | None
    first_occurred_at: datetime
    last_occurred_at: datetime
    observation_count: int


class EventListResponse(BaseModel):
    items: list[EventSummary]
    total: int
    limit: int
    offset: int


class ObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_key: str
    label: str
    sub_labels: list[str]
    confidence: float | None
    stationary: bool | None
    track: dict[str, Any]


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    media_type: str
    source_ref: str
    captured_at: datetime | None
    privacy_class: str
    availability: str
    sha256: str | None
    expires_at: datetime | None
    metadata_json: dict[str, Any]


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    revision: int
    outcome: str
    policy_id: str
    policy_version: str
    confidence: float | None
    reasons: list[str]
    rule_trace: dict[str, Any]
    degraded: bool
    degraded_reasons: list[str]
    created_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    action_id: UUID
    decision_id: UUID
    channel: str
    stage: str
    idempotency_key: str
    delivery_status: str
    external_message_id: str | None
    attempts: int
    last_error: str | None
    created_at: datetime


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_id: UUID
    verdict: str
    reason: str | None
    actor: str
    created_at: datetime


class RawMessageResponse(BaseModel):
    id: UUID
    transport: str
    channel: str
    schema_version: str
    payload: dict[str, Any]
    payload_sha256: str
    observed_at: datetime
    quarantined: bool
    quarantine_reason: str | None


class TimelineItem(BaseModel):
    id: UUID
    lifecycle: str
    occurred_at: datetime
    labels: list[str]
    zones: list[str]
    partial_history: bool
    source_namespace: str
    source_entity_id: str


class EventDetail(BaseModel):
    id: UUID
    source_instance_id: UUID
    source_name: str
    source_type: str
    source_version: str | None
    camera_id: UUID | None
    camera_name: str | None
    source_namespace: str
    source_entity_id: str
    source_revision: str
    dedupe_key: str
    schema_version: str
    event_kind: str
    lifecycle: str
    occurred_at: datetime
    observed_at: datetime
    processed_at: datetime | None
    start_at: datetime | None
    end_at: datetime | None
    partial_history: bool
    labels: list[str]
    zones: list[str]
    extensions: dict[str, Any]
    raw_message: RawMessageResponse | None
    objects: list[ObjectResponse]
    evidence: list[EvidenceResponse]
    decisions: list[DecisionResponse]
    notifications: list[NotificationResponse]
    feedback: FeedbackResponse | None
    first_occurred_at: datetime
    last_occurred_at: datetime
    observation_count: int
    timeline: list[TimelineItem]
    related_entity_ids: list[str]


class FeedbackCreate(BaseModel):
    verdict: Literal["important", "not_important", "false_positive", "uncertain"]
    reason: str | None = Field(default=None, max_length=1000)
    actor: str = Field(default="local-user", min_length=1, max_length=255)


def _linked_event_ids(observations: list[Observation]) -> list[str]:
    linked: set[str] = set()
    for observation in observations:
        links = observation.extensions.get("links", [])
        if not isinstance(links, list):
            continue
        for link in links:
            if (
                isinstance(link, dict)
                and link.get("namespace") == "frigate.event"
                and isinstance(link.get("source_entity_id"), str)
            ):
                linked.add(cast(str, link["source_entity_id"]))
    return sorted(linked)


@router.get("", response_model=EventListResponse)
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    event_kind: str | None = None,
    lifecycle: str | None = None,
    label: str | None = None,
    source_instance_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EventListResponse:
    entity_columns = (
        Observation.source_instance_id,
        Observation.source_namespace,
        Observation.source_entity_id,
    )
    ranked = select(
        Observation.id.label("observation_id"),
        func.row_number()
        .over(
            partition_by=entity_columns,
            order_by=(Observation.occurred_at.desc(), Observation.id.desc()),
        )
        .label("position"),
    ).subquery()
    aggregates = (
        select(
            *entity_columns,
            func.min(func.coalesce(Observation.start_at, Observation.occurred_at)).label(
                "first_occurred_at"
            ),
            func.max(func.coalesce(Observation.end_at, Observation.occurred_at)).label(
                "last_occurred_at"
            ),
            func.count().label("observation_count"),
        )
        .group_by(*entity_columns)
        .subquery()
    )
    latest_reviews = list(
        (
            await session.scalars(
                select(Observation)
                .join(ranked, ranked.c.observation_id == Observation.id)
                .where(
                    ranked.c.position == 1,
                    Observation.source_namespace == "frigate.review",
                )
            )
        ).all()
    )
    linked_keys = [
        (review.source_instance_id, "frigate.event", event_id)
        for review in latest_reviews
        for event_id in _linked_event_ids([review])
    ]
    filters = [ranked.c.position == 1]
    if event_kind is None and linked_keys:
        filters.append(
            tuple_(
                Observation.source_instance_id,
                Observation.source_namespace,
                Observation.source_entity_id,
            ).not_in(linked_keys)
        )
    if event_kind:
        filters.append(Observation.event_kind == event_kind)
    if lifecycle:
        filters.append(Observation.lifecycle == lifecycle)
    if label:
        filters.append(Observation.labels.contains([label]))
    if source_instance_id:
        filters.append(Observation.source_instance_id == source_instance_id)
    if occurred_from:
        filters.append(aggregates.c.last_occurred_at >= occurred_from)
    if occurred_to:
        filters.append(aggregates.c.last_occurred_at <= occurred_to)
    where = and_(*filters)
    joined = (
        select(
            Observation,
            SourceInstance.name,
            Camera.display_name,
            aggregates.c.first_occurred_at,
            aggregates.c.last_occurred_at,
            aggregates.c.observation_count,
        )
        .join(ranked, ranked.c.observation_id == Observation.id)
        .join(SourceInstance, SourceInstance.id == Observation.source_instance_id)
        .outerjoin(Camera, Camera.id == Observation.camera_id)
        .join(
            aggregates,
            and_(
                aggregates.c.source_instance_id == Observation.source_instance_id,
                aggregates.c.source_namespace == Observation.source_namespace,
                aggregates.c.source_entity_id == Observation.source_entity_id,
            ),
        )
        .where(where)
    )
    total = int((await session.scalar(select(func.count()).select_from(joined.subquery()))) or 0)
    rows = (
        await session.execute(
            joined.order_by(aggregates.c.last_occurred_at.desc(), Observation.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items: list[EventSummary] = []
    for observation, source_name, camera_name, first_at, last_at, count in rows:
        feedback = await _latest_feedback(session, observation.id)
        items.append(
            EventSummary(
                id=observation.id,
                occurred_at=observation.occurred_at,
                event_kind=observation.event_kind,
                lifecycle=observation.lifecycle,
                labels=observation.labels,
                zones=observation.zones,
                partial_history=observation.partial_history,
                source_name=source_name,
                camera_name=camera_name,
                feedback_verdict=feedback.verdict if feedback else None,
                first_occurred_at=first_at,
                last_occurred_at=last_at,
                observation_count=count,
            )
        )
    return EventListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{observation_id}", response_model=EventDetail)
async def get_event(
    observation_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> EventDetail:
    row = (
        await session.execute(
            select(Observation, SourceInstance, Camera)
            .join(SourceInstance, SourceInstance.id == Observation.source_instance_id)
            .outerjoin(Camera, Camera.id == Observation.camera_id)
            .where(Observation.id == observation_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    observation, source, camera = row
    timeline = list(
        (
            await session.scalars(
                select(Observation)
                .where(
                    Observation.source_instance_id == observation.source_instance_id,
                    Observation.source_namespace == observation.source_namespace,
                    Observation.source_entity_id == observation.source_entity_id,
                )
                .order_by(Observation.occurred_at, Observation.id)
            )
        ).all()
    )
    related_entity_ids = (
        _linked_event_ids(timeline) if observation.source_namespace == "frigate.review" else []
    )
    display_timeline = timeline
    if related_entity_ids:
        display_timeline = list(
            (
                await session.scalars(
                    select(Observation)
                    .where(
                        Observation.source_instance_id == observation.source_instance_id,
                        Observation.source_namespace == "frigate.event",
                        Observation.source_entity_id.in_(related_entity_ids),
                    )
                    .order_by(Observation.occurred_at, Observation.id)
                )
            ).all()
        )
    first_occurred_at = min(item.start_at or item.occurred_at for item in display_timeline)
    last_occurred_at = max(item.end_at or item.occurred_at for item in display_timeline)
    raw = (
        await session.get(RawSourceMessage, observation.raw_message_id)
        if observation.raw_message_id
        else None
    )
    object_rows = list(
        (
            await session.scalars(
                select(ObservedObject).where(
                    ObservedObject.observation_id.in_([item.id for item in display_timeline])
                )
            )
        ).all()
    )
    objects = list({item.object_key: item for item in object_rows}.values())
    evidence = list(
        (
            await session.scalars(
                select(Evidence)
                .where(Evidence.observation_id == observation.id)
                .order_by(Evidence.captured_at)
            )
        ).all()
    )
    decisions = list(
        (
            await session.scalars(
                select(Decision)
                .where(
                    Decision.subject_type == "observation", Decision.subject_id == observation.id
                )
                .order_by(Decision.revision.desc())
            )
        ).all()
    )
    notifications = list(
        (
            await session.execute(
                select(Notification, Action)
                .join(Action, Action.id == Notification.action_id)
                .join(Decision, Decision.id == Action.decision_id)
                .where(
                    Decision.subject_type == "observation",
                    Decision.subject_id == observation.id,
                )
                .order_by(Notification.created_at.desc())
            )
        ).all()
    )
    feedback = await _latest_feedback(session, observation.id)
    return EventDetail(
        **{
            key: getattr(observation, key)
            for key in (
                "id",
                "source_instance_id",
                "camera_id",
                "source_namespace",
                "source_entity_id",
                "source_revision",
                "dedupe_key",
                "schema_version",
                "event_kind",
                "lifecycle",
                "occurred_at",
                "observed_at",
                "processed_at",
                "start_at",
                "end_at",
                "partial_history",
                "labels",
                "zones",
                "extensions",
            )
        },
        source_name=source.name,
        source_type=source.source_type,
        source_version=source.source_version,
        camera_name=camera.display_name if camera else None,
        raw_message=RawMessageResponse.model_validate(raw, from_attributes=True) if raw else None,
        objects=[ObjectResponse.model_validate(item) for item in objects],
        evidence=[EvidenceResponse.model_validate(item) for item in evidence],
        decisions=[DecisionResponse.model_validate(item) for item in decisions],
        notifications=[
            NotificationResponse(
                id=notification.id,
                action_id=action.id,
                decision_id=action.decision_id,
                channel=notification.channel,
                stage=notification.stage,
                idempotency_key=notification.idempotency_key,
                delivery_status=notification.delivery_status,
                external_message_id=notification.external_message_id,
                attempts=action.attempts,
                last_error=action.last_error,
                created_at=notification.created_at,
            )
            for notification, action in notifications
        ],
        related_entity_ids=related_entity_ids,
        feedback=FeedbackResponse.model_validate(feedback) if feedback else None,
        first_occurred_at=first_occurred_at,
        last_occurred_at=last_occurred_at,
        observation_count=len(display_timeline),
        timeline=[
            TimelineItem(
                id=item.id,
                lifecycle=item.lifecycle,
                occurred_at=item.occurred_at,
                labels=item.labels,
                zones=item.zones,
                partial_history=item.partial_history,
                source_namespace=item.source_namespace,
                source_entity_id=item.source_entity_id,
            )
            for item in display_timeline
        ],
    )


@router.post(
    "/{observation_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    observation_id: UUID,
    body: FeedbackCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FeedbackResponse:
    observation = await session.get(Observation, observation_id)
    if observation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    decision = await session.scalar(
        select(Decision)
        .where(Decision.subject_type == "observation", Decision.subject_id == observation_id)
        .order_by(Decision.revision.desc())
        .limit(1)
    )
    if decision is None:
        decision = Decision(
            subject_type="observation",
            subject_id=observation_id,
            revision=1,
            outcome="no_action",
            policy_id="ui-feedback-anchor",
            policy_version="1.0.0",
            reasons=["created to anchor manual feedback"],
        )
        session.add(decision)
        await session.flush()
    previous = await _latest_feedback(session, observation_id)
    feedback = Feedback(
        decision_id=decision.id,
        verdict=body.verdict,
        reason=body.reason,
        actor=body.actor,
        supersedes_feedback_id=previous.id if previous else None,
    )
    session.add(feedback)
    await session.flush()
    session.add(
        AuditRecord(
            actor=body.actor,
            action="feedback.created",
            target_type="observation",
            target_id=observation_id,
            before={"verdict": previous.verdict} if previous else None,
            after={"verdict": body.verdict, "reason": body.reason},
        )
    )
    return FeedbackResponse.model_validate(feedback)


async def _latest_feedback(session: AsyncSession, observation_id: UUID) -> Feedback | None:
    return cast(
        Feedback | None,
        await session.scalar(
            select(Feedback)
            .join(Decision, Decision.id == Feedback.decision_id)
            .where(Decision.subject_type == "observation", Decision.subject_id == observation_id)
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
            .limit(1)
        ),
    )
