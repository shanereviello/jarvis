# Model and provider routing proposal — draft

This proposal is for human review. It does not replace the approved v0.5 architecture, authorize provider access, install Ollama, change any active service, or enable paid execution.

## Goal

Let the operator select an approved model and configuration for a job while preserving the agent, its tools, workspace boundaries, history and approval rules. Support separate defaults for Jarvis planning, Codex planning, Codex implementation and other admitted job types. Preserve interactive model controls in the operator's native Codex and Hermes environments. A separate adapter is required to propagate a model choice from Linear to the unattended runtime; a model chosen in an interactive desktop is not assumed to control a Linear agent session.

## Current observed boundary

The installed Codex App Server launcher obtains the existing engineering OpenAI API credential via systemd and starts an App Server with an isolated Codex home. The current execution and planning adapters do not explicitly pass a model selection in their thread-start parameters. The staged planning provider configuration also assumes that OpenAI credential. The reporting journal can record returned thread model and provider metadata, but that alone does not establish requested-versus-effective selection or policy enforcement. Hermes provider configuration and its actual per-session model selection still need a separate host-specific read-only audit.

## Proposed configuration

- Maintain a protected operator-controlled catalog of provider profiles. Each selectable profile identifies a provider and model, its credential reference or private endpoint, appropriate context and capability requirements, cost category, and allowed job types. Keep credential values outside the catalog and agent-visible requests.
- Set an explicit default profile for each agent and job type. Allow a human to choose another allowed profile for a particular job through a trusted control surface, and retain that selection with the job. Normal conversation text, agent output, Linear issue descriptions, and tool arguments do not by themselves grant model-selection or provider-changing authority.
- Define precedence as a verified human job selection, then the configured job default. Invalid, unavailable, or unauthorized selections stop with an actionable status. Do not silently change providers, send data to a cloud provider, rerun an uncertain request, or incur a paid fallback.
- Keep the selection stable for a running turn. Record the requested profile, effective provider and model, configuration revision, selection source, and availability/capability result in engineering history and runtime evidence without credentials. Resume and follow-up rules must be verified with the specific runtime; do not silently switch an existing thread to a different provider.
- Treat routing and resource authorization as separate from permission to read, write, create issues, designate architecture, or execute code. A model may not expand its own access by requesting another profile. Maintain distinct Codex and Jarvis identities and credentials.
- Support a local Ollama endpoint as an optional provider only after checking model availability, tool-calling/Responses compatibility, context length, concurrency, memory and performance on the actual host. Require a private authenticated or otherwise access-controlled network path appropriate to the deployment. A local inference provider is not automatically a suitable tool-using coding model.
- Retain a reliable OpenAI profile while additional providers are explicitly configured and tested. No production runtime, billing arrangement, or local-model download changes as part of this draft.

A read-only hardware inventory saw an NVIDIA GeForce RTX 3060 and approximately 31 GiB of system memory on server01. GPU driver status, available VRAM, Ollama availability and practical throughput have not yet been verified; these values do not establish that a particular model will fit or perform adequately.

## Acceptance still needed

1. Inventory the actual Hermes provider configuration, supported model override surface, and current native controls without printing credentials.
2. Confirm what model/provider controls the installed Codex App Server version accepts for new sessions, resumes and follow-ups. Verify the exact Ollama and model combination with real tool calls before offering it for unattended engineering work.
3. Validate authenticated human selection, per-job defaults, unavailable-model refusal, no implicit paid/cloud fallback, isolation, reporting, restart recovery and cost attribution. Test manually selected and default paths for both agents.
4. Decide the human selection surface and initial providers, then obtain approval for the revised architecture and separate deployment or paid tests.
