from __future__ import annotations

import json
import unittest
from pathlib import Path

from activity_ledger.execution_state import ExecutionState, ExecutionStateMachine
from activity_ledger.workflow_registry import ContractError, ProfileError, WorkflowRegistry, normalized_contract_sha256

ROOT = Path(__file__).parents[1]


class Phase4AContractTests(unittest.TestCase):
    def valid_contract(self) -> dict:
        return json.loads((ROOT / "contracts/examples/bounded-code-modification.json").read_text())

    def test_registry_profiles_and_stable_normalization(self) -> None:
        registry = WorkflowRegistry()
        normalized, first = normalized_contract_sha256(self.valid_contract())
        _, second = normalized_contract_sha256(self.valid_contract())
        self.assertEqual(first, second)
        self.assertEqual(normalized["limits"]["model"], "gpt-5.6-luna")
        self.assertEqual(registry.get("code-change-v1")["enabled"], True)
        with self.assertRaises(ProfileError): registry.get("unknown-v1")
        with self.assertRaises(ProfileError): registry.get("ros2-navigation-post-test-v1")

    def test_registry_rejects_policy_mismatches_and_forbidden_fields(self) -> None:
        registry = WorkflowRegistry()
        contract = self.valid_contract()
        contract["operation"] = "analyze"
        with self.assertRaises(ProfileError): registry.normalize(contract)
        contract = self.valid_contract()
        contract["requested_capabilities"] = ["docker_socket"]
        with self.assertRaises(ProfileError): registry.normalize(contract)
        contract = self.valid_contract()
        contract["docker_options"] = {"privileged": True}
        with self.assertRaises(ContractError): registry.normalize(contract)
        contract = self.valid_contract()
        contract["input_artifacts"] = [{"kind": "log", "path": "relative.log", "access": "read_write", "sha256": "0" * 64, "size_bytes": 0, "media_type": "text/plain", "metadata": {}}]
        with self.assertRaises(ContractError): registry.normalize(contract)

    def test_state_machine_legal_paths_and_terminal_immutability(self) -> None:
        machine = ExecutionStateMachine()
        path = [ExecutionState.VALIDATED, ExecutionState.AWAITING_EXECUTION_APPROVAL, ExecutionState.QUEUED, ExecutionState.ALLOCATED, ExecutionState.RUNNING, ExecutionState.VERIFYING, ExecutionState.AWAITING_REVIEW, ExecutionState.APPROVED, ExecutionState.CLOSING, ExecutionState.CLOSED]
        for state in path:
            machine = machine.transition(state)
        self.assertEqual(machine.state, ExecutionState.CLOSED)
        with self.assertRaises(ValueError): machine.transition(ExecutionState.RUNNING)
        with self.assertRaises(ValueError): ExecutionStateMachine().transition(ExecutionState.QUEUED)

    def test_cancellation_and_failure_require_closing(self) -> None:
        machine = ExecutionStateMachine(ExecutionState.AWAITING_EXECUTION_APPROVAL).transition(ExecutionState.CANCELLED).transition(ExecutionState.CLOSING).transition(ExecutionState.CLOSED)
        self.assertEqual(machine.state, ExecutionState.CLOSED)
        machine = ExecutionStateMachine(ExecutionState.ALLOCATED).transition(ExecutionState.FAILED).transition(ExecutionState.CLOSING).transition(ExecutionState.CLOSED)
        self.assertEqual(machine.state, ExecutionState.CLOSED)

    def test_schemas_and_profiles_parse(self) -> None:
        for path in (ROOT / "contracts").rglob("*.json"):
            json.loads(path.read_text())
        profiles = list((ROOT / "contracts/profiles").glob("*.json"))
        self.assertEqual(len(profiles), 7)
        self.assertEqual(json.loads((ROOT / "contracts/profiles/ros2-navigation-post-test-v1.json").read_text())["enabled"], False)
        self.assertEqual(json.loads((ROOT / "contracts/profiles/phase5b-bounded-codex-code-change-v2.json").read_text())["executor_profile"], "phase5b-codex-executor-v2")


if __name__ == "__main__":
    unittest.main()
