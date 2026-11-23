"""Processing-job manifests, daily product replacement, and scratch publication."""

import json
import os
import subprocess
from contextlib import closing, nullcontext
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from psycopg.rows import dict_row

from com import ParallelGamit
from geode import compute_wire, dbConnection, pyJobServer
from geode.gamit import campaign, gamit_session, gamit_task, globk_task, parse_ztd
from geode.pyDate import Date


def wire_round_trip(value):
    return compute_wire.decode(json.loads(json.dumps(compute_wire.encode(value))))


def write_products(directory, date, station="TEST"):
    directory.mkdir(exist_ok=True)
    (directory / "hfixture.glx").write_bytes(b"fixture")
    (directory / f"TST{date.wwwwd()}.znd").write_text(
        f"ATM_ZEN X {station} XX 2024 4 9 0 0 0 2.000 +0.100 3.000\n"
    )
    (directory / f"TST{date.wwwwd()}.snx").write_text(
        "+SOLUTION/ESTIMATE\n"
        + "".join(
            f" {n} STA{axis} {station} A 1 24:100:43200 m 2 .100E+01 .100E+01\n"
            for n, axis in enumerate("XYZ", 1)
        )
        + "-SOLUTION/ESTIMATE\n+SOLUTION/MATRIX_ESTIMATE L COVA\n"
        " 1 1 1.0\n 2 1 0.1 1.0\n 3 1 0.2 0.3 1.0\n-SOLUTION/MATRIX_ESTIMATE L COVA\n"
    )


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
    assert "Fewer than two observing stations" in failure["fatals"][0]
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

    (tmp_path / f"TST{date.wwwwd()}.snx").touch()
    vertex = SimpleNamespace(
        X=1, Y=2, Z=3, sigX=1, sigY=2, sigZ=3, sigXY=4, sigXZ=5, sigYZ=6
    )
    monkeypatch.setattr(
        gamit_session.snxParse,
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
            f'CREATE TABLE {table} ("Project" text, "Year" int, "DOY" int, subnet int, system text)'
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
            gamit_session.completed_session(
                first, solution, row_key, ["G"], "TST", date
            )
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
            assert not gamit_session.completed_session(
                second, solution, row_key, ["G"], "TST", date
            )


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
    write_products(dest / "glbf", date)

    def simulate_solver(self, *args, **kwargs):
        (Path(self.solution_pwd) / "result").write_text("replacement")
        write_products(Path(self.solution_pwd) / "glbf", date)
        return [
            dict(
                Project="geod",
                Year=2024,
                DOY=100,
                subnet=1,
                system=system,
                nrms=nrms,
                success=(system not in failures),
            )
            for system in reported
        ]

    monkeypatch.setattr(gamit_task.GamitTask, "start", simulate_solver)
    config = SimpleNamespace(
        gamitopt={"solutions_dir": str(tmp_path), "org": "TST", "systems": ["G", "E"]}
    )
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
            gamitopts={"systems": ["G", "E"], "org": "TST"},
            orbits={},
            subnet_record=session.subnet_record,
        )
        nrms = 1
        reported = ["G", "E"]
        failures = {"E"}
        assert not all(
            r["success"] for r in ParallelGamit.run_gamit_session(params, False, run)
        )
        assert (dest / "result").read_text() == "original"
        assert db.execute("SELECT system,nrms,api_id FROM gamit_stats").fetchall() == [
            ("G", 0.25, 1)
        ]
        reported = ["G"]
        failures = set()
        with pytest.raises(ValueError, match="Incomplete constellation"):
            ParallelGamit.run_gamit_session(params, False, run)
        assert (dest / "result").read_text() == "original"
        reported = ["G", "E"]
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
        assert db.execute(
            "SELECT nrms,api_id FROM gamit_stats WHERE system='G'"
        ).fetchone() == (0.5, 1)
        assert db.execute(
            "SELECT nrms FROM gamit_stats WHERE system='E'"
        ).fetchone() == (0.5,)
        assert gamit_session.completed_session(
            coordinator, dest, session.subnet_record, ["G", "E"], "TST", date
        )
        (dest / "glbf" / f"TST{date.wwwwd()}.snx").unlink()
        assert not gamit_session.completed_session(
            coordinator, dest, session.subnet_record, ["G", "E"], "TST", date
        )
        assert not (dest / ".geode-publish-pending").exists()


@pytest.mark.parametrize(
    "unusable", ["missing", "empty", "unparseable", "foreign", "truncated"]
)
def test_incomplete_subnet_ztd_keeps_whole_prior_day(
    tmp_path, connect, postgres_connection, unusable
):
    date = Date(year=2024, doy=100)
    db = postgres_connection
    db.execute(
        """CREATE TABLE gamit_ztd ("Project" text, "Year" int, "DOY" int, "NetworkCode" text, "StationCode" text, "Date" timestamp, model float, sigma float, "ZTD" float, api_id serial, PRIMARY KEY ("Project","Year","DOY","NetworkCode","StationCode","Date"))"""
    )
    products = []
    for station in ("FIRS", "NEXT"):
        directory = tmp_path / station
        write_products(directory, date, station)
        products.append(
            dict(
                directory=str(directory),
                name=station,
                date=date,
                stations=[(station, "net", station.lower())],
            )
        )
    task = parse_ztd.ParseZtdTask("TST", "geod", products, date)
    with closing(connect()) as cnn:
        assert task.execute(cnn) == []
        query = 'SELECT "StationCode", "ZTD", api_id FROM gamit_ztd ORDER BY 1'
        previous = db.execute(query).fetchall()
        assert previous == [("firs", 3.0, 1), ("next", 3.0, 2)]
        (Path(products[0]["directory"]) / f"TST{date.wwwwd()}.znd").write_text(
            "ATM_ZEN X FIRS XX 2024 4 9 0 0 0 2.000 +0.100 6.000\n"
        )
        other = Path(products[1]["directory"]) / f"TST{date.wwwwd()}.znd"
        if unusable == "missing":
            other.unlink()
        else:
            other.write_text(
                {
                    "empty": "",
                    "unparseable": "invalid",
                    "truncated": "ATM_ZEN X NEXT  1 2024 4 9 0 0 0.1234 +-   0.0086 2.6643\nATM_ZEN X NEXT  1 2024 4 9 2 0 0.1234 +-",
                    "foreign": "ATM_ZEN X FIRS XX 2024 4 9 0 0 0 2.000 +0.100 3.000\n",
                }[unusable]
            )
        errors = task.execute(cnn)
        assert len(errors) == 1 and "NEXT" in errors[0]
        assert db.execute(query).fetchall() == previous


