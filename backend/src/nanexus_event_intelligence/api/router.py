from fastapi import APIRouter

from nanexus_event_intelligence.api.routes.events import router as events_router
from nanexus_event_intelligence.api.routes.health import router as health_router
from nanexus_event_intelligence.api.routes.processor import router as processor_router
from nanexus_event_intelligence.api.routes.review_items import router as review_items_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(events_router)
api_router.include_router(review_items_router)
api_router.include_router(processor_router)
