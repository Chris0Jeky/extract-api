"""Deterministic accuracy harness (NO LLM judges anywhere).

Runs both providers on the identical schema and fixtures and reports, per field:
exact-match rate (after canonical normalization), null-handling correctness, and
the hallucinated-field rate (model invented a value for a genuinely-absent field).
Output is a markdown table committed to evals/reports/ plus cost and p50/p95
latency per doc type per provider. Real scoring lands in T16/T17.
"""

from __future__ import annotations

import sys


def run_accuracy(doc_type: str, provider: str) -> int:
    """Score one (doc_type, provider) pair against the REVIEWED fixtures."""
    raise NotImplementedError("deterministic accuracy scoring lands in T16/T17")


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("accuracy harness CLI lands in T16/T17")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
