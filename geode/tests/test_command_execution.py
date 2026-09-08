"""Exercise subprocess boundaries without requiring GNSS executables."""

import shlex
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from geode.pyRunWithRetry import RunCommand, RunCommandWithRetryExeception


def test_quoted_arguments_and_lists():
    args = [
        sys.executable,
        "-c",
        "import sys; print(sys.argv[1])",
        "a path with spaces",
    ]
    for command in (args, shlex.join(args)):
        assert RunCommand(command, 5).run_shell() == ("a path with spaces\n", "")


def test_default_stdin_is_eof():
    args = [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"]
    assert RunCommand(args, 5).run_shell() == ("''\n", "")


def test_working_directory_and_input_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "input file").write_text("hello\n")
    args = [sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"]
    assert RunCommand(args, 5, cat_file="input file").run_shell() == ("hello\n", "")


def test_missing_executable_propagates(tmp_path):
    with pytest.raises(FileNotFoundError):
        RunCommand([str(tmp_path / "missing")], 5).run_shell()


def test_timeout_is_bounded_and_retries_reopen_input(tmp_path, monkeypatch):
    path = tmp_path / "input"
    path.write_text("hello")
    inputs = []

    def timeout(*args, **kwargs):
        inputs.append(kwargs["stdin"])
        assert kwargs["stdin"].read() == "hello"
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(RunCommandWithRetryExeception, match="Timeout after 3"):
        RunCommand(["unused"], 0.01, cwd=tmp_path, cat_file="input").run_shell()
    assert len(inputs) == 3
    assert all(stream.closed for stream in inputs)


def test_failed_cluster_submission_does_not_wait():
    import threading

    import dispy

    from geode.pyJobServer import JobServer

    server = JobServer.__new__(JobServer)
    server.run_parallel = True
    server.close = False
    server._node_init_lock = threading.Lock()
    server.cluster = SimpleNamespace(
        send_file=Mock(), submit_node=Mock(return_value=None)
    )
    server.check_gamit_tables = None
    server.check_archive = True
    server.check_executables = False
    server.check_atx = True
    server.software_sync = ()
    server.result = []
    server.nodes = []
    node = SimpleNamespace(name="test", avail_cpus=1)
    server.check_cluster(dispy.DispyNode.Initialized, node, None)
    assert server.nodes == []
    assert server.result == []

    server.cluster.submit_node.assert_called_once_with(
        node, None, True, False, True, ()
    )


@pytest.mark.parametrize(
    "tool",
    [
        "PlotETM",
        "AlterETM",
        "EtmStacker",
        "ScanArchive",
        "ArchiveService",
        "DownloadSources",
        "LocateRinex",
        "StationReport",
        "StationKmz",
        "CampaignPlanner",
        "AntennaCatalog",
    ],
)
def test_cli_help_requires_no_database(tool, tmp_path):
    import os

    # Installed CLI modules must work outside the checkout without a config file.
    environment = {
        **os.environ,
        "POSTGRES_HOST": "invalid.invalid",
        "MPLBACKEND": "Agg",
    }
    result = subprocess.run(
        [sys.executable, "-m", f"com.{tool}", "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
