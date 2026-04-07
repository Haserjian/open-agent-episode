# OAE v0.1 Execution Plan

**Date:** 2026-04-06
**Author:** Tim B. Haserjian
**Status:** Alpha — schema complete, exporter live-verified, package metadata present, repo not yet initialized

---

## 1. Placement decision

**Recommendation: new repo `open-agent-episode`.**

Why: OAE is a neutral interchange spec. Placing it inside `assay` makes it look like an Assay feature rather than a cross-vendor artifact. External maintainers evaluating a PR that says "see `Haserjian/open-agent-episode`" will see a standalone spec with fixtures and a schema. If it says "see `Haserjian/assay/oae/`", it looks like vendor tooling.

Downside of standalone repo: one more repo to maintain; the first exporter (`assay oae export`) still lives in `assay` or imports from `open-agent-episode`. This is fine — the spec repo owns the schema + fixtures + README, and `assay` is the first producer.

Migration path: the export command skeleton (`src/assay_oae/export.py`) ships in this repo for now. When `assay` integrates it as a subcommand (`assay oae export`), this file moves there and `open-agent-episode` becomes pure spec + fixtures + docs.

---

## 2. Repo tree

```
open-agent-episode/
  README.md                              # Thesis + quick start
  LICENSE                                # Apache-2.0
  EXECUTION_PLAN.md                      # This file
  schema/
    oae.v0.1.schema.json                 # Normative schema
  fixtures/
    claude_minimal.json                  # Claude Code session
    codex_minimal.json                   # Codex CLI session
    github_action_minimal.json           # GitHub Actions CI run
  examples/
    real_proof_pack_wrapped.json         # Real proof pack → OAE mapping
  src/
    assay_oae/
      __init__.py
      export.py                          # First producer: proof pack → OAE
```

---

## 3. Schema design notes

**Required fields:** `schema_version`, `episode_id`, `capture_class`, `identity`, `instruction`, `events`, `artifacts`, `verification`.

**Credibility fields (load-bearing):**

- `capture_class` — declares what the producer actually captured. Without this, consumers assume FULL fidelity and get burned.
- `replay_class` — declares replay fidelity. Without this, the spec promises magic.
- `profiles[]` — extensibility mechanism. Base OAE stays small; domain rules live in profiles.
- `redactions[]` — structural, not a footnote. Every redaction must declare path + reason.
- `parent_episode_id` — delegation/subagent support (v0.1 is single-link; v0.2 adds full topology).

**Verification semantics:** inherited from Assay. integrity (bytes unchanged) + claims (governance checks hold) + exit_code (0/1/2/3). Not reinvented.

---

## 4. v0.1 / v0.2 boundary

### v0.1 (ship now)

- Schema with all required + credibility fields
- 3 fixtures that validate against schema
- 1 real proof pack wrapped as OAE
- Export command skeleton (Python)
- README readable as thesis
- Tamper test (flip byte → verify FAIL)

### v0.2 (after ship, not before)

- Subagent/delegation topology (`child_episode_ids[]`, delegation edges)
- External anchor profiles (Rekor, RFC 3161 details)
- MCP trace adapter (TS + Python)
- Claude Agent SDK hook adapter
- OpenTelemetry semantic attribute mapping
- Trust model separation (producer/operator/signer/verifier/anchor as distinct identities)
- Version negotiation (`min_reader_version`)
- W3C PROV / SLSA provenance mapping docs
- Conformance test suite (producer tests, verifier tests, tamper tests, omission tests)

---

## 5. Cut-line scope

### Session 1 (3-4 hours) — SHIP

- [x] Schema (`oae.v0.1.schema.json`)
- [x] README (waist framing, what-OAE-is-not, relationship to Assay)
- [x] 3 fixtures (claude, codex, github_action)
- [x] Real proof pack wrapped (`examples/real_proof_pack_wrapped.json`)
- [x] Export skeleton (`src/assay_oae/export.py`)
- [x] Validate fixtures against schema (ajv or jsonschema)
- [x] Run export skeleton against real proof pack, verify output
- [ ] `git init` + first commit + push to `Haserjian/open-agent-episode`

### Session 2 (2-3 hours) — HARDEN

- [ ] Tamper test script: flip one byte in proof pack, re-export, verify FAIL
- [x] Add `LICENSE` (Apache-2.0)
- [x] Add `pyproject.toml` for the export module
- [ ] Thesis post draft (separate file, not the README)
- [ ] First MCP-adjacent issue/PR draft

### Explicitly out of scope until after ship

- 20-repo PR campaign (backlog, not sprint)
- TS implementation of export
- MCP trace adapter
- Claude hook adapter
- Conformance test suite
- HTML proof page renderer
- OpenTelemetry mapping
- Subagent topology
- Any schema field marked v0.2

---

## 6. Acceptance checklist

Binary pass/fail. All must be YES before declaring "shipped."

| # | Check | Status |
|---|-------|--------|
| 1 | `schema/oae.v0.1.schema.json` exists and is valid JSON Schema (Draft 2020-12) | YES |
| 2 | All 3 fixtures validate against the schema | YES |
| 3 | `examples/real_proof_pack_wrapped.json` validates against the schema | YES |
| 4 | `real_proof_pack_wrapped.json` references real sha256 values from `proof_pack_trace_20260301T055107_9e84bd2a/pack_manifest.json` | YES |
| 5 | `src/assay_oae/export.py` runs against real proof pack and produces valid OAE | YES |
| 6 | Tamper test: modify one byte in referenced artifact → verification field shows FAIL | YES |
| 7 | README opens with waist framing | YES |
| 8 | README says what OAE is NOT within first 3 sections | YES |
| 9 | Schema includes `capture_class` with 4-value enum | YES |
| 10 | Schema includes `replay_class` with 4-value enum | YES |
| 11 | Schema includes `redactions[]` with path + reason | YES |
| 12 | Schema includes `profiles[]` | YES |
| 13 | Schema includes `parent_episode_id` | YES |
| 14 | Schema includes verification with integrity/claims/exit_code | YES |
| 15 | README is understandable by an external maintainer in 5 minutes | YES |

---

## 7. Maintainer-read test

Could a maintainer from MCP / GitHub / Claude ecosystem understand this in 5 minutes?

Test criteria:
- README does not require reading Assay docs to understand what OAE is
- Schema is self-documenting (every field has a description)
- Fixtures are minimal but credible (not toy data)
- The relationship to Assay is explicit: "wraps, does not replace"
- No jargon that requires internal context (no "organism", no "Compact", no "Loom")

---

## 8. Next move after ship

### Thesis post

Structure:
1. The stack is forming (instruction waist + tool waist are institutionalizing)
2. Why vendor-native controls are insufficient (trust-boundary localness, mixed-vendor reality, offline verification need)
3. What OAE is (one bounded unit, portable, verifiable, replay-hinted not replay-fantasized)
4. What OAE is not
5. Live demo (schema, fixtures, one proof pack wrapped, fail case)

Length: 1500-2000 words. Not a manifesto.

### First MCP-adjacent move

**Target:** `modelcontextprotocol/typescript-sdk` or `modelcontextprotocol/inspector`

**Shape:** example folder + thin helper, not a protocol change. Title: "feat: optional session export as portable evidence artifact"

**Why this target:** Inspector is where people debug MCP servers. Adding "Export OAE" turns debugging sessions into verifiable artifacts. It is additive, default-off, and small.

**Do not** open 20 issues simultaneously. Open one. Get signal. Iterate.
