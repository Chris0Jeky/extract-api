# Synthetic ISO-4217 audit fixtures

These files are hand-specified parser and policy test inputs, not downloads from
SIX and not an authoritative currency dataset. Names, publication dates and
withdrawal dates are test data. Their SHA-256 hashes identify these synthetic
bytes only.

- `synthetic-list-one.xml` fixes the 178 distinct code names recorded by the
  2026-11-05 audit in issue #10. It also contains one duplicate USD entity record
  and one no-currency entity, for 180 records. Selected fund flags exercise the
  rule that flags do not override the explicit policy.
- `synthetic-list-three.xml` is a four-code subset, containing retained ANG/BGN
  and unaccepted HRK/VEF. It is not a complete historical list and its withdrawal
  dates must not be used as real currency dates.

The code names are committed independently of `schemas/iso4217.py`; tests do not
build the baseline from the accepted runtime set. Use freshly obtained official
XML files, not these fixtures, for a real maintenance audit. See
`docs/ops/CURRENCY_AUDIT.md` for the procedure and provenance limits.
