from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionState(str, Enum):
    SUBMITTED = "submitted"
    VALIDATED = "validated"
    AWAITING_EXECUTION_APPROVAL = "awaiting_execution_approval"
    QUEUED = "queued"
    ALLOCATED = "allocated"
    RUNNING = "running"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"
    CLOSING = "closing"
    CLOSED = "closed"


LEGAL_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.SUBMITTED: frozenset({ExecutionState.VALIDATED, ExecutionState.CANCELLED}),
    ExecutionState.VALIDATED: frozenset({ExecutionState.AWAITING_EXECUTION_APPROVAL, ExecutionState.CANCELLED}),
    ExecutionState.AWAITING_EXECUTION_APPROVAL: frozenset({ExecutionState.QUEUED, ExecutionState.REJECTED, ExecutionState.CANCELLED}),
    ExecutionState.QUEUED: frozenset({ExecutionState.ALLOCATED, ExecutionState.CANCELLED}),
    ExecutionState.ALLOCATED: frozenset({ExecutionState.RUNNING, ExecutionState.CANCELLED, ExecutionState.FAILED}),
    ExecutionState.RUNNING: frozenset({ExecutionState.VERIFYING, ExecutionState.FAILED, ExecutionState.CANCELLED}),
    ExecutionState.VERIFYING: frozenset({ExecutionState.AWAITING_REVIEW, ExecutionState.FAILED}),
    ExecutionState.AWAITING_REVIEW: frozenset({ExecutionState.APPROVED, ExecutionState.REJECTED, ExecutionState.FAILED}),
    ExecutionState.APPROVED: frozenset({ExecutionState.CLOSING}),
    ExecutionState.REJECTED: frozenset({ExecutionState.CLOSING}),
    ExecutionState.CANCELLED: frozenset({ExecutionState.CLOSING}),
    ExecutionState.FAILED: frozenset({ExecutionState.CLOSING}),
    ExecutionState.CLOSING: frozenset({ExecutionState.CLOSED}),
    ExecutionState.CLOSED: frozenset(),
}


@dataclass(frozen=True)
class ExecutionStateMachine:
    state: ExecutionState = ExecutionState.SUBMITTED

    def transition(self, target: ExecutionState) -> "ExecutionStateMachine":
        if target not in LEGAL_TRANSITIONS[self.state]:
            raise ValueError(f"illegal execution transition: {self.state} -> {target}")
        return ExecutionStateMachine(target)

    def can_transition(self, target: ExecutionState) -> bool:
        return target in LEGAL_TRANSITIONS[self.state]
