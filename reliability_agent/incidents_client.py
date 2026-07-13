"""Supabase client for fetching and claiming reliability incidents."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx

from config import Settings, get_settings
from reliability_agent.catalog import FailureCatalog, get_catalog
from reliability_agent.incident import (
    Incident,
    IncidentRow,
    IncidentStatus,
    validate_incident_row,
)


class IncidentClaimError(RuntimeError):
    """Raised when an incident cannot be claimed (missing or already claimed)."""


class IncidentClient:
    """Read/claim ``public.incidents`` via Supabase REST."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        catalog: FailureCatalog | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.catalog = catalog or get_catalog()
        self._owns_client = client is None
        base = self.settings.supabase_url.rstrip("/")
        headers = {
            "apikey": self.settings.supabase_role_key,
            "Authorization": f"Bearer {self.settings.supabase_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = client or httpx.AsyncClient(
            base_url=f"{base}/rest/v1",
            headers=headers,
            timeout=30.0,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> IncidentClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def get_by_id(self, incident_id: UUID | str) -> IncidentRow | None:
        response = await self._client.get(
            "/incidents",
            params={"id": f"eq.{incident_id}", "select": "*"},
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        return IncidentRow.model_validate(rows[0])

    async def list_open(self, *, limit: int = 20) -> list[IncidentRow]:
        response = await self._client.get(
            "/incidents",
            params={
                "status": f"eq.{IncidentStatus.OPEN.value}",
                "select": "*",
                "order": "created_at.asc",
                "limit": str(limit),
            },
        )
        response.raise_for_status()
        return [IncidentRow.model_validate(row) for row in response.json()]

    async def claim(self, incident_id: UUID | str) -> IncidentRow:
        """Atomically move an open incident to ``processing``.

        Raises IncidentClaimError if the row is missing or already claimed.
        """
        response = await self._client.patch(
            "/incidents",
            params={
                "id": f"eq.{incident_id}",
                "status": f"eq.{IncidentStatus.OPEN.value}",
            },
            json={"status": IncidentStatus.PROCESSING.value},
            headers={"Prefer": "return=representation"},
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise IncidentClaimError(
                f"incident {incident_id} is not open (missing or already claimed)"
            )
        return IncidentRow.model_validate(rows[0])

    async def update_status(
        self,
        incident_id: UUID | str,
        status: IncidentStatus,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> IncidentRow:
        payload: dict[str, Any] = {"status": status.value}
        if metadata is not None:
            payload["metadata"] = metadata
        response = await self._client.patch(
            "/incidents",
            params={"id": f"eq.{incident_id}"},
            json=payload,
            headers={"Prefer": "return=representation"},
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise KeyError(f"incident not found: {incident_id}")
        return IncidentRow.model_validate(rows[0])

    async def fetch_and_claim(self, incident_id: UUID | str) -> Incident:
        """Load, validate against catalog, claim, return hydrated Incident."""
        row = await self.get_by_id(incident_id)
        if row is None:
            raise KeyError(f"incident not found: {incident_id}")
        # Validate catalog before claiming so we don't claim bad rows.
        validate_incident_row(row, catalog=self.catalog)
        claimed = await self.claim(incident_id)
        return validate_incident_row(claimed, catalog=self.catalog)

    async def claim_next_open(self) -> Incident | None:
        """Claim the oldest open incident, or None if the queue is empty."""
        open_rows = await self.list_open(limit=1)
        if not open_rows:
            return None
        try:
            return await self.fetch_and_claim(open_rows[0].id)
        except IncidentClaimError:
            return None
