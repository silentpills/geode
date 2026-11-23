"""Processing-job manifests, daily product replacement, and scratch publication."""

import json
from contextlib import closing, nullcontext
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg.rows import dict_row

from com import ParallelGamit
from geode import compute_wire, dbConnection
from geode.gamit import campaign, gamit_session, gamit_task, globk_task, parse_ztd
from geode.pyDate import Date


def wire_round_trip(value):
    return compute_wire.decode(json.loads(json.dumps(compute_wire.encode(value))))


@pytest.fixture
def local_guard(monkeypatch):
    connection = object()
    monkeypatch.setattr(
        ParallelGamit,
        "active_day",
        lambda *args: nullcontext((connection, lambda: None)),
    )
    return connection


@pytest.fixture
def connect(postgres_connection, monkeypatch):
    original = dbConnection.Cnn

    def new_connection(*args, **kwargs):
        wrapper = object.__new__(original)
        wrapper.active_transaction = False
        wrapper.cnn = psycopg.connect(
            postgres_connection.info.dsn, autocommit=True, row_factory=dict_row
        )
        wrapper.cursor = wrapper.cnn.cursor()
        return wrapper

    monkeypatch.setattr(dbConnection, "Cnn", new_connection)
    return new_connection


def test_gamit_dry_run_from_session_manifest(tmp_path, monkeypatch, local_guard):
    date = Date(year=2024, doy=100)
    prepared = tmp_path / "prepared"
    scratch = tmp_path / "scratch" / "001"
    (prepared / "tables").mkdir(parents=True)
    (prepared / "observations").write_text("original")
    session = SimpleNamespace(
        ready=True,
        get_rinex_filenames=lambda: [],
        solution_pwd=str(tmp_path / "published"),
        prepared_pwd=str(prepared),
        subnet_record={},
        remote_pwd=str(scratch),
        NetName="sample",
        DirName="sample.001",
        date=date,
        subnet=1,
        GamitOpts=dict(
            org="TST",
            expt="geod",
            systems=["G"],
            eop_type="usno",
            noftp="yes",
            overconst_action="inflate",
            unused="private",
        ),
        Config=SimpleNamespace(
            sp3_path="sp3",
            brdc_path="brdc",
            ionex_path="ionex",
            sp3types=["COD"],
            options={"password": "private"},
        ),
    )
    gamit_session.GamitSession.initialize(session)
    encoded = wire_round_trip(session.params)
    assert "private" not in repr(encoded)
    monkeypatch.setattr(gamit_task.GamitTask, "fetch_orbits", lambda self: None)
    monkeypatch.setattr(gamit_task.GamitTask, "fetch_rinex", lambda self: None)
    assert ParallelGamit.run_gamit_session(encoded, True, "attempt-1") == []
    assert (prepared / "observations").read_text() == "original"
    assert "Copy results" in (prepared / "monitor.log").read_text()
    assert not list(scratch.parent.iterdir())
    assert not (tmp_path / "published").exists()
    (failure,) = ParallelGamit.run_gamit_session(encoded, False, "attempt-2")
    assert not failure["success"]
    assert "No configured constellation" in failure["error"]
    assert wire_round_trip(failure) == failure


def test_session_product_inputs_preserve_ztd_and_station_aliases(
    tmp_path, monkeypatch, local_guard
):
    date = Date(year=2024, doy=100)
    options = dict(org="TST", expt="geod", eop_type="usno")
    session = SimpleNamespace(
        pwd_glbf=str(tmp_path),
        date=date,
        DirName="geod.001",
        NetName="geod",
        StationInstances=[
            SimpleNamespace(
                StationAlias="test",
                NetworkCode="net",
                StationCode="orig",
                private="private",
            )
        ],
        GamitOpts=options,
    )
    products = wire_round_trip([gamit_session.session_products(session)])
    assert "private" not in repr(products)
    (tmp_path / ("TST" + date.wwwwd() + ".znd")).write_text(
        "ATM_ZEN X TEST XX 2024 4 9 0 0 0 2.000 +0.100 3.000\n"
    )
    actual = []
    monkeypatch.setattr(parse_ztd, "replace_day", lambda *args: actual.append(args))
    assert ParallelGamit.run_parse_ztd("TST", "GeoD", products, date, "attempt") == []
    assert (
        parse_ztd.ParseZtdTask(
            SimpleNamespace(gamitopt=options), "GeoD", [session], date
        ).execute(local_guard)
        == []
    )
    assert actual[0] == actual[1]
    assert actual[0][4] == [
        dict(
            NetworkCode="net",
            StationCode="orig",
            Date="2024-04-09 00:00:00",
            Project="geod",
            model=1,
            sigma=0.1,
            ZTD=3,
            Year=2024,
            DOY=100,
        )
    ]

    (tmp_path / "sample.snx").touch()
    vertex = SimpleNamespace(
        X=1, Y=2, Z=3, sigX=1, sigY=2, sigZ=3, sigXY=4, sigXZ=5, sigYZ=6
    )
    monkeypatch.setattr(
        globk_task.snxParse,
        "snxFileParser",
        lambda path: SimpleNamespace(
            parse=lambda: None, stationDict={"TEST": vertex}, varianceFactor=4
        ),
    )
    monkeypatch.setattr(gamit_session, "replace_day", lambda *args: actual.append(args))
    assert (
        ParallelGamit.run_globk(
            str(tmp_path), "geod", date, products, "regional", options, "attempt"
        )
        == []
    )
    (row,) = actual[-1][4]
    assert (row["NetworkCode"], row["StationCode"], row["X"], row["sigmayz"]) == (
        "net",
        "orig",
        1,
        12,
    )


