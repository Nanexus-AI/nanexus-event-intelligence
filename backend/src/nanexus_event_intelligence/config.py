from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+asyncpg://nanexus:nanexus@localhost:5432/nanexus"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    pipeline_stream: str = "nanexus:canonical-events"
    pipeline_group: str = "nanexus:canonical-workers"
    alert_shadow_group: str = "nanexus:shadow-decisions"
    notification_group: str = "nanexus:community-notifications"
    notification_webhook_enabled: bool = False
    notification_webhook_url: str = ""
    notification_webhook_trusted_internal: bool = False
    notification_webhook_secret: SecretStr | None = None
    notification_webhook_timeout_seconds: float = 5.0
    pipeline_dlq_stream: str = "nanexus:canonical-events:dlq"
    pipeline_batch_size: int = 50
    pipeline_block_ms: int = 1000
    pipeline_pending_idle_ms: int = 30_000
    pipeline_max_delivery_attempts: int = 5
    pipeline_max_inflight_messages: int = 100_000
    pipeline_error_backoff_seconds: float = 2.0
    frigate_mqtt_host: str = ""
    frigate_mqtt_port: int = 1883
    frigate_mqtt_username: str = ""
    frigate_mqtt_password: SecretStr | None = None
    frigate_mqtt_topic_prefix: str = "frigate"
    frigate_mqtt_client_id: str = "nanexus-frigate-live-ingest"
    frigate_mqtt_tls: bool = False
    frigate_mqtt_ingest_timeout_seconds: float = 30.0
    frigate_source_name: str = "frigate-primary"
    frigate_source_version: str = ""
    frigate_http_base_url: str = ""
    frigate_http_bearer_token: SecretStr | None = None
    frigate_http_username: str = ""
    frigate_http_password: SecretStr | None = None
    frigate_http_proxy_secret: SecretStr | None = None
    frigate_http_trusted_internal: bool = False
    frigate_http_ca_bundle: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
