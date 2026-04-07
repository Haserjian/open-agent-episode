"""
assay oae export <proof-pack-dir> [-o output.oae.json]

First OAE producer: wraps an existing Assay proof pack into an Open Agent Episode.

Input:  A proof pack directory containing pack_manifest.json + receipt_pack.jsonl + verify_report.json
Output: An OAE v0.1 JSON file referencing the proof pack as an artifact.

CRITICAL DESIGN RULE: The exporter MUST recompute integrity from live bytes.
It MUST NOT republish stale verification claims from the manifest or verify_report.
The manifest declares what hashes *should* be. The exporter checks what they *are*.
If they diverge, the exporter emits FAIL. This is the proof boundary.
"""

import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Hash utilities (reuse Assay's conventions)
# ---------------------------------------------------------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_hex(path.read_bytes())


# ---------------------------------------------------------------------------
# Live integrity verification
# ---------------------------------------------------------------------------

def verify_pack_integrity(pack_dir: Path, manifest: dict) -> dict:
    """
    Recompute file hashes from live bytes and compare against manifest.

    Returns a dict with:
        integrity: "PASS" | "FAIL"
        mismatches: list of {path, expected, actual}
        missing: list of paths
        live_file_hashes: dict of {path: sha256}
    """
    mismatches = []
    missing = set()
    live_file_hashes = {}

    for rel_path in manifest.get("expected_files", []):
        if not (pack_dir / rel_path).exists():
            missing.add(rel_path)

    for file_entry in manifest.get("files", []):
        rel_path = file_entry["path"]
        expected_hash = file_entry["sha256"]
        file_path = pack_dir / rel_path

        if not file_path.exists():
            missing.add(rel_path)
            continue

        actual_hash = sha256_file(file_path)
        live_file_hashes[rel_path] = actual_hash

        if actual_hash != expected_hash:
            mismatches.append({
                "path": rel_path,
                "expected": expected_hash,
                "actual": actual_hash,
            })

    integrity = "PASS" if (not mismatches and not missing) else "FAIL"

    return {
        "integrity": integrity,
        "mismatches": mismatches,
        "missing": sorted(missing),
        "live_file_hashes": live_file_hashes,
    }


def format_uri_hint(pack_dir: Path) -> str:
    """Return a portable, non-authoritative locator hint for the pack."""
    return f"{pack_dir.name}/" if pack_dir.name else str(pack_dir)


# ---------------------------------------------------------------------------
# Instruction surface helpers
# ---------------------------------------------------------------------------

def find_instruction_surfaces(repo_root: Path) -> list[dict]:
    """Scan for known instruction files and hash them."""
    surfaces = []
    candidates = [
        ("CLAUDE.md", "CLAUDE_MD", "repo"),
        ("AGENTS.md", "AGENTS_MD", "repo"),
        (".github/copilot-instructions.md", "COPILOT_INSTRUCTIONS", "repo"),
    ]
    # Also scan .claude/rules/ for directory-scoped surfaces
    rules_dir = repo_root / ".claude" / "rules"
    if rules_dir.is_dir():
        for f in sorted(rules_dir.glob("*.md")):
            candidates.append((str(f.relative_to(repo_root)), "CLAUDE_MD", "directory"))

    for rel_path, kind, scope in candidates:
        p = repo_root / rel_path if not Path(rel_path).is_absolute() else Path(rel_path)
        if p.exists():
            surfaces.append({
                "kind": kind,
                "path": str(rel_path),
                "sha256": sha256_file(p),
                "scope": scope,
            })
    return surfaces


def compute_effective_digest(surfaces: list[dict]) -> str:
    """SHA-256 of ordered surface hashes + scopes. Deterministic across machines."""
    material = "\n".join(f"{s['sha256']}:{s.get('scope', '')}" for s in surfaces)
    return sha256_hex(material.encode("utf-8"))


# ---------------------------------------------------------------------------
# Receipt → event mapping
# ---------------------------------------------------------------------------

def receipt_to_event(receipt: dict, seq: int) -> dict:
    """Map an Assay receipt (JSONL line) to an OAE event."""
    event = {
        "event_id": receipt.get("receipt_id", f"evt_{seq:03d}"),
        "ts": receipt.get("timestamp") or receipt.get("_stored_at", ""),
        "kind": "TOOL_CALL",  # most receipts are model/tool calls
    }
    # Build summary from available fields
    parts = []
    if receipt.get("type"):
        parts.append(receipt["type"])
    if receipt.get("call"):
        parts.append(receipt["call"])
    if receipt.get("model_id"):
        parts.append(f"model:{receipt['model_id']}")
    if receipt.get("provider"):
        parts.append(f"provider:{receipt['provider']}")
    event["summary"] = " | ".join(parts) if parts else f"receipt seq={seq}"
    return event


# ---------------------------------------------------------------------------
# Core export logic
# ---------------------------------------------------------------------------

def export_proof_pack_to_oae(
    pack_dir: Path,
    repo_root: Optional[Path] = None,
    output_path: Optional[Path] = None,
) -> dict:
    """
    Read a proof pack directory and produce an OAE v0.1 JSON.

    INTEGRITY IS RECOMPUTED FROM LIVE BYTES. The exporter does not trust
    the manifest's receipt_integrity or the verify_report's passed field.
    It recomputes file hashes and compares them against the manifest.
    If any file hash diverges, integrity is FAIL and exit_code is 2.

    Args:
        pack_dir: Path to proof pack directory (must contain pack_manifest.json)
        repo_root: Optional repo root for instruction surface scanning
        output_path: Optional path to write OAE JSON (otherwise returns dict)

    Returns:
        The OAE dict.
    """
    # --- Load pack manifest ---
    manifest_path = pack_dir / "pack_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No pack_manifest.json in {pack_dir}")
    manifest = json.loads(manifest_path.read_text())
    attestation = manifest.get("attestation", {})

    # --- LIVE INTEGRITY CHECK ---
    # This is the proof boundary. We recompute from current bytes.
    # We do NOT trust the manifest's receipt_integrity or the verify_report.
    integrity_result = verify_pack_integrity(pack_dir, manifest)

    # --- Load receipts ---
    # Parse receipts only after integrity passes. If integrity has already failed,
    # emit a fail-closed OAE instead of trusting or parsing corrupted bytes.
    receipts_path = pack_dir / "receipt_pack.jsonl"
    receipts = []
    if integrity_result["integrity"] == "PASS" and receipts_path.exists():
        for line in receipts_path.read_text().strip().split("\n"):
            if line.strip():
                receipts.append(json.loads(line))

    # --- Build events from receipts ---
    events = []
    if not receipts:
        events.append({
            "event_id": "evt_001",
            "ts": attestation.get("timestamp_start", datetime.now(timezone.utc).isoformat()),
            "kind": "SESSION_START",
            "summary": f"Proof pack {manifest.get('pack_id', 'unknown')}",
        })
    else:
        for i, r in enumerate(receipts):
            events.append(receipt_to_event(r, i))

    # --- Build artifacts ---
    # Use the live file hashes, not the manifest's declared hashes.
    pack_root = manifest.get("pack_root_sha256") or manifest.get("attestation_sha256", "")

    artifacts = [{
        "type": "PROOF_PACK",
        "sha256": pack_root,
        "uri_hint": format_uri_hint(pack_dir),
        "metadata": {
            "pack_id": manifest.get("pack_id", ""),
            "run_id": attestation.get("run_id", ""),
            "n_receipts": attestation.get("n_receipts", len(receipts)),
            "assurance_level": attestation.get("assurance_level", ""),
            "proof_tier": attestation.get("proof_tier", ""),
            "mode": attestation.get("mode", ""),
            "signer_id": manifest.get("signer_id", ""),
            "signer_pubkey_sha256": manifest.get("signer_pubkey_sha256", ""),
            "files": integrity_result["live_file_hashes"],
        },
    }]

    # --- Build instruction surface ---
    instruction_surfaces = []
    if repo_root:
        instruction_surfaces = find_instruction_surfaces(repo_root)
    if not instruction_surfaces:
        # Fallback: use suite_hash as a pseudo-instruction-surface
        instruction_surfaces = [{
            "kind": "OTHER",
            "path": f"suite:{attestation.get('suite_id', 'unknown')}",
            "sha256": attestation.get("suite_hash", "0" * 64),
            "scope": "suite",
        }]

    effective_digest = compute_effective_digest(instruction_surfaces)

    # --- Build verification FROM LIVE CHECK ---
    # integrity: derived from live hash comparison, NOT from manifest
    # claims: we inherit the manifest's claim_check ONLY if integrity passes.
    #         If integrity fails, claims are N_A (we cannot trust them).
    integrity = integrity_result["integrity"]

    if integrity == "PASS":
        # Integrity is live-verified. Claims can be inherited from the
        # attestation because the underlying bytes are confirmed unchanged.
        claims = attestation.get("claim_check", "N_A")
    else:
        # Integrity failed. Claims are untrustworthy — mark as N_A.
        claims = "N_A"

    exit_code = 0
    if integrity == "FAIL":
        exit_code = 2
    elif claims == "FAIL":
        exit_code = 1

    # Build verification notes from live results
    notes_parts = []
    if integrity == "PASS":
        notes_parts.append(
            f"Live integrity check: all {len(integrity_result['live_file_hashes'])} "
            f"hashed files match manifest and all expected files are present."
        )
        if claims == "PASS":
            notes_parts.append(
                f"Claims inherited from attestation (bytes confirmed unchanged)."
            )
    else:
        if integrity_result["mismatches"]:
            for m in integrity_result["mismatches"]:
                notes_parts.append(
                    f"INTEGRITY FAIL: {m['path']} — "
                    f"manifest declares {m['expected']}, "
                    f"live bytes hash to {m['actual']}."
                )
        if integrity_result["missing"]:
            for p in integrity_result["missing"]:
                notes_parts.append(f"INTEGRITY FAIL: {p} — file missing from pack directory.")
        if receipts_path.exists():
            notes_parts.append("Receipt parsing skipped because integrity failed.")
        notes_parts.append("Claims marked N_A because integrity failed.")

    verification = {
        "integrity": integrity,
        "claims": claims,
        "verifier": {
            "name": "assay-oae-export",
            "version": "0.1.0",
        },
        "exit_code": exit_code,
        "notes": " ".join(notes_parts),
    }

    # --- Assemble OAE ---
    oae = {
        "schema_version": "oae.v0.1",
        "episode_id": f"ep_{attestation.get('run_id', manifest.get('pack_id', 'unknown'))}",
        "capture_class": "HASH_ONLY",
        "replay_class": "NONE",
        "profiles": ["assay.integrity.v1"],
        "identity": {
            "producer": {
                "kind": "sdk",
                "name": "assay",
                "version": attestation.get("verifier_version", "unknown"),
                "vendor": "haserjian",
            },
            "operator": {
                "mode": "unknown",
            },
        },
        "instruction": {
            "surfaces": instruction_surfaces,
            "effective_digest": effective_digest,
        },
        "events": events,
        "artifacts": artifacts,
        "evidence": {
            "anchors": [],
            "redactions": [],
        },
        "verification": verification,
    }

    # --- Write output ---
    if output_path:
        output_path.write_text(json.dumps(oae, indent=2) + "\n")
        print(f"OAE written to {output_path}", file=sys.stderr)

    return oae


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main():
    """Usage: python -m assay_oae.export <proof-pack-dir> [-o output.oae.json] [--repo-root <path>]"""
    import argparse
    parser = argparse.ArgumentParser(description="Export Assay proof pack to OAE v0.1")
    parser.add_argument("pack_dir", type=Path, help="Path to proof pack directory")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output OAE JSON path")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root for instruction surface scanning")
    args = parser.parse_args()

    if not args.output:
        args.output = args.pack_dir / "episode.oae.json"

    oae = export_proof_pack_to_oae(args.pack_dir, args.repo_root, args.output)
    print(json.dumps(oae, indent=2))


if __name__ == "__main__":
    main()
