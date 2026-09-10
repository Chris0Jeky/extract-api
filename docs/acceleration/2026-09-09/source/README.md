# extract-api acceleration bundle

**Repository:** `Chris0Jeky/extract-api`  
**Review snapshot:** `main` at `aeacafa63685af3b47030375d13b2b5c1d5979f9`  
**Review date:** 2026-09-04

This bundle turns the repository review into material an in-repo agent can actually execute. It contains:

- a self-contained interactive decision studio;
- a comprehensive technical/product review;
- issue close/rewrite/split recommendations;
- a dependency-aware task graph with human and paid-call gates;
- draft ADRs for benchmark metrics, run durability, transport failures and corpus governance;
- machine-readable JSON schemas and example manifests;
- implementation sketches and complete reference modules;
- 38 synthetic fixtures marked `DRAFT` so human work starts at review rather than authorship;
- prompts, checklists, issue comments and safe unbundling scripts.

## Bottom line

`extract-api` is not an unfinished CRUD prototype. The data plane is already a disciplined, compact, synchronous LLM extraction service with strict Pydantic contracts, a two-attempt validation-retry loop, OpenAI/Anthropic adapters, deterministic errors, PDF text extraction, SQLite replay protection, cost accounting, Docker and strong CI.

The project is nevertheless **not yet evidence-complete**. Its advertised differentiator is measured per-field quality, but the repository currently has ten reviewed invoice fixtures, no reviewed job-posting fixtures, no committed evaluation report and unresolved accounting semantics. The next milestone should therefore be **benchmark integrity and corpus completion**, not more extraction features.

The strongest horizon is to make this repository both:

1. a credible reference implementation showing how to make structured-output LLM calls strict, inspectable and cost-aware; and
2. a reusable structured-output workload for a wider **LLM Release Gate** that detects regressions in model, prompt, gateway, schema, cost and latency.

A generic hosted extraction API may become useful, but it is a weaker near-term wedge than the evidence/release-gate role. Do not build OCR, async queues, more providers, invoice.v2 or multi-tenancy before the first measured baseline.

## Start here

1. Open `decision-deck/index.html` and make or adjust the recommendations.
2. Export `extract-api-agent-handoff.json` from the deck.
3. Read `AGENT_BOOTSTRAP.md`.
4. From this bundle, run:

```bash
python scripts/validate_bundle.py
python scripts/unbundle.py --repo /path/to/extract-api          # dry-run
python scripts/unbundle.py --repo /path/to/extract-api --apply  # safe copy to .acceleration/extract-api
python scripts/render_agent_plan.py   --selection /path/to/extract-api-agent-handoff.json   --out /path/to/PLAN_FROM_DECISIONS.md
```

`unbundle.py` never touches application source or overwrites files by default. It copies the bundle into `.acceleration/extract-api/`, where the in-repo agent can inspect and selectively promote drafts through normal PRs.

## Important safety boundaries

- No paid provider call is authorised by this bundle. Paid tasks require an explicit human approval tied to a run ID and maximum spend.
- Candidate fixtures are `DRAFT`; an agent must not self-promote them to `REVIEWED`.
- Agent safety-floor changes require independent/human review. The constrained agent should not unilaterally weaken its own guardrails.
- Revalidate the repository head before acting. This review is pinned to `aeacafa63685af3b47030375d13b2b5c1d5979f9`.
- This review was static. CI evidence was inspected through GitHub, but the source tree could not be cloned and tests were not independently executed in the review environment.

## Main files

| File | Purpose |
|---|---|
| `MASTER_REVIEW.md` | Complete review, architecture, issue analysis, risks and horizon |
| `AGENT_BOOTSTRAP.md` | Exact in-repo agent operating instructions |
| `decision-deck/index.html` | Interactive decisions, notes and JSON/Markdown export |
| `machine/agent-task-manifest.json` | Dependency-aware execution graph |
| `machine/issue-triage.json` | Close/rewrite/split/keep recommendations for every open issue |
| `decisions/` | Draft ADRs ready to adapt into `docs/adr/` |
| `implementation/` | Schemas, examples, patch guidance and reference code |
| `candidate-fixtures/` | 14 invoice and 24 job-posting DRAFT candidates |
| `prompts/` | Agent, fixture drafting/review and paid-run prompts |
| `templates/` | Reports, checklists, issue comments and decision logs |
| `sources/source-map.json` | Repository source URLs used by the review |
