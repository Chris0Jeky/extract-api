"""Test-only caller key. Not a secret: it exists in no deployment, only in this repository."""

import hashlib

TEST_KEY = "test-caller-key-not-a-secret"
TEST_KEY_SHA256 = hashlib.sha256(TEST_KEY.encode()).hexdigest()
AUTH = {"Authorization": f"Bearer {TEST_KEY}"}
