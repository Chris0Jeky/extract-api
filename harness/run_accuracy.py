"""Deterministic accuracy harness (NO LLM judges anywhere).

Scores a provider over the REVIEWED fixtures for a doc type: per-field exact-match (after
canonical normalization), null-handling, and the hallucinated-field rate, plus cost and
p50/p95 latency. Scoring itself is pure (harness/scoring.py) and unit-tested offline;
producing real numbers needs `--live`, which POSTs each fixture to the serving endpoint.
DRAFT-labelled fixtures are never scored (ADR 0003). The markdown report lands in
evals/reports/ via T17.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from harness.scoring import AccuracyReport, aggregate, render_markdown, score_record
from schemas.registry import resolve

# A predictor maps a fixture to (predicted_record, cost_usd, latency_ms). Injecting it keeps
# run_accuracy testable offline; --live supplies the real endpoint-backed implementation.
Predictor = Callable[[dict[str, object]], tuple[dict[str, object], float, float]]

_FIXTURE_DIRS = {"invoice": "invoices", "uk_job_posting": "job_postings"}
_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def load_reviewed_fixtures(doc_type: str, root: Path | None = None) -> list[dict[str, object]]:
    """Load only the REVIEWED fixtures for a doc type; DRAFT labels are never scored."""
    base = (root or _FIXTURES_ROOT) / _FIXTURE_DIRS[doc_type]
    fixtures: list[dict[str, object]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("label_status") == "REVIEWED" and data.get("doc_type") == doc_type:
            fixtures.append(data)
    return fixtures


def run_accuracy(
    doc_type: str,
    provider: str,
    predict: Predictor,
    *,
    fixtures: list[dict[str, object]] | None = None,
    schema_version: str = "v1",
) -> AccuracyReport:
    """Score `provider` over `doc_type`'s REVIEWED fixtures (or an injected fixture list)."""
    items = load_reviewed_fixtures(doc_type) if fixtures is None else fixtures
    model_cls = resolve(doc_type, schema_version)
    scored = []
    costs: list[float] = []
    latencies: list[float] = []
    for fx in items:
        predicted, cost, latency = predict(fx)
        expected = fx["expected"]
        assert isinstance(expected, dict)
        scored.append(score_record(model_cls, predicted, expected))
        costs.append(cost)
        latencies.append(latency)
    return aggregate(doc_type, provider, scored, costs, latencies)


def live_predictor(base_url: str, provider: str) -> Predictor:
    """A predictor that POSTs each fixture to a serving /v1/extract and reads the result."""
    import httpx  # local import: only --live needs an HTTP client

    def predict(fx: dict[str, object]) -> tuple[dict[str, object], float, float]:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/v1/extract",
            json={
                "doc_type": fx["doc_type"],
                "schema_version": fx["schema_version"],
                "content": fx["content"],
                "provider": provider,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        body = resp.json()
        meta = body["meta"]
        return body["data"], float(meta["cost_usd"]), float(meta["latency_ms"])

    return predict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic accuracy harness (no LLM judge).")
    parser.add_argument("--doc-type", required=True, choices=sorted(_FIXTURE_DIRS))
    parser.add_argument("--provider", default="openai")
    parser.add_argument("--live", action="store_true", help="POST fixtures to a live endpoint")
    parser.add_argument("--base-url", default="http://localhost:8200")
    parser.add_argument("--out", default=None, help="write the markdown report to this path")
    args = parser.parse_args(argv)

    fixtures = load_reviewed_fixtures(args.doc_type)
    if not fixtures:
        print(
            f"no REVIEWED {args.doc_type} fixtures to score (DRAFT labels are excluded).",
            file=sys.stderr,
        )
        return 1
    if not args.live:
        # Producing numbers needs real provider calls; the scoring is unit-tested offline.
        print(
            f"{len(fixtures)} REVIEWED {args.doc_type} fixtures found. Re-run with --live "
            "(against a serving endpoint) to score them and emit the table.",
            file=sys.stderr,
        )
        return 2

    report = run_accuracy(
        args.doc_type, args.provider, live_predictor(args.base_url, args.provider)
    )
    markdown = render_markdown(report)
    if args.out:
        Path(args.out).write_text(markdown + "\n", encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
