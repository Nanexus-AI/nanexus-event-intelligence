import pytest
from pydantic import SecretStr, ValidationError

from nanexus_event_intelligence.adapters.frigate.http_config import FrigateHttpConfig


def test_https_origin_and_bearer_token_are_valid() -> None:
    config = FrigateHttpConfig(
        base_url="https://frigate.local:8971/", bearer_token=SecretStr("token")
    )
    assert config.origin == "https://frigate.local:8971"


@pytest.mark.parametrize(
    "base_url",
    [
        "frigate.local:8971",
        "https://user:pass@frigate.local:8971",
        "https://frigate.local:8971/api",
        "https://frigate.local:8971?token=secret",
        "http://frigate.local:5000",
    ],
)
def test_rejects_unsafe_or_non_origin_urls(base_url: str) -> None:
    with pytest.raises(ValidationError):
        FrigateHttpConfig(base_url=base_url)


def test_internal_http_requires_explicit_trust_boundary() -> None:
    config = FrigateHttpConfig(base_url="http://frigate.local:5000", trusted_internal=True)
    assert config.trusted_internal


def test_rejects_multiple_authentication_modes() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        FrigateHttpConfig(
            base_url="https://frigate.local:8971",
            bearer_token=SecretStr("token"),
            proxy_secret=SecretStr("proxy"),
        )


def test_requires_complete_username_password_pair() -> None:
    with pytest.raises(ValidationError, match="together"):
        FrigateHttpConfig(base_url="https://frigate.local:8971", username="viewer")
