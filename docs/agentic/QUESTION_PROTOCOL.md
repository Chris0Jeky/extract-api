# Question protocol (ask vs proceed)

Stay autonomous but safe. Ask only when the answer is genuinely Chris's to make;
otherwise proceed with a stated, reversible assumption.

## Ask first

- Irreversible or hard-to-reverse actions (data loss, history rewrite, deletes).
- Anything touching credentials, secrets, or security posture.
- Outward-facing actions beyond the declared authority (deploy, publish to a
  third party). Pushing a branch and opening a PR are free at T2.
- A decision that contradicts a locked decision or an ADR.

## Proceed with a stated assumption

For everything else, pick the obvious option, note it, and continue. Use the
template so the choice is visible and reversible:

```
Assumption: <specific assumption>.
Reason: <source or convention>.
Reversible by changing <file/setting>.
```

## Batch questions

If several questions arise, batch them into one numbered list with a recommended
default per item, rather than interrupting repeatedly.
