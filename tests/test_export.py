import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, validate

from assay_oae.export import export_proof_pack_to_oae, sha256_file


def _write_pack(pack_dir: Path) -> Path:
    pack_dir.mkdir()

    receipt_path = pack_dir / "receipt_pack.jsonl"
    receipt_path.write_text(
        '{"receipt_id":"r_001","timestamp":"2026-04-06T00:00:00Z","type":"model_call","provider":"test","model_id":"demo"}\n',
        encoding="utf-8",
    )

    verify_report_path = pack_dir / "verify_report.json"
    verify_report_path.write_text(
        json.dumps(
            {
                "claim_verification": {
                    "passed": True,
                    "n_claims": 1,
                    "n_passed": 1,
                }
            }
        ),
        encoding="utf-8",
    )

    transcript_path = pack_dir / "verify_transcript.md"
    transcript_path.write_text("verification transcript\n", encoding="utf-8")

    signature_path = pack_dir / "pack_signature.sig"
    signature_path.write_text("signature\n", encoding="utf-8")

    manifest = {
        "pack_id": "pack_test_001",
        "pack_root_sha256": "a" * 64,
        "attestation": {
            "run_id": "trace_test_001",
            "suite_id": "manual",
            "suite_hash": "0" * 64,
            "verifier_version": "1.11.1",
            "claim_check": "PASS",
            "assurance_level": "L0",
            "proof_tier": "signed-pack",
            "mode": "shadow",
            "n_receipts": 1,
            "timestamp_start": "2026-04-06T00:00:00Z",
        },
        "files": [
            {"path": "receipt_pack.jsonl", "sha256": sha256_file(receipt_path)},
            {"path": "verify_report.json", "sha256": sha256_file(verify_report_path)},
            {"path": "verify_transcript.md", "sha256": sha256_file(transcript_path)},
        ],
        "expected_files": [
            "receipt_pack.jsonl",
            "verify_report.json",
            "verify_transcript.md",
            "pack_manifest.json",
            "pack_signature.sig",
        ],
        "signer_id": "assay-local",
        "signer_pubkey_sha256": "b" * 64,
    }

    manifest_path = pack_dir / "pack_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return receipt_path


def test_export_passes_for_unchanged_pack(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    receipt_path = _write_pack(pack_dir)

    oae = export_proof_pack_to_oae(pack_dir)

    assert oae["artifacts"][0]["uri_hint"] == "pack/"
    assert oae["artifacts"][0]["metadata"]["files"]["receipt_pack.jsonl"] == sha256_file(receipt_path)
    assert oae["verification"]["integrity"] == "PASS"
    assert oae["verification"]["claims"] == "PASS"
    assert oae["verification"]["exit_code"] == 0


def test_export_fails_closed_for_tampered_file(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    receipt_path = _write_pack(pack_dir)
    receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")

    oae = export_proof_pack_to_oae(pack_dir)

    assert oae["artifacts"][0]["metadata"]["files"]["receipt_pack.jsonl"] == sha256_file(receipt_path)
    assert oae["verification"]["integrity"] == "FAIL"
    assert oae["verification"]["claims"] == "N_A"
    assert oae["verification"]["exit_code"] == 2
    assert "receipt_pack.jsonl" in oae["verification"]["notes"]


def test_export_fails_when_expected_file_is_missing(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    _write_pack(pack_dir)
    (pack_dir / "pack_signature.sig").unlink()

    oae = export_proof_pack_to_oae(pack_dir)

    assert oae["verification"]["integrity"] == "FAIL"
    assert oae["verification"]["claims"] == "N_A"
    assert "pack_signature.sig" in oae["verification"]["notes"]


def test_export_fails_when_manifest_omits_expected_files(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    _write_pack(pack_dir)

    manifest_path = pack_dir / "pack_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("expected_files")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    oae = export_proof_pack_to_oae(pack_dir)

    assert oae["verification"]["integrity"] == "FAIL"
    assert oae["verification"]["claims"] == "N_A"
    assert "manifest.expected_files" in oae["verification"]["notes"]


def test_cli_module_exports_schema_valid_oae(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    _write_pack(pack_dir)
    output_path = tmp_path / "episode.oae.json"
    env = os.environ.copy()
    src_dir = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = str(src_dir)

    subprocess.run(
        [sys.executable, "-m", "assay_oae.export", str(pack_dir), "-o", str(output_path)],
        check=True,
        env=env,
    )

    schema_path = Path(__file__).resolve().parents[1] / "schema" / "oae.v0.1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = json.loads(output_path.read_text(encoding="utf-8"))
    validate(instance=data, schema=schema, cls=Draft202012Validator)