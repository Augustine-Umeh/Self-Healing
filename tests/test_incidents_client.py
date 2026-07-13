from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from reliability_agent.catalog import load_catalog
from reliability_agent.incident import IncidentStatus, validate_incident_row
from reliability_agent.incidents_client import IncidentClaimError, IncidentClient

CATALOG = load_catalog()


def _row(
    *,
    status: str = "open",
    failure_id: str = "embedder_down",
    diagnosis: str = "PROCESS_DOWN",
) -> dict:
    return {
        "id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "failure_id": failure_id,
        "diagnosis": diagnosis,
        "service": "embedder",
        "stage": "embed-image",
        "media_id": None,
        "error": "connection refused",
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_get_by_id_returns_row() -> None:
    row = _row()
    incident_id = row["id"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/incidents")
        return httpx.Response(200, json=[row])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.supabase.co/rest/v1"
    ) as http:
        client = IncidentClient(
            settings=_fake_settings(),
            client=http,
            catalog=CATALOG,
        )
        got = await client.get_by_id(incident_id)
    assert got is not None
    assert str(got.id) == incident_id
    assert got.failure_id == "embedder_down"


@pytest.mark.asyncio
async def test_list_open() -> None:
    rows = [_row(), _row()]

    def handler(request: httpx.Request) -> httpx.Response:
        assert "status=eq.open" in str(request.url)
        return httpx.Response(200, json=rows)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.supabase.co/rest/v1"
    ) as http:
        client = IncidentClient(
            settings=_fake_settings(),
            client=http,
            catalog=CATALOG,
        )
        got = await client.list_open()
    assert len(got) == 2


@pytest.mark.asyncio
async def test_claim_success() -> None:
    open_row = _row(status="open")
    claimed = {**open_row, "status": "processing"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(200, json=[claimed])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.supabase.co/rest/v1"
    ) as http:
        client = IncidentClient(
            settings=_fake_settings(),
            client=http,
            catalog=CATALOG,
        )
        got = await client.claim(open_row["id"])
    assert got.status == IncidentStatus.PROCESSING


@pytest.mark.asyncio
async def test_claim_already_taken() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.supabase.co/rest/v1"
    ) as http:
        client = IncidentClient(
            settings=_fake_settings(),
            client=http,
            catalog=CATALOG,
        )
        with pytest.raises(IncidentClaimError):
            await client.claim(uuid4())


@pytest.mark.asyncio
async def test_fetch_and_claim_hydrates() -> None:
    open_row = _row(status="open")
    claimed = {**open_row, "status": "processing"}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.method == "GET":
            return httpx.Response(200, json=[open_row])
        return httpx.Response(200, json=[claimed])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://example.supabase.co/rest/v1"
    ) as http:
        client = IncidentClient(
            settings=_fake_settings(),
            client=http,
            catalog=CATALOG,
        )
        incident = await client.fetch_and_claim(open_row["id"])

    assert incident.status == IncidentStatus.PROCESSING
    assert incident.diagnosis == "PROCESS_DOWN"
    assert incident.service == "embedder"
    assert calls["n"] == 2


def test_hydrate_rejects_unknown_failure() -> None:
    row = _row(failure_id="not_a_real_failure", diagnosis="PROCESS_DOWN")
    with pytest.raises(KeyError, match="unknown failure id"):
        validate_incident_row(row, catalog=CATALOG)


def _fake_settings():
    from config import Settings

    return Settings(
        mefid_api_url="http://localhost:8000",
        observe_interval_seconds=60,
        stuck_processing_minutes=30,
        count_delta_tolerance=0,
        supabase_url="https://example.supabase.co",
        supabase_role_key="test-key",
        supabase_admin_api_key="test-admin",
    )
