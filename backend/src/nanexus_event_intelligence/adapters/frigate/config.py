"""Frigate-only connection configuration."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class FrigateMqttConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(min_length=1)
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = None
    password: SecretStr | None = None
    topic_prefix: str = "frigate"
    client_id: str = "nanexus-frigate-recorder"
    tls: bool = False
    keepalive: int = Field(default=60, ge=5, le=3600)
    reconnect_delay_seconds: float = Field(default=1.0, gt=0, le=60)
    reconnect_max_seconds: float = Field(default=30.0, gt=0, le=300)

    @field_validator("topic_prefix")
    @classmethod
    def validate_topic_prefix(cls, value: str) -> str:
        prefix = value.strip().strip("/")
        if not prefix or "+" in prefix or "#" in prefix:
            raise ValueError("topic_prefix must be a concrete MQTT topic prefix")
        return prefix

    @property
    def recording_topics(self) -> tuple[str, ...]:
        return tuple(
            f"{self.topic_prefix}/{suffix}"
            for suffix in ("reviews", "events", "tracked_object_update", "available")
        )
