# Paid benchmark approval and operator checklist

## Approval

- Run ID:
- Repository SHA:
- Corpus version/hash:
- Providers/models:
- Fixture selection:
- Maximum spend USD:
- Price source/date:
- Approved by:
- Approval timestamp:
- Transport retry/abort limits:
- Unknown-cost policy:

## Offline evidence

- [ ] Working tree clean
- [ ] `make ci-quick`
- [ ] `make fixtures-validate`
- [ ] `make smoke`
- [ ] Full perfect rehearsal
- [ ] Full failure/interruption/resume rehearsal
- [ ] Manifest schema validation
- [ ] Journal write/fsync test
- [ ] No secrets/raw content in logs

## Configuration

- [ ] Exact non-empty model IDs
- [ ] Provider/effective route expected
- [ ] SDK versions recorded
- [ ] Input/output prices finite and nonnegative
- [ ] Budget exceeds approved upper-bound estimate but not approval cap
- [ ] Timeout/retries frozen
- [ ] Prompt/schema/dependency/container hashes frozen

## Pilot

- [ ] 2-3 representative fixtures per provider/domain
- [ ] Live structured-output compatibility proven
- [ ] Cost/tokens/attempts present
- [ ] 422 failed-cost path checked or rehearsed
- [ ] No mixed provider/model
- [ ] Human pilot approval obtained

## Full run

- [ ] New run directory; no overwrite
- [ ] Journal appended after every fixture
- [ ] No unresolved ambiguous-sent outcomes
- [ ] Infrastructure threshold not exceeded
- [ ] Spend within cap
- [ ] Journal complete and valid
- [ ] Summary/report regenerated from journal
- [ ] Outlier review completed
- [ ] Public claim approval completed
