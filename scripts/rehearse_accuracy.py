"""Rehearse the accuracy pipeline through the real API with per-fixture canned output.

This checks plumbing, not model quality. Only REVIEWED fixtures are loaded, and their
expected labels are supplied to FixtureClient one at a time. Every document still passes
through caller auth, the extraction endpoint, strict validation, and the accuracy scorer.
No server, provider credentials, paid calls, or persistent database are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from harness.run_accuracy import (
    FIXTURE_DIRS,
    Prediction,
    PredictionFailed,
    load_reviewed_fixtures,
    run_accuracy,
)
from harness.scoring import AccuracyReport, render_markdown

_CALLER_KEY = "offline-rehearsal-only-not-a-secret"
_ENV = {
    "LLM_PROVIDER_MODE": "fixture",
    "FIXTURE_CANNED_TEXT": "",
    "FIXTURE_LATENCY_MS": "0",
    "EXTRACT_API_KEY_SHA256S": hashlib.sha256(_CALLER_KEY.encode()).hexdigest(),
    "EXTRACT_BUDGET_USD": "0",
}


@contextmanager
def _fixture_environment() -> Iterator[None]:
    saved = {name: os.environ.get(name) for name in _ENV}
    os.environ.update(_ENV)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def rehearse(doc_type: str, *, fixtures_root: Path | None = None) -> AccuracyReport:
    """Run the REVIEWED corpus through an in-process fixture-mode API at zero cost.

    The temporary environment is process-wide, like scripts/smoke.py. Run this as a
    standalone development command, never inside a concurrent serving process.
    """
    fixtures = load_reviewed_fixtures(doc_type, root=fixtures_root)
    if not fixtures:
        raise ValueError(f"no REVIEWED {doc_type} fixtures; DRAFT labels are never scored")

    with _fixture_environment(), tempfile.TemporaryDirectory() as directory:
        # Import after pinning the fixture environment: api.main creates a default app at
        # import time, and ambient live auth/budget config must not control this rehearsal.
        from fastapi.testclient import TestClient

        from api.budget import BudgetGuard
        from api.idempotency import SqliteIdempotencyStore
        from api.main import create_app
        from api.models import ExtractResponse

        store = SqliteIdempotencyStore(str(Path(directory) / "rehearsal.sqlite"))
        app = create_app(idempotency_store=store, budget=BudgetGuard(0.0))
        with TestClient(app, headers={"Authorization": f"Bearer {_CALLER_KEY}"}) as client:

            def predict(fixture: dict[str, object]) -> Prediction:
                os.environ["FIXTURE_CANNED_TEXT"] = json.dumps(fixture["expected"])
                response = client.post(
                    "/v1/extract",
                    json={
                        "doc_type": fixture["doc_type"],
                        "schema_version": fixture["schema_version"],
                        "content": fixture["content"],
                        "provider": "default",
                    },
                )
                if response.status_code != 200:
                    raise PredictionFailed(
                        f"offline endpoint returned HTTP {response.status_code}", cost_usd=0.0
                    )
                body = ExtractResponse.model_validate_json(response.content)
                if body.meta.provider != "fixture" or body.meta.cost_usd != 0.0:
                    raise RuntimeError("offline rehearsal must use the zero-cost fixture provider")
                return Prediction(
                    record=body.data,
                    cost_usd=body.meta.cost_usd,
                    latency_ms=body.meta.latency_ms,
                    provider=body.meta.provider,
                )

            return run_accuracy(doc_type, "fixture", predict, fixtures=fixtures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc-type", choices=sorted(FIXTURE_DIRS), default="invoice")
    parser.add_argument("--fixtures-root", type=Path)
    args = parser.parse_args(argv)
    try:
        report = rehearse(args.doc_type, fixtures_root=args.fixtures_root)
    except (ValueError, OSError) as exc:
        print(f"rehearsal failed: {exc}", file=sys.stderr)
        return 1
    print("# OFFLINE REHEARSAL")
    print("\nExpected labels are echoed through FixtureClient; this is not provider accuracy.")
    print("No paid calls. Latency measures local fixture plumbing, not a real model.\n")
    print(render_markdown(report))
    return int(
        report.n_failures > 0 or report.n_skipped > 0 or report.overall_exact_match_rate != 1.0
    )


if __name__ == "__main__":
    sys.exit(main())
