from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID


ROOT = Path(__file__).parents[2]
PROFILE_DIR = ROOT / "contracts" / "profiles"
FORBIDDEN_KEYS = {
    "docker_options", "container_image", "image", "mounts", "docker_socket", "database_credentials", "api_keys", "auth_json",
    "privileged", "host_network", "shell_command", "shell", "argv", "environment", "credentials", "secret_path", "host_path",
    "model_endpoint", "dependency_install", "remote_push", "merge", "force", "tag", "commit", "push", "deployment", "acl_administration",
}
PHASE5B_PROFILE = "phase5b-bounded-codex-code-change-v1"
PHASE5B_EXECUTOR = "phase5b-codex-executor-v1"
PHASE5B_V2_PROFILE = "phase5b-bounded-codex-code-change-v2"
PHASE5B_V2_EXECUTOR = "phase5b-codex-executor-v2"
PHASE5B_MODEL = "phase5b_model_profile_v1"
PHASE5B_NETWORK = "phase5b_model_egress_v1"
PHASE5B_VALIDATION = "phase5b-disposable-python-unit-v1"
PHASE5B_CAPABILITIES = ["git_read", "git_write_workspace", "test_structured_argv"]
PHASE5B_ARTIFACTS = ["phase5b_codex_executor_result", "phase5b_codex_patch"]
PHASE5B_VALIDATION_PLAN = {
    "command_id": "unit",
    "argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."],
    "cwd_relative": ".",
    "timeout_seconds": 45,
    "warnings_as_errors": False,
}
PHASE5B_FAILURES = {
    "work_order_rejected", "repository_binding_failed", "instruction_validation_failed", "repository_policy_violation",
    "model_timeout", "model_error", "malformed_model_response", "tool_limit_exceeded", "output_limit_exceeded",
    "validation_failed", "validation_timeout", "git_policy_violation", "git_commit_failed", "evidence_generation_failed",
    "evidence_publication_failed",
}
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_RE = re.compile(r"^[0-9a-f]{40}$")
_RELATIVE_RE = re.compile(r"^[^/\\\x00][^\\\x00]*$")


class ProfileError(ValueError):
    pass


class ContractError(ValueError):
    pass


