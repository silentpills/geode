"""FixPlate persistence on isolated PostgreSQL, without operational GNSS jobs."""

import json
import shutil
import subprocess
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import psycopg
import pytest
from psycopg.rows import dict_row

from com import FixPlate
from geode import dbConnection, pyETM
from geode.pyDate import Date
from geode.reference_frames import frame_provenance, save_frame, source_epochs


@pytest.fixture
def frame_db(postgres_connection):
    connection = postgres_connection
    subprocess.run(
        [
            shutil.which("psql"),
            "-h",
            connection.info.host,
            "-p",
            str(connection.info.port),
            "-U",
            connection.info.user,
            "-d",
            connection.info.dbname,
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(
                Path(__file__).resolve().parents[2]
                / "geode/sql/bootstrap_v1/schema.sql"
            ),
        ],
        check=True,
        capture_output=True,
    )
    connection.execute("INSERT INTO networks (\"NetworkCode\") VALUES ('tst')")
    connection.execute(
        'INSERT INTO stations ("NetworkCode", "StationCode", auto_x, auto_y, auto_z) '
        "VALUES ('tst', 'aaaa', 6378137, 0, 0), ('tst', 'bbbb', 0, 6378137, 0)"
    )
    for code in ("aaaa", "bbbb"):
        for doy, project in ((1, "zeta"), (2, "alpha")):
            connection.execute(
                'INSERT INTO gamit_soln ("NetworkCode", "StationCode", "Year", "DOY", "Project") '
                "VALUES ('tst', %s, 2026, %s, %s)",
                (code, doy, project),
            )
            connection.execute(
                'INSERT INTO stacks ("NetworkCode", "StationCode", "Year", "DOY", "Project", name) '
                "VALUES ('tst', %s, 2026, %s, %s, 'source')",
                (code, doy, project),
            )
            connection.execute(
                'INSERT INTO ppp_soln ("NetworkCode", "StationCode", "Year", "DOY", "ReferenceFrame") '
                "VALUES ('tst', %s, 2026, %s, 'IGS20')",
                (code, doy),
            )
    before = connection.execute("SELECT * FROM stacks ORDER BY api_id").fetchall()
    with connection.transaction():
        connection.execute(
            files("geode").joinpath("sql/reference_frames_v1.sql").read_text()
        )
    cnn = SimpleNamespace(
        cnn=connection, cursor=connection.cursor(row_factory=dict_row)
    )
    cnn.insert_many = MethodType(dbConnection.Cnn.insert_many, cnn)
    cnn.query_float = MethodType(dbConnection.Cnn.query_float, cnn)
    cnn.query = MethodType(dbConnection.Cnn.query, cnn)
    cnn.original_rows = before
    return cnn


def fit(ppp=False):
    href = [dict(NetworkCode="tst", StationCode="aaaa", plate="SA")]
    vref = [
        dict(NetworkCode="tst", StationCode="bbbb", lat=0, lon=90, vu_external=0.002)
    ]
    return frame_provenance(href, vref, np.arange(1, 7).reshape(6, 1), "source", ppp)


def rows(code="aaaa", ppp=False):
    return [
        dict(
            NetworkCode="tst",
            StationCode=code,
            Year=2026,
            DOY=doy,
            Project=None if ppp else project,
            ppp_reference_frame="IGS20" if ppp else None,
            X=float(doy),
            Y=2.0,
            Z=3.0,
        )
        for doy, project in ((1, "zeta"), (2, "alpha"))
    ]


def snapshot(cnn, name="fixed"):
    return tuple(
        cnn.cnn.execute(query, (name,)).fetchall()
        for query in (
            "SELECT * FROM stacks WHERE name=%s ORDER BY api_id",
            "SELECT * FROM reference_frames WHERE frame_name=%s",
            "SELECT * FROM reference_frame_constraints WHERE constraints_id=%s ORDER BY api_id",
        )
    )