def test_failed_combination_preserves_prior_tree(tmp_path, monkeypatch):
    destination = tmp_path / "glbf"
    destination.mkdir()
    (destination / "reference.snx").write_bytes(b"reference")
    task = globk_task.Globk(
        str(destination),
        Date(year=2024, doy=100),
        [{}, {}],
        options=dict(org="TST", expt="geod", eop_type="usno"),
    )

    def fail(self):
        (Path(self.pwd_comb) / "partial.snx").write_bytes(b"partial")
        raise RuntimeError("interrupted")

    monkeypatch.setattr(globk_task.Globk, "_combine", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        task.execute()
    assert [p.name for p in destination.iterdir()] == ["reference.snx"]
    assert (destination / "reference.snx").read_bytes() == b"reference"


def test_failed_directory_promotion_restores_previous_tree(tmp_path, monkeypatch):
    destination = tmp_path / "solution"
    staged = tmp_path / "staged"
    destination.mkdir()
    staged.mkdir()
    (destination / "previous").touch()
    rename = Path.rename

    def fail(self, target):
        if self == staged:
            raise OSError("promotion failed")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", fail)
    with pytest.raises(OSError, match="promotion failed"):
        gamit_session.publish_directory(staged, destination)
    assert (destination / "previous").exists()
    assert staged.exists()


def test_failed_day_insert_rolls_back_replacement(postgres_connection, connect):
    db = postgres_connection
    db.execute(
        'CREATE TABLE gamit_soln ("Project" text, "Year" integer, "DOY" integer, "X" integer CHECK ("X" > 0), '
        '"NetworkCode" text, "StationCode" text, api_id serial, PRIMARY KEY ("Project", "Year", "DOY", "NetworkCode", "StationCode"))'
    )
    db.execute("INSERT INTO gamit_soln VALUES ('geod', 2024, 100, 10, 'net', 'abcd')")
    base = dict(
        Project="geod", Year=2024, DOY=100, NetworkCode="net", StationCode="abcd"
    )
    date = Date(year=2024, doy=100)
    with closing(connect()) as cnn, pytest.raises(psycopg.errors.CheckViolation):
        gamit_session.replace_day(
            cnn,
            "gamit_soln",
            "geod",
            date,
            [dict(base, X=1), dict(base, X=-1, StationCode="efgh")],
        )
    assert db.execute('SELECT "X" FROM gamit_soln').fetchall() == [(10,)]
    with closing(connect()) as cnn:
        gamit_session.replace_day(cnn, "gamit_soln", "geod", date, [dict(base, X=2)])
    assert db.execute('SELECT "X",api_id FROM gamit_soln').fetchall() == [(2, 1)]


def test_campaign_fences_stale_purge_and_overlapping_work(
    tmp_path, postgres_connection, connect
):
    db = postgres_connection
    for name in ("compute_jobs_v1.sql", "compute_private_v1.sql"):
        db.execute(files("geode").joinpath("sql", name).read_text())
    for table in (
        "gamit_soln_excl",
        "stacks",
        "gamit_soln",
        "gamit_stats",
        "gamit_subnets",
        "gamit_ztd",
    ):
        db.execute(
            f'CREATE TABLE {table} ("Project" text, "Year" int, "DOY" int, subnet int)'
        )
    date = Date(year=2024, doy=100)
    solution = tmp_path / "geod"
    solution.mkdir()
    (solution / "retain.snx").write_bytes(b"observations")
    row_key = dict(Project="geod", Year=2024, DOY=100, subnet=0)
    with closing(connect()) as first, closing(connect()) as second:
        with pytest.raises(
            gamit_session.GamitSessionException, match="move only this session"
        ):
            gamit_session.completed_session(first, solution, row_key)
        with campaign.campaign_run(first, "geod", [date]) as old:
            with pytest.raises(RuntimeError, match="Another campaign"):
                with campaign.campaign_run(second, "geod", [date]):
                    pytest.fail("overlapping coordinator admitted")
        # Simulate loss of the coordinator while an already submitted worker remains live.
        with campaign.active_day("geod", date, old):
            with pytest.raises(RuntimeError, match="worker is still"):
                with campaign.campaign_run(second, "geod", [date]):
                    pytest.fail("busy day admitted")
        with campaign.campaign_run(second, "geod", [date]) as current:
            with pytest.raises(RuntimeError, match="Superseded"):
                ParallelGamit.purge_solution(str(tmp_path), "geod", date, old, "TST")
            assert (solution / "retain.snx").read_bytes() == b"observations"
            # Both recorded and unrecorded dotted paths share this prefix.
            paths = [
                "geod.TST001",
                "geod.TST002",
                "geod.TST003",
                "geod.extra",
                ".geod.TST001.previous",
            ]
            for name in paths:
                (tmp_path / name).mkdir()
            db.execute(
                "INSERT INTO gamit_subnets VALUES ('geod', 2024, 100, 1), ('geod', 2024, 100, 2), ('geod.TST002', 2024, 100, 0), ('geod.extra', 2024, 100, 0)"
            )
            with pytest.raises(RuntimeError, match="Ambiguous ownership"):
                ParallelGamit.purge_solution(
                    str(tmp_path), "geod", date, current, "TST"
                )
            assert all((tmp_path / name).exists() for name in paths)
            assert solution.is_dir()
            # Reconcile subnet 2 as belonging only to the independent dotted project.
            db.execute(
                """DELETE FROM gamit_subnets WHERE "Project"='geod' AND subnet=2"""
            )
            ParallelGamit.purge_solution(str(tmp_path), "geod", date, current, "TST")
            assert not (tmp_path / "geod.TST001").exists()
            assert not (tmp_path / ".geod.TST001.previous").exists()
            assert all(
                (tmp_path / name).exists()
                for name in ("geod.TST002", "geod.TST003", "geod.extra")
            )
            assert db.execute(
                'SELECT "Project" FROM gamit_subnets ORDER BY "Project"'
            ).fetchall() == [("geod.TST002",), ("geod.extra",)]
            assert not solution.exists()
            assert not gamit_session.completed_session(second, solution, row_key)


def test_targeted_subnet_replacement_preserves_previous_until_both_outputs_commit(
    tmp_path, connect, postgres_connection, monkeypatch
):
    db = postgres_connection
    for name in ("compute_jobs_v1.sql", "compute_private_v1.sql"):
        db.execute(files("geode").joinpath("sql", name).read_text())
    db.execute(
        'CREATE TABLE gamit_stats ("Project" text, "Year" int, "DOY" int, subnet int, system text, nrms float CHECK(nrms > 0), api_id serial, PRIMARY KEY ("Project","Year","DOY",subnet,system))'
    )
    db.execute(
        'CREATE TABLE gamit_subnets ("Project" text, "Year" int, "DOY" int, subnet int, stations text[], alias text[], ties text[], centroid numeric[], api_id serial, PRIMARY KEY ("Project","Year","DOY",subnet))'
    )
    db.execute("INSERT INTO gamit_stats VALUES ('geod',2024,100,1,'G',0.25)")
    db.execute(
        "INSERT INTO gamit_subnets VALUES ('geod',2024,100,1,'{net.orig}', '{}','{}','{}')"
    )
    date = Date(year=2024, doy=100)
    dest = tmp_path / "2024/100/geod.TST001"
    dest.mkdir(parents=True)
    (dest / "result").write_text("original")

    def simulate_solver(self, *args, **kwargs):
        (Path(self.solution_pwd) / "result").write_text("replacement")
        return [
            dict(
                Project="geod",
                Year=2024,
                DOY=100,
                subnet=1,
                system="G",
                nrms=nrms,
                success=True,
            )
        ]

    monkeypatch.setattr(gamit_task.GamitTask, "start", simulate_solver)
    config = SimpleNamespace(gamitopt={"solutions_dir": str(tmp_path)})
    with (
        closing(connect()) as coordinator,
        campaign.campaign_run(coordinator, "geod", [date]) as run,
    ):
        session = gamit_session.GamitSession(
            coordinator, None, "geod", "TST", 1, date, config, [], rebuild=True
        )
        assert not session.ready
        assert session.prepared_pwd != session.solution_pwd
        assert db.execute("SELECT stations FROM gamit_subnets").fetchone() == (
            ["net.orig"],
        )
        params = dict(
            solution_pwd=session.solution_pwd,
            prepared_pwd=session.prepared_pwd,
            remote_pwd=session.remote_pwd,
            DirName=session.DirName,
            NetName=session.NetName,
            date=date,
            gamitopts={"systems": ["G"]},
            orbits={},
            subnet_record=session.subnet_record,
        )
        nrms = -1
        with pytest.raises(psycopg.errors.CheckViolation):
            ParallelGamit.run_gamit_session(params, False, run)
        assert (dest / "result").read_text() == "original"
        assert db.execute("SELECT stations,api_id FROM gamit_subnets").fetchone() == (
            ["net.orig"],
            1,
        )
        assert db.execute("SELECT nrms,api_id FROM gamit_stats").fetchone() == (0.25, 1)
        nrms = 0.5
        ParallelGamit.run_gamit_session(params, False, run)
        assert (dest / "result").read_text() == "replacement"
        assert db.execute("SELECT stations,api_id FROM gamit_subnets").fetchone() == (
            [],
            1,
        )
        assert db.execute("SELECT nrms,api_id FROM gamit_stats").fetchone() == (0.5, 1)
        assert not (dest / ".geode-publish-pending").exists()
