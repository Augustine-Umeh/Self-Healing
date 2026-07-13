"""Incident contract — payload Mefid emits and the agent ingest.

Mefid writes / POSTs an incident when a catalogued failure occurs. The agent
validates ``failure_id`` against ``failures.yaml`` and uses ``diagnosis`` as the
outcome label for diagnose / remediate.

Required:
  failure_id  — must match a FailureEntry.id in the catalog

Optional (recommended when known):
  service, stage, media_id, error, metadata

diagnosis may be omitted on emit; resolve_incident fills it from the catalog.
If both are present, they must agree with the catalog row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from reliability_agent.catalog import FailureCatalog, get_catalog


class IncidentStatus(str, Enum):
    OPEN = "open"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class IncidentCreate(BaseModel):
    """Payload Mefid sends when escalating a failure (webhook / DB insert)."""

    failure_id: str
    diagnosis: str | None = None
    service: str | None = None
    stage: str | None = None
    media_id: UUID | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("failure_id")
    @classmethod
    def _failure_id_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("failure_id must be non-empty")
        return cleaned


class Incident(BaseModel):
    """Persisted / agent-facing incident after catalog resolution."""

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: IncidentStatus = IncidentStatus.OPEN
    failure_id: str
    diagnosis: str
    service: str | None = None
    stage: str | None = None
    media_id: UUID | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_diagnosis(self) -> Incident:
        if not self.diagnosis:
            raise ValueError("diagnosis is required on a resolved incident")
        return self


def resolve_incident(
    payload: IncidentCreate | dict[str, Any],
    catalog: FailureCatalog | None = None,
) -> Incident:
    """Validate failure_id against the catalog and build a full Incident.

    Fills diagnosis from the catalog when omitted. Rejects unknown failure_ids
    and diagnosis mismatches.
    """
    create = (
        payload
        if isinstance(payload, IncidentCreate)
        else IncidentCreate.model_validate(payload)
    )
    catalog = catalog or get_catalog()

    if not catalog.has_failure(create.failure_id):
        raise KeyError(f"unknown failure id: {create.failure_id}")

    entry = catalog.get_failure(create.failure_id)
    if create.diagnosis is not None and create.diagnosis != entry.diagnosis:
        raise ValueError(
            f"diagnosis {create.diagnosis!r} does not match catalog "
            f"{entry.diagnosis!r} for failure_id {create.failure_id!r}"
        )

    return Incident(
        failure_id=create.failure_id,
        diagnosis=entry.diagnosis,
        service=create.service or entry.service,
        stage=create.stage or entry.stage,
        media_id=create.media_id,
        error=create.error,
        metadata=create.metadata,
    )