def test_additive_schema_preserves_rows_ids_and_reapplies(frame_db):
    cnn = frame_db
    original_fields = [
        column.name
        for column in cnn.cnn.execute("SELECT * FROM stacks LIMIT 0").description
    ][:-2]
    columns = psycopg.sql.SQL(", ").join(map(psycopg.sql.Identifier, original_fields))
    query = psycopg.sql.SQL("SELECT {} FROM stacks ORDER BY api_id").format(columns)
    assert cnn.cnn.execute(query).fetchall() == cnn.original_rows
    with cnn.cnn.transaction():
        cnn.cnn.execute(
            files("geode").joinpath("sql/reference_frames_v1.sql").read_text()
        )
    assert cnn.cnn.execute(query).fetchall() == cnn.original_rows
    assert cnn.cnn.execute(
        "SELECT project FROM gamit_projects ORDER BY project"
    ).fetchall() == [("alpha",), ("zeta",)]


def test_units_projects_constraint_ids_and_replacement(frame_db):
    cnn = frame_db
    provenance, constraints = fit()
    assert provenance["euler_pole"] == pytest.approx(
        np.arange(1, 4) * 1e-9 * 180 / np.pi * 3600 * 1000
    )
    assert [constraints[0][key] for key in ("vx", "vy", "vz")] == pytest.approx(
        [0, 0.002, 0], abs=1e-16
    )
    assert save_frame(cnn, "fixed", provenance, constraints, [rows()]) == 2
    record = cnn.query_float("SELECT * FROM reference_frames", as_dict=True)[0]
    assert record["source_projects"] == {"alpha": 1, "zeta": 1}
    assert record["project"] == "alpha"
    assert str(record["first_epoch"]) == "2026-01-01 00:00:00"
    assert str(record["last_epoch"]) == "2026-01-02 00:00:00"
    constraint_id = cnn.cnn.execute(
        "SELECT api_id FROM reference_frame_constraints"
    ).fetchone()
    replacement = rows()
    replacement[0]["X"] = 9.0
    save_frame(cnn, "fixed", provenance, constraints, [replacement])
    assert cnn.cnn.execute("SELECT api_id FROM reference_frames").fetchone() == (
        record["api_id"],
    )
    assert (
        cnn.cnn.execute("SELECT api_id FROM reference_frame_constraints").fetchone()
        == constraint_id
    )
    assert cnn.cnn.execute(
        'SELECT "Project" FROM stacks WHERE name=\'fixed\' ORDER BY "DOY"'
    ).fetchall() == [("zeta",), ("alpha",)]


def test_failure_rolls_back_coordinates_metadata_and_constraints(frame_db):
    cnn = frame_db
    provenance, constraints = fit()
    save_frame(cnn, "fixed", provenance, constraints, [rows()])
    before = snapshot(cnn)
    changed = dict(provenance, euler_pole=[9.0, 8.0, 7.0])
    invalid = [dict(constraints[0], station_code="none")]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        save_frame(cnn, "fixed", changed, invalid, [rows("bbbb")])
    assert snapshot(cnn) == before
    with pytest.raises(psycopg.errors.UniqueViolation):
        save_frame(cnn, "fixed", changed, [], [rows(), rows()])
    assert snapshot(cnn) == before
    with pytest.raises(ValueError, match="No corrected"):
        save_frame(cnn, "fixed", changed, [], [])
    assert snapshot(cnn) == before


def test_preserve_checks_fit_constraints_and_source_provenance(frame_db):
    cnn = frame_db
    provenance, constraints = fit()
    save_frame(cnn, "fixed", provenance, constraints, [rows()])
    before = snapshot(cnn)
    for changed in (
        dict(provenance, fixed_plate="NA"),
        dict(provenance, euler_pole=[1, 2, 3]),
        dict(provenance, euler_pole_stations=["tst.bbbb"]),
        dict(provenance, source_stack="other"),
    ):
        with pytest.raises(ValueError, match="different"):
            save_frame(
                cnn, "fixed", changed, constraints, [rows("bbbb")], preserve=True
            )
        assert snapshot(cnn) == before
    with pytest.raises(ValueError, match="VREF"):
        save_frame(cnn, "fixed", provenance, [], [rows("bbbb")], preserve=True)
    with pytest.raises(ValueError, match="without saved fit"):
        save_frame(
            cnn, "source", dict(provenance, source_stack="other"), [], [], preserve=True
        )
    assert (
        save_frame(
            cnn, "fixed", provenance, constraints, [rows(), rows("bbbb")], preserve=True
        )
        == 2
    )
    assert cnn.cnn.execute("SELECT source_projects FROM reference_frames").fetchone()[
        0
    ] == {"alpha": 2, "zeta": 2}
    cnn.cnn.execute(
        "DELETE FROM stacks WHERE name='source' AND \"StationCode\"='aaaa' AND \"DOY\"=1"
    )
    after = snapshot(cnn)
    with pytest.raises(ValueError, match="source provenance"):
        save_frame(cnn, "fixed", provenance, constraints, [], preserve=True)
    assert snapshot(cnn) == after


