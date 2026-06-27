"""Deterministic accuracy harness (NO LLM judges anywhere).

Scores a provider over the REVIEWED fixtures for a doc type: per-field exact-match (after
canonical normalization) and the hallucinated-field rate, plus cost and success-only
p50/p95 latency (a null-handling-correctness rate over expected-null fields is pending
issue #46). Scoring itself is pure (harness/scoring.py) and unit-tested offline;
producing real numbers needs `--live`, which POSTs each fixture to the serving endpoint.
DRAFT-labelled fixtures are never scored (ADR 0003). The markdown report lands in
evals/reports/ via T17.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from harness.scoring import AccuracyReport, aggregate, render_markdown, score_failed, score_record
from schemas.registry import resolve


@dataclass(frozen=True)
class Prediction:
    """One fixture's extracted record plus the cost/latency and the provider the server used."""

    record: dict[str, object]
    cost_usd: float
    latency_ms: float
    provider: str


class PredictionFailed(Exception):
    """The endpoint did not return a usable record for a fixture (a non-2xx or transport error).

    A failed extraction is itself the accuracy signal, so the harness records it (the fixture's
    fields all count as missed) and continues, rather than aborting the whole run.
    """


# A predictor maps a fixture to a Prediction or raises PredictionFailed. Injecting it keeps
# run_accuracy testable offline; --live supplies the real endpoint-backed implementation.
Predictor = Callable[[dict[str, object]], Prediction]

_FIXTURE_DIRS = {"invoice": "invoices", "uk_job_posting": "job_postings"}
_PROVIDERS = ("openai", "anthropic", "default")
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
) -> AccuracyReport:
    """Score `provider` over `doc_type`'s REVIEWED fixtures (or an injected fixture list)."""
    items = load_reviewed_fixtures(doc_type) if fixtures is None else fixtures
    scored = []
    costs: list[float] = []
    latencies: list[float] = []
    failures = 0
    resolved_provider = provider  # fallback if every fixture fails (no server label to read)
    for fx in items:
        expected = fx["expected"]
        assert isinstance(expected, dict)
        # Resolve each fixture against ITS OWN schema_version, so a mixed-version corpus is
        # scored correctly rather than all canonicalized against one run-level model.
        model_cls = resolve(doc_type, str(fx["schema_version"]))
        try:
            prediction = predict(fx)
        except PredictionFailed:
            # A failed extraction is the accuracy signal: count every field as missed and
            # keep going, so one hard (or transiently-failing) fixture cannot erase the run.
            scored.append(score_failed(model_cls, expected))
            failures += 1
            continue
        resolved_provider = prediction.provider  # the provider the server actually used
        scored.append(score_record(model_cls, prediction.record, expected))
        costs.append(prediction.cost_usd)
        latencies.append(prediction.latency_ms)
    return aggregate(doc_type, resolved_provider, scored, costs, latencies, n_failures=failures)


def live_predictor(base_url: str, provider: str) -> Predictor:
    """A predictor that POSTs each fixture to a serving /v1/extract and reads the result.

    A non-2xx (e.g. a terminal validation_failed 422, provider_error 502) or a transport
    error becomes PredictionFailed, so the run records that fixture as a failed extraction
    and continues instead of crashing on the documents the harness exists to measure.
    """
    import httpx  # local import: only --live needs an HTTP client

    def predict(fx: dict[str, object]) -> Prediction:
        try:
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
        except httpx.HTTPStatusError as exc:
            raise PredictionFailed(
                f"{fx.get('fixture_id', '?')}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise PredictionFailed(f"{fx.get('fixture_id', '?')}: {type(exc).__name__}") from exc
        body = resp.json()
        meta = body["meta"]
        return Prediction(
            record=body["data"],
            cost_usd=float(meta["cost_usd"]),
            latency_ms=float(meta["latency_ms"]),
            provider=str(meta["provider"]),  # the provider the server resolved (not the request)
        )

    return predict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic accuracy harness (no LLM judge).")
    parser.add_argument("--doc-type", required=True, choices=sorted(_FIXTURE_DIRS))
    parser.add_argument("--provider", default="openai", choices=_PROVIDERS)
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
