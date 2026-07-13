from __future__ import annotations

from uuid import uuid4

import pytest

from reliability_agent.catalog import load_catalog
from reliability_agent.incident import (
    IncidentCreate,
    IncidentStatus,
    resolve_incident,
)

CATALOG = load_catalog()


def test_resolve_fills_diagnosis_from_catalog() -> None:
    payload = IncidentCreate(
        failure_id="transcript_missing",
        media_id=uuid4(),
        error="Whisper raised",
    )
    incident = resolve_incident(payload, CATALOG)
    assert incident.diagnosis == "TRANSCRIPT_MISSING"
    assert incident.status == IncidentStatus.OPEN
    assert incident.service == "transcribe"
    assert incident.stage == "transcribe"


def test_resolve_accepts_matching_diagnosis() -> None:
    payload = {
        "failure_id": "caption_missing",
        "diagnosis": "CAPTION_MISSING",
        "error": "caption engine crashed",
    }
    incident = resolve_incident(payload, CATALOG)
    assert incident.diagnosis == "CAPTION_MISSING"
    assert incident.failure_id == "caption_missing"


def test_resolve_rejects_unknown_failure_id() -> None:
    with pytest.raises(KeyError, match="unknown failure id"):
        resolve_incident({"failure_id": "not_in_catalog"}, CATALOG)


def test_resolve_rejects_diagnosis_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match catalog"):
        resolve_incident(
            {
                "failure_id": "transcript_missing",
                "diagnosis": "CAPTION_MISSING",
            },
            CATALOG,
        )


def test_stage_override_for_global_failure() -> None:
    """Global rows (no stage) can carry stage in the incident payload."""
    payload = IncidentCreate(
        failure_id="embedder_model_not_loaded",
        stage="embed-image",
        media_id=uuid4(),
    )
    incident = resolve_incident(payload, CATALOG)
    assert incident.diagnosis == "MODEL_NOT_LOADED"
    assert incident.stage == "embed-image"
    assert incident.service == "embedder"


def test_empty_failure_id_rejected() -> None:
    with pytest.raises(ValueError, match="failure_id"):
        IncidentCreate(failure_id="  ")
