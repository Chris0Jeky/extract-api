"""Offline behavior evidence must not be confused with a vulnerability scan gate."""

import hashlib
import json
import socket
from pathlib import Path

import pytest
import yaml
from scripts import probe_runtime_security as probe


def test_runtime_probes_use_no_network_and_identify_packaged_sources(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("runtime probes must never open a socket")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    report = probe.build_report(image_ref="synthetic@sha256:test", image_id="sha256:local")
    assert report["image"] == {
        "reference": "synthetic@sha256:test",
        "id": "sha256:local",
    }
    assert {check["cve"] for check in report["checks"]} == {
        "CVE-2025-15367",
        "CVE-2026-103995",
    }
    for check in report["checks"]:
        assert check["status"] in {
            "affected_behavior_observed",
            "affected_behavior_not_observed",
        }
        source = check["source"]
        assert source["sha256"] == hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest()
        assert any(case["kind"] == "control" for case in check["cases"])
        assert all(case["outcome"] != "error" for case in check["cases"])


@pytest.mark.parametrize(
    "cases, expected",
    [
        (
            [
                probe.Case("valid", "control", "expected", "ok"),
                probe.Case("invalid", "regression", "expected", "rejected"),
            ],
            "affected_behavior_not_observed",
        ),
        (
            [
                probe.Case("valid", "control", "expected", "ok"),
                probe.Case("invalid", "regression", "unexpected", "accepted"),
            ],
            "affected_behavior_observed",
        ),
        ([probe.Case("valid", "control", "unexpected", "rejected")], "inconclusive"),
        ([probe.Case("invalid", "regression", "error", "RuntimeError")], "inconclusive"),
        ([], "inconclusive"),
    ],
)
def test_probe_status_distinguishes_finding_from_broken_probe(cases, expected):
    assert probe.check_status(cases) == expected


def test_poplib_rejection_must_happen_before_sending(monkeypatch):
    import poplib

    def reject_after_send(self, line):
        self._putline(line.encode(self.encoding))
        raise ValueError("too late")

    monkeypatch.setattr(poplib.POP3, "_putcmd", reject_after_send)
    cases = probe.probe_poplib()
    regressions = [case for case in cases if case.kind == "regression"]
    assert regressions
    assert all(case.outcome == "unexpected" for case in regressions)


def test_http_probe_checks_underscored_chunks_with_enough_body_bytes():
    cases = probe.probe_http_client()
    underscored = next(case for case in cases if case.name == "chunk_size_1_f")
    # A vulnerable parser must be able to read all 31 bytes. A short body would
    # make both vulnerable and patched parsers raise IncompleteRead.
    assert underscored.observation in {"accepted 31 bytes", "rejected"}


def test_cli_emits_json_and_finding_is_report_only(capsys, monkeypatch):
    monkeypatch.setattr(
        probe,
        "build_report",
        lambda **kwargs: {"checks": [{"status": "affected_behavior_observed"}]},
    )
    assert probe.main([]) == 0
    assert json.loads(capsys.readouterr().out)["checks"][0]["status"] == (
        "affected_behavior_observed"
    )


def test_cli_fails_when_a_probe_is_inconclusive(capsys, monkeypatch):
    monkeypatch.setattr(
        probe, "build_report", lambda **kwargs: {"checks": [{"status": "inconclusive"}]}
    )
    assert probe.main([]) == 2
    assert json.loads(capsys.readouterr().out)["checks"][0]["status"] == "inconclusive"


def test_image_probes_the_smoked_reference_offline_without_changing_scan_policy():
    path = Path(__file__).resolve().parent.parent / ".github/workflows/image.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    for name, smoke_name in (
        ("local-image", "Smoke the locally built image"),
        ("published-image", "Pull and smoke the pushed digest"),
    ):
        steps = workflow["jobs"][name]["steps"]
        smoke = next(step for step in steps if step.get("name") == smoke_name)
        probe_step = next(
            step for step in steps if step.get("name") == "Probe packaged CPython security behavior"
        )
        assert probe_step["env"]["IMAGE_REF"] == smoke["env"]["IMAGE_REF"]
        assert steps.index(probe_step) > steps.index(smoke)
        assert "--network none" in probe_step["run"]
        assert "--read-only" in probe_step["run"]
        assert "--user 10001:10001" in probe_step["run"]
        assert "readonly" in probe_step["run"]
        assert '"$IMAGE_REF" /runtime-probe.py' in probe_step["run"]
        assert "runtime-security.json" in probe_step["run"]
        scan = next(step for step in steps if "anchore/scan-action@" in step.get("uses", ""))
        assert scan["with"]["severity-cutoff"] == "critical"
        assert scan["with"]["only-fixed"] == "true"
        assert scan["with"]["fail-build"] == "true"
        upload = next(
            step for step in steps if step.get("name") == "Upload runtime behavior evidence"
        )
        assert "always()" in upload["if"]
        assert upload["with"]["path"] == "runtime-security.json"