class WorkflowRegistry:
    def __init__(self, profile_dir: Path = PROFILE_DIR) -> None:
        self.profile_dir = Path(profile_dir)
        self._profiles = {p.stem: json.loads(p.read_text()) for p in sorted(self.profile_dir.glob("*.json"))}

    def get(self, name: str) -> dict[str, Any]:
        profile = self._profiles.get(name)
        if profile is None:
            raise ProfileError(f"unknown workflow profile: {name}")
        version = profile.get("profile_version")
        if version not in {"workflow-profile-v1", "workflow-profile-v2"}:
            if version == "workflow-profile-v3":
                self._validate_v3_profile(profile)
            else:
                raise ProfileError(f"unsupported workflow profile version: {version}")
        if version == "workflow-profile-v2":
            self._validate_v2_profile(profile)
        if not profile.get("enabled", False):
            raise ProfileError(f"workflow profile is disabled: {name}")
        image = profile.get("pinned_executor_image", "")
        if "@sha256:" not in image or len(image.rsplit("@sha256:", 1)[1]) != 64:
            raise ProfileError("executor image must be digest pinned")
        return profile

    @staticmethod
    def _validate_v2_profile(profile: dict[str, Any]) -> None:
        expected_keys = {
            "profile_version", "profile_name", "allowed_operations", "executor_profile",
            "pinned_executor_image", "accepted_input_kinds", "workspace_access",
            "preprocessor_profiles", "validation_profile", "output_contract",
            "allowed_capabilities", "resource_limits", "enabled",
        }
        if set(profile) != expected_keys or profile.get("profile_version") != "workflow-profile-v2":
            raise ProfileError("workflow-profile-v2 shape is invalid")
        if (
            not isinstance(profile.get("allowed_operations"), list)
            or not profile["allowed_operations"]
            or not isinstance(profile.get("executor_profile"), str)
            or not isinstance(profile.get("accepted_input_kinds"), list)
            or not isinstance(profile.get("allowed_capabilities"), list)
            or not isinstance(profile.get("enabled"), bool)
        ):
            raise ProfileError("workflow-profile-v2 fields are invalid")
        limits = profile.get("resource_limits")
        output = profile.get("output_contract")
        if not isinstance(limits, dict) or not isinstance(output, dict):
            raise ProfileError("workflow-profile-v2 immutable policy is incomplete")
        if set(limits) != {"model", "timeout_seconds", "maximum_attempts", "network_policy"}:
            raise ProfileError("workflow-profile-v2 resource policy shape is invalid")
        if set(output) != {"schema_name", "schema_version", "required_artifact_types"}:
            raise ProfileError("workflow-profile-v2 output policy shape is invalid")
        if not isinstance(limits.get("model"), str):
            raise ProfileError("workflow-profile-v2 model policy is invalid")
        timeout = limits.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
            raise ProfileError("workflow-profile-v2 timeout policy is invalid")
        if limits.get("maximum_attempts") != 1:
            raise ProfileError("workflow-profile-v2 attempt policy is invalid")
        if limits.get("network_policy") not in {"none", "runner_egress"}:
            raise ProfileError("workflow-profile-v2 network policy is invalid")
        if not isinstance(output.get("schema_name"), str) or not isinstance(output.get("schema_version"), str):
            raise ProfileError("workflow-profile-v2 output schema policy is invalid")
        artifact_types = output.get("required_artifact_types")
        if (
            not isinstance(artifact_types, list)
            or not artifact_types
            or any(not isinstance(value, str) or not value for value in artifact_types)
            or len(set(artifact_types)) != len(artifact_types)
        ):
            raise ProfileError("workflow-profile-v2 artifact policy is invalid")

    def normalize(self, contract: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(contract, dict):
            raise ContractError("execution contract must be an object")
        self._reject_forbidden_keys(contract)
        required = {"contract_version", "idempotency_key", "task_key", "operation", "workflow_template", "executor_profile", "requested_by", "objective", "workspace", "input_artifacts", "context_references", "output_contract", "validation_profile", "limits", "requested_capabilities", "created_at"}
        missing = required - contract.keys()
        if missing:
            raise ContractError(f"missing contract fields: {sorted(missing)}")
        if contract["contract_version"] == "execution-request-v2":
            required_v2 = {"acceptance_criteria", "permitted_context_manifest"}
            allowed_v2 = required | required_v2 | ({"phase5b_policy"} if "phase5b_policy" in contract else set())
            if set(contract) != allowed_v2:
                raise ContractError("execution-request-v2 fields are not exact")
            self._validate_task_delivery(contract["objective"], contract["acceptance_criteria"], contract["permitted_context_manifest"])
        elif contract["contract_version"] != "execution-request-v1":
            raise ContractError("unsupported contract version")
        if contract["operation"] not in {"analyze", "review", "modify", "verify"}:
            raise ContractError("unsupported operation")
        profile = self.get(contract["workflow_template"])
        if profile.get("profile_version") == "workflow-profile-v3":
            return self._normalize_v3_contract(contract, profile)
        if contract["operation"] not in profile["allowed_operations"]:
            raise ProfileError("operation is not allowed by workflow profile")
        if contract["executor_profile"] != profile["executor_profile"]:
            raise ProfileError("executor profile mismatch")
        workspace = contract["workspace"]
        if workspace.get("access") != profile["workspace_access"]:
            raise ProfileError("workspace access mismatch")
        if workspace.get("repository_path") and not Path(workspace["repository_path"]).is_absolute():
            raise ContractError("repository path must be absolute")
        for artifact in contract["input_artifacts"]:
            if artifact.get("access") != "read_only" or not Path(artifact.get("path", "")).is_absolute():
                raise ContractError("external input artifacts must be absolute read-only paths")
            if artifact.get("kind") not in profile["accepted_input_kinds"]:
                raise ProfileError(f"input kind is not accepted: {artifact.get('kind')}")
        requested = set(contract["requested_capabilities"])
        if not requested <= set(profile["allowed_capabilities"]):
            raise ProfileError("requested capability is not allowed")
        limits = dict(contract["limits"])
        if profile.get("profile_version") == "workflow-profile-v2":
            policy_limits = profile["resource_limits"]
            policy_output = profile["output_contract"]
            if limits.get("model") != policy_limits["model"]:
                raise ProfileError("model violates profile policy")
            timeout = limits.get("timeout_seconds")
            if isinstance(timeout, bool) or timeout != policy_limits["timeout_seconds"]:
                raise ProfileError("timeout violates profile policy")
            if limits.get("maximum_attempts") != policy_limits["maximum_attempts"]:
                raise ProfileError("maximum attempts violate profile policy")
            if limits.get("network_policy") != policy_limits["network_policy"]:
                raise ProfileError("network policy violates profile policy")
            output_contract = contract["output_contract"]
            if output_contract.get("schema_name") != policy_output["schema_name"] or output_contract.get("schema_version") != policy_output["schema_version"]:
                raise ProfileError("output schema violates profile policy")
            artifact_types = output_contract.get("required_artifact_types")
            expected_artifact_types = policy_output["required_artifact_types"]
            if (
                not isinstance(artifact_types, list)
                or any(not isinstance(value, str) for value in artifact_types)
                or len(set(artifact_types)) != len(artifact_types)
                or set(artifact_types) != set(expected_artifact_types)
            ):
                raise ProfileError("required artifact types violate profile policy")
            if contract["requested_capabilities"] != profile["allowed_capabilities"]:
                raise ProfileError("requested capability is not exactly allowed by profile")
            return json.loads(json.dumps(contract, sort_keys=True))
        defaults = {"model": "gpt-5.6-luna", "reasoning_effort": "low", "maximum_attempts": 1, "network_policy": profile["network_policy"]}
        for key, value in defaults.items():
            limits.setdefault(key, value)
        if limits["maximum_attempts"] != 1 or limits["network_policy"] != profile["network_policy"]:
            raise ProfileError("limits violate profile policy")
        normalized = dict(contract)
        normalized["limits"] = limits
        normalized["requested_capabilities"] = sorted(requested)
        return json.loads(json.dumps(normalized, sort_keys=True))

    @staticmethod
    def _validate_v3_profile(profile: dict[str, Any]) -> None:
        expected = {
            "profile_version", "profile_name", "allowed_operations", "executor_profile", "pinned_executor_image",
            "accepted_input_kinds", "workspace_access", "preprocessor_profiles", "validation_profile", "output_contract",
            "allowed_capabilities", "model_policy", "transport_policy", "network_policy", "resource_limits",
            "instruction_policy", "validation_policy", "git_policy", "repository_policy", "enabled",
        }
        if set(profile) != expected or profile.get("profile_version") != "workflow-profile-v3":
            raise ProfileError("workflow-profile-v3 shape is invalid")
        if profile.get("profile_name") not in {PHASE5B_PROFILE, PHASE5B_V2_PROFILE} or profile.get("executor_profile") not in {PHASE5B_EXECUTOR, PHASE5B_V2_EXECUTOR}:
            raise ProfileError("workflow-profile-v3 identity is invalid")
        if profile.get("allowed_operations") != ["modify"] or profile.get("accepted_input_kinds") != ["repository", "text"]:
            raise ProfileError("workflow-profile-v3 operation or input policy is invalid")
        if profile.get("workspace_access") != "leased_write_worktree" or profile.get("preprocessor_profiles") != []:
            raise ProfileError("workflow-profile-v3 workspace policy is invalid")
        if profile.get("validation_profile") != PHASE5B_VALIDATION or profile.get("allowed_capabilities") != PHASE5B_CAPABILITIES:
            raise ProfileError("workflow-profile-v3 capability policy is invalid")
        if profile.get("pinned_executor_image", "").rsplit("@sha256:", 1)[-1].__len__() != 64:
            raise ProfileError("workflow-profile-v3 executor image is not digest pinned")
        expected_version = "2" if profile.get("profile_name") == PHASE5B_V2_PROFILE else "1"
        expected_executor = PHASE5B_V2_EXECUTOR if expected_version == "2" else PHASE5B_EXECUTOR
        if profile.get("executor_profile") != expected_executor or profile.get("output_contract") != {"schema_name": "phase5b-codex-executor-result", "schema_version": expected_version, "required_artifact_types": PHASE5B_ARTIFACTS}:
            raise ProfileError("workflow-profile-v3 output policy is invalid")
        if profile.get("model_policy") != {"policy_id": "phase5b_model_policy_v1", "model_profile_id": PHASE5B_MODEL, "caller_selectable": False, "allow_future_local_worker": True}:
            raise ProfileError("workflow-profile-v3 model policy is invalid")
        if profile.get("transport_policy") != {"policy_id": "phase5b_model_transport_v1", "endpoint_binding": "protected_deployment_configuration", "caller_selectable": False, "approved_endpoint_count": 1}:
            raise ProfileError("workflow-profile-v3 transport policy is invalid")
        if profile.get("network_policy") != PHASE5B_NETWORK:
            raise ProfileError("workflow-profile-v3 network policy is invalid")
        limits = profile.get("resource_limits")
        expected_limits = {
            "overall_timeout_seconds": 180, "model_deadline_seconds": 120, "validation_deadline_seconds": 45, "maximum_attempts": 1,
            "max_model_iterations": 8, "max_tool_calls": 32, "max_changed_files": 8, "max_total_changed_bytes": 32768,
            "max_changed_file_bytes": 8192, "max_patch_bytes": 65536, "max_validation_commands": 1, "max_stdout_bytes": 16384,
            "max_stderr_bytes": 16384, "max_instruction_files": 1, "max_instruction_bytes": 16384, "max_model_summary_bytes": 16384,
            "max_result_bytes": 131072, "max_failure_bytes": 32768, "max_commit_message_bytes": 200,
        }
        if limits != expected_limits or any(isinstance(v, bool) for v in limits.values()):
            raise ProfileError("workflow-profile-v3 resource policy is invalid")
        if profile.get("instruction_policy") != {"policy_id": "root-agents-only-v1", "allowed_paths": ["AGENTS.md"], "nested_allowed": False, "require_sha256": True, "max_files": 1, "max_bytes": 16384}:
            raise ProfileError("workflow-profile-v3 instruction policy is invalid")
        if profile.get("validation_policy") != {"plan_id": PHASE5B_VALIDATION, "command_form": "structured_argv", "shell_allowed": False, "caller_commands_allowed": False, "repository_commands_allowed": False, "max_commands": 1, "max_stdout_bytes": 16384, "max_stderr_bytes": 16384, "warnings_as_errors_controlled": True}:
            raise ProfileError("workflow-profile-v3 validation policy is invalid")
        if profile.get("git_policy") != {"output_policy": "local-commit-no-remote-v1", "local_commit_required": True, "remote_push_allowed": False, "merge_allowed": False, "force_allowed": False, "tag_creation_allowed": False, "hooks_enabled": False}:
            raise ProfileError("workflow-profile-v3 git policy is invalid")
        if profile.get("repository_policy") != {"submodules_allowed": False, "lfs_allowed": False, "nested_repositories_allowed": False, "sparse_checkout_allowed": False, "alternates_allowed": False, "symlinked_root_allowed": False, "special_files_allowed": False, "dependency_install_allowed": False}:
            raise ProfileError("workflow-profile-v3 repository policy is invalid")

    @staticmethod
    def _normalize_v3_contract(contract: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if contract["contract_version"] == "execution-request-v2":
            return WorkflowRegistry._normalize_v3_contract_v2(contract, profile)
        if contract["operation"] != "modify" or contract["executor_profile"] != PHASE5B_EXECUTOR:
            raise ProfileError("Phase 5B operation or executor mismatch")
        if contract["workspace"] != {"access": "leased_write_worktree"}:
            raise ProfileError("Phase 5B workspace must be allocator-derived")
        if contract["input_artifacts"]:
            raise ProfileError("Phase 5B first profile accepts no input artifacts")
        if contract["validation_profile"] != PHASE5B_VALIDATION:
            raise ProfileError("Phase 5B validation profile mismatch")
        if contract["requested_capabilities"] != PHASE5B_CAPABILITIES:
            raise ProfileError("Phase 5B capabilities must exactly match the profile")
        limits = contract["limits"]
        if any(isinstance(limits.get(key), bool) for key in ("timeout_seconds", "maximum_attempts")):
            raise ContractError("Phase 5B integer policy fields cannot be boolean")
        if limits.get("model") != PHASE5B_MODEL or limits.get("network_policy") != PHASE5B_NETWORK or limits.get("timeout_seconds") != 180 or limits.get("maximum_attempts") != 1:
            raise ProfileError("Phase 5B resource policy mismatch")
        output = contract["output_contract"]
        if output.get("output_directory") != "/phase5b/derived" or output.get("schema_name") != "phase5b-codex-executor-result" or output.get("schema_version") != "1" or output.get("required_artifact_types") != PHASE5B_ARTIFACTS:
            raise ProfileError("Phase 5B output policy mismatch")
        normalized = json.loads(json.dumps(contract, sort_keys=True))
        normalized["phase5b_policy"] = {
            "model_policy_id": PHASE5B_MODEL,
            "transport_policy_id": "phase5b_model_transport_v1",
            "network_policy": PHASE5B_NETWORK,
            "validation_plan_id": PHASE5B_VALIDATION,
            "resource_limits": profile["resource_limits"],
            "instruction_policy": profile["instruction_policy"],
            "validation_policy": profile["validation_policy"],
            "git_policy": profile["git_policy"],
            "repository_policy": profile["repository_policy"],
        }
        return normalized

    @staticmethod
    def _normalize_v3_contract_v2(contract: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        if profile.get("profile_name") != PHASE5B_V2_PROFILE or contract["workflow_template"] != PHASE5B_V2_PROFILE or contract["executor_profile"] != PHASE5B_V2_EXECUTOR:
            raise ProfileError("Phase 5B v2 profile binding mismatch")
        if contract["operation"] != "modify" or contract["workspace"] != {"access": "leased_write_worktree"} or contract["input_artifacts"] or contract["context_references"]:
            raise ProfileError("Phase 5B v2 workspace or input policy mismatch")
        if contract["validation_profile"] != PHASE5B_VALIDATION or contract["requested_capabilities"] != PHASE5B_CAPABILITIES:
            raise ProfileError("Phase 5B v2 execution policy mismatch")
        limits = contract["limits"]
        if any(isinstance(limits.get(key), bool) for key in ("timeout_seconds", "maximum_attempts")) or limits != {"model": PHASE5B_MODEL, "reasoning_effort": limits.get("reasoning_effort"), "timeout_seconds": 180, "maximum_attempts": 1, "network_policy": PHASE5B_NETWORK}:
            raise ProfileError("Phase 5B v2 resource policy mismatch")
        if contract["output_contract"] != {"schema_name": "phase5b-codex-executor-result", "schema_version": "2", "output_directory": "/phase5b/derived", "retain": True, "required_artifact_types": PHASE5B_ARTIFACTS}:
            raise ProfileError("Phase 5B v2 output policy mismatch")
        normalized = json.loads(json.dumps(contract, sort_keys=True))
        normalized["phase5b_policy"] = {"model_policy_id": PHASE5B_MODEL, "transport_policy_id": "phase5b_model_transport_v1", "network_policy": PHASE5B_NETWORK, "validation_plan_id": PHASE5B_VALIDATION, "resource_limits": profile["resource_limits"], "instruction_policy": profile["instruction_policy"], "validation_policy": profile["validation_policy"], "git_policy": profile["git_policy"], "repository_policy": profile["repository_policy"], "delivery_version": "phase5b-task-delivery-v2"}
        return normalized

    @staticmethod
    def _validate_task_delivery(objective: Any, criteria: Any, context: Any) -> None:
        if not isinstance(objective, str) or not 1 <= len(objective.encode("utf-8")) <= 8192 or "\x00" in objective or any(ord(char) < 32 and char not in "\n\r\t" for char in objective):
            raise ContractError("objective is invalid or exceeds UTF-8 byte limit")
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 16:
            raise ContractError("acceptance criteria count is invalid")
        criterion_ids: set[str] = set()
        for criterion in criteria:
            if not isinstance(criterion, dict) or set(criterion) != {"criterion_id", "statement", "required"}:
                raise ContractError("acceptance criterion shape is invalid")
            identifier = criterion["criterion_id"]
            statement = criterion["statement"]
            required = criterion["required"]
            if not isinstance(identifier, str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", identifier) is None or identifier in criterion_ids:
                raise ContractError("acceptance criterion id is invalid or duplicated")
            if not isinstance(statement, str) or not 1 <= len(statement.encode("utf-8")) <= 2048 or "\x00" in statement:
                raise ContractError("acceptance criterion statement is invalid")
            if not isinstance(required, bool):
                raise ContractError("acceptance criterion required flag is invalid")
            criterion_ids.add(identifier)
        if not isinstance(context, list) or len(context) > 32:
            raise ContractError("permitted context count is invalid")
        context_ids: set[str] = set(); paths: set[str] = set(); folded: set[str] = set(); total = 0
        for entry in context:
            if not isinstance(entry, dict) or set(entry) != {"context_id", "relative_path", "sha256", "size_bytes", "media_type", "purpose"}:
                raise ContractError("permitted context entry shape is invalid")
            if not isinstance(entry["context_id"], str) or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", entry["context_id"]) is None or entry["context_id"] in context_ids:
                raise ContractError("permitted context id is invalid")
            path = entry["relative_path"]
            if not isinstance(path, str) or not 1 <= len(path) <= 255 or path.startswith("/") or "\\" in path or "\x00" in path or any(part in {"", ".", "..", ".git"} for part in path.split("/")):
                raise ContractError("permitted context path is unsafe")
            if path in paths or path.casefold() in folded:
                raise ContractError("permitted context path is duplicated or case-colliding")
            WorkflowRegistry._require_sha(entry["sha256"], "permitted context sha256")
            WorkflowRegistry._require_bounded_int(entry["size_bytes"], 0, 65536, "permitted context size")
            if not isinstance(entry["media_type"], str) or not 1 <= len(entry["media_type"]) <= 128 or not isinstance(entry["purpose"], str) or not 1 <= len(entry["purpose"].encode("utf-8")) <= 512:
                raise ContractError("permitted context metadata is invalid")
            context_ids.add(entry["context_id"]); paths.add(path); folded.add(path.casefold()); total += entry["size_bytes"]
        if total > 262144:
            raise ContractError("permitted context exceeds total size limit")

    @staticmethod
    def validate_phase5b_work_order(order: dict[str, Any]) -> dict[str, Any]:
        required = {
            "schema_name", "schema_version", "request_id", "claim_id", "run_id", "task_key", "contract_sha256", "controller_id",
            "attempt_number", "workflow_template", "executor_profile", "model_profile", "repository_registration_id", "allocation_id",
            "worktree_id", "baseline_commit", "task_branch", "instruction_manifest", "validation_plan_id", "validation_plan_sha256",
            "validation_commands", "resource_limits", "executor_deadline_unix_seconds", "output_policy", "recipe",
        }
        if not isinstance(order, dict) or set(order) != required:
            raise ContractError("Phase 5B work order fields are not exact")
        if order["schema_name"] != "phase5b-codex-work-order" or order["schema_version"] != "1":
            raise ContractError("Phase 5B work order schema identity is invalid")
        for key in ("request_id", "claim_id", "run_id", "allocation_id", "worktree_id"):
            WorkflowRegistry._require_uuid(order[key], key)
        if not isinstance(order["task_key"], str) or re.fullmatch(r"TASK-[0-9]{8}-[0-9]{3}", order["task_key"]) is None:
            raise ContractError("Phase 5B task key is invalid")
        WorkflowRegistry._require_sha(order["contract_sha256"], "contract_sha256")
        WorkflowRegistry._require_sha(order["validation_plan_sha256"], "validation_plan_sha256")
        WorkflowRegistry._require_git(order["baseline_commit"], "baseline_commit")
        if not isinstance(order["controller_id"], str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", order["controller_id"]) is None:
            raise ContractError("Phase 5B controller identity is invalid")
        if order["attempt_number"] != 1 or order["workflow_template"] != PHASE5B_PROFILE or order["executor_profile"] != PHASE5B_EXECUTOR or order["model_profile"] != PHASE5B_MODEL or order["validation_plan_id"] != PHASE5B_VALIDATION or order["output_policy"] != "local-commit-no-remote-v1" or order["recipe"] != "phase5b-codex-code-change-v1":
            raise ProfileError("Phase 5B work order policy identity mismatch")
        if not isinstance(order["task_branch"], str) or not order["task_branch"] or order["task_branch"] == "main" or order["task_branch"].startswith("/") or "\x00" in order["task_branch"] or "\\" in order["task_branch"] or any(ord(char) < 32 for char in order["task_branch"]):
            raise ContractError("Phase 5B task branch is invalid")
        manifest = order["instruction_manifest"]
        if not isinstance(manifest, list) or len(manifest) > 1:
            raise ContractError("Phase 5B instruction manifest count is invalid")
        for entry in manifest:
            if set(entry) != {"relative_path", "sha256", "size_bytes", "media_type"} or entry["relative_path"] != "AGENTS.md" or entry["media_type"] != "text/markdown":
                raise ContractError("Phase 5B instruction manifest is invalid")
            WorkflowRegistry._require_sha(entry["sha256"], "instruction sha256")
            WorkflowRegistry._require_bounded_int(entry["size_bytes"], 1, 16384, "instruction size")
        commands = order["validation_commands"]
        if not isinstance(commands, list) or len(commands) != 1:
            raise ContractError("Phase 5B validation command count is invalid")
        command = commands[0]
        if set(command) != {"command_id", "argv", "cwd_relative", "timeout_seconds", "warnings_as_errors"} or command["command_id"] != "unit" or command["cwd_relative"] != "." or command["timeout_seconds"] != 45 or not isinstance(command["warnings_as_errors"], bool):
            raise ContractError("Phase 5B validation command policy is invalid")
        argv = command["argv"]
        if not isinstance(argv, list) or not 1 <= len(argv) <= 8 or argv[0] in {"sh", "bash", "dash", "zsh"} or any(arg in {"-c", "--command"} for arg in argv) or any(not isinstance(arg, str) or not arg or any(char in arg for char in ";&|$`()<>\\\\") for arg in argv):
            raise ContractError("Phase 5B validation argv is invalid")
        limits = order["resource_limits"]
        expected_limits = {
            "overall_timeout_seconds": 180, "model_deadline_seconds": 120, "validation_deadline_seconds": 45, "max_model_iterations": 8,
            "max_tool_calls": 32, "max_changed_files": 8, "max_total_changed_bytes": 32768, "max_changed_file_bytes": 8192,
            "max_patch_bytes": 65536, "max_validation_commands": 1, "max_stdout_bytes": 16384, "max_stderr_bytes": 16384,
            "max_instruction_files": 1, "max_instruction_bytes": 16384, "max_model_summary_bytes": 16384, "max_result_bytes": 131072,
            "max_failure_bytes": 32768, "max_commit_message_bytes": 200,
        }
        if limits != expected_limits or any(isinstance(value, bool) or not isinstance(value, int) for value in limits.values()):
            raise ProfileError("Phase 5B resource ceilings are invalid")
        WorkflowRegistry._require_bounded_int(order["executor_deadline_unix_seconds"], 1, 2147483647, "executor deadline")
        return json.loads(json.dumps(order, sort_keys=True))

    @staticmethod
    def validate_phase5b_work_order_v2(order: dict[str, Any]) -> dict[str, Any]:
        required = {"schema_name", "schema_version", "request_id", "claim_id", "run_id", "task_key", "contract_sha256", "controller_id", "attempt_number", "workflow_template", "executor_profile", "model_profile", "repository_registration_id", "allocation_id", "worktree_id", "baseline_commit", "task_branch", "instruction_manifest", "validation_plan_id", "validation_plan_sha256", "validation_commands", "resource_limits", "executor_deadline_unix_seconds", "output_policy", "recipe", "normalized_contract"}
        if not isinstance(order, dict) or set(order) != required or order["schema_name"] != "phase5b-codex-work-order" or order["schema_version"] != "2":
            raise ContractError("Phase 5B v2 work order fields or identity are invalid")
        for key in ("request_id", "claim_id", "run_id", "allocation_id", "worktree_id"):
            WorkflowRegistry._require_uuid(order[key], key)
        if not isinstance(order["task_key"], str) or re.fullmatch(r"TASK-[0-9]{8}-[0-9]{3}", order["task_key"]) is None:
            raise ContractError("Phase 5B v2 task key is invalid")
        WorkflowRegistry._require_sha(order["contract_sha256"], "contract_sha256")
        WorkflowRegistry._require_git(order["baseline_commit"], "baseline_commit")
        if not isinstance(order["controller_id"], str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", order["controller_id"]) is None:
            raise ContractError("Phase 5B v2 controller identity is invalid")
        if isinstance(order["attempt_number"], bool) or order["attempt_number"] != 1 or order["workflow_template"] != PHASE5B_V2_PROFILE or order["executor_profile"] != PHASE5B_V2_EXECUTOR or order["model_profile"] != PHASE5B_MODEL or order["output_policy"] != "local-commit-no-remote-v1" or order["recipe"] != "phase5b-codex-code-change-v2":
            raise ProfileError("Phase 5B v2 work order profile binding is invalid")
        if order["task_branch"] == "main" or not isinstance(order["task_branch"], str) or order["task_branch"].startswith("/") or "\\" in order["task_branch"] or "\x00" in order["task_branch"]:
            raise ContractError("Phase 5B v2 task branch is invalid")
        normalized = WorkflowRegistry().normalize(order["normalized_contract"])
        if normalized != order["normalized_contract"]:
            raise ContractError("Phase 5B v2 normalized contract is not canonical")
        policy = normalized.get("phase5b_policy")
        if not isinstance(policy, dict) or policy.get("delivery_version") != "phase5b-task-delivery-v2" or normalized.get("workflow_template") != PHASE5B_V2_PROFILE or normalized.get("executor_profile") != PHASE5B_V2_EXECUTOR:
            raise ProfileError("Phase 5B v2 normalized contract binding is invalid")
        # Request digests retain normalized_contract_sha256's escaped-Unicode
        # convention. This is distinct from canonical work-order serialization.
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != order["contract_sha256"] or normalized["task_key"] != order["task_key"]:
            raise ContractError("Phase 5B v2 task delivery does not match admitted contract")
        manifest = order["instruction_manifest"]
        if not isinstance(manifest, list) or len(manifest) > 1:
            raise ContractError("Phase 5B v2 instruction manifest is invalid")
        for entry in manifest:
            if not isinstance(entry, dict) or set(entry) != {"relative_path", "sha256", "size_bytes", "media_type"} or entry["relative_path"] != "AGENTS.md" or entry["media_type"] != "text/markdown":
                raise ContractError("Phase 5B v2 instruction manifest is invalid")
            WorkflowRegistry._require_sha(entry["sha256"], "instruction sha256")
            WorkflowRegistry._require_bounded_int(entry["size_bytes"], 1, 16384, "instruction size")
        commands = order["validation_commands"]
        if not isinstance(commands, list) or len(commands) != 1:
            raise ContractError("Phase 5B v2 validation command count is invalid")
        command = commands[0]
        if not isinstance(command, dict) or set(command) != {"command_id", "argv", "cwd_relative", "timeout_seconds", "warnings_as_errors"} or command["command_id"] != "unit" or command["cwd_relative"] != "." or command["timeout_seconds"] != 45 or not isinstance(command["warnings_as_errors"], bool):
            raise ContractError("Phase 5B v2 validation command is invalid")
        argv = command["argv"]
        if not isinstance(argv, list) or not 1 <= len(argv) <= 8 or any(not isinstance(arg, str) or not arg or any(char in arg for char in ";&|$`()<>\\") for arg in argv) or argv[0] in {"sh", "bash", "dash", "zsh"} or any(arg in {"-c", "--command"} for arg in argv):
            raise ContractError("Phase 5B v2 validation argv is invalid")
        limits = order["resource_limits"]
        expected = {"overall_timeout_seconds": 180, "model_deadline_seconds": 120, "validation_deadline_seconds": 45, "max_model_iterations": 8, "max_tool_calls": 32, "max_changed_files": 8, "max_total_changed_bytes": 32768, "max_changed_file_bytes": 8192, "max_patch_bytes": 65536, "max_validation_commands": 1, "max_stdout_bytes": 16384, "max_stderr_bytes": 16384, "max_instruction_files": 1, "max_instruction_bytes": 16384, "max_model_summary_bytes": 16384, "max_result_bytes": 131072, "max_failure_bytes": 32768, "max_commit_message_bytes": 200}
        if limits != expected or any(isinstance(value, bool) or not isinstance(value, int) for value in limits.values()):
            raise ProfileError("Phase 5B v2 resource ceilings are invalid")
        WorkflowRegistry._require_bounded_int(order["executor_deadline_unix_seconds"], 1, 2147483647, "executor deadline")
        return json.loads(json.dumps(order, sort_keys=True))

    @staticmethod
    def validate_phase5b_result(result: dict[str, Any]) -> dict[str, Any]:
        common = {"schema_name", "schema_version", "request_id", "claim_id", "run_id", "attempt_number", "contract_sha256", "repository_registration_id", "allocation_id", "worktree_id", "baseline_commit", "task_branch", "executor_profile", "model_profile", "validation_plan_id", "outcome"}
        success = {"changed_file_manifest", "patch_descriptor", "commit_descriptor", "validation_results", "model_summary", "result_sha256"}
        failure = {"failure_classification", "failure_code", "safe_message", "result_sha256"}
        if not isinstance(result, dict) or not common <= set(result):
            raise ContractError("Phase 5B result fields are incomplete")
        if result["schema_name"] != "phase5b-codex-executor-result" or result["schema_version"] != "1":
            raise ContractError("Phase 5B result schema identity is invalid")
        for key in ("request_id", "claim_id", "run_id", "allocation_id", "worktree_id"):
            WorkflowRegistry._require_uuid(result[key], key)
        WorkflowRegistry._require_sha(result["contract_sha256"], "contract_sha256")
        WorkflowRegistry._require_git(result["baseline_commit"], "baseline_commit")
        if result["attempt_number"] != 1 or result["executor_profile"] != PHASE5B_EXECUTOR or result["model_profile"] != PHASE5B_MODEL or result["validation_plan_id"] != PHASE5B_VALIDATION or result["task_branch"] == "main":
            raise ProfileError("Phase 5B result binding is invalid")
        if result["outcome"] == "pass":
            if set(result) != common | success or "failure_classification" in result:
                raise ContractError("Phase 5B success result fields are not exact")
            files = result["changed_file_manifest"]
            if not isinstance(files, list) or len(files) > 8:
                raise ContractError("Phase 5B changed-file manifest is invalid")
            paths = []
            total = 0
            for entry in files:
                if set(entry) != {"relative_path", "status", "sha256", "size_bytes", "media_type"}:
                    raise ContractError("Phase 5B changed-file entry is invalid")
                WorkflowRegistry._require_relative_path(entry["relative_path"])
                WorkflowRegistry._require_sha(entry["sha256"], "changed-file sha256")
                WorkflowRegistry._require_bounded_int(entry["size_bytes"], 0, 8192, "changed-file size")
                paths.append(entry["relative_path"]); total += entry["size_bytes"]
            if paths != sorted(set(paths)) or total > 32768:
                raise ContractError("Phase 5B changed-file ordering or size is invalid")
            patch = result["patch_descriptor"]
            if set(patch) != {"artifact_type", "media_type", "relative_name", "sha256", "size_bytes", "canonical"} or patch["artifact_type"] != "phase5b_codex_patch" or patch["media_type"] != "text/x-diff" or patch["canonical"] is not True:
                raise ContractError("Phase 5B patch descriptor is invalid")
            WorkflowRegistry._require_relative_path(patch["relative_name"]); WorkflowRegistry._require_sha(patch["sha256"], "patch sha256"); WorkflowRegistry._require_bounded_int(patch["size_bytes"], 1, 65536, "patch size")
            commit = result["commit_descriptor"]
            if set(commit) != {"commit_id", "parent_commit_id", "branch", "message", "tree_sha256", "changed_file_count"}:
                raise ContractError("Phase 5B commit descriptor is invalid")
            WorkflowRegistry._require_git(commit["commit_id"], "commit id"); WorkflowRegistry._require_git(commit["parent_commit_id"], "commit parent"); WorkflowRegistry._require_sha(commit["tree_sha256"], "tree sha256")
            if commit["parent_commit_id"] != result["baseline_commit"] or commit["branch"] != result["task_branch"] or commit["changed_file_count"] != len(files) or not isinstance(commit["message"], str) or not 1 <= len(commit["message"].encode()) <= 200:
                raise ContractError("Phase 5B commit policy is invalid")
            validation = result["validation_results"]
            if not isinstance(validation, list) or len(validation) != 1 or validation[0].get("exit_code") != 0 or validation[0].get("timed_out") is not False:
                raise ContractError("Phase 5B validation result is not successful")
            return json.loads(json.dumps(result, sort_keys=True))
        if result["outcome"] == "failed":
            if set(result) != common | failure or result["failure_classification"] not in PHASE5B_FAILURES or not isinstance(result["failure_code"], str) or not isinstance(result["safe_message"], str) or len(result["safe_message"]) > 512:
                raise ContractError("Phase 5B failure result is invalid")
            return json.loads(json.dumps(result, sort_keys=True))
        raise ContractError("Phase 5B result outcome is invalid")

    @staticmethod
    def validate_phase5b_result_v2(result: dict[str, Any], expected_criterion_ids: set[str] | None = None) -> dict[str, Any]:
        common = {"schema_name", "schema_version", "request_id", "claim_id", "run_id", "attempt_number", "contract_sha256", "repository_registration_id", "allocation_id", "worktree_id", "baseline_commit", "task_branch", "executor_profile", "model_profile", "validation_plan_id", "outcome"}
        if not isinstance(result, dict) or not common <= set(result) or result["schema_name"] != "phase5b-codex-executor-result" or result["schema_version"] != "2":
            raise ContractError("Phase 5B v2 result identity is invalid")
        for key in ("request_id", "claim_id", "run_id", "allocation_id", "worktree_id"):
            WorkflowRegistry._require_uuid(result[key], key)
        WorkflowRegistry._require_sha(result["contract_sha256"], "contract_sha256")
        WorkflowRegistry._require_git(result["baseline_commit"], "baseline_commit")
        if isinstance(result["attempt_number"], bool) or result["attempt_number"] != 1 or result["executor_profile"] != PHASE5B_V2_EXECUTOR or result["model_profile"] != PHASE5B_MODEL or result["validation_plan_id"] != PHASE5B_VALIDATION or not isinstance(result["task_branch"], str) or result["task_branch"] == "main":
            raise ProfileError("Phase 5B v2 result binding is invalid")
        if result["outcome"] == "failed":
            required = common | {"failure_classification", "failure_code", "safe_message", "result_sha256"}
            if set(result) != required or result["failure_classification"] not in PHASE5B_FAILURES or not isinstance(result["failure_code"], str) or not isinstance(result["safe_message"], str) or len(result["safe_message"].encode("utf-8")) > 512:
                raise ContractError("Phase 5B v2 failure result is invalid")
            return json.loads(json.dumps(result, sort_keys=True))
        if result["outcome"] != "pass":
            raise ContractError("Phase 5B v2 result outcome is invalid")
        required = common | {"changed_file_manifest", "patch_descriptor", "commit_descriptor", "validation_results", "model_summary", "criterion_evidence", "result_sha256"}
        if set(result) != required:
            raise ContractError("Phase 5B v2 success result fields are not exact")
        files = result["changed_file_manifest"]
        if not isinstance(files, list) or not files or len(files) > 8:
            raise ContractError("Phase 5B v2 changed-file manifest is invalid")
        paths: list[str] = []
        total = 0
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {"relative_path", "status", "sha256", "size_bytes", "media_type"} or entry["status"] not in {"added", "modified", "deleted"}:
                raise ContractError("Phase 5B v2 changed-file entry is invalid")
            WorkflowRegistry._require_relative_path(entry["relative_path"])
            WorkflowRegistry._require_sha(entry["sha256"], "changed-file sha256")
            WorkflowRegistry._require_bounded_int(entry["size_bytes"], 0, 8192, "changed-file size")
            if not isinstance(entry["media_type"], str) or not 1 <= len(entry["media_type"]) <= 128:
                raise ContractError("Phase 5B v2 changed-file media type is invalid")
            paths.append(entry["relative_path"]); total += entry["size_bytes"]
        if paths != sorted(set(paths)) or total > 32768:
            raise ContractError("Phase 5B v2 changed-file ordering or size is invalid")
        patch = result["patch_descriptor"]
        if not isinstance(patch, dict) or set(patch) != {"artifact_type", "media_type", "relative_name", "sha256", "size_bytes", "canonical"} or patch["artifact_type"] != "phase5b_codex_patch" or patch["media_type"] != "text/x-diff" or patch["canonical"] is not True:
            raise ContractError("Phase 5B v2 patch descriptor is invalid")
        WorkflowRegistry._require_relative_path(patch["relative_name"]); WorkflowRegistry._require_sha(patch["sha256"], "patch sha256"); WorkflowRegistry._require_bounded_int(patch["size_bytes"], 1, 65536, "patch size")
        commit = result["commit_descriptor"]
        if not isinstance(commit, dict) or set(commit) != {"commit_id", "parent_commit_id", "branch", "message", "tree_sha256", "changed_file_count"}:
            raise ContractError("Phase 5B v2 commit descriptor is invalid")
        WorkflowRegistry._require_git(commit["commit_id"], "commit id"); WorkflowRegistry._require_git(commit["parent_commit_id"], "commit parent"); WorkflowRegistry._require_sha(commit["tree_sha256"], "tree sha256")
        if not isinstance(commit["branch"], str) or isinstance(commit["changed_file_count"], bool) or not isinstance(commit["changed_file_count"], int) or commit["branch"] != result["task_branch"] or commit["parent_commit_id"] != result["baseline_commit"] or commit["changed_file_count"] != len(files) or not isinstance(commit["message"], str) or not 1 <= len(commit["message"].encode("utf-8")) <= 200:
            raise ContractError("Phase 5B v2 commit policy is invalid")
        validation = result["validation_results"]
        if not isinstance(validation, list) or len(validation) != 1:
            raise ContractError("Phase 5B v2 validation result is invalid")
        item = validation[0]
        expected_validation = {"command_id", "argv_digest", "cwd_relative", "exit_code", "timed_out", "warnings_as_errors", "stdout_sha256", "stdout_size_bytes", "stdout_excerpt", "stderr_sha256", "stderr_size_bytes", "stderr_excerpt"}
        if not isinstance(item, dict) or set(item) != expected_validation or item["command_id"] != "unit" or item["cwd_relative"] != "." or isinstance(item["exit_code"], bool) or not isinstance(item["exit_code"], int) or item["exit_code"] != 0 or item["timed_out"] is not False or item["warnings_as_errors"] is not False:
            raise ContractError("Phase 5B v2 validation result is not successful")
        for key in ("argv_digest", "stdout_sha256", "stderr_sha256"):
            WorkflowRegistry._require_sha(item[key], key)
        approved_argv = PHASE5B_VALIDATION_PLAN["argv"]
        approved_argv_digest = hashlib.sha256(json.dumps(approved_argv, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        if item["argv_digest"] != approved_argv_digest:
            raise ContractError("Phase 5B v2 validation argv is not the trusted plan")
        for key, maximum in (("stdout_size_bytes", 16384), ("stderr_size_bytes", 16384)):
            WorkflowRegistry._require_bounded_int(item[key], 0, maximum, key)
        if not isinstance(item["stdout_excerpt"], str) or not isinstance(item["stderr_excerpt"], str) or len(item["stdout_excerpt"].encode("utf-8")) > 16384 or len(item["stderr_excerpt"].encode("utf-8")) > 16384:
            raise ContractError("Phase 5B v2 validation excerpts are invalid")
        summary = result["model_summary"]
        expected_summary = {"model_profile", "transport_profile", "client_version", "iteration_count", "tool_call_count", "input_bytes", "output_bytes", "duration_ms", "termination", "cost_units"}
        if not isinstance(summary, dict) or set(summary) != expected_summary or summary["model_profile"] != PHASE5B_MODEL or summary["transport_profile"] != "phase5b_model_transport_v1" or not isinstance(summary["client_version"], str) or not 1 <= len(summary["client_version"]) <= 128 or summary["termination"] != "completed":
            raise ContractError("Phase 5B v2 model summary is invalid")
        for key, maximum in (("iteration_count", 8), ("tool_call_count", 32)):
            WorkflowRegistry._require_bounded_int(summary[key], 0, maximum, key)
        for key in ("input_bytes", "output_bytes", "duration_ms"):
            WorkflowRegistry._require_bounded_int(summary[key], 0, 2147483647, key)
        if summary["cost_units"] is not None:
            WorkflowRegistry._require_bounded_int(summary["cost_units"], 0, 2147483647, "cost_units")
        evidence = result["criterion_evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 16 or any(not isinstance(item, dict) or set(item) != {"criterion_id", "outcome", "evidence_refs"} or not isinstance(item["criterion_id"], str) or item["outcome"] != "not_independently_verified" or not isinstance(item["evidence_refs"], list) or len(item["evidence_refs"]) > 8 or any(not isinstance(ref, str) or len(ref) > 255 for ref in item["evidence_refs"]) for item in evidence):
            raise ContractError("Phase 5B v2 criterion evidence is invalid")
        ids = {item["criterion_id"] for item in evidence}
        if len(ids) != len(evidence) or (expected_criterion_ids is not None and ids != expected_criterion_ids):
            raise ContractError("Phase 5B v2 criterion evidence does not match admitted criteria")
        return json.loads(json.dumps(result, sort_keys=True))

    @staticmethod
    def _require_uuid(value: Any, name: str) -> None:
        if not isinstance(value, str) or _UUID_RE.fullmatch(value) is None or str(UUID(value)) != value:
            raise ContractError(f"invalid {name}")

    @staticmethod
    def _require_sha(value: Any, name: str) -> None:
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ContractError(f"invalid {name}")

    @staticmethod
    def _require_git(value: Any, name: str) -> None:
        if not isinstance(value, str) or _GIT_RE.fullmatch(value) is None:
            raise ContractError(f"invalid {name}")

    @staticmethod
    def _require_bounded_int(value: Any, minimum: int, maximum: int, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ContractError(f"invalid {name}")

    @staticmethod
    def _require_relative_path(value: Any) -> None:
        if not isinstance(value, str) or not _RELATIVE_RE.fullmatch(value) or value in {".", ".."} or value.endswith("/") or "//" in value or any(part in {".", ".."} for part in value.split("/")) or any(ord(char) < 32 for char in value):
            raise ContractError("invalid worktree-relative path")

    @staticmethod
    def _reject_forbidden_keys(value: Any) -> None:
        if isinstance(value, dict):
            forbidden = FORBIDDEN_KEYS.intersection(value)
            if forbidden:
                raise ContractError(f"forbidden contract fields: {sorted(forbidden)}")
            for item in value.values():
                WorkflowRegistry._reject_forbidden_keys(item)
        elif isinstance(value, list):
            for item in value:
                WorkflowRegistry._reject_forbidden_keys(item)


def normalized_contract_sha256(contract: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = WorkflowRegistry().normalize(contract)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return normalized, hashlib.sha256(encoded).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def deserialize_phase5b_work_order(raw: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError("duplicate work-order key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError("work-order JSON is invalid") from exc
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ContractError("work-order JSON is not canonical")
    if value.get("schema_version") == "2":
        return WorkflowRegistry.validate_phase5b_work_order_v2(value)
    return WorkflowRegistry.validate_phase5b_work_order(value)


def phase5b_validation_plan(plan_id: str) -> dict[str, Any]:
    if plan_id != PHASE5B_VALIDATION:
        raise ContractError("unknown Phase 5B validation plan")
    return json.loads(json.dumps(PHASE5B_VALIDATION_PLAN, sort_keys=True))


def phase5b_validation_plan_sha256(plan_id: str) -> str:
    plan = phase5b_validation_plan(plan_id)
    encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
