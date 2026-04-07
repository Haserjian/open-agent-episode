# Security Policy

## Reporting a vulnerability

If you find a security issue in the OAE exporter, schema, or verification guidance, do not open a public issue first.

Report it privately to the maintainer with:

- a short description of the issue
- affected version or commit
- reproduction steps or proof of concept
- expected impact

Until a dedicated private reporting channel is added, use GitHub security advisories for this repo if available. If that path is unavailable, contact the maintainer directly and avoid publishing exploit details before a fix is ready.

## Scope

This policy covers:

- the reference exporter under `src/assay_oae/`
- the published schema under `schema/`
- verification guidance in the public docs

It does not cover third-party tools that consume OAE unless the issue is caused by this repo's reference implementation or published artifacts.