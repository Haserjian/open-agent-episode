# Issue: Export inspector session as portable evidence artifact

**Target repo:** `modelcontextprotocol/inspector`
**Type:** Feature request
**Scope:** Additive, default-off

---

## Title

Export inspector session as a portable evidence artifact (Open Agent Episode)

## Body

### Problem

When debugging MCP servers in Inspector, the session data — tool calls, results, errors, timing — exists only within the Inspector UI. Teams that need to share, archive, or independently verify a debugging session have no portable export format.

This matters for:
- **Audit trails:** security teams reviewing what an MCP server did during a debugging session
- **Reproducibility:** sharing a session artifact with another team member who was not present
- **CI integration:** exporting session results from Inspector's CLI mode into a verification pipeline
- **Cross-boundary trust:** providing evidence of MCP server behavior to an external party without giving them access to your Inspector instance

### Proposal

Add an optional "Export session" capability that emits a portable JSON artifact describing the Inspector session. The proposed format is [Open Agent Episode (OAE)](https://github.com/Haserjian/open-agent-episode), a minimal evidence envelope designed for exactly this use case.

An exported session would include:
- Ordered tool_call / tool_result events (hash-chained for omission detection)
- Content-addressed references to payloads (sha256)
- Declared capture class (what fidelity the export provides)
- Verification summary (integrity check on referenced artifacts)

### Why OAE fits

OAE is a thin JSON schema (Draft 2020-12) with a stable event grammar that already includes `TOOL_CALL` and `TOOL_RESULT` as first-class event kinds. It is designed to wrap vendor-native artifacts without replacing them. The schema, fixtures, and a reference exporter are public at [Haserjian/open-agent-episode](https://github.com/Haserjian/open-agent-episode).

### Scope

- **UI:** "Export OAE" button or menu item in the session view
- **CLI:** `--export-oae <path>` flag for scripted/CI usage
- **No protocol changes.** This is purely an Inspector-side export.
- **Default off.** No behavioral change unless the user explicitly exports.

### What this does NOT propose

- No changes to the MCP protocol or wire format
- No mandatory adoption of OAE by MCP servers or clients
- No dependency on external verification tooling (though OAE artifacts can be verified by any schema-aware validator)

### References

- [OAE schema (v0.1)](https://github.com/Haserjian/open-agent-episode/blob/main/schema/oae.v0.1.schema.json)
- [OAE README](https://github.com/Haserjian/open-agent-episode/blob/main/README.md)
- Inspector already has a CLI mode for scripting — export is a natural extension of that surface
