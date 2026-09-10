# In-repo agent bootstrap: extract-api acceleration

You are operating inside `Chris0Jeky/extract-api`. This bundle was prepared from snapshot `aeacafa63685af3b47030375d13b2b5c1d5979f9` on 2026-09-04. The current repository may have moved. Treat this bundle as an evidence-backed proposal, not higher authority than the live user prompt, `AGENTS.md`, the current tier declaration, or current code.

## Mission

Drive the repository from engineering-complete/evidence-incomplete to a reproducible measured v0.1 release, then package the benchmark as a reusable release-gate workload. Progress is merged, verified slices and reviewed evidence, not more planning documents.

## Authority and safety

1. Read the user prompt, `AGENTS.md`, `.agent-harness/tier.json`, `CLAUDE.md`, `tasks/BACKLOG.md`, current ADRs and this bundle.
2. Record conflicts. Current code and tests beat stale narrative status, except where an explicit owner decision locks a contract.
3. Do not run paid provider calls without a fresh explicit human approval naming run ID, providers/models, fixture set and maximum spend.
4. Do not change `DRAFT` to `REVIEWED` unless the commit is explicitly human-authored/approved. An agent may correct DRAFT candidates but must not certify its own ground truth.
5. Do not weaken or self-certify the agent safety floor. Changes to shared guardrails require independent/human review.
6. Never commit keys, `.env`, raw sensitive real documents, provider response bodies containing source content, or private provenance material.
7. Keep one coherent slice per PR. Preserve the existing strict/fail-loud philosophy.

## First-run ritual

Run and save the output under `.acceleration/extract-api/baseline/`:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git log -1 --oneline
python --version
uv --version
make ci-quick
make fixtures-validate
make smoke
```

Also inspect:

```bash
git ls-files .agent-harness .claude/hooks .claude/settings.json
python - <<'PY'
from pathlib import Path
for p in [Path('.agent-harness/tier.json'), Path('.claude/settings.json'), Path('.claude/hooks/dispatch.py')]:
    print(p, 'exists=' + str(p.exists()))
PY
```

If current `HEAD` differs from `aeacafa63685af3b47030375d13b2b5c1d5979f9`, compare changes touching `api/`, `llm/`, `schemas/`, `harness/`, `fixtures/`, `tasks/`, `docs/`, `.claude/` and `.agent-harness/`. Amend the task manifest rather than blindly applying stale assumptions.

## Inputs

- `machine/agent-task-manifest.json`: authoritative task/dependency proposal from this bundle.
- `machine/default-selections.json`: recommended decisions.
- A deck export, when provided: user-selected decisions override defaults.
- `machine/issue-triage.json`: issue hygiene actions.
- `decisions/ADR-*.md`: drafts, not accepted records.
- `candidate-fixtures/`: synthetic DRAFT candidates, not truth.

Validate the bundle first:

```bash
python .acceleration/extract-api/scripts/validate_bundle.py
```

Render the active plan:

```bash
python .acceleration/extract-api/scripts/render_agent_plan.py   --selection .acceleration/extract-api/machine/default-selections.json   --out .acceleration/extract-api/ACTIVE_PLAN.md
```

Replace the selection input with the exported deck JSON when available.

## Execution order

### Wave 0: current-state proof

- Revalidate head and open work.
- Merge/refresh #119 if still applicable and green.
- Record actual tests/coverage/gates. Do not repeat stale 323/99% claims without measuring them.

### Wave 1: tracking coherence

- Close #86, #87 and #91 if their premises remain fixed.
- Rewrite/split #74, #79, #80 and #88.
- Create evidence milestones/labels.
- Reconcile STATUS/PLAN/ADR/CLAUDE/README drift.

This wave may proceed in parallel with ADR drafting but should land before agents use the backlog as authority.

### Wave 2: benchmark contract and safety

Do not implement scoring semantics until the owner accepts the metric decisions. Then:

- implement layered request/extraction/semantic accounting;
- fix expected-null hallucination denominator;
- preserve strict document-level success;
- surface failed 422 cost;
- classify transport/infrastructure outcomes;
- add frozen manifest, append-only JSONL journal and hash-safe resume;
- prevent mixed provider/model/config runs;
- add targeted job-schema invariants if approved.

All of Wave 2 must be fully offline-testable.

### Wave 3: corpus factory

- Import candidate fixtures without overwriting existing IDs.
- Keep every imported file DRAFT.
- Generate a sidecar corpus manifest and coverage matrix.
- Present human review batches ordered low ambiguity first.
- Track real-anonymized sourcing as human tasks.
- Never add fixtures the schema cannot faithfully label unless they are explicitly marked inadmissible and excluded from scoring.

### Wave 4: deterministic rehearsal

Build a test-only response map or in-process ASGI runner. It must not let production runtime load `expected` labels. Prove:

- a perfect whole-corpus run;
- validation failure with billed cost;
- provider/control-plane/transport failures;
- interruption and resume;
- output write failure;
- provider/model drift rejection;
- incomplete-run claim guard.

### Wave 5: paid evidence

Hard gate. Require a human-created approval record. Run a representative pilot first. Stop on:

- unexpected provider/model;
- unknown/zero price not explicitly approved;
- missing usage under a cost-required policy;
- infrastructure failure above threshold;
- manifest mismatch;
- budget risk;
- journal write failure;
- secrets/content appearing in logs.

Only after pilot review may a full run proceed.

### Wave 6: publish and gate

Generate the report from the journal, obtain human claim approval, update README/status, create a release artifact, then promote a human-approved baseline. Gate rules should be relative to measured variance; do not invent absolute floors before data.

### Wave 7: post-evidence hardening

Resolve shared floor provenance, duplicate hook/normalizer cleanup, gateway-only deployment, structured logs and scale-triggered epics. Do not pull these into the release-blocker path unless they directly invalidate evidence or safe deployment.

## PR expectations

Every PR must state:

- task ID(s) from the manifest;
- contract changed or preserved;
- files touched;
- tests run and exact results;
- paid calls: yes/no and approval reference;
- fixture truth status changed: yes/no and reviewer;
- known follow-ups explicitly not bundled.

## Stop conditions

Stop and ask for an owner decision only when execution would otherwise:

- spend money;
- promote ground truth;
- change a public metric definition;
- change a schema field set/versioning contract;
- expose the service publicly;
- alter licensing;
- alter shared agent guardrails;
- publish claims or a release.

For ordinary implementation uncertainty, choose the recommended default in the decision catalog, document the reversible choice and continue.

## Completion report

At the end of each wave, produce:

- merged PRs and task IDs;
- current gate outputs;
- issue/milestone changes;
- decisions consumed and unresolved;
- corpus counts by source/status/type;
- paid spend, only if authorised;
- next unblocked wave;
- divergences from this bundle and why.
