"""便携程序冒烟验证器：真实 CLI 契约及验证失败时的保护。"""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "build" / "verify_portable.py"
SOURCE_COMMAND = [sys.executable, "-m", "thesislint.cli"]


@pytest.fixture
def verifier():
    return runpy.run_path(str(SCRIPT))


def test_smoke_runs_real_cli_without_gui_and_cleans_synthetic_files(verifier, monkeypatch):
    original_run = subprocess.run
    calls = []

    def record(command, **kwargs):
        calls.append((command, kwargs))
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    completed = verifier["verify_portable"](SOURCE_COMMAND)

    assert len(completed) == 7
    assert len(calls) == 7
    assert all(command[:3] == SOURCE_COMMAND for command, _ in calls)
    assert all("--help" in command or "--format" in command for command, _ in calls)
    assert all(options["timeout"] > 0 for _, options in calls)
    assert all(not options.get("shell", False) for _, options in calls)
    documents = [Path(command[3]) for command, _ in calls if "--format" in command]
    assert any(
        " " in path.name and any(ord(char) > 127 for char in path.name) for path in documents
    )
    assert all(not path.exists() for path in documents)


@pytest.mark.parametrize(
    "failure,reason",
    [
        (subprocess.TimeoutExpired(["portable"], 30), "timed out"),
        (OSError("missing"), "could not start"),
    ],
)
def test_process_failure_identifies_scenario(verifier, monkeypatch, failure, reason):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError, match=rf"help:.*{reason}"):
        verifier["verify_portable"](SOURCE_COMMAND)


def test_wrong_exit_code_fails_even_with_help_output(verifier, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 2, "--format --strict", ""),
    )
    with pytest.raises(RuntimeError, match=r"help:.*expected exit 0.*got 2"):
        verifier["verify_portable"](SOURCE_COMMAND)


@pytest.mark.parametrize("payload", ["not JSON", "[]", "{}"])
def test_exit_zero_is_insufficient_without_valid_report(verifier, monkeypatch, payload):
    def run(command, **kwargs):
        stdout = "--format --strict" if "--help" in command else payload
        return subprocess.CompletedProcess(command, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="table normal:"):
        verifier["verify_portable"](SOURCE_COMMAND)


def test_verifier_catches_missing_table_entry_despite_success_exit(verifier, monkeypatch):
    original_run = subprocess.run

    def drop_entry(command, **kwargs):
        result = original_run(command, **kwargs)
        if "--format" in command:
            report = json.loads(result.stdout)
            report["entries"].pop()
            result.stdout = json.dumps(report)
        return result

    monkeypatch.setattr(subprocess, "run", drop_entry)
    with pytest.raises(RuntimeError, match=r"table normal:.*entries"):
        verifier["verify_portable"](SOURCE_COMMAND)


def test_main_rejects_missing_executable_without_launching_anything(
    verifier, monkeypatch, tmp_path
):
    def unexpected(*args, **kwargs):
        pytest.fail("missing executable must not be launched")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(SystemExit) as exc:
        verifier["main"](["--executable", str(tmp_path / "missing.exe")])
    assert exc.value.code == 2
