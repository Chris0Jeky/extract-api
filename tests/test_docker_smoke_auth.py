"""The Docker smoke authenticates like a real caller: its container gets only the key's hash."""

import hashlib

from scripts import docker_persistence_smoke as smoke


def test_post_sends_the_smoke_caller_key(monkeypatch):
    seen = {}

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        return _Response()

    monkeypatch.setattr(smoke, "urlopen", fake_urlopen)
    assert smoke._post(1, {"k": "v"}, "idem-key") == (200, {})
    assert seen["authorization"] == f"Bearer {smoke._CALLER_KEY}"


def test_container_receives_the_hash_and_never_the_key(monkeypatch):
    calls = []
    monkeypatch.setattr(smoke, "_run", lambda *args, **kwargs: calls.append(args))
    smoke._start_container(image="img", container="c", volume="v", port=1, canned_text="{}")
    (args,) = calls
    digest = hashlib.sha256(smoke._CALLER_KEY.encode()).hexdigest()
    assert f"EXTRACT_API_KEY_SHA256S={digest}" in args
    assert not any(smoke._CALLER_KEY in arg for arg in args)
