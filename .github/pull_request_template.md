## Summary
<!-- 1-3 bullets: what changed and why -->

## Type of change
<!-- feat / fix / refactor / test / chore / docs -->

## Checklist
- [ ] `make ci-quick` passes (ruff + mypy strict + pytest)
- [ ] Behavior change ships with tests; errors handled explicitly (no swallowed failures)
- [ ] No secrets committed (env refs only; `.env.example` updated if needed)
- [ ] Small, conventional commits (`<area>: <imperative summary>`)
- [ ] No em dashes anywhere
- [ ] Provider SDKs imported only in `llm/client.py`

## Risk notes
- Security impact:
- Behavior / regression risk:
- Follow-up tasks:

## Test plan
<!-- How did you verify this change? Commands + results, including any manual API checks. -->
