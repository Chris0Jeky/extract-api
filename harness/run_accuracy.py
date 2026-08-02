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
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from harness.scoring import AccuracyReport, aggregate, render_markdown, score_failed, score_record
from schemas.registry import UnknownSchema, resolve

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


class MisplacedFixture(Exception):
    """A REVIEWED fixture sits under the wrong doc-type directory (its doc_type disagrees with
    the folder it was loaded from).

    Silently excluding it (the old behavior) would under-count the corpus and could mis-score
    a real document; the labeled corpus is ground truth, so a misfiled REVIEWED fixture is a
    loud setup error, not a row to drop (issue #57). DRAFT fixtures are exempt: they are never
    scored regardless of placement.
    """


# A predictor maps a fixture to a Prediction, or raises PredictionFailed (a quality failure,
# scored) / ControlPlaneRejection (skipped, not scored). Injecting it keeps run_accuracy
# testable offline; --live supplies the real endpoint-backed implementation.
Predictor = Callable[[dict[str, object]], Prediction]

# The canonical doc_type -> fixtures subdirectory map (single source of truth for the corpus
# layout). Public so scripts/validate_fixtures.py can enforce the same placement invariant
# corpus-wide (issue #63) instead of duplicating a map that could drift from the harness.
FIXTURE_DIRS = {"invoice": "invoices", "uk_job_posting": "job_postings"}
_PROVIDERS = ("openai", "anthropic", "default")
_FIXTURES_ROOT = Path(__file__).resolve().parent.parent / "fixtures"
# Taxonomy codes that mean "rejected by a control-plane guard before any model call"; these
# are not extraction-quality signals, so the harness skips them rather than scoring them (#52).
_CONTROL_PLANE_CODES = frozenset({"budget_exceeded", "idempotency_conflict"})


