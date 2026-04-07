"""
Tests for the independent OAE verifier.

The verifier imports NOTHING from assay_oae. These tests confirm
that a fresh user can verify envelopes without the exporter.
"""

import json
import subprocess
import os
import sys
from pathlib import Path

import pytest

from oae_verify.verify import verify_envelope, VerifyResult


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "schema" / "oae.v0.1.schema.json"
FIXTURES_DIR = REPO_ROOT / "fixtures"
EXAMPLES_DIR = REPO_ROOT / "examples"


@pytest.fixture
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load(name: str) -> dict:
    """Load a fixture or example by filename."""
    for d in (FIXTURES_DIR, EXAMPLES_DIR):
        p = d / name
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(name)


# ---------------------------------------------------------------------------
# Valid fixtures should pass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", [
    "claude_minimal.json",
    "codex_minimal.json",
    "github_action_minimal.json",
])
def test_valid_fixtures_pass_cleanly(schema: dict, fixture_name: str) -> None:
    """Valid fixtures must verify with zero errors AND zero warnings."""
    oae = _load(fixture_name)
    result = verify_envelope(oae, schema)
    assert not result.errors, f"{fixture_name} errors: {result.errors}"
    assert not result.warnings, f"{fixture_name} warnings: {result.warnings}"
    assert result.exit_code == 0, f"{fixture_name} exit_code={result.exit_code}, expected 0"


def test_real_example_passes_cleanly(schema: dict) -> None:
    """The canonical exporter-generated example must also verify cleanly."""
    oae = _load("real_proof_pack_wrapped.json")
    result = verify_envelope(oae, schema)
    assert not result.errors, f"real_proof_pack_wrapped errors: {result.errors}"
    assert not result.warnings, f"real_proof_pack_wrapped warnings: {result.warnings}"
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Broken fixture must produce nonzero exit_code
# ---------------------------------------------------------------------------

def test_broken_fixture_catches_inconsistencies(schema: dict) -> None:
    oae = _load("broken_inconsistent.json")
    result = verify_envelope(oae, schema)

    # Must catch at least one warning (consistency issues)
    assert result.warnings, "broken fixture should produce warnings"

    # Specific checks it should catch:
    # 1. integrity=FAIL but claims=PASS (should be N_A)
    claims_warn = [w for w in result.warnings if "claims" in w.lower()]
    assert claims_warn, "should warn about claims=PASS when integrity=FAIL"

    # 2. exit_code=0 but integrity=FAIL (should be 2)
    exit_warn = [w for w in result.warnings if "exit_code" in w.lower()]
    assert exit_warn, "should warn about exit_code inconsistency"

    # 3. effective_digest mismatch
    digest_warn = [w for w in result.warnings if "effective_digest" in w.lower()]
    assert digest_warn, "should warn about effective_digest mismatch"


def test_broken_fixture_exit_code_is_nonzero(schema: dict) -> None:
    oae = _load("broken_inconsistent.json")
    result = verify_envelope(oae, schema)
    assert result.exit_code != 0, f"broken fixture should have nonzero exit_code, got 0"


# ---------------------------------------------------------------------------
# Schema-invalid input must produce errors
# ---------------------------------------------------------------------------

def test_missing_required_fields_produces_errors(schema: dict) -> None:
    """An envelope missing required fields should get schema errors."""
    oae = {"schema_version": "oae.v0.1"}  # missing everything else
    result = verify_envelope(oae, schema)
    assert result.errors, "missing-fields envelope should have errors"
    assert result.exit_code == 2


def test_bad_schema_version_produces_error(schema: dict) -> None:
    """Wrong schema_version should fail schema validation."""
    oae = _load("claude_minimal.json")
    oae["schema_version"] = "oae.v99.0"
    result = verify_envelope(oae, schema)
    schema_errors = [e for e in result.errors if "schema_version" in e.lower()]
    assert schema_errors, "wrong schema_version should produce schema error"


def test_invalid_timestamp_format_produces_error(schema: dict) -> None:
    """Schema format: date-time must be enforced, not silently ignored."""
    oae = _load("claude_minimal.json")
    oae["events"][0]["ts"] = "not-a-timestamp"
    result = verify_envelope(oae, schema)
    ts_errors = [e for e in result.errors if "not-a-timestamp" in e or "date-time" in e.lower() or "format" in e.lower()]
    assert ts_errors, f"invalid timestamp should produce format error, got errors={result.errors}"


def test_invalid_capture_class_produces_error(schema: dict) -> None:
    oae = _load("claude_minimal.json")
    oae["capture_class"] = "INVALID_CLASS"
    result = verify_envelope(oae, schema)
    assert result.errors


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_schema_still_runs_consistency_checks() -> None:
    """Verifier should work even without schema (skips schema check)."""
    oae = _load("claude_minimal.json")
    result = verify_envelope(oae, schema=None)
    # Should still check digest, chain, etc. — no crash
    assert isinstance(result, VerifyResult)


def test_empty_events_with_schema_fails(schema: dict) -> None:
    """Schema requires minItems:1 on events."""
    oae = _load("claude_minimal.json")
    oae["events"] = []
    result = verify_envelope(oae, schema)
    assert result.errors


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

def test_cli_returns_zero_for_valid_fixture() -> None:
    """Valid fixtures must return exit code 0 — no warnings tolerated."""
    env = os.environ.copy()
    src_dir = REPO_ROOT / "src"
    env["PYTHONPATH"] = str(src_dir)

    proc = subprocess.run(
        [
            sys.executable, "-m", "oae_verify.verify",
            str(FIXTURES_DIR / "claude_minimal.json"),
            "--schema", str(SCHEMA_PATH),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, (
        f"CLI should return 0 for valid fixture, got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_cli_returns_nonzero_for_broken_fixture() -> None:
    env = os.environ.copy()
    src_dir = REPO_ROOT / "src"
    env["PYTHONPATH"] = str(src_dir)

    proc = subprocess.run(
        [
            sys.executable, "-m", "oae_verify.verify",
            str(FIXTURES_DIR / "broken_inconsistent.json"),
            "--schema", str(SCHEMA_PATH),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0, (
        f"CLI should return nonzero for broken fixture\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )


def test_cli_json_output() -> None:
    env = os.environ.copy()
    src_dir = REPO_ROOT / "src"
    env["PYTHONPATH"] = str(src_dir)

    proc = subprocess.run(
        [
            sys.executable, "-m", "oae_verify.verify",
            str(FIXTURES_DIR / "broken_inconsistent.json"),
            "--schema", str(SCHEMA_PATH),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    output = json.loads(proc.stdout)
    assert "exit_code" in output
    assert "errors" in output
    assert "warnings" in output
    assert output["exit_code"] != 0
