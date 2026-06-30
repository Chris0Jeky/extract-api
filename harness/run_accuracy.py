"""Deterministic accuracy harness (NO LLM judges anywhere).

Scores a provider over the REVIEWED fixtures for a doc type: per-field exact-match (after
canonical normalization) and the hallucinated-field rate, plus cost and success-only
p50/p95 latency (a null-handling-correctness rate over expected-null fields is pending
issue #46). Scoring itself is pure (harness/scoring.py) and unit-tested offline;
producing real numbers needs `--live`, which POSTs each fixture to the serving endpoint.
A control-plane rejection (budget_exceeded 402 / idempotency_conflict 409) never reached the
model, so it is skipped, not scored as a missed extraction (issue #52). DRAFT-labelled
fixtures are never scored (ADR 0003). The markdown report lands in evals/reports/ via T17.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from harness.scoring import AccuracyReport, aggregate, render_markdown, score_failed, score_record
from schemas.registry import resolve

if TYPE_CHECKING:
    import httpx  # type-only: the runtime import stays local to live_predictor (--live only)


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


class ControlPlaneRejection(Exception):
    """The endpoint rejected a fixture BEFORE any model call, for a reason unrelated to the
    document (a budget_exceeded 402 or idempotency_conflict 409).

    This is NOT an accuracy signal: the model never saw the document, so the fixture must be
    excluded from the per-field denominator rather than scored as all-missed. Otherwise a
    mid-run budget cap would silently deflate the headline numbers the product rests on
    (issue #52). The run records it as skipped (AccuracyReport.n_skipped) and continues.
    """


# A predictor maps a fixture to a Prediction, or raises PredictionFailed (a quality failure,
# scored) / ControlPlaneRejection (skipped, not scored). Injecting it keeps run_accuracy
# testable offline; --live supplies the real endpoint-backed implementation.
Predictor = Callable[[dict[str, object]], Prediction]

_FIXTURE_DIRS = {"invoice": "invoices", "uk_job_posting": "job_postings"}
_PROVIDERS = ("openai", "anthropic", "default")
_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
# Taxonomy codes that mean "rejected by a control-plane guard before any model call"; these
# are not extraction-quality signals, so the harness skips them rather than scoring them (#52).
_CONTROL_PLANE_CODES = frozenset({"budget_exceeded", "idempotency_conflict"})


def _response_error_code(resp: httpx.Response) -> str | None:
    """The taxonomy `error` code from a non-2xx body, or None if it is not a coded error.

    Defensive: a body that is not JSON, not an object, or carries no string `error` (e.g. a
    gateway HTML page) yields None, so the caller treats it as a quality failure rather than
    skipping a fixture it could not positively classify as control-plane.
    """
    try:
        body = resp.json()
    except (ValueError, TypeError):  # not JSON / undecodable body
        return None
    if isinstance(body, dict):
        code = body.get("error")
        if isinstance(code, str):
            return code
    return None


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
    skipped = 0
    resolved_provider = provider  # fallback if every fixture fails (no server label to read)
    for fx in items:
        expected = fx["expected"]
        assert isinstance(expected, dict)
        # Resolve each fixture against ITS OWN schema_version, so a mixed-version corpus is
        # scored correctly rather than all canonicalized against one run-level model.
        model_cls = resolve(doc_type, str(fx["schema_version"]))
        try:
            prediction = predict(fx)
        except ControlPlaneRejection:
            # The fixture never reached the model (a budget/idempotency guard rejected it). It
            # is not an accuracy signal, so keep it OUT of the per-field denominator (issue #52).
            skipped += 1
            continue
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
    return aggregate(
        doc_type,
        resolved_provider,
        scored,
        costs,
        latencies,
        n_failures=failures,
        n_skipped=skipped,
    )


def live_predictor(base_url: str, provider: str) -> Predictor:
    """A predictor that POSTs each fixture to a serving /v1/extract and reads the result.

    An extraction-quality non-2xx (a terminal validation_failed 422, provider_error 502, ...)
    or a transport error becomes PredictionFailed, so the run records that fixture as a failed
    extraction and continues instead of crashing on the documents the harness exists to
    measure. A control-plane non-2xx (budget_exceeded 402 / idempotency_conflict 409) becomes
    ControlPlaneRejection, so the run SKIPS it (the model never ran) rather than scoring it as
    all-missed and deflating the numbers (issue #52).
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
            fixture_id = fx.get("fixture_id", "?")
            if _response_error_code(exc.response) in _CONTROL_PLANE_CODES:
                # Rejected before any model call; skip it instead of scoring all-missed (#52).
                raise ControlPlaneRejection(
                    f"{fixture_id}: HTTP {exc.response.status_code} (control-plane)"
                ) from exc
            raise PredictionFailed(f"{fixture_id}: HTTP {exc.response.status_code}") from exc
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
