"""A failed database wait or migration must prevent application startup."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("failure", ["wait_for_database", "migrate", ""])
def test_entrypoint_stops_before_application_on_database_failure(tmp_path, failure):
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
        },
        capture_output=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (failure == "")
    assert marker.exists() == (failure == "")
