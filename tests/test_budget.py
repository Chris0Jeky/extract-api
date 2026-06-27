"""Per-run budget guard (T18): cap enforcement, reconcile, env construction, no leak."""

from __future__ import annotations

import pytest

from api.budget import BudgetGuard, budget_from_env
from api.errors import ExtractError


def test_disabled_guard_never_raises():
    guard = BudgetGuard(0.0)
    assert not guard.enabled
    guard.add(1000.0)
    guard.check()  # no-op when disabled


def test_check_passes_below_cap_and_raises_at_cap():
    guard = BudgetGuard(1.0)
    assert guard.enabled
    guard.check()  # spent 0 < 1
    guard.add(0.5)
    guard.check()  # 0.5 < 1
    guard.add(0.5)  # committed == cap
    with pytest.raises(ExtractError) as exc:
        guard.check()
    assert exc.value.code.value == "budget_exceeded"


def test_add_reconciles_actual_spend():
    guard = BudgetGuard(10.0)
    guard.add(1.5)
    guard.add(2.5)
    assert guard.spent_usd == pytest.approx(4.0)


def test_check_does_not_leak_budget_figures():
    guard = BudgetGuard(0.001)
    guard.add(0.002)
    with pytest.raises(ExtractError) as exc:
        guard.check()
    assert "0.001" not in exc.value.detail
    assert "0.002" not in exc.value.detail


def test_budget_from_env_unset_is_disabled(monkeypatch):
    monkeypatch.delenv("EXTRACT_BUDGET_USD", raising=False)
    assert not budget_from_env().enabled


def test_budget_from_env_reads_the_cap(monkeypatch):
    monkeypatch.setenv("EXTRACT_BUDGET_USD", "2.50")
    guard = budget_from_env()
    assert guard.enabled
    guard.add(2.50)
    with pytest.raises(ExtractError) as exc:
        guard.check()
    assert exc.value.code.value == "budget_exceeded"


def test_budget_from_env_invalid_fails_loud(monkeypatch):
    monkeypatch.setenv("EXTRACT_BUDGET_USD", "notanumber")
    with pytest.raises(ValueError, match="EXTRACT_BUDGET_USD"):
        budget_from_env()
