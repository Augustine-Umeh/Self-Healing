"""Catalog-backed diagnose for claimed incidents (no remediation)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from reliability_agent.catalog import FailureCatalog, get_catalog
from reliability_agent.incident import Incident


class Disposition(str, Enum):
    """What the agent should do next — planned only until act is wired."""

    REMEDIATE = "remediate"
    ESCALATE = "escalate"


# Outcome diagnosis → planned remediation kind (not executed yet).
_PLANNED_ACTION_BY_DIAGNOSIS: dict[str, str] = {
    "PROCESS_DOWN": "restart_service",
    "MODEL_NOT_LOADED": "restart_service",
    "DEPENDENCY_UNREACHABLE": "wait_for_dependency",
    "FRAMES_MISSING": "reprocess_extract",
    "IMAGE_EMBEDDINGS_MISSING": "reembed_images",
    "IMAGE_NOT_INDEXED": "reindex_images",
    "TRANSCRIPT_MISSING": "retranscribe",
    "TRANSCRIPT_NOT_INDEXED": "reindex_transcripts",
    "CAPTION_MISSING": "recaption",
    "CAPTION_NOT_INDEXED": "reindex_captions",
    "ORPHAN_VECTORS": "reconcile_index",
    "IN_MEMORY_DISK_DRIFT": "reload_index",
    "PARTIAL_UPLOAD": "reprocess_or_mark_failed",
}


class DiagnoseResult(BaseModel):
    """Light diagnose output for one claimed incident."""

    failure_id: str
    diagnosis: str
    failure_class: str
    description: str
    service: str | None = None
    stage: str | None = None
    agent_actionable: bool
    disposition: Disposition
    planned_action: str | None = None
    reason: str
    catalog_notes: str | None = None
    metadata: dict = Field(default_factory=dict)


def diagnose_incident(
    incident: Incident,
    catalog: FailureCatalog | None = None,
) -> DiagnoseResult:
    """Map a validated incident to disposition + planned action via the catalog.

    Does not call Mefid or mutate incident status.
    """
    catalog = catalog or get_catalog()
    entry = catalog.get_failure(incident.failure_id)
    diagnosis_meta = catalog.get_diagnosis(entry.diagnosis)

    actionable = entry.agent_actionable
    planned = _PLANNED_ACTION_BY_DIAGNOSIS.get(entry.diagnosis)

    if not actionable:
        disposition = Disposition.ESCALATE
        reason = (
            f"failure {entry.id!r} is marked agent_actionable=false "
            f"(diagnosis {entry.diagnosis})"
        )
        planned = None
    elif entry.diagnosis == "DEPENDENCY_UNREACHABLE":
        # Agent cannot bring MinIO/Supabase back; surface as escalate for now.
        disposition = Disposition.ESCALATE
        reason = (
            f"dependency {entry.dependency or 'unknown'!r} unreachable; "
            "manual/infra recovery required"
        )
        planned = None
    else:
        disposition = Disposition.REMEDIATE
        reason = (
            f"diagnosis {entry.diagnosis} → planned {planned}"
            if planned
            else f"diagnosis {entry.diagnosis}; no planned action mapped yet"
        )

    return DiagnoseResult(
        failure_id=incident.failure_id,
        diagnosis=entry.diagnosis,
        failure_class=diagnosis_meta.failure_class,
        description=diagnosis_meta.description,
        service=incident.service or entry.service,
        stage=incident.stage or entry.stage,
        agent_actionable=actionable,
        disposition=disposition,
        planned_action=planned if disposition == Disposition.REMEDIATE else None,
        reason=reason,
        catalog_notes=entry.notes,
        metadata=dict(incident.metadata),
    )
