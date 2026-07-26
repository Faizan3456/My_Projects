#!/usr/bin/env python3
"""Walk the whole loop against a running API, with no provider keys needed.

    python scripts/demo.py [http://localhost:8000]

Creates a project, runs a turn with the offline agent, forces a limit so a
handover snapshot is written, then continues with another agent to show the work
resuming from shared memory.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# Against a protected deployment, authenticate as a service rather than a user:
#   SERVICE_TOKEN=... python scripts/demo.py https://agents.openedgetechnologies.com/api
HEADERS = (
    {"X-Service-Token": os.environ["SERVICE_TOKEN"]}
    if os.environ.get("SERVICE_TOKEN")
    else {}
)


def show(title: str, body: object = "") -> None:
    print(f"\n\033[1m{title}\033[0m")
    if body:
        print(body)


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60, headers=HEADERS) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        show("Service", health.json())

        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        project = client.post(
            "/projects",
            json={
                "name": f"Demo project {stamp}",
                "description": "Created by scripts/demo.py",
                "current_task": "Build the ledger service",
                "next_step": "Define the ledger tables",
            },
        )
        project.raise_for_status()
        pid = project.json()["id"]
        show("Project created", pid)

        first = client.post(
            f"/projects/{pid}/turns",
            json={"agent_name": "echo", "message": "Draft the ledger tables"},
        )
        first.raise_for_status()
        show("Turn 1", f"status={first.json()['status']} · {first.json()['summary']}")

        limited = client.post(
            f"/projects/{pid}/turns",
            json={"agent_name": "echo", "message": "SIMULATE_LIMIT"},
        )
        limited.raise_for_status()
        handover = limited.json()["handover"]
        show(
            "Turn 2 hit a limit",
            f"reason={handover['reason']}\n"
            f"resume at: {handover['suggested_next_step']}\n"
            f"context status: {limited.json()['context']['status']}",
        )

        # In a real setup this would be a different provider. With no keys
        # configured, the same offline agent demonstrates the resume path.
        resumed = client.post(
            f"/projects/{pid}/turns", json={"agent_name": "echo", "message": ""}
        )
        resumed.raise_for_status()
        show(
            "Turn 3 resumed",
            f"status={resumed.json()['status']} · "
            f"context={resumed.json()['context']['status']}",
        )

        events = client.get(f"/projects/{pid}/events").json()
        show("History (newest first)")
        for event in events:
            print(f"  {event['type']:<15} {event['agent_name'] or 'user':<8} "
                  f"{event['summary'][:70]}")

    print(f"\nOpen http://localhost:3000 and select 'Demo project {stamp}'.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"Cannot reach the API at {BASE}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
