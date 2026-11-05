"""Report sink failures must not waste requests or destroy an earlier report."""

import os
import stat
import tempfile
from pathlib import Path

import httpx
import pytest

import harness.run_accuracy as runner
from test_run_accuracy import _ok_body, _resp, _write


@pytest.fixture
def live_run(tmp_path, monkeypatch):
    fixtures = tmp_path / "fixtures"
    _write(fixtures / "invoices", "one.json", "REVIEWED")
    monkeypatch.setattr(runner, "_FIXTURES_ROOT", fixtures)
    monkeypatch.setenv("EXTRACT_API_KEY", "synthetic-test-key")
    calls = []

    def post(*args, **kwargs):
        calls.append(kwargs)
        return _resp(200, _ok_body())

    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_directory_output_is_rejected_before_any_live_request(tmp_path, live_run):
    target = tmp_path / "report.md"
    target.mkdir()
    with pytest.raises(IsADirectoryError):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert live_run == []
    assert target.is_dir()


def test_partial_report_write_preserves_old_report_and_stdout(
    tmp_path, monkeypatch, live_run, capsys
):
    target = tmp_path / "report.md"
    target.write_text("previous complete report", encoding="utf-8")
    original = Path.write_text

    def partial_write(path, data, **kwargs):
        original(path, data[:8], **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", partial_write)
    with pytest.raises(OSError, match="disk full"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert len(live_run) == 1
    assert target.read_text() == "previous complete report"
    assert "overall exact-match: 100.0%" in capsys.readouterr().out
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fixtures", "report.md"]


def test_provider_abort_preserves_report_and_cleans_reserved_file(tmp_path, monkeypatch, live_run):
    target = tmp_path / "report.md"
    target.write_text("previous complete report", encoding="utf-8")

    def abort(*args, **kwargs):
        assert target.read_text() == "previous complete report"
        raise RuntimeError("unexpected provider failure")

    monkeypatch.setattr(runner, "run_accuracy", abort)
    with pytest.raises(RuntimeError, match="unexpected provider failure"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert target.read_text() == "previous complete report"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fixtures", "report.md"]


def test_unwritable_output_directory_fails_before_live_requests(tmp_path, monkeypatch, live_run):
    def denied(*args, **kwargs):
        raise PermissionError("report directory is not writable")

    monkeypatch.setattr(tempfile, "mkstemp", denied)
    with pytest.raises(PermissionError, match="not writable"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(tmp_path / "report.md")])
    assert live_run == []
    assert not (tmp_path / "report.md").exists()


def test_existing_report_write_access_is_checked_without_truncation(
    tmp_path, monkeypatch, live_run
):
    target = tmp_path / "report.md"
    target.write_text("previous complete report")
    original = os.open

    def denied(path, flags, *args, **kwargs):
        if Path(path) == target:
            raise PermissionError("report is not writable")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(PermissionError, match="report is not writable"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert live_run == []
    assert target.read_text() == "previous complete report"


def test_atomic_publish_failure_keeps_old_report_and_stdout(
    tmp_path, monkeypatch, live_run, capsys
):
    target = tmp_path / "report.md"
    target.write_text("previous complete report")

    def fail_replace(self, destination):
        assert "overall exact-match: 100.0%" in self.read_text()
        raise PermissionError("cannot replace report")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(PermissionError, match="cannot replace report"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert len(live_run) == 1
    assert target.read_text() == "previous complete report"
    assert "overall exact-match: 100.0%" in capsys.readouterr().out
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fixtures", "report.md"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO check")
def test_non_regular_output_is_rejected_without_opening_it(tmp_path, live_run):
    target = tmp_path / "report-pipe"
    os.mkfifo(target)
    with pytest.raises(OSError, match="regular file"):
        runner.main(["--doc-type", "invoice", "--live", "--out", str(target)])
    assert live_run == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink and permission semantics")
def test_symlink_target_is_replaced_completely_and_keeps_permissions(tmp_path, live_run):
    target = tmp_path / "actual.md"
    target.write_text("previous complete report")
    target.chmod(0o640)
    link = tmp_path / "report.md"
    link.symlink_to(target.name)
    assert runner.main(["--doc-type", "invoice", "--live", "--out", str(link)]) == 0
    assert len(live_run) == 1
    assert link.is_symlink()
    assert "overall exact-match: 100.0%" in target.read_text()
    assert link.read_text() == target.read_text()
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "actual.md",
        "fixtures",
        "report.md",
    ]
