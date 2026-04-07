# Contributing

OAE is a small spec repo. Keep changes minimal, explicit, and reproducible.

## Ground rules

- Schema changes must include updated fixtures or tests.
- Exporter changes must preserve fail-closed behavior.
- Documentation should describe only behavior that is true in the repo now.
- Keep v0.1 small. Do not add v0.2 fields without an explicit versioned plan.

## Local checks

```bash
python3 -m pip install -e '.[dev]'
pytest -q
npx --yes --package ajv-cli --package ajv-formats \
  ajv validate -c ajv-formats -s schema/oae.v0.1.schema.json \
  --spec=draft2020 \
  -d fixtures/claude_minimal.json \
  -d fixtures/codex_minimal.json \
  -d fixtures/github_action_minimal.json \
  -d examples/real_proof_pack_wrapped.json
```

## Pull requests

- Describe the user-visible or verifier-visible change.
- Call out any schema compatibility impact.
- Include tests for fail-closed paths when touching verification logic.