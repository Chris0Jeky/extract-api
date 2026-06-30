"""Deterministic per-field accuracy scoring (NO LLM judges anywhere).

Compares a predicted record against the labeled `expected` record field by field, after
canonical normalization (both are run through the strict model so dates/money are compared
in their canonical form, not as raw strings). Each field gets one outcome:

- match:        predicted == expected (including both null)
- mismatch:     both non-null but different
- missed:       expected has a value, predicted is null (the model dropped a real value)
- hallucinated: expected is null, predicted is non-null (the model invented a value for a
                genuinely-absent field)

Aggregation reports per-field exact-match rate, the hallucinated-field rate, plus total
cost and success-only p50/p95 latency (failed extractions are counted as n_failures but do
not contribute a latency sample). Control-plane rejections (a budget_exceeded 402 or
idempotency_conflict 409 that never reached the model) are counted as n_skipped and kept
out of the per-field denominator entirely, so they cannot deflate the headline numbers
(issue #52). A dedicated null-handling-correctness rate over expected-null fields is pending
issue #46. Pure and dependency-light, so it is trivially testable and never touches the
network.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel


class FieldOutcome(StrEnum):
    match = "match"
    mismatch = "mismatch"
    missed = "missed"
    hallucinated = "hallucinated"


def _canonical(model_cls: type[BaseModel], record: dict[str, object]) -> dict[str, object]:
    """Round-trip a record through the strict model so comparison is after normalization.

    Via JSON, because the models are strict (string -> date is accepted in JSON mode but
    rejected in python mode), and so both sides land in the same canonical serialized form.
    """
    return model_cls.model_validate_json(json.dumps(record)).model_dump(mode="json")


def score_record(
    model_cls: type[BaseModel], predicted: dict[str, object], expected: dict[str, object]
) -> dict[str, FieldOutcome]:
    """Per-field outcome for one predicted vs expected record (both canonicalized first)."""
    pred = _canonical(model_cls, predicted)
    exp = _canonical(model_cls, expected)
    outcomes: dict[str, FieldOutcome] = {}
    for key, want in exp.items():
        got = pred.get(key)
        if got == want:
            outcomes[key] = FieldOutcome.match
        elif want is None:
            outcomes[key] = FieldOutcome.hallucinated
        elif got is None:
            outcomes[key] = FieldOutcome.missed
        else:
            outcomes[key] = FieldOutcome.mismatch
    return outcomes


def score_failed(
    model_cls: type[BaseModel], expected: dict[str, object]
) -> dict[str, FieldOutcome]:
    """Outcomes for a fixture whose extraction failed entirely (no record produced).

    The model returned nothing usable, so every expected field counts as missed; this
    keeps a failed extraction in the per-field denominator (it is the accuracy signal),
    rather than dropping the fixture or crashing the run. Pair with AccuracyReport.n_failures.
    """
    return dict.fromkeys(_canonical(model_cls, expected), FieldOutcome.missed)


@dataclass
class FieldStats:
    total: int = 0
    matches: int = 0
    mismatches: int = 0
    missed: int = 0
    hallucinated: int = 0

    @property
    def exact_match_rate(self) -> float:
        return self.matches / self.total if self.total else 0.0


@dataclass
class AccuracyReport:
    doc_type: str
    provider: str
    n_fixtures: int
    per_field: dict[str, FieldStats] = field(default_factory=dict)
    cost_usd_total: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    n_failures: int = 0  # fixtures whose extraction failed entirely (no record produced)
    # fixtures a control-plane guard rejected before any model call (budget_exceeded 402 /
    # idempotency_conflict 409); never scored, so excluded from the per-field denominator (#52).
    n_skipped: int = 0

    @property
    def total_fields(self) -> int:
        return sum(s.total for s in self.per_field.values())

    @property
    def total_matches(self) -> int:
        return sum(s.matches for s in self.per_field.values())

    @property
    def total_hallucinated(self) -> int:
        return sum(s.hallucinated for s in self.per_field.values())

    @property
    def overall_exact_match_rate(self) -> float:
        return self.total_matches / self.total_fields if self.total_fields else 0.0

    @property
    def hallucinated_field_rate(self) -> float:
        return self.total_hallucinated / self.total_fields if self.total_fields else 0.0


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted, non-empty list."""
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(pct / 100.0 * len(sorted_values)))
    return sorted_values[rank - 1]


def aggregate(
    doc_type: str,
    provider: str,
    scored: list[dict[str, FieldOutcome]],
    costs_usd: list[float],
    latencies_ms: list[float],
    *,
    n_failures: int = 0,
    n_skipped: int = 0,
) -> AccuracyReport:
    """Fold per-fixture field outcomes + cost/latency into one report."""
    report = AccuracyReport(
        doc_type=doc_type,
        provider=provider,
        n_fixtures=len(scored),
        n_failures=n_failures,
        n_skipped=n_skipped,
    )
    for outcomes in scored:
        for key, outcome in outcomes.items():
            stats = report.per_field.setdefault(key, FieldStats())
            stats.total += 1
            if outcome is FieldOutcome.match:
                stats.matches += 1
            elif outcome is FieldOutcome.mismatch:
                stats.mismatches += 1
            elif outcome is FieldOutcome.missed:
                stats.missed += 1
            else:
                stats.hallucinated += 1
    report.cost_usd_total = sum(costs_usd)
    ordered = sorted(latencies_ms)
    report.latency_p50_ms = _percentile(ordered, 50)
    report.latency_p95_ms = _percentile(ordered, 95)
    return report


def render_markdown(report: AccuracyReport) -> str:
    """Render one report as a committable markdown section (per-field + summary)."""
    lines = [
        f"### {report.doc_type} / {report.provider}",
        "",
        f"- fixtures scored: {report.n_fixtures} ({report.n_failures} failed extraction(s))",
    ]
    if report.n_skipped:
        # A control-plane rejection (budget_exceeded/idempotency_conflict) never reached the
        # model, so it is excluded from the accuracy denominator; surface it loudly so the
        # numbers below are not misread as covering the whole corpus (issue #52).
        lines.append(
            f"- skipped (control-plane, not scored): {report.n_skipped} "
            "(accuracy below covers the scored subset only)"
        )
    lines += [
        f"- overall exact-match: {report.overall_exact_match_rate:.1%} "
        f"({report.total_matches}/{report.total_fields})",
        f"- hallucinated-field rate: {report.hallucinated_field_rate:.1%} "
        f"({report.total_hallucinated}/{report.total_fields})",
        f"- cost: ${report.cost_usd_total:.4f} | latency p50/p95 (successful): "
        f"{report.latency_p50_ms:.0f}/{report.latency_p95_ms:.0f} ms",
        "",
        "| field | exact-match | mismatch | missed | hallucinated |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key in sorted(report.per_field):
        s = report.per_field[key]
        lines.append(
            f"| `{key}` | {s.exact_match_rate:.0%} ({s.matches}/{s.total}) "
            f"| {s.mismatches} | {s.missed} | {s.hallucinated} |"
        )
    return "\n".join(lines)
