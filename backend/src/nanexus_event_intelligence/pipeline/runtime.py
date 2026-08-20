"""Long-running PIPE-001 process wiring database outbox to Redis workers."""

import asyncio
import socket
from typing import cast

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from nanexus_event_intelligence.alerts.handler import ShadowDecisionHandler
from nanexus_event_intelligence.config import get_settings
from nanexus_event_intelligence.notifications.handler import CommunityNotificationHandler
from nanexus_event_intelligence.notifications.webhook import (
    WebhookNotificationAdapter,
    WebhookNotificationConfig,
)
from nanexus_event_intelligence.persistence.database import create_engine, create_session_factory
from nanexus_event_intelligence.pipeline.config import RedisStreamConfig
from nanexus_event_intelligence.pipeline.handlers import ObservationProcessedHandler
from nanexus_event_intelligence.pipeline.outbox import OutboxPublisher, OutboxRedis
from nanexus_event_intelligence.pipeline.worker import RedisStreamWorker, WorkerRedis

logger = structlog.get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    config = RedisStreamConfig(
        stream=settings.pipeline_stream,
        group=settings.pipeline_group,
        dlq_stream=settings.pipeline_dlq_stream,
        batch_size=settings.pipeline_batch_size,
        block_ms=settings.pipeline_block_ms,
        pending_idle_ms=settings.pipeline_pending_idle_ms,
        max_delivery_attempts=settings.pipeline_max_delivery_attempts,
        max_inflight_messages=settings.pipeline_max_inflight_messages,
    )
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    publisher = OutboxPublisher(session_factory, cast(OutboxRedis, redis), config)
    shadow_config = config.model_copy(update={"group": settings.alert_shadow_group, "block_ms": 0})
    worker = RedisStreamWorker(
        cast(WorkerRedis, redis),
        config,
        consumer_name=f"pipeline-{socket.gethostname()}",
        handler=ObservationProcessedHandler(session_factory),
    )
    shadow_worker = RedisStreamWorker(
        cast(WorkerRedis, redis),
        shadow_config,
        consumer_name=f"shadow-{socket.gethostname()}",
        handler=ShadowDecisionHandler(session_factory),
    )
    notification_adapter: WebhookNotificationAdapter | None = None
    notification_worker: RedisStreamWorker | None = None
    if settings.notification_webhook_enabled:
        webhook_config = WebhookNotificationConfig(
            url=settings.notification_webhook_url,
            trusted_internal=settings.notification_webhook_trusted_internal,
            secret=settings.notification_webhook_secret,
            timeout_seconds=settings.notification_webhook_timeout_seconds,
        )
        notification_adapter = WebhookNotificationAdapter(webhook_config)
        notification_config = config.model_copy(
            update={"group": settings.notification_group, "block_ms": 0}
        )
        notification_worker = RedisStreamWorker(
            cast(WorkerRedis, redis),
            notification_config,
            consumer_name=f"notify-{socket.gethostname()}",
            handler=CommunityNotificationHandler(session_factory, notification_adapter),
        )
    try:
        await worker.ensure_group()
        await shadow_worker.ensure_group()
        if notification_worker is not None:
            await notification_worker.ensure_group()
        while True:
            try:
                publish_result = await publisher.publish_batch()
                worker_results = [await worker.run_once(), await shadow_worker.run_once()]
                if notification_worker is not None:
                    worker_results.append(await notification_worker.run_once())
                if publish_result.backpressured:
                    logger.warning("pipeline_backpressured", stream=config.stream)
                if publish_result.failed or any(result.failed for result in worker_results):
                    logger.warning(
                        "pipeline_retry_pending",
                        publish_failed=publish_result.failed,
                        worker_failed=sum(result.failed for result in worker_results),
                    )
            except (RedisError, SQLAlchemyError) as error:
                logger.warning("pipeline_dependency_unavailable", error_type=type(error).__name__)
                await asyncio.sleep(settings.pipeline_error_backoff_seconds)
    finally:
        if notification_adapter is not None:
            await notification_adapter.aclose()
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
