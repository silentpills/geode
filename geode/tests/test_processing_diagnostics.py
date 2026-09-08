"""PPP residual parsing and real PostgreSQL schema regression tests."""

import ast
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from geode.pyPPP import RunPPP


@pytest.mark.parametrize("direction", ["BWD", "FWD"])
def test_residual_bins_and_backward_preference(tmp_path, direction):
    path = tmp_path / "solution.res"
    rows = [
        f"{direction} 0 0 0 0 0 10.1 0 0.02",
        f"{direction} 0 0 0 0 0 10.2 0 0.04",
        "invalid line",
    ]
    if direction == "BWD":
        rows.append("FWD 0 0 0 0 0 10 0 99")
    path.write_text("\n".join(rows))
    result = SimpleNamespace(path_res_file=str(path))
    RunPPP.parse_res_file(result)
    assert result.elevation_residuals.shape == (91,)
    assert result.elevation_residuals[10] == pytest.approx(0.03)
    assert np.isnan(result.elevation_residuals[0])


def test_missing_residual_file_is_optional(tmp_path):
    result = SimpleNamespace(
        path_res_file=str(tmp_path / "missing"), elevation_residuals=None
    )
    RunPPP.parse_res_file(result)
    assert result.elevation_residuals is None


def test_processing_schema_is_repeatable_and_cascades(postgres_connection):
    """Load the real schema, reapply Django SQL, and exercise the PPP foreign key."""
    cnn = postgres_connection
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            shutil.which("psql"),
            "-h",
            cnn.info.host,
            "-p",
            "55439",
            "-U",
            "geode_test",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(root / "database/schema.sql"),
        ],
        check=True,
        capture_output=True,
    )
    migration = ast.parse(
        (root / "web/backend/api/migrations/0034_processing_diagnostics.py").read_text()
    )
    statements = [
        ast.literal_eval(n.args[0])
        for n in ast.walk(migration)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "RunSQL"
    ]
    for _ in range(2):
        for sql in statements:
            cnn.execute(sql)
    cnn.execute("INSERT INTO networks (\"NetworkCode\") VALUES ('tst')")
    cnn.execute(
        "INSERT INTO stations (\"NetworkCode\", \"StationCode\") VALUES ('tst', 'test')"
    )
    cnn.execute(
        'INSERT INTO ppp_soln ("NetworkCode", "StationCode", "Year", "DOY", "ReferenceFrame") VALUES (\'tst\', \'test\', 2026, 1, \'IGS20\')'
    )
    cnn.execute(
        "INSERT INTO ppp_antenna_residuals (network_code, station_code, year, doy, reference_frame, antenna_code, radome_code, residuals) VALUES ('tst', 'test', 2026, 1, 'IGS20', 'TEST', 'NONE', %s)",
        ([0.01] * 91,),
    )
    assert cnn.execute(
        "SELECT cardinality(residuals) FROM ppp_antenna_residuals"
    ).fetchone() == (91,)
    cnn.execute("DELETE FROM ppp_soln WHERE \"NetworkCode\" = 'tst'")
    assert cnn.execute("SELECT count(*) FROM ppp_antenna_residuals").fetchone() == (0,)
