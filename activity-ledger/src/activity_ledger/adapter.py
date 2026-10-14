from __future__ import annotations

from typing import Any

from .ledger import ActivityLedger


class InternalLedgerAdapter:
    """Small internal boundary for runner-originated activity events.

    The adapter deliberately accepts only structured event payloads and writes
    through the existing ledger service; it is not a public HTTP endpoint.
    """

    def __init__(self, ledger: ActivityLedger) -> None:
        self.ledger = ledger

    def start_simulated_run(self, task_key: str) -> str:
        try:
            self.ledger.get_task(task_key)
        except KeyError:
            self.ledger.create_task(
                task_key=task_key,
                title="Simulated runner task",
                description="Disposable Phase 2A event-ingestion exercise.",
                origin_type="simulated",
            )
        return self.ledger.start_run(task_key, actor="simulated-runner", source_interface="internal-adapter")

    def ingest_runner_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if not event_type or not isinstance(payload, dict):
            raise ValueError("runner events require a type and object payload")
        self.ledger.append_event(run_id, event_type, payload)
