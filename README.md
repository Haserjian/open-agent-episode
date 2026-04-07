# Open Agent Episode (OAE)

**A portable, verifiable evidence envelope for AI agent work sessions.**

MCP is the tool waist. `AGENTS.md` / `CLAUDE.md` are the instruction waist. **OAE is the evidence waist.**

---

## What OAE is

An Open Agent Episode is a single JSON object describing one bounded unit of agent work — an "episode" — across:

- A declared **instruction surface** (what rules governed the agent)
- A captured **execution transcript** (what happened)
- Referenced **artifacts** (what was produced — commits, diffs, proof packs, test results)
- Summarized **evidence** (integrity hashes, external anchors, redaction manifests)
- Deterministic **verification results** (integrity and claims, split explicitly)
- Optional **replay hints** (how to re-run under comparable conditions, with declared fidelity)

OAE is designed for the world that already exists: multiple agent surfaces (Claude Code, Codex, Copilot, MCP-connected tools), multiple instruction formats (`CLAUDE.md`, `AGENTS.md`, `copilot-instructions.md`, `.github/agents/*.md`), and no portable evidence artifact that crosses them.

The spec is minimal by design. It standardizes the **episode boundary**, not the agent stack. Vendors keep their runtimes. OAE becomes the interchange object their outputs serialize into.

## What OAE is not

- **Not a runtime.** OAE does not execute agents or manage tool calls.
- **Not a vendor replacement.** It wraps vendor-native artifacts; it does not compete with them.
- **Not a governance platform.** It carries evidence of governance decisions; it does not make them.
- **Not a crypto religion.** Hashes and signatures are used where they provide tamper evidence. Nothing more.
- **Not a replay engine.** Replay hints are best-effort metadata with declared fidelity classes. OAE does not promise deterministic replay.

## Relationship to Assay

OAE wraps and references [Assay](https://github.com/Haserjian/assay) proof packs as artifacts — it does not replace them.

v0.1 ships with one producer implementation: Assay proof packs. The cross-vendor story is the schema and fixtures today, not multiple exporters already landed.

Assay proof packs remain the compiled evidence artifact for an episode. OAE is the interchange envelope that carries a proof pack reference alongside instruction-surface digests, execution events, artifact pointers, and verification summaries. An OAE object can exist without an Assay proof pack (e.g., a minimal Codex session export), and an Assay proof pack can exist without OAE (e.g., existing CI verification workflows). When both exist, they compose: the proof pack is referenced by `pack_root_sha256` inside `artifacts[]`.

The verification semantics — integrity vs. claims, exit codes 0/1/2/3 — are inherited directly from Assay's verifier contract. OAE does not reinvent them.

## Key design decisions

**Capture classes, not fake determinism.** Not every producer can export the same fidelity. OAE declares a `capture_class` (`FULL`, `HASH_ONLY`, `SUMMARY_ONLY`, `OPAQUE_VENDOR_REF`) so consumers know what they are getting. A `HASH_ONLY` episode from a black-box vendor is still useful for tamper detection even if you cannot replay it.

**Replay classes, not replay fantasies.** The `replay_class` field (`NONE`, `BEST_EFFORT`, `BOUNDED`, `DETERMINISTIC`) prevents the spec from promising what agent runtimes cannot deliver. Most real-world episodes are `BEST_EFFORT` at best.

**Redaction is structural, not a footnote.** The `redactions[]` manifest declares what was removed and why. Verifiers can distinguish "this field was redacted for PII" from "this field is missing because the producer dropped it." This follows the Assay Protocol's receipt privacy guidance.

**Profiles for extensibility.** The base OAE schema stays small. Everything domain-specific — tool safety governance, tri-temporal constraints, subagent topology — lives in declared profiles (e.g., `assay.integrity.v1`, `assay.tool_safety.v1`). Third parties adopt OAE without adopting every Assay law.

**Verification = integrity + claims.** Following Assay's explicit split: integrity checks whether bytes are unchanged; claims checks whether declared governance assertions hold. These are independent verdicts with independent failure modes.

## Why now

The Agentic AI Foundation (Linux Foundation) now houses both MCP and `AGENTS.md` as institutional projects. GitHub's enterprise agent control plane is GA with MCP registry governance and agent-session audit fields. Claude Code exposes hook boundaries (`PreToolUse`, `PostToolUse`, `Stop`) for audit without model-context cost. Codex formalizes `AGENTS.md` scoping with deterministic precedence rules. Microsoft shipped the Agent Governance Toolkit as open-source runtime middleware. NIST launched an AI Agent Standards Initiative targeting interoperability. The EU AI Act's Article 12 logging requirements for high-risk systems apply from August 2, 2026.

The instruction waist and the tool waist are institutionalizing. The evidence waist is still unowned.

## Quick start

```bash
# Validate a fixture (requires ajv-cli + ajv-formats for Draft 2020-12 + date-time)
npx --yes --package ajv-cli --package ajv-formats \
  ajv validate -c ajv-formats -s schema/oae.v0.1.schema.json \
  --spec=draft2020 -d fixtures/claude_minimal.json

# Or validate with Python jsonschema (>= 4.18)
python3 -c "
import json
from jsonschema import validate, Draft202012Validator
schema = json.load(open('schema/oae.v0.1.schema.json'))
data = json.load(open('fixtures/claude_minimal.json'))
validate(instance=data, schema=schema, cls=Draft202012Validator)
print('PASS')
"

# Install the local package
python3 -m pip install -e .

# Export from an Assay proof pack
assay-oae-export path/to/proof_pack/ -o episode.oae.json

# Or run directly from a checkout without installing
PYTHONPATH=src python3 -m assay_oae.export path/to/proof_pack/ -o episode.oae.json

# Tamper test: the exporter recomputes file hashes from live bytes.
# If any byte in a manifest-covered file has changed, integrity → FAIL, exit_code → 2.
```

## Schema

See [`schema/oae.v0.1.schema.json`](schema/oae.v0.1.schema.json).

## Fixtures

- [`fixtures/claude_minimal.json`](fixtures/claude_minimal.json) — Claude Code session with hook-captured tool calls
- [`fixtures/codex_minimal.json`](fixtures/codex_minimal.json) — Codex CLI session with AGENTS.md instruction surface
- [`fixtures/github_action_minimal.json`](fixtures/github_action_minimal.json) — GitHub Actions CI run with proof pack verification

## v0.1 / v0.2 boundary

**v0.1 ships:** schema, 3 fixtures, one Assay proof-pack exporter, one real wrapped proof pack, live integrity failure on tamper, this README.

**v0.2 adds (not before ship):** subagent/delegation topology (`child_episode_ids`, delegation edges), external anchor profiles (Rekor, RFC 3161), MCP trace adapter, OpenTelemetry attribute mapping, trust model separation (producer/operator/signer/verifier/anchor identity as distinct concepts), version negotiation (`min_reader_version`).

## License

Apache-2.0
