# The Evidence Waist

MCP is the tool waist. `AGENTS.md` and `CLAUDE.md` are the instruction waist. The evidence waist is still missing.

This post introduces Open Agent Episode (OAE): a portable, verifiable evidence envelope for AI agent work sessions. It is not a runtime, not a governance platform, and not a new vendor stack. It is one JSON object that describes what an agent did, what rules governed it, what artifacts it produced, and whether the evidence was tampered with.

## The stack is forming

In the last six months, the surfaces that control AI agent behavior have converged faster than most people expected.

The tool layer now has a real standard. MCP — the Model Context Protocol — is an official project under the Agentic AI Foundation at the Linux Foundation, with a spec, SDKs in four languages, a public registry, an inspector for debugging, and enterprise governance via registry allowlists. When an agent calls a tool, MCP is increasingly the wire format.

The instruction layer is also institutionalizing. OpenAI donated `AGENTS.md` to the Agentic AI Foundation. Codex reads `AGENTS.md` files with defined precedence and scoping rules. Claude Code reads `CLAUDE.md` and `.claude/rules/` with hook boundaries for auditing tool calls. GitHub Copilot supports repository custom instructions, path-specific instruction files, and agent instructions via `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md`. These are different formats, but they solve the same problem: declaring what rules govern an agent in a given repo or directory.

So the instruction waist and the tool waist are becoming real. But what about the evidence layer?

## What is missing

When an agent finishes a work session — whether it's Claude fixing a bug, Codex adding a feature, or a GitHub Actions workflow verifying a proof pack — what portable artifact describes what happened?

Today, the answer depends on which vendor you used. Claude Code has session logs. Codex has JSONL output. GitHub has workflow run artifacts and agent-session audit log fields. Each of these is useful within its own ecosystem. None of them cross trust boundaries.

A security reviewer who receives work from an AI agent wants to know: What instruction surface governed this session? What tools were called? What code changed? Was the evidence tampered with? Can I verify this offline without trusting the vendor's runtime?

Right now, answering those questions requires vendor-specific tooling and vendor-specific trust assumptions. There is no portable evidence artifact that crosses providers, crosses organizations, and supports independent offline verification.

That is the gap OAE fills.

## What OAE is

An Open Agent Episode is a single JSON object. It contains:

A declared **instruction surface** — the `CLAUDE.md`, `AGENTS.md`, or other instruction files that governed the agent, identified by content hash and scope. The effective policy is encoded as a deterministic digest so you can verify that two sessions ran under the same rules.

An ordered **event stream** — tool calls, model outputs, file writes, test runs, checkpoints. Events can be hash-chained so omission is detectable. The event grammar is stable across producers: `TOOL_CALL`, `TOOL_RESULT`, `FILE_WRITE`, `COMMAND`, `TEST_RUN`, `CHECKPOINT_SEAL`.

Referenced **artifacts** — git commits, PRs, proof packs, MCP traces, test results. Each is content-addressed by sha256. The artifact is not stuffed into the episode; it is referenced by hash so the episode stays small and the artifact can be verified independently.

A **verification summary** — split explicitly into integrity (did the bytes change?) and claims (did the declared governance checks pass?). These are independent verdicts with independent failure modes and a 4-value exit code. This split matters because a session can have intact bytes but failed policy checks, or vice versa.

And two credibility fields that stop the spec from promising what it cannot deliver: **capture class** (FULL, HASH_ONLY, SUMMARY_ONLY, OPAQUE_VENDOR_REF) declares how much the producer actually captured. **Replay class** (NONE, BEST_EFFORT, BOUNDED, DETERMINISTIC) declares how reproducible the session is. Most real-world episodes are BEST_EFFORT at best. Saying so is stronger than pretending otherwise.

## What OAE is not

OAE does not replace vendor-native control planes. It wraps them. GitHub's agent audit logs, MCP's tool call traces, and Assay's proof packs all continue to exist as they are. OAE is the interchange envelope that carries references to those artifacts across trust boundaries.

OAE does not attempt to standardize the whole agent stack. It standardizes the episode boundary — the minimal portable object you need to answer "what happened, under what rules, and can I verify it."

OAE does not claim perfect replay. The `replay_class` field exists precisely because most agent sessions are non-deterministic. Declaring that honestly is more useful than pretending it away.

## The proof boundary

The hardest design decision in OAE was not the schema. It was the verification semantics.

The first version of the exporter read the manifest's declared integrity status and republished it. That meant a tampered proof pack still produced a PASS verdict, because the exporter was trusting paper receipts over present bytes.

That failure was caught during QA. The fix was simple but load-bearing: the exporter now recomputes file hashes from live bytes and compares them against the manifest. If any hash diverges, integrity is FAIL, exit code is 2, and claims are marked N/A because they cannot be trusted when the underlying evidence has changed.

This is not a technical detail. It is the thesis in miniature: portable evidence becomes credible only when present bytes outrank inherited claims.

## Live demo

The schema, fixtures, and exporter are public at [github.com/Haserjian/open-agent-episode](https://github.com/Haserjian/open-agent-episode).

The repo contains a real proof-pack mapping wrapped as OAE. Point the exporter at a local Assay proof pack and you can see `integrity: PASS, claims: PASS, exit_code: 0` for an untampered pack. Flip one byte in a manifest-covered file, re-export, and you get `integrity: FAIL, claims: N_A, exit_code: 2` with a note naming the exact file and the hash mismatch.

CI runs pytest and validates all fixtures against the Draft 2020-12 schema on every push. The alpha is self-defending.

## What comes next

OAE v0.1 ships with one producer (Assay proof pack export), three fixtures (Claude, Codex, GitHub Actions), and a deliberately minimal schema. That is intentional. The spec should earn its fields through real adoption, not through speculative completeness.

v0.2 will add subagent/delegation topology, external anchor profiles (Rekor, RFC 3161), MCP trace adapters, and OpenTelemetry attribute mapping — but only after v0.1 has proven useful to at least one external consumer.

The first outward move is an issue on the MCP Inspector: export a debugging session as a portable evidence artifact. Inspector is where people already go to test and debug MCP servers. Adding "Export OAE" turns a debugging session into a verifiable artifact that can be archived, shared, and verified offline. It is additive, default-off, and small.

If the evidence waist is real, adoption will come from utility, not from a standards campaign. The bet is that the problem — "I need a portable, verifiable record of what this agent did" — is already felt by enough people that the right artifact will find its audience.

The schema is at [open-agent-episode/schema/oae.v0.1.schema.json](https://github.com/Haserjian/open-agent-episode/blob/main/schema/oae.v0.1.schema.json). The README explains what OAE is and is not. The exporter is `pip install -e '.[dev]'` away.

Present bytes outrank inherited claims. That is the whole game.