def _preflight_fixtures(
    doc_type: str, fixtures: list[dict[str, object]]
) -> list[tuple[dict[str, object], type[BaseModel], dict[str, object]]]:
    """Resolve and validate every fixture before any predictor call.

    Accuracy runs may make paid provider calls, so fixture setup errors must be found for the
    complete selected corpus up front.  Schema versions are intentionally type-checked instead
    of coerced: a non-string value is malformed fixture data, not an alternate spelling of a
    registered version.
    """
    prepared: list[tuple[dict[str, object], type[BaseModel], dict[str, object]]] = []
    for index, fx in enumerate(fixtures, start=1):
        fixture_id = fx.get("fixture_id")
        fixture_ref = (
            fixture_id if isinstance(fixture_id, str) and fixture_id else f"fixture #{index}"
        )
        if "doc_type" not in fx:
            raise ValueError(f"{fixture_ref}: missing doc_type")
        fixture_doc_type = fx["doc_type"]
        if not isinstance(fixture_doc_type, str) or not fixture_doc_type.strip():
            raise ValueError(f"{fixture_ref}: doc_type must be a non-empty string")
        if fixture_doc_type != doc_type:
            raise ValueError(
                f"{fixture_ref}: doc_type {fixture_doc_type!r} does not match selected "
                f"doc_type {doc_type!r}"
            )
        if "schema_version" not in fx:
            raise ValueError(f"{fixture_ref}: missing schema_version")
        schema_version = fx["schema_version"]
        if not isinstance(schema_version, str) or not schema_version:
            raise ValueError(f"{fixture_ref}: schema_version must be a non-empty string")
        try:
            model_cls = resolve(doc_type, schema_version)
        except UnknownSchema as exc:
            raise ValueError(
                f"{fixture_ref}: invalid schema_version {schema_version!r}: {exc}"
            ) from exc

        if "content" not in fx:
            raise ValueError(f"{fixture_ref}: missing content")
        content = fx["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"{fixture_ref}: content must be a non-empty string")
        if "expected" not in fx:
            raise ValueError(f"{fixture_ref}: missing expected label")
        expected = fx["expected"]
        if not isinstance(expected, dict):
            raise ValueError(f"{fixture_ref}: expected must be a JSON object")
        try:
            model_cls.model_validate_json(json.dumps(expected))
        except (ValidationError, TypeError, ValueError) as exc:
            detail = (
                f"{exc.error_count()} validation error(s)"
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            raise ValueError(
                f"{fixture_ref}: expected label fails {doc_type}.{schema_version}: {detail}"
            ) from exc
        prepared.append((fx, model_cls, expected))
    return prepared


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
    """Load only the REVIEWED fixtures for a doc type; DRAFT labels are never scored.

    A REVIEWED fixture whose own doc_type disagrees with the directory it sits in is a misfiled
    ground-truth file: fail loud (MisplacedFixture) rather than silently dropping or mis-scoring
    it (issue #57). DRAFT fixtures are skipped regardless of placement.
    """
    base = (root or _FIXTURES_ROOT) / FIXTURE_DIRS[doc_type]
    fixtures: list[dict[str, object]] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            # A fixture file that is a JSON array/primitive would make data.get() raise a
            # cryptic AttributeError; fail loud with the offending file instead.
            raise ValueError(
                f"{path.name}: fixture must be a JSON object, not {type(data).__name__}"
            )
        if data.get("label_status") != "REVIEWED":
            continue  # DRAFT / unlabelled is never scored, wherever it sits
        if data.get("doc_type") != doc_type:
            raise MisplacedFixture(
                f"{path.name}: REVIEWED fixture has doc_type={data.get('doc_type')!r} but sits "
                f"under the {doc_type!r} directory ({FIXTURE_DIRS[doc_type]}/); "
                "move it or fix its label"
            )
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
    prepared = _preflight_fixtures(doc_type, items)
    scored = []
    costs: list[float] = []
    latencies: list[float] = []
    failures = 0
    skipped = 0
    resolved_provider = provider  # fallback if every fixture fails (no server label to read)
    for fx, model_cls, expected in prepared:
        try:
            prediction = predict(fx)
        except ControlPlaneRejection as exc:
            # The fixture never reached the model (a budget/idempotency guard rejected it). It
            # is not an accuracy signal, so keep it OUT of the per-field denominator (issue #52).
            fixture_id = fx.get("fixture_id", "?")
            print(
                f"accuracy: fixture {fixture_id}: skipped (control-plane): {exc}",
                file=sys.stderr,
            )
            skipped += 1
            continue
        except PredictionFailed as exc:
            # A failed extraction is the accuracy signal: count every field as missed and
            # keep going, so one hard (or transiently-failing) fixture cannot erase the run.
            fixture_id = fx.get("fixture_id", "?")
            print(f"accuracy: fixture {fixture_id}: prediction failed: {exc}", file=sys.stderr)
            scored.append(score_failed(model_cls, expected))
            failures += 1
            continue
        resolved_provider = prediction.provider  # the provider the server actually used
        try:
            outcomes = score_record(model_cls, prediction.record, expected)
        except ValidationError:
            # A schema-invalid predicted record (an older/broken endpoint returning a 200 with
            # object-but-invalid `data`, e.g. {}) is a failed extraction, not a crash. `expected`
            # is validated upstream (fixtures-validate + the REVIEWED gate), so a ValidationError
            # here is the prediction's, not the fixture's (issue #57).
            scored.append(score_failed(model_cls, expected))
            failures += 1
            continue
        scored.append(outcomes)
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


def live_predictor(base_url: str, provider: str, *, timeout: float = 120.0) -> Predictor:
    """A predictor that POSTs each fixture to a serving /v1/extract and reads the result.

    An extraction-quality non-2xx (a terminal validation_failed 422, provider_error 502, ...)
    or a transport error becomes PredictionFailed, so the run records that fixture as a failed
    extraction and continues instead of crashing on the documents the harness exists to
    measure. A control-plane non-2xx (budget_exceeded 402 / idempotency_conflict 409) becomes
    ControlPlaneRejection, so the run SKIPS it (the model never ran) rather than scoring it as
    all-missed and deflating the numbers (issue #52). A 2xx body that is not a valid
    ExtractResponse (a gateway login/HTML page, an older server shape) is likewise a
    PredictionFailed, not an uncaught crash that aborts the whole run (issue #57). `timeout`
    is the per-request HTTP timeout in seconds, configurable so a legitimately slow extraction
    is not spuriously failed.
    """
    import httpx  # local import: only --live needs an HTTP client

    def predict(fx: dict[str, object]) -> Prediction:
        fixture_id = fx.get("fixture_id", "?")
        try:
            resp = httpx.post(
                f"{base_url.rstrip('/')}/v1/extract",
                json={
                    "doc_type": fx["doc_type"],
                    "schema_version": fx["schema_version"],
                    "content": fx["content"],
                    "provider": provider,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if _response_error_code(exc.response) in _CONTROL_PLANE_CODES:
                # Rejected before any model call; skip it instead of scoring all-missed (#52).
                raise ControlPlaneRejection(
                    f"{fixture_id}: HTTP {exc.response.status_code} (control-plane)"
                ) from exc
            raise PredictionFailed(f"{fixture_id}: HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise PredictionFailed(f"{fixture_id}: {type(exc).__name__}") from exc
        # A 2xx is not a guarantee of the right SHAPE (gateway login page, older server, proxy
        # error rendered 200). Parse defensively and turn any shape error into a fixture failure
        # so one odd response cannot crash the whole run (issue #57).
        try:
            body = resp.json()
            meta = body["meta"]
            record = body["data"]
            cost_usd = float(meta["cost_usd"])
            latency_ms = float(meta["latency_ms"])
            server_provider = str(meta["provider"])  # the provider the server resolved
        except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
            # ArithmeticError covers OverflowError from float() of an out-of-range JSON integer.
            raise PredictionFailed(
                f"{fixture_id}: malformed 2xx response ({type(exc).__name__})"
            ) from exc
        if not isinstance(record, dict):
            raise PredictionFailed(f"{fixture_id}: 2xx 'data' is not a JSON object")
        if not (math.isfinite(cost_usd) and math.isfinite(latency_ms)):
            # float("nan")/float("inf") parse without error, so a 2xx metric of "nan"/"inf"
            # would silently poison the cost total and latency percentiles; reject it (issue #57).
            raise PredictionFailed(f"{fixture_id}: 2xx cost/latency is not a finite number")
        return Prediction(
            record=record, cost_usd=cost_usd, latency_ms=latency_ms, provider=server_provider
        )

    return predict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic accuracy harness (no LLM judge).")
    parser.add_argument("--doc-type", required=True, choices=sorted(FIXTURE_DIRS))
    parser.add_argument("--provider", default="openai", choices=_PROVIDERS)
    parser.add_argument("--live", action="store_true", help="POST fixtures to a live endpoint")
    parser.add_argument("--base-url", default="http://localhost:8200")
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="--live per-request HTTP timeout in seconds (default 120)",
    )
    parser.add_argument("--out", default=None, help="write the markdown report to this path")
    args = parser.parse_args(argv)
    # `<= 0` alone would let NaN through (every NaN comparison is False) and inf would mean
    # "no effective timeout"; require a positive, finite value so a bad flag fails loud.
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive, finite number of seconds")

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

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report = run_accuracy(
        args.doc_type,
        args.provider,
        live_predictor(args.base_url, args.provider, timeout=args.timeout),
    )
    markdown = render_markdown(report)
    stdout_error: Exception | None = None
    try:
        print(markdown)
    except Exception as exc:
        # A closed or redirected stdout must not prevent the requested report file from
        # being written.  Re-raise after the file sink is attempted so the CLI still fails
        # loudly instead of hiding the output error.
        stdout_error = exc
    if args.out:
        try:
            Path(args.out).write_text(markdown + "\n", encoding="utf-8")
        except Exception as exc:
            if stdout_error is not None:
                raise exc from stdout_error
            raise
    if stdout_error is not None:
        raise stdout_error
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
