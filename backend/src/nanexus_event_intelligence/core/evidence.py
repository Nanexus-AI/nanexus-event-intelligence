"""Source-neutral port for authorized evidence content."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class EvidenceContentRequest:
    evidence_id: UUID
    source_type: str
    source_namespace: str
    source_entity_id: str
    extensions: dict[str, object]


class EvidenceContentUnavailable(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class EvidenceContent:
    content: bytes
    content_type: str


class EvidenceContentReader(Protocol):
    async def read(self, request: EvidenceContentRequest) -> EvidenceContent: ...
