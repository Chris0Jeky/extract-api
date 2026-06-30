"""Deterministic per-field accuracy scoring (T16): outcomes, aggregation, markdown."""

from __future__ import annotations

import pytest

from harness.scoring import FieldOutcome, aggregate, render_markdown, score_failed, score_record
from schemas.registry import resolve

_MODEL = resolve("invoice", "v1")
# A valid invoice (total == subtotal + tax; nullable fields explicitly null).
_BASE: dict[str, object] = {
    "invoice_number": "INV-1",
    "issue_date": "2026-01-15",
    "due_date": None,
    "currency": "GBP",
    "subtotal_minor": 10000,
    "tax_minor": 2000,
    "total_minor": 12000,
    "vendor_name": "Acme Ltd",
    "vendor_tax_id": None,
    "buyer_name": None,
    "line_items": None,
}


def _rec(**over: object) -> dict[str, object]:
    return {**_BASE, **over}


def test_identical_records_all_match():
    assert set(score_record(_MODEL, _rec(), _rec()).values()) == {FieldOutcome.match}


def test_mismatch_on_a_changed_value():
    outcomes = score_record(_MODEL, _rec(invoice_number="INV-2"), _rec())
    assert outcomes["invoice_number"] is FieldOutcome.mismatch
    assert outcomes["currency"] is FieldOutcome.match


def test_hallucinated_when_expected_is_null():
    # Model invented a value for a genuinely-absent (null) field.
    outcomes = score_record(_MODEL, _rec(buyer_name="Invented Buyer Co"), _rec())
    assert outcomes["buyer_name"] is FieldOutcome.hallucinated


def test_missed_when_predicted_is_null():
    outcomes = score_record(_MODEL, _rec(vendor_tax_id=None), _rec(vendor_tax_id="GB123456789"))
    assert outcomes["vendor_tax_id"] is FieldOutcome.missed


def test_aggregate_rolls_up_per_field_rates_cost_and_latency():
    scored = [
        score_record(_MODEL, _rec(), _rec()),  # all match
        score_record(_MODEL, _rec(invoice_number="X"), _rec()),  # invoice_number mismatch
        score_record(_MODEL, _rec(buyer_name="ghost"), _rec()),  # buyer_name hallucinated
        score_record(_MODEL, _rec(vendor_tax_id=None), _rec(vendor_tax_id="GB1")),  # missed
    ]
    report = aggregate(
        "invoice", "openai", scored, [0.01, 0.02, 0.03, 0.04], [10.0, 30.0, 20.0, 40.0]
    )
    assert report.n_fixtures == 4
    assert report.per_field["invoice_number"].matches == 3
    assert report.per_field["invoice_number"].mismatches == 1
    assert report.per_field["buyer_name"].hallucinated == 1
    assert report.per_field["vendor_tax_id"].missed == 1
    assert report.total_hallucinated == 1
    assert report.cost_usd_total == pytest.approx(0.10)
    assert report.latency_p50_ms == pytest.approx(20.0)  # nearest-rank p50 of 10/20/30/40
    assert report.latency_p95_ms == pytest.approx(40.0)
    assert 0.0 < report.overall_exact_match_rate < 1.0


def test_score_failed_marks_every_field_missed():
    # A failed extraction (no record) counts every expected field as missed.
    outcomes = score_failed(_MODEL, _rec())
    assert set(outcomes.values()) == {FieldOutcome.missed}
    assert set(outcomes) == set(_BASE)  # every field accounted for


def test_aggregate_carries_failure_count():
    report = aggregate("invoice", "openai", [score_failed(_MODEL, _rec())], [], [], n_failures=1)
    assert report.n_failures == 1
    assert report.overall_exact_match_rate == 0.0  # a failed extraction got nothing right


def test_empty_run_is_safe():
    report = aggregate("invoice", "openai", [], [], [])
    assert report.n_fixtures == 0
    assert report.n_failures == 0
    assert report.overall_exact_match_rate == 0.0
    assert report.hallucinated_field_rate == 0.0


def test_render_markdown_has_summary_and_per_field_table():
    report = aggregate("invoice", "openai", [score_record(_MODEL, _rec(), _rec())], [0.01], [12.0])
    md = render_markdown(report)
    assert "### invoice / openai" in md
    assert "overall exact-match: 100.0%" in md
    assert "latency p50/p95 (successful):" in md  # honest: success-only latency
    assert "| field | exact-match | mismatch | missed | hallucinated |" in md
    assert "`invoice_number`" in md
    assert "skipped (control-plane" not in md  # no skip line when nothing was skipped


def test_aggregate_carries_skipped_count():
    report = aggregate("invoice", "openai", [score_failed(_MODEL, _rec())], [], [], n_skipped=2)
    assert report.n_skipped == 2
    assert report.n_failures == 0


def test_render_markdown_surfaces_skipped_control_plane_fixtures():
    # A skipped fixture is excluded from the denominator but must be surfaced loudly so the
    # numbers are not misread as covering the whole corpus (issue #52).
    report = aggregate(
        "invoice", "openai", [score_record(_MODEL, _rec(), _rec())], [0.01], [12.0], n_skipped=3
    )
    md = render_markdown(report)
    assert "skipped (control-plane, not scored): 3" in md
    assert "scored subset only" in md
