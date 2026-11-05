# Status

Current handoff: 2026-11-05.

## Engineering state

The invoice and job-posting API paths, both provider adapters, strict validation
and retry trail, SQLite replay, budget accounting, PDF text extraction, caller
auth, and deterministic accuracy harness are implemented. Provider timeout values
must be positive and finite; retry counts must be nonnegative. This describes
repository behavior, not a deployed service or measured provider performance.

Both provider adapters reject malformed token counts and overflowing/non-finite
costs through `provider_error`, preserving known spend from previous attempts.
Absent usage retains the documented zero fallback; unknown charges are not
reconstructed. PDF text limits include the separators inserted between pages,
including blank pages.

The #46 metric work is complete. Exact null matches earn exact-match credit.
Hallucination and null-handling correctness rates use expected-null fields in
usable, schema-valid predictions, are complementary, and show `n/a` when that
conditional denominator is zero. Failed records earn no exact-match credit;
reports explicitly count their expected-null fields as exclusions from the
conditional null metrics. Terminal validation failures retain billed costs.
Connection errors and connection timeouts before a request is sent are skipped
with zero cost; other transport failures remain failures. Schema-invalid
predictions have an explicit diagnostic (#74).

Successful HTTP response metadata is also validated: cost and latency must be
finite, nonnegative JSON numbers (not booleans or numeric strings), and provider
must be a nonblank string. Malformed metadata counts as a failed extraction while
preserving independently known cost. Report destinations are checked before live
requests, and completed reports replace the target atomically so partial writes
do not destroy an earlier report. Stdout remains a separate output sink. See
`docs/testing/MANUAL_VERIFICATION.md` for the failure-path checks and limitations.

Readiness now exposes the startup-captured `caller_auth_configured` boolean.
Deployment verification requires literal `true` and a keyless extraction probe
that returns 401. The probe uses an invalid `{}` body so an auth regression cannot
trigger provider work. Operational steps are in `docs/ops/RUNBOOK.md`; owner
provisioning remains open.

## Fixtures and evidence still needed

| Corpus | REVIEWED | DRAFT |
| --- | ---: | ---: |
| Invoices | 10 | 20 |
| Job postings | 0 | 20 |

The 40 new fixtures are synthetic drafts. The existing 10 reviewed invoices are
unchanged. DRAFT fixtures remain excluded from scoring, and the T15 target of
30-50 reviewed fixtures per type with a 50/50 real/synthetic mix is not met.
`uv run make accuracy-rehearsal` echoes reviewed labels through the real API at
zero provider cost; it verifies orchestration, not provider accuracy.

The remaining human evidence and provisioning tasks are recorded in
`tasks/BACKLOG.md`:

- **T15:** human label review and corpus completion.
- **T17:** paid runs against both providers and the committed accuracy,
  hallucination, null-handling, cost, and latency table.
- **T20:** measured README numbers after those runs.
- **T21:** gateway trace evidence.
- **H1-H7:** owner hosting, secrets, deployment, live-provider, and domain setup.

These tasks remain open. The README keeps its numbers-pending statement.

## Deferred and closed follow-ups

Sequential idempotency replay is the current contract; concurrent in-flight
reservation remains deferred in #42. Invoice schema changes in #35 and #54 need
coordinated `invoice.v2` work. Hook follow-ups #13, #83, and #167 remain open.
The #88 integrity gap is covered by a verified upstream commit and SHA-256 pin,
a cheap check in ordinary CI and `ci-quick`, and a canonical matrix workflow
conditional on floor or integrity/gate changes. The vendored floor is not wired
by committed settings; these checks do not prove runtime activation.
The #167 source archive remains on the owner host and
is not included in the repository. #10 remains open for periodic currency audits;
#32 remains a tripwire for future HTTPException paths that need an owner taxonomy
decision.

The stale lockfile issue #6 and fixes tracked by #57, #79, #86, #87, and #91 have
been resolved. Use current PR checks for exact test counts and coverage rather
than historical snapshots.

## Maintenance evidence

`scripts/audit_iso4217.py` compares local SIX current/historical XML with the actual
v1 membership and explicit compatibility policy. It reports reproducible hashes,
publication metadata and reviewable drift without changing the 160-code set.
The regression fixtures are synthetic; a fresh official-source run remains
outstanding. Commands, exit codes and quarterly cadence are documented in
`docs/ops/CURRENCY_AUDIT.md`.

The image workflow now records offline behavior probes and installed-source hashes
for the two CPython findings in #194. Both behaviors were reproduced in the
packaged Python 3.13.18 image; application exploitability and supported remediation
remain unresolved. An inconclusive probe fails the job while preserving its JSON
artifact and summary. Grype's gate is unchanged. See
`docs/ops/RUNTIME_SECURITY.md`; these probes are not a vulnerability-clearance claim.

## Reproducible local checks

```sh
uv sync --locked --extra dev
uv run make ci-quick
uv run make fixtures-validate
uv run make smoke
uv run make accuracy-rehearsal
```

The full-suite coverage floor is 95%. These local checks require no paid provider
run and do not satisfy T17, T20, T21, or owner provisioning.
