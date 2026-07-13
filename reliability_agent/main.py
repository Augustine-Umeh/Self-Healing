"""CLI: claim the next open incident (or a specific id) and log it."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from reliability_agent.incidents_client import IncidentClaimError, IncidentClient


async def _run(*, incident_id: str | None) -> int:
    async with IncidentClient() as client:
        try:
            if incident_id:
                incident = await client.fetch_and_claim(incident_id)
            else:
                incident = await client.claim_next_open()
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        except IncidentClaimError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if incident is None:
        print(json.dumps({"claimed": False, "message": "no open incidents"}))
        return 0

    payload = {
        "claimed": True,
        "incident_id": str(incident.id),
        "status": incident.status.value,
        "failure_id": incident.failure_id,
        "diagnosis": incident.diagnosis,
        "service": incident.service,
        "stage": incident.stage,
        "media_id": str(incident.media_id) if incident.media_id else None,
        "error": incident.error,
        "created_at": incident.created_at.isoformat(),
    }
    print(json.dumps(payload, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Claim a reliability incident and print diagnosis (no remediation yet)."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim the oldest open incident and exit",
    )
    parser.add_argument(
        "--incident-id",
        type=str,
        default=None,
        help="Claim a specific incident id instead of the oldest open one",
    )
    args = parser.parse_args()

    if not args.once and args.incident_id is None:
        parser.error("pass --once and/or --incident-id")

    raise SystemExit(asyncio.run(_run(incident_id=args.incident_id)))


if __name__ == "__main__":
    main()
