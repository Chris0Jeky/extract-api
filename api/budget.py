"""Per-run USD budget guard.

Caps cumulative LLM spend for the running process against EXTRACT_BUDGET_USD. Once the
committed total reaches the cap, further extractions fail loud with `budget_exceeded` (402)
*before* spending more. Opt-in: an unset or non-positive cap disables the guard.

Reserve-reconcile NOTE (a deliberate v1 simplification, flagged for review): this guard
checks the COMMITTED total before a call and adds the actual cost after (the "reconcile"
step); it does not pre-reserve an estimated cost. So under high concurrency a small
overshoot past the cap is possible (bounded by the number of in-flight calls). A stricter
reserve-with-estimate (the full Hero-1 pattern) is a future refinement if needed.
"""

from __future__ import annotations

import logging
import os
import threading

from api.errors import ErrorCode, ExtractError

logger = logging.getLogger("extract.api")


class BudgetGuard:
    """Thread-safe cumulative-spend cap for one process run."""

    def __init__(self, cap_usd: float) -> None:
        self._cap = cap_usd
        self._spent = 0.0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._cap > 0.0

    def check(self) -> None:
        """Raise budget_exceeded if the committed spend has reached the cap (no-op if disabled)."""
        if not self.enabled:
            return
        with self._lock:
            spent = self._spent
        if spent >= self._cap:
            # Log the exact figures server-side; keep the client body free of budget config.
            logger.warning("budget exceeded: spent $%.4f of $%.4f cap", spent, self._cap)
            raise ExtractError(
                ErrorCode.budget_exceeded, detail="the per-run budget has been reached"
            )

    def add(self, cost_usd: float) -> None:
        """Reconcile the actual cost of a completed call into the committed total."""
        with self._lock:
            self._spent += cost_usd

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent


def budget_from_env() -> BudgetGuard:
    """Build a BudgetGuard from EXTRACT_BUDGET_USD (unset/non-positive -> disabled)."""
    raw = os.environ.get("EXTRACT_BUDGET_USD", "")
    if not raw:
        return BudgetGuard(0.0)
    try:
        cap = float(raw)
    except ValueError as exc:
        raise ValueError(f"env EXTRACT_BUDGET_USD={raw!r} is not a valid float") from exc
    return BudgetGuard(cap)
