"""Shared ingestion result structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from models.messages_kernel import CanonicalFinding


@dataclass
class IngestionResult:
    """Represents the outcome of a scanner ingestion run."""

    scanner_id: str
    processed: int
    canonical_findings: List[CanonicalFinding] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return self.processed > 0