def test_ppp_foreign_key_ambiguity_and_engine_ownership(frame_db):
    cnn = frame_db
    provenance, constraints = fit(ppp=True)
    save_frame(cnn, "pppfixed", provenance, constraints, [rows(ppp=True)])
    assert (
        cnn.cnn.execute(
            "SELECT engine, \"Project\", ppp_reference_frame FROM stacks WHERE name='pppfixed'"
        ).fetchall()
        == [("ppp", None, "IGS20")] * 2
    )
    assert cnn.cnn.execute(
        "SELECT project, source_projects FROM reference_frames"
    ).fetchone() == ("gpspace", {"gpspace": 2})
    with pytest.raises(psycopg.IntegrityError):
        cnn.cnn.execute("DELETE FROM ppp_soln WHERE \"StationCode\"='aaaa'")
    with pytest.raises(ValueError, match="another processing engine"):
        save_frame(cnn, "source", provenance, constraints, [rows(ppp=True)])
    with pytest.raises(ValueError, match="another processing engine"):
        save_frame(cnn, "pppfixed", *fit(), [rows()])
    with pytest.raises(psycopg.Error, match="another processing engine"):
        cnn.insert_many("stacks", [dict(rows()[0], name="pppfixed")])
    with pytest.raises(pyETM.pyETMException, match="corrected PPP"):
        pyETM.GamitSoln(cnn, [], "tst", "aaaa", "pppfixed")
    from geode.etm.data.solution_data import GAMITSolutionData, SolutionDataException

    with pytest.raises(SolutionDataException, match="corrected PPP"):
        GAMITSolutionData._load_project_info(
            SimpleNamespace(
                stack_name="pppfixed", network_code="tst", station_code="aaaa"
            ),
            cnn,
        )
    cnn.cnn.execute(
        'INSERT INTO ppp_soln ("NetworkCode", "StationCode", "Year", "DOY", "ReferenceFrame") VALUES (\'tst\', \'aaaa\', 2026, 1, \'IGS14\')'
    )
    with pytest.raises(ValueError, match="Ambiguous PPP"):
        source_epochs(cnn, "tst", "aaaa", "ignored", ppp=True)
    with pytest.raises(ValueError, match="source provenance"):
        save_frame(cnn, "pppfixed", provenance, constraints, [], preserve=True)


def test_new_metadata_cannot_destroy_scientific_rows(frame_db):
    cnn = frame_db
    save_frame(cnn, "fixed", *fit(), [rows()])
    before = snapshot(cnn)
    for query in (
        "DELETE FROM reference_frames WHERE frame_name='fixed'",
        "UPDATE reference_frames SET frame_name='renamed' WHERE frame_name='fixed'",
        "DELETE FROM gamit_projects WHERE project='zeta'",
        "UPDATE gamit_projects SET project='renamed' WHERE project='zeta'",
        "UPDATE reference_frames SET source_projects='{\"missing\": 1}' WHERE frame_name='fixed'",
    ):
        with pytest.raises(psycopg.Error):
            cnn.cnn.execute(query)
        assert snapshot(cnn) == before