def test_multi_system_glx_uses_calendar_date(tmp_path, monkeypatch):
    params = dict(
        DirName="bbay",
        date=Date(year=2023, doy=289),
        orbits={},
        gamitopts={"expt": "bbay", "systems": ["G", "E"]},
    )
    task = gamit_task.GamitTask(str(tmp_path), params, str(tmp_path))
    products = tmp_path / "glbf"
    products.mkdir()
    name = "h2310161200_bbay.glx"
    results = [dict(system=s, glbf=name) for s in ("G", "E")]
    (products / "out.prt").write_text(
        f"1 ../gsoln/G/{name} 1.0 0.0 0.1 -1.0 USED\n"
        f"2 ../gsoln/E/{name} 4.0 0.0 0.2 -1.0 USED\n"
    )
    monkeypatch.setattr(task, "execute", lambda *args, **kwargs: None)
    task.combine_systems(results)
    assert f" out_glb {name}\n" in (products / "globk.cmd").read_text()
    archived = products / "h23102891200_bbay.glx"
    archived.write_bytes(b"legacy combined solution")
    assert gamit_session.subnet_glx(products) == archived


def test_globk_requires_one_glx_from_each_subnet(tmp_path):
    date = Date(year=2024, doy=100)
    destination = tmp_path / "combined"
    destination.mkdir()
    previous = destination / "previous"
    previous.write_bytes(b"preserved")
    products = []
    for name in ("subnet1", "subnet2"):
        directory = tmp_path / name
        directory.mkdir()
        products.append(dict(name=name, directory=str(directory)))
    (tmp_path / "subnet1" / "hfirst.glx").write_bytes(b"input")
    task = globk_task.Globk(
        str(destination),
        date,
        products,
        options=dict(org="TST", eop_type="usno", expt="geod"),
    )
    for contents in (None, b"", b"duplicate"):
        if contents is not None:
            (tmp_path / "subnet2" / "hsecond.glx").write_bytes(contents)
            if contents:
                (tmp_path / "subnet2" / "hother.glx").write_bytes(b"unexpected")
        with pytest.raises(ValueError, match="subnet2"):
            task.execute(store_result=lambda _: pytest.fail("Partial replacement"))
        assert previous.read_bytes() == b"preserved"


def test_globk_rejected_or_missing_input_is_not_a_complete_combination(tmp_path):
    report = tmp_path / "out.prt"
    names = ["../gsoln/G/hday.glx", "../gsoln/E/hday.glx"]
    for status in ("NOT USED", "NO DATA", "USED"):
        report.write_text(
            f" 1 {names[0]} 1.0 0.0 0.1 -1.0 USED\n 2 {names[1]} 4.0 0.0 0.2 -1.0 {status}\n"
        )
        if status == "USED":
            globk_task.verify_globk_inputs(report, names)
        else:
            with pytest.raises(globk_task.GlobkException, match=names[1]):
                globk_task.verify_globk_inputs(report, names)


def test_glbtosnx_nonzero_exit_propagates_even_if_it_writes_an_output(
    tmp_path, monkeypatch
):
    date = Date(year=2024, doy=100)
    params = dict(
        DirName="sample",
        NetName="geod",
        orbits={},
        gamitopts={"org": "TST", "systems": ["G"]},
        date=date,
    )
    task = gamit_task.GamitTask(str(tmp_path), params, str(tmp_path))
    task.success = True
    directory = tmp_path / "glbf"
    directory.mkdir()
    (directory / "hday.glx").write_bytes(b"input")
    converter = tmp_path / "glbtosnx"
    converter.write_text('#!/bin/sh\necho partial > "$4"\nexit 23\n')
    converter.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    with pytest.raises(subprocess.CalledProcessError) as error:
        task.finish()
    assert error.value.returncode == 23
    assert (directory / f"TST{date.wwwwd()}.snx").read_text() == "partial\n"


def test_campaign_coordinator_surfaces_scientific_job_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pyJobServer, "check_processing_environment", lambda *_: None)
    result = [
        {
            "success": False,
            "session": "geod.001",
            "system": "E",
            "nrms": 0,
            "wl": 0,
            "fatals": ["fixture failure"],
        }
    ]
    with pyJobServer.JobServer(SimpleNamespace(run_parallel=False)) as server:
        server.create_cluster(lambda: result, callback=ParallelGamit.gamit_callback)
        server.submit()
        with pytest.raises(RuntimeError, match="GAMIT failed for geod.001"):
            server.wait()
        assert "fixture failure" in (tmp_path / "FATAL.log").read_text()

        server.create_cluster(
            lambda: ["missing subnet"], callback=ParallelGamit.job_callback
        )
        server.submit()
        with pytest.raises(RuntimeError, match="missing subnet"):
            server.wait()
