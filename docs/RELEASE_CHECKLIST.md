# Local V1 Release Checklist

This checklist supports review; it does not declare a release.

Use the [verification guide](development/verification.md#tier-4-release-verification) for exact script steps, environments and side effects, and its [integration tier](development/verification.md#tier-5-explicitly-authorized-integration) for separately authorized live/browser/clean-machine/process checks. This checklist retains the release gates; a change-based test recommendation cannot waive them.

## Automated credential-free gate

After `setup-local.ps1`, run:

```powershell
.\scripts\verify-release.ps1
```

It runs every credential-free Python test **except** those marked
`windows_process`, plus the complete frontend suite, TypeScript typecheck,
production build, Python compilation, Ruff correctness rules
(`E9,F63,F7,F82`), Python dependency consistency, production npm vulnerability
audit, documentation/API/security tests, and Git whitespace validation. It
performs no ESPN request, starts no real application/launcher process, and does
not alter user databases. The repository does not currently claim a full-style
Ruff baseline.

**Credential-free does not mean offline or read-only.** The production npm audit contacts the configured registry; compilation/tests/builds write bytecode, caches, temporary data and frontend artifacts. Its audit threshold is `--omit=dev --audit-level=high`, not a full dependency-security guarantee. Do not use `audit fix` or upgrade dependencies to bypass a failure without authorization. An earlier failing step prevents later checks; report which actually ran. Dated audit/test counts elsewhere are historical evidence.

The disposable launcher/process tier is explicit because it creates and terminates launcher-owned test processes:

```powershell
.\scripts\verify-release.ps1 -IncludeWindowsProcessTests
```

The switch adds one dedicated `pytest -m windows_process` invocation after the
default tier. The default selector is `not windows_process`, so the two sets are
disjoint and the marked tests execute exactly once. On unsupported operating
systems, the marked tests are collected in the opt-in tier and skipped by their
existing platform conditions.

## Reviewer signoff

- [ ] Revision and working tree recorded.
- [ ] Clean setup and production-local start succeed on Windows.
- [ ] Health identity matches the launcher metadata and static assets come from `frontend/dist`.
- [ ] Sanitized refresh/snapshot workflow or accepted live evidence reconciled.
- [ ] Baseline, action search, manual scenario, retained history, and restart smoke succeed.
- [ ] Statistical incompleteness and capability limitations remain visible.
- [ ] No P0 or P1 finding remains open.
- [ ] Known limitations and recovery procedure reviewed.
- [ ] Private data, credentials, databases, and temporary artifacts are absent from Git.
- [ ] Independent reviewer decides release disposition.