@pytest.mark.parametrize("ppp", [False, True])
def test_fixplate_spools_before_transaction_filters_and_preserves(
    frame_db, monkeypatch, tmp_path, ppp
):
    cnn = frame_db
    calls = []

    def fake_etm(connection, network, station, **kwargs):
        # Model calculations may commit internally, so none may run inside save.
        assert (
            connection.cnn.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
        )
        calls.append(station)
        connection.cnn.commit()
        dates = [Date(year=2026, doy=doy) for doy in (1, 2)]
        return SimpleNamespace(
            soln=SimpleNamespace(date=dates), L=np.array([[1, 2], [3, 4], [5, 6]])
        )

    monkeypatch.setattr(pyETM, "GamitETM", fake_etm)
    monkeypatch.setattr(pyETM, "PPPETM", fake_etm)
    args = SimpleNamespace(
        stack_name=["ignored" if ppp else "source"],
        ppp_solutions=ppp,
        save_stack="fixed",
        save_filter=["tst.aaaa"],
        preserve_stack=False,
        plot_etms=False,
        directory=str(tmp_path),
    )
    href = [dict(NetworkCode="tst", StationCode="aaaa", plate="SA")]
    FixPlate.save_corrected_stack(cnn, args, href, [], np.ones((3, 1)))
    assert calls == ["aaaa"]
    args.save_filter = None
    args.preserve_stack = True
    FixPlate.save_corrected_stack(cnn, args, href, [], np.ones((3, 1)))
    assert calls == ["aaaa", "bbbb"]
    assert cnn.cnn.execute(
        "SELECT count(*) FROM stacks WHERE name='fixed'"
    ).fetchone() == (4,)
    before = snapshot(cnn)
    args.preserve_stack = False

    def broken_etm(*a, **kw):
        raise pyETM.pyETMException("unfit station")

    monkeypatch.setattr(pyETM, "GamitETM", broken_etm)
    monkeypatch.setattr(pyETM, "PPPETM", broken_etm)
    with pytest.raises(pyETM.pyETMException, match="unfit station"):
        FixPlate.save_corrected_stack(cnn, args, href, [], np.ones((3, 1)))
    assert snapshot(cnn) == before


def test_decimal_matrices_and_vref_tokens():
    records = [
        (Decimal("1.5"), [[Decimal("0.1"), Decimal("0.2")]]),
        {"params": [[Decimal("1"), Decimal("2")]]},
    ]
    converted = dbConnection.cast_array_to_float(records)
    assert converted == [(1.5, [[0.1, 0.2]]), {"params": [[1.0, 2.0]]}]
    json.dumps(converted)
    assert FixPlate.vertical_reference_tokens(
        ["tst.aaaa", "1.0", "tst.bbbb", "-2.0"]
    ) == ["tst.aaaa 1.0", "tst.bbbb -2.0"]
    assert FixPlate.vertical_reference_tokens(["tst.aaaa 1.0"]) == ["tst.aaaa 1.0"]
    with pytest.raises(ValueError, match="velocity"):
        FixPlate.vertical_reference_tokens(["tst.aaaa"])


def test_euler_pole_uses_vref_selection_and_matrix_velocities(monkeypatch, tmp_path):
    selections = []

    def selected(cnn, tokens, **kwargs):
        selections.append(tokens)
        if len(selections) == 1:
            return [dict(NetworkCode="tst", StationCode="aaaa")]
        return [dict(NetworkCode="tst", StationCode="bbbb", parameters=["2.0"])]

    monkeypatch.setattr(FixPlate, "process_stnlist", selected)
    cnn = SimpleNamespace(
        query_float=lambda *a, **kw: [
            dict(
                auto_x=6378137,
                auto_y=0,
                auto_z=0,
                plate="SA",
                params=[
                    [Decimal("0"), Decimal("0.001")],
                    [Decimal("0"), Decimal("0.002")],
                    [Decimal("0"), Decimal("0.003")],
                ],
            )
        ]
    )
    observations = []

    def adjusted(design, obs):
        observations.append(obs)
        return (
            np.arange(1, 7).reshape(6, 1),
            np.ones((1, 6)),
            np.ones((3, 1), dtype=bool),
            np.zeros((3, 1)),
            np.ones((1, 1)),
            None,
            np.eye(6),
        )

    monkeypatch.setattr(FixPlate, "adjust_lsq", adjusted)
    captured = []
    monkeypatch.setattr(
        FixPlate, "save_corrected_stack", lambda *args: captured.append(args)
    )
    args = SimpleNamespace(
        include_stations=["tst.aaaa"],
        vertical_ref=["tst.bbbb", "2.0"],
        directory=str(tmp_path),
        save_stack="fixed",
        stack_name=["source"],
        ppp_solutions=False,
        plot_etms=False,
    )
    FixPlate.euler_pole(args, cnn)
    assert selections == [["tst.aaaa"], ["tst.bbbb 2.0"]]
    assert observations[0].ravel() == pytest.approx([0.001, 0.002, 0.001])
    _, _, href, vref, _ = captured[0]
    assert href[0]["plate"] == "SA"
    assert vref[0]["vu_external"] == 0.002
