"""Deterministic per-field accuracy scoring (NO LLM judges anywhere).

Compares a predicted record against the labeled `expected` record field by field, after
canonical normalization (both are run through the strict model so dates/money are compared
in their canonical form, not as raw strings). Each field gets one outcome:

- match:        predicted == expected, both non-null
- null_match:   predicted == expected == null
- mismatch:     both non-null but different
- missed:       expected has a value, predicted is null (the model dropped a real value)
- hallucinated: expected is null, predicted is non-null (the model invented a value for a
                genuinely-absent field)
- failed_null:  expected is null, but extraction failed so null handling was not observed

Aggregation reports per-field exact-match rate, the hallucinated-field rate, plus total
cost and success-only p50/p95 latency (failed extractions are counted as n_failures but do
not contribute a latency sample). Requests that never reached the model, including
control-plane rejections and connection failures, are counted as n_skipped and kept
out of the per-field denominator entirely, so they cannot deflate the headline numbers
(issue #52). Hallucination and null-handling correctness share the expected-null denominator
from usable records. Failed null fields are reported separately and excluded from those
conditional rates; they remain in overall exact-match with no credit (issue #46).
Pure and dependency-light, so it is trivially testable and never touches the network.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel


class FieldOutcome(StrEnum):
    match = "match"
    null_match = "null_match"
    mismatch = "mismatch"
    missed = "missed"
    hallucinated = "hallucinated"
    failed_null = "failed_null"


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
            outcomes[key] = FieldOutcome.null_match if want is None else FieldOutcome.match
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

    Present values count as missed; expected-null fields get a separate failed-null outcome
    because neither correct null handling nor hallucination was observed. Every field stays
    in the exact-match denominator with no credit. Pair with AccuracyReport.n_failures.
    """
    return {
        key: FieldOutcome.failed_null if value is None else FieldOutcome.missed
        for key, value in _canonical(model_cls, expected).items()
    }


@dataclass
class FieldStats:
    total: int = 0
    matches: int = 0
    null_matches: int = 0  # subset of matches, retained in exact-match totals
    mismatches: int = 0
    missed: int = 0
    hallucinated: int = 0
    failed_null: int = 0

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
    cost_usd_successful: float = 0.0
    cost_usd_failed: float = 0.0
    n_failed_cost_unknown: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    n_failures: int = 0  # fixtures whose extraction failed entirely (no record produced)
    # Fixtures rejected before a model call or not sent because connecting failed; never
    # scored, so excluded from the per-field denominator (#52, #74).
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
    def total_null_matches(self) -> int:
        return sum(s.null_matches for s in self.per_field.values())

    @property
    def total_failed_null(self) -> int:
        return sum(s.failed_null for s in self.per_field.values())

    @property
    def total_null_opportunities(self) -> int:
        """Expected-null fields in usable records; failed extractions are unobservable."""
        return self.total_null_matches + self.total_hallucinated

    @property
    def overall_exact_match_rate(self) -> float:
        return self.total_matches / self.total_fields if self.total_fields else 0.0

    @property
    def hallucinated_field_rate(self) -> float:
        denominator = self.total_null_opportunities
        return self.total_hallucinated / denominator if denominator else 0.0

    @property
    def null_handling_correctness_rate(self) -> float:
        denominator = self.total_null_opportunities
        return self.total_null_matches / denominator if denominator else 0.0


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
    failed_costs_usd: list[float] | None = None,
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
            elif outcome is FieldOutcome.null_match:
                stats.matches += 1
                stats.null_matches += 1
            elif outcome is FieldOutcome.mismatch:
                stats.mismatches += 1
            elif outcome is FieldOutcome.missed:
                stats.missed += 1
            elif outcome is FieldOutcome.hallucinated:
                stats.hallucinated += 1
            elif outcome is FieldOutcome.failed_null:
                stats.failed_null += 1
    report.cost_usd_successful = sum(costs_usd)
    report.cost_usd_failed = sum(failed_costs_usd or [])
    report.n_failed_cost_unknown = n_failures - len(failed_costs_usd or [])
    # The total is a known subtotal when any failed request's spend is unavailable.
    report.cost_usd_total = report.cost_usd_successful + report.cost_usd_failed
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
        # Skipped requests never reached the model; make the scored subset explicit.
        lines.append(
            f"- skipped (before model call, not scored): {report.n_skipped} "
            "(accuracy below covers the scored subset only)"
        )
    # When nothing was scored (an empty corpus, or every fixture skipped as control-plane),
    # 0/0 is not 0%: show "n/a" so the headline never claims a measured rate it does not have.
    overall = f"{report.overall_exact_match_rate:.1%}" if report.total_fields else "n/a"
    null_opportunities = report.total_null_opportunities
    halluc = f"{report.hallucinated_field_rate:.1%}" if null_opportunities else "n/a"
    null_correct = f"{report.null_handling_correctness_rate:.1%}" if null_opportunities else "n/a"
    cost_scope = "known billed requests" if report.n_failed_cost_unknown else "all billed requests"
    failed_cost = f"${report.cost_usd_failed:.4f}"
    if report.n_failed_cost_unknown:
        failed_cost += f" known; unknown failed spend: {report.n_failed_cost_unknown} request(s)"
    lines += [
        f"- overall exact-match: {overall} ({report.total_matches}/{report.total_fields})",
        f"- hallucinated-field rate: {halluc} ({report.total_hallucinated}/{null_opportunities})",
        f"- null-handling correctness: {null_correct} "
        f"({report.total_null_matches}/{null_opportunities})",
        "- null-metric denominator: expected-null fields in usable records; "
        f"{report.total_failed_null} failed expected-null field(s) excluded "
        "(failed fields remain in overall exact-match without credit)",
        f"- cost ({cost_scope}): ${report.cost_usd_total:.4f} "
        f"(successful: ${report.cost_usd_successful:.4f}; failed: {failed_cost}) "
        "| latency p50/p95 (successful): "
        f"{report.latency_p50_ms:.0f}/{report.latency_p95_ms:.0f} ms",
        "",
        "Correct nulls are included in exact-match; failed nulls receive no exact-match credit.",
        "",
        "| field | exact-match | mismatch | missed | hallucinated | correct null | failed null |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key in sorted(report.per_field):
        s = report.per_field[key]
        lines.append(
            f"| `{key}` | {s.exact_match_rate:.0%} ({s.matches}/{s.total}) "
            f"| {s.mismatches} | {s.missed} | {s.hallucinated} "
            f"| {s.null_matches} | {s.failed_null} |"
        )
    return "\n".join(lines)
