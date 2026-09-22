"""Public canonical ReviewItem lookup."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nanexus_event_intelligence.api.dependencies import get_session
from nanexus_event_intelligence.api.routes.events import EventDetail, get_event
from nanexus_event_intelligence.persistence.models import (
    Observation,
    ReviewItem,
    ReviewObservation,
    SourceEntityMap,
)

router = APIRouter(prefix="/review-items", tags=["review-items"])


async def latest_observation_id_for_review(
    session: AsyncSession, review_item_id: UUID
) -> UUID | None:
    """Resolve a canonical ReviewItem UUID to its latest public review observation."""
    review = await session.get(ReviewItem, review_item_id)
    if review is None:
        return None

    linked = await session.scalar(
        select(Observation.id)
        .join(ReviewObservation, ReviewObservation.observation_id == Observation.id)
        .where(ReviewObservation.review_item_id == review_item_id)
        .order_by(Observation.occurred_at.desc(), Observation.id.desc())
        .limit(1)
    )
    if linked is not None:
        return linked

    mapping = await session.scalar(
        select(SourceEntityMap).where(
            SourceEntityMap.internal_entity_id == review_item_id,
            SourceEntityMap.entity_type.in_(("review_item", "review")),
        )
    )
    if mapping is None:
        return None
    return cast(
        UUID | None,
        await session.scalar(
            select(Observation.id)
            .where(
                Observation.source_instance_id == mapping.source_instance_id,
                Observation.source_namespace == mapping.namespace,
                Observation.source_entity_id == mapping.source_entity_id,
                Observation.event_kind == "review",
            )
            .order_by(Observation.occurred_at.desc(), Observation.id.desc())
            .limit(1)
        ),
    )


@router.get("/{review_item_id}", response_model=EventDetail)
async def get_review_item(
    review_item_id: UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> EventDetail:
    observation_id = await latest_observation_id_for_review(session, review_item_id)
    if observation_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
    return await get_event(observation_id, session)
