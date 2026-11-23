"""Isolated PostgreSQL for integration tests, using the dedicated Pixi server tools."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest


@pytest.fixture(scope="session")
def postgres_bin():
    """Use the sibling Pixi environment's matching server and client programs."""
    prefix = Path(sys.prefix)
    if (prefix / "conda-meta/pixi").exists():
        bindir = prefix.parent / "postgres" / "bin"
        if not (bindir / "initdb").is_file():
            pytest.fail(
                "Install the PostgreSQL tools with pixi install --locked -e postgres"
            )
        return bindir

    initdb = shutil.which("initdb")
    if initdb is None:
        pytest.skip("PostgreSQL integration tests need the Pixi postgres environment")
    return Path(initdb).resolve().parent


@pytest.fixture
def postgres_connection(tmp_path, postgres_bin):
    cluster = tmp_path / "data"
    socket_dir = tmp_path / "socket"
    socket_dir.mkdir()
    subprocess.run(
        [
            postgres_bin / "initdb",
            "-D",
            str(cluster),
            "-A",
            "trust",
            "--no-locale",
            "--encoding=UTF8",
            "-U",
            "geode_test",
        ],
        check=True,
        capture_output=True,
    )
    with (tmp_path / "postgres.log").open("w") as log:
        process = subprocess.Popen(
            [
                postgres_bin / "postgres",
                "-D",
                str(cluster),
                "-k",
                str(socket_dir),
                "-h",
                "",
                "-p",
                "55439",
            ],
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    cnn = psycopg.connect(
                        host=str(socket_dir),
                        port=55439,
                        user="geode_test",
                        dbname="postgres",
                        autocommit=True,
                    )
                    break
                except psycopg.OperationalError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail((tmp_path / "postgres.log").read_text())
                    time.sleep(0.1)
            with cnn:
                yield cnn
        finally:
            process.terminate()
            process.wait(timeout=20)
            # Keep the log, but do not retain a stopped database for every test.
            # A suite can otherwise exhaust temporary-directory disk quotas.
            shutil.rmtree(cluster, ignore_errors=True)
