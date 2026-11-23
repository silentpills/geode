"""A failed database wait or migration must prevent application startup."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "failure,auto_migrate,starts",
    [
        ("wait_for_database", "true", False),
        ("migrate", "true", False),
        ("", "true", True),
        ("wait_for_database", "false", False),
        ("migrate", "false", True),
    ],
)
def test_entrypoint_stops_before_application_on_database_failure(
    tmp_path, failure, auto_migrate, starts
):
    python = tmp_path / "python"
    python.write_text('#!/bin/bash\n[[ "$2" != "$FAIL_STEP" ]]\n')
    python.chmod(0o755)
    marker = tmp_path / "started"
    result = subprocess.run(
        ["bash", str(ROOT / "web/backend/entrypoint.sh"), "touch", str(marker)],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "FAIL_STEP": failure,
            "GEODE_AUTO_MIGRATE": auto_migrate,
        },
        capture_output=True,
        timeout=10,
    )
    assert (result.returncode == 0) == starts
    assert marker.exists() == starts


@pytest.mark.parametrize(
    "override",
    [
        {"GEODE_APP_PASSWORD": ""},
        {"GEODE_APP": "pgamit"},
        {"GEODE_OWNER": "postgres"},
        {"GEODE_OWNER_PASSWORD": "test-app-secret"},
        {},
    ],
)
def test_bundled_database_preflight_precedes_initialization(tmp_path, override):
    marker = tmp_path / "initialized"
    entrypoint = tmp_path / "docker-entrypoint.sh"
    entrypoint.write_text('#!/bin/sh\ntouch "$INIT_MARKER"\n')
    entrypoint.chmod(0o755)
    result = subprocess.run(
        ["sh", str(ROOT / "database/start-bundled-postgres.sh"), "postgres"],
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "POSTGRES_PASSWORD": "test-admin-secret",
            "GEODE_OWNER": "pgamit",
            "GEODE_OWNER_PASSWORD": "test-owner-secret",
            "GEODE_APP": "geode_app",
            "GEODE_APP_PASSWORD": "test-app-secret",
            "INIT_MARKER": str(marker),
            **override,
        },
        capture_output=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (not override)
    assert marker.exists() == (not override)
    assert b"-secret" not in result.stderr
