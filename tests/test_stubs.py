"""Remaining M0 stubs fail loudly (NotImplementedError) until their task lands.

The idempotency store is implemented (T11; see test_idempotency.py); the accuracy
harness is still a stub until T16.
"""

import pytest

from harness.run_accuracy import run_accuracy


def test_accuracy_stub():
    with pytest.raises(NotImplementedError):
        run_accuracy("invoice", "openai")
