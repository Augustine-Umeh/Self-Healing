from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from reliability_agent.incident import Incident, IncidentStatus
from reliability_agent.main import _run


def test_run_once_no_open_incidents(capsys) -> None:
    client = AsyncMock()
    client.claim_next_open = AsyncMock(return_value=None)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("reliability_agent.main.IncidentClient", return_value=client):
        code = asyncio.run(_run(incident_id=None))

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"claimed": False, "message": "no open incidents"}


def test_run_once_claims_and_logs(capsys) -> None:
    incident = Incident(
        id=uuid4(),
        created_at=datetime.now(timezone.utc),
        status=IncidentStatus.PROCESSING,
        failure_id="embedder_down",
        diagnosis="PROCESS_DOWN",
        service="embedder",
        stage="embed-image",
        error="connection refused",
    )
    client = AsyncMock()
    client.claim_next_open = AsyncMock(return_value=incident)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("reliability_agent.main.IncidentClient", return_value=client):
        code = asyncio.run(_run(incident_id=None))

    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["claimed"] is True
    assert out["failure_id"] == "embedder_down"
    assert out["diagnosis"] == "PROCESS_DOWN"
    assert out["status"] == "processing"
    assert out["incident_id"] == str(incident.id)
