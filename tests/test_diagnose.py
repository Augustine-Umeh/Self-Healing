from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from reliability_agent.catalog import get_catalog
from reliability_agent.diagnose import Disposition, diagnose_incident
from reliability_agent.incident import Incident, IncidentStatus

CATALOG = get_catalog()


def _incident(failure_id: str, **kwargs) -> Incident:
    entry = CATALOG.get_failure(failure_id)
    defaults = dict(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        status=IncidentStatus.PROCESSING,
        failure_id=failure_id,
        diagnosis=entry.diagnosis,
        service=entry.service,
        stage=entry.stage,
    )
    defaults.update(kwargs)
    return Incident(**defaults)


def test_diagnose_actionable_remediate() -> None:
    result = diagnose_incident(_incident("embed_images_inference_failed"), CATALOG)
    assert result.diagnosis == "IMAGE_EMBEDDINGS_MISSING"
    assert result.failure_class == "DEGRADED_MULTIMODAL"
    assert result.disposition == Disposition.REMEDIATE
    assert result.planned_action == "reembed_images"
    assert result.agent_actionable is True


def test_diagnose_not_actionable_escalates() -> None:
    result = diagnose_incident(_incident("extract_video_unopenable"), CATALOG)
    assert result.diagnosis == "FRAMES_MISSING"
    assert result.disposition == Disposition.ESCALATE
    assert result.planned_action is None
    assert result.agent_actionable is False


def test_diagnose_process_down_restart() -> None:
    result = diagnose_incident(_incident("embedder_down"), CATALOG)
    assert result.diagnosis == "PROCESS_DOWN"
    assert result.disposition == Disposition.REMEDIATE
    assert result.planned_action == "restart_service"


def test_diagnose_dependency_escalates() -> None:
    result = diagnose_incident(_incident("minio_unreachable"), CATALOG)
    assert result.diagnosis == "DEPENDENCY_UNREACHABLE"
    assert result.disposition == Disposition.ESCALATE
    assert result.planned_action is None


def test_diagnose_unknown_failure_raises() -> None:
    bad = Incident(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        status=IncidentStatus.PROCESSING,
        failure_id="not_in_catalog",
        diagnosis="PROCESS_DOWN",
    )
    with pytest.raises(KeyError):
        diagnose_incident(bad, CATALOG)
