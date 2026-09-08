"""Isolated PostgreSQL for integration tests, using the Pixi dev tools."""

import shutil
import subprocess
import time
from pathlib import Path

import psycopg
import pytest


@pytest.fixture
def postgres_connection(tmp_path):
    initdb, postgres, psql = (
        shutil.which(name) for name in ("initdb", "postgres", "psql")
    )
    if not all((initdb, postgres, psql)):
        pytest.skip("PostgreSQL test tools are included in the Pixi dev environment")
    root = Path(__file__).resolve().parents[2]
    cluster = tmp_path / "data"
    socket_dir = tmp_path / "socket"
    socket_dir.mkdir()
    subprocess.run(
        [
            initdb,
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
                postgres,
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
