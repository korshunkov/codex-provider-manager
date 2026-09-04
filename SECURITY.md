# Security Policy

## Supported version

Use the latest commit or release from `main`.

## Reporting

Report vulnerabilities privately to the maintainer through GitHub:
<https://github.com/korshunkov/codex-provider-manager/security/advisories/new>.

Do not include real API keys, request payloads, or other sensitive data in a
report.

## Scope notes

The app stores provider credentials in `~/.codex/provider-credentials.json`
with `0600` permissions. The local proxy listens only on `127.0.0.1`.
