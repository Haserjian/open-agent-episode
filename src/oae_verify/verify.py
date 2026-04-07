"""
oae-verify <envelope.json>

Independent verifier for Open Agent Episode (OAE) v0.1 envelopes.

This module shares ZERO code with the exporter (assay_oae.export).
Producer and verifier must not share hidden trust shortcuts.

What this verifier checks:
  1. Schema validity — envelope conforms to oae.v0.1.schema.json (Draft 2020-12),
     including format enforcement (date-time, etc.).
  2. Instruction digest — recomputes effective_digest from declared surfaces.
  3. Event field shapes — validates prev_event_hash format where present.
  4. Artifact hashes — validates sha256 format on all content-addressed refs.
  5. Verification consistency — exit_code matches integrity/claims pair.
  6. Credibility fields — capture_class and replay_class are declared.

What this verifier does NOT check:
  - Event chain integrity (OAE v0.1 does not define a canonical event-hashing
    algorithm, so recomputing predecessor hashes is not yet possible).
  - Whether the referenced bytes (proof packs, git commits) still exist.
  - Whether the producer's integrity/claims verdicts are correct.
  - Replay fidelity.

The verifier is envelope-only. It answers: "Is this OAE internally consistent
and schema-valid?" — not "Did the agent actually do what this says?"

Exit codes (Assay-compatible):
  0 — envelope is valid and internally consistent
  1 — envelope is schema-valid but has consistency warnings
  2 — envelope fails schema validation (structural integrity)
  3 — verifier error (bad input, missing schema, etc.)
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Hash utilities (independent — no imports from assay_oae)
# ---------------------------------------------------------------------------

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex digest. Identical algorithm, independent implementation."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Verification checks
# ---------------------------------------------------------------------------

class VerifyResult:
    """Accumulates findings from all verification checks."""

    def __init__(self) -> None:
        self.errors: list[str] = []      # structural failures (exit_code 2)
        self.warnings: list[str] = []    # consistency issues (exit_code 1)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.warnings:
            return 1
        return 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def summary(self) -> str:
        parts = []
        for e in self.errors:
            parts.append(f"  ERROR: {e}")
        for w in self.warnings:
            parts.append(f"  WARN:  {w}")
        if not parts:
            parts.append("  All checks passed.")
        return "\n".join(parts)


def check_schema(oae: dict, schema: dict, result: VerifyResult) -> None:
    """Validate envelope against JSON Schema Draft 2020-12 with format enforcement."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        result.error("jsonschema package not installed — cannot validate schema")
        return

    format_checker = FormatChecker()

    # jsonschema's built-in date-time format support is inert unless its
    # companion validator is installed. Detect that explicitly so the verifier
    # fails closed instead of silently treating invalid timestamps as valid.
    try:
        format_checker.check("not-a-timestamp", "date-time")
    except Exception:
        pass
    else:
        result.error(
            "Schema format checking for date-time is inactive; install "
            "rfc3339-validator to enforce OAE timestamp validation"
        )
        return

    validator = Draft202012Validator(schema, format_checker=format_checker)
    errors = sorted(validator.iter_errors(oae), key=lambda e: list(e.path))
    for err in errors:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        result.error(f"Schema: {path} — {err.message}")


def check_instruction_digest(oae: dict, result: VerifyResult) -> None:
    """Recompute effective_digest from declared surfaces and compare."""
    instruction = oae.get("instruction", {})
    surfaces = instruction.get("surfaces", [])
    declared_digest = instruction.get("effective_digest", "")

    if not surfaces:
        result.error("instruction.surfaces is empty")
        return

    # Recompute: same algorithm as the spec defines
    # SHA-256 of ordered "{sha256}:{scope}\n" joined by "\n"
    material = "\n".join(
        f"{s.get('sha256', '')}:{s.get('scope', '')}" for s in surfaces
    )
    recomputed = _sha256_hex(material.encode("utf-8"))

    if recomputed != declared_digest:
        result.warn(
            f"instruction.effective_digest mismatch: "
            f"declared={declared_digest[:16]}…, "
            f"recomputed={recomputed[:16]}…"
        )


def check_event_fields(oae: dict, result: VerifyResult) -> None:
    """
    Validate event field shapes (NOT chain integrity).

    OAE v0.1 does not define a canonical event-hashing algorithm, so this
    check cannot recompute predecessor hashes. It only validates:
      - prev_event_hash format (64 lowercase hex chars) where present
      - first event should be the chain root (no prev_event_hash)

    Chain integrity verification requires a spec-defined hashing algorithm.
    Until OAE defines one, this is field-shape validation only.
    """
    events = oae.get("events", [])
    if len(events) < 2:
        return

    has_chain = any(e.get("prev_event_hash") for e in events)
    if not has_chain:
        return  # No chain declared — nothing to verify

    # First event should NOT have prev_event_hash (it's the root)
    if events[0].get("prev_event_hash"):
        result.warn("First event has prev_event_hash — should be chain root")

    # Verify prev_event_hash format on all chained events
    for i, event in enumerate(events):
        peh = event.get("prev_event_hash")
        if peh and not SHA256_PATTERN.match(peh):
            result.error(
                f"events[{i}].prev_event_hash is not a valid SHA-256: {peh[:20]}…"
            )


def check_artifact_hashes(oae: dict, result: VerifyResult) -> None:
    """Validate sha256 format on all artifacts that declare one."""
    for i, art in enumerate(oae.get("artifacts", [])):
        sha = art.get("sha256")
        if sha and not SHA256_PATTERN.match(sha):
            result.error(
                f"artifacts[{i}].sha256 is not a valid SHA-256: {sha[:20]}…"
            )


def check_verification_consistency(oae: dict, result: VerifyResult) -> None:
    """Check that exit_code is consistent with integrity/claims pair."""
    v = oae.get("verification", {})
    integrity = v.get("integrity", "")
    claims = v.get("claims", "")
    exit_code = v.get("exit_code")

    if exit_code is None:
        return  # exit_code is optional in schema

    # Expected mapping:
    #   integrity FAIL → exit_code 2
    #   integrity PASS, claims FAIL → exit_code 1
    #   both PASS → exit_code 0
    #   integrity FAIL, claims anything-but-N_A → inconsistent
    expected = None
    if integrity == "FAIL":
        expected = 2
    elif integrity == "PASS" and claims == "FAIL":
        expected = 1
    elif integrity == "PASS" and claims == "PASS":
        expected = 0

    if expected is not None and exit_code != expected:
        result.warn(
            f"verification.exit_code={exit_code} inconsistent with "
            f"integrity={integrity}, claims={claims} (expected {expected})"
        )

    # If integrity FAIL, claims should be N_A (can't trust them)
    if integrity == "FAIL" and claims not in ("N_A", "FAIL"):
        result.warn(
            f"integrity=FAIL but claims={claims} — "
            f"claims should be N_A when integrity fails"
        )


def check_credibility_fields(oae: dict, result: VerifyResult) -> None:
    """Verify credibility fields are present and well-formed."""
    if "capture_class" not in oae:
        result.error("capture_class is required but missing")
    if oae.get("replay_class") is None and oae.get("capture_class") == "FULL":
        result.warn(
            "capture_class=FULL but replay_class is not declared — "
            "consumers cannot assess replay fidelity"
        )


def check_redaction_manifest(oae: dict, result: VerifyResult) -> None:
    """If redactions are present, verify they have required fields."""
    evidence = oae.get("evidence", {})
    redactions = evidence.get("redactions", [])
    for i, r in enumerate(redactions):
        if not r.get("path"):
            result.error(f"evidence.redactions[{i}].path is missing")
        if not r.get("reason"):
            result.error(f"evidence.redactions[{i}].reason is missing")
        hp = r.get("hash_placeholder")
        if hp and not SHA256_PATTERN.match(hp):
            result.warn(
                f"evidence.redactions[{i}].hash_placeholder "
                f"is not a valid SHA-256: {hp[:20]}…"
            )


# ---------------------------------------------------------------------------
# Main verify function
# ---------------------------------------------------------------------------

def verify_envelope(
    oae: dict,
    schema: Optional[dict] = None,
) -> VerifyResult:
    """
    Run all verification checks on an OAE envelope.

    Args:
        oae: Parsed OAE JSON object.
        schema: Optional parsed JSON Schema. If provided, schema validation
                is performed. If None, schema check is skipped.

    Returns:
        VerifyResult with errors and warnings.
    """
    result = VerifyResult()

    if schema:
        check_schema(oae, schema, result)

    # Even if schema fails, run consistency checks — they may reveal
    # additional issues worth reporting.
    check_instruction_digest(oae, result)
    check_event_fields(oae, result)
    check_artifact_hashes(oae, result)
    check_verification_consistency(oae, result)
    check_credibility_fields(oae, result)
    check_redaction_manifest(oae, result)

    return result


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Usage: oae-verify <envelope.json> [--schema <schema.json>]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Independent verifier for OAE v0.1 envelopes"
    )
    parser.add_argument(
        "envelope",
        type=Path,
        help="Path to OAE envelope JSON file",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Path to OAE JSON Schema (default: auto-detect from repo)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    # Load envelope
    if not args.envelope.exists():
        print(f"Error: {args.envelope} not found", file=sys.stderr)
        sys.exit(3)

    try:
        oae = json.loads(args.envelope.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error loading envelope: {exc}", file=sys.stderr)
        sys.exit(3)

    # Load schema
    schema = None
    if args.schema:
        schema_path = args.schema
    else:
        # Auto-detect: look for schema relative to this file's repo
        candidates = [
            Path(__file__).resolve().parents[2] / "schema" / "oae.v0.1.schema.json",
            Path.cwd() / "schema" / "oae.v0.1.schema.json",
        ]
        for c in candidates:
            if c.exists():
                schema_path = c
                break
        else:
            schema_path = None

    if schema_path and schema_path.exists():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: could not load schema: {exc}", file=sys.stderr)
    elif schema_path:
        print(f"Warning: schema not found at {schema_path}", file=sys.stderr)

    # Verify
    result = verify_envelope(oae, schema)

    # Output
    if args.json:
        output = {
            "envelope": str(args.envelope),
            "exit_code": result.exit_code,
            "errors": result.errors,
            "warnings": result.warnings,
        }
        print(json.dumps(output, indent=2))
    else:
        status = {0: "PASS", 1: "WARN", 2: "FAIL", 3: "ERROR"}[result.exit_code]
        print(f"oae-verify: {args.envelope.name} → {status} (exit_code={result.exit_code})")
        print(result.summary())

    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
