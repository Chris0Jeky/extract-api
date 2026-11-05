# ISO-4217 membership audit

`scripts/audit_iso4217.py` compares the committed `ISO_4217_ALPHA` set with local
copies of SIX's current and historical currency XML. It reports differences for
review. It does not download data, rewrite the accepted set, or implement
date-aware currency validation.

This is the reproducible audit step for [issue #10](https://github.com/Chris0Jeky/extract-api/issues/10).
The ongoing maintenance issue stays open. Its decisions deferring date-aware
membership and special-unit expansion still apply.

## Run an audit

Obtain both files directly from SIX and preserve their original bytes:

- [Current Currency & Funds, List One](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml)
- [Historical Currencies & Funds, List Three](https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-three.xml)

Run from the repository with Python 3.12 or 3.13. The audit uses only the standard
library and loads the accepted constant from this checkout, without importing
the service or its provider dependencies.

```bash
python scripts/audit_iso4217.py \
  --current /path/to/list-one.xml \
  --historical /path/to/list-three.xml

python scripts/audit_iso4217.py \
  --current /path/to/list-one.xml \
  --historical /path/to/list-three.xml \
  --format json > /path/to/currency-audit.json
```

An absolute script path also works from another working directory. Both source
paths are required. The default format is human-readable text; JSON has
`report_version: 1`. Successful parsing writes a report to stdout, including
when drift is found. Invalid input writes a diagnostic to stderr and leaves
stdout empty. Inspect the exit status when redirecting output.

| Exit | Meaning | Next step |
| --- | --- | --- |
| `0` | Supplied code sets agree with the explicit v1 policy. | Record the audit and its source evidence. |
| `1` | At least one membership or policy-status difference needs review. | Investigate the reported codes and the relevant SIX amendments. |
| `2` | Invalid XML, unreadable input, or contradictory/malformed policy. | Correct the input or configuration, then run again. No valid audit report was produced. |

## Existing v1 policy

The expected accepted set is the current list minus the explicit exclusions,
plus the retained historical codes. The script reads runtime membership from
`schemas/iso4217.py`; it does not maintain a second accepted-set snapshot.

| Decision | Codes |
| --- | --- |
| Retain historical codes for existing documents | `ANG`, `BGN` |
| Exclude fund and special-unit codes | `BOV`, `CLF`, `COU`, `MXV`, `USN`, `UYI`, `UYW`, `XAD`, `XBA`, `XBB`, `XBC`, `XBD`, `XSU`, `XUA` |
| Exclude precious metals | `XAG`, `XAU`, `XPD`, `XPT` |
| Exclude testing and no-currency codes | `XTS`, `XXX` |

`CHE` and `CHW` are accepted WIR fund exceptions. `XDR` and the other accepted
supranational currencies remain included. Neither an `IsFund` flag nor an `X`
prefix automatically excludes a code. A previously unknown current code,
including one marked as a fund, requires review.

The policy records the [owner decisions in #10](https://github.com/Chris0Jeky/extract-api/issues/10#issuecomment-4755926425)
and the [2026-11-05 audit](https://github.com/Chris0Jeky/extract-api/issues/10#issuecomment-6647475480).
That audit recorded 160 accepted codes, including 158 current codes and retained
`ANG`/`BGN`, against 178 distinct current codes. Those counts describe that review;
the CLI does not require upstream counts to remain fixed.

The historical list confirms the two retention exceptions. A newly withdrawn
accepted code still requires a retention decision even if it appears in List
Three. Other historical entries, including `HRK` and `VEF`, do not become
accepted merely because they appear in the source. Withdrawal dates are not
used to validate a document's issue date.

## Read the findings

Every finding contains a sorted list of codes. An empty list means no difference
of that kind was found.

| Finding | What needs review |
| --- | --- |
| `current_not_accepted` | Current codes missing from v1 that are not explicitly excluded. |
| `accepted_not_current` | Accepted codes absent from the current list that have no retention exception. |
| `retained_not_accepted` | A configured historical exception is missing from runtime membership. |
| `retained_missing_from_history` | A retention exception cannot be found in the supplied historical list. |
| `excluded_not_current` | An exclusion is absent from the current list and may be stale. |
| `retained_now_current` | A historical exception is current again, so the recorded status needs review. |

Contradictory exclusion/retention rules, accepting an explicitly excluded code,
or malformed policy codes produce exit `2`. Fix the decision or configuration
explicitly; do not suppress these errors by automatically changing membership.

## Provenance and parser limits

Each source report includes the root `Pblshd` date, a SHA-256 digest of the exact
input bytes, record count, distinct code count, and no-currency record count.
Duplicate country/entity records contribute to the record count and share one
alphabetic code in the membership comparison. The publication date describes
the file, not a single effective date for all its currencies.

The reported SIX URLs are reference labels. They do not prove that the local
files came from those URLs. A hash identifies bytes; it does not authenticate
their origin, prove completeness, or establish that they are current. The CLI
does not check a signature, contact SIX, or reject a file based on its age. A
historical subset containing both retention exceptions can pass this comparison.
Before treating a clean result as a current maintenance audit, independently
confirm the download source and publication dates against SIX. Retain the raw
files with the report and record the checkout commit used for the comparison.

Inputs must use the `ISO_4217` root, a valid `YYYY-MM-DD` publication date, and
the expected `CcyTbl/CcyNtry` or `HstrcCcyTbl/HstrcCcyNtry` structure. Each code
must contain exactly three uppercase ASCII letters. Missing codes are rejected
except current entries explicitly named `No universal currency` with no numeric
code. Empty code sets, ambiguous code elements, mixed or duplicate tables,
malformed XML, DTD/entity declarations, and files larger than 2 MiB are rejected.
Unknown fields inside currency records are ignored. This is a membership audit,
not validation of currency names, numeric identifiers, minor units, fund flags,
withdrawal ranges, or every other field in SIX's files.

Reports contain no wall-clock timestamp or local filename. Given the same
source bytes, accepted set, audit policy, and script version, their contents are
deterministic. Reformatting or reordering a source changes its byte hash even
when membership findings stay the same.

## Maintenance cadence and follow-up

Run the audit quarterly, when a currency-related fixture fails, or when a known
SIX amendment could affect accepted document currencies. Record the review date,
checkout commit, both publication dates and hashes, findings, and resulting
decision in issue #10. Keep the issue open for subsequent audits.

Investigate drift before editing `schemas/iso4217.py`. A membership change needs
its own reviewed change, updated regression expectations, and an explicit
decision about affected documents. Adding a special unit or date-aware behavior
does not follow automatically from an audit finding.

This slice has no scheduled workflow and makes no network request during CI.
An audit against locally supplied fresh sources is separate from the offline
regression suite:

```bash
uv run python -m pytest --no-cov tests/test_audit_iso4217.py tests/test_iso4217.py
```

The XML files under `tests/fixtures/iso4217/` are clearly labeled synthetic test
inputs. Their independently committed code names exercise the reviewed baseline,
while their names and dates are test data. The historical fixture is deliberately
incomplete. Do not use these fixtures as evidence of today's ISO-4217 membership
or reuse official-download hashes for their synthetic bytes.
