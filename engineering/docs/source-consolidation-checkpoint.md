# Source consolidation checkpoint — 2026-10-13

Source-only review candidate based on canonical Jarvis main ec591178ed5c2813da4f1a3252a0ecf290f19b36, preserving deployed MCP/Linear modifications and importing ledger/native engineering subprojects from independent history. No credentials/auth directories, runtime state, installed binaries, caches or donor Git metadata imported.

Current MCP Python layout remains intact. Deployment sources moved to deploy/mcp and deploy/hermes; obsolete baseline root compose.yml is removed in this review copy only. Ledger operational sources omit inactive controller/executor services while retaining adapter compatibility mounts until consumer audit. No deployed container, image, volume, secret path or installed code changed.

Validation:27 MCP/Linear tests,61 ledger compatibility tests,84 native runner tests,5 inventory tests and6 relocated model-free native scenarios passed. One Pydantic lifespan annotation warning remains; no runtime upgrade or unrelated fix inferred. Historical migration byte invariance uses hashes from original required revision3d6433b because its history is not part of canonical Jarvis.

No source is staged/committed/merged/pushed. Human review must approve the exact complete source patch before promotion into canonical Git. Root-owned releases, credential relocation and service cutover are later separate checkpoints.
