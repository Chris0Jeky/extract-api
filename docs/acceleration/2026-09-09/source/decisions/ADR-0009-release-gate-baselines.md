# ADR-0009: Human-promoted release-gate baselines

- Status: Proposed
- Related: LLM Release Gate horizon

## Decision

A benchmark run becomes a regression baseline only through an explicit human-approved promotion file/PR. “Latest” is never implicitly the baseline.

Comparisons require compatible corpus/schema/prompt identity unless the rule explicitly allows a changed dimension. Start with relative regression rules and warnings; derive thresholds from repeated-run variance rather than intuition.

## Required baseline metadata

- run ID and run manifest hash;
- report/summary hashes;
- promotion date and approver;
- intended scope (provider/model/doc type);
- compatible corpus/schema/prompt constraints;
- absolute floors, if any, with rationale;
- relative block/warn rules;
- expiry/revalidation trigger.

## Recommended cadence

- offline deterministic suite on every PR;
- paid canary on provider/prompt/schema/client/gateway changes, never on untrusted fork code;
- full paid corpus on release candidates or explicit baseline refresh;
- periodic variance runs to calibrate thresholds.

## Consequences

The repository becomes a living quality instrument rather than a one-off README benchmark. Baselines remain accountable and cannot drift merely because a new run exists.
