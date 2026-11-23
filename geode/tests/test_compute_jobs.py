"""Processing transport contracts, including an opt-in real broker qualification."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from celery.exceptions import Ignore

from geode import compute, compute_receipts, compute_wire, pyJobServer
from geode.etm.core.type_declarations import SolutionType
from geode.pyDate import Date

ROOT = Path(__file__).resolve().parents[2]


def test_processing_wire_roundtrip():
    array = np.array([("abcd", 1.5)], dtype=[("station", "U4"), ("value", ">f8")])
    payload = {
        3: (
            array,
            b"binary",
            Decimal("2.30"),
            datetime(2020, 1, 5),
            Date(year=2020, doy=3, hour=3),
            SolutionType.PPP,
        ),
        "map": np.nan,
    }
    encoded = json.dumps(compute_wire.encode(payload), allow_nan=False)
    result = compute_wire.decode(json.loads(encoded))
    values = result[3]
    np.testing.assert_array_equal(values[0], array)
    assert values[0].dtype == array.dtype
    assert values[1:4] == payload[3][1:4]
    assert values[4].to_json() == payload[3][4].to_json()
    assert values[5] is SolutionType.PPP
    assert np.isnan(result["map"])
    precise_date = Date(fyear=2020.123456789)
    assert (
        compute_wire.decode(compute_wire.encode(precise_date)).fyear
        == precise_date.fyear
    )
    scalar = np.longdouble("1.234567890123456789")
    restored_scalar = compute_wire.decode(compute_wire.encode(scalar))
    assert type(restored_scalar) is type(scalar) and restored_scalar == scalar
    with pytest.raises(ValueError):
        compute_wire.encode(np.array([object()], dtype=object))
    with pytest.raises(TypeError):
        compute_wire.encode(object())
    with pytest.raises(ValueError):
        compute_wire.decode({"function": "arbitrary"})


def test_serial_callback_and_wait(monkeypatch):
    monkeypatch.setattr(pyJobServer, "check_processing_environment", lambda *_: None)
    completed = []
    with pyJobServer.JobServer(SimpleNamespace(run_parallel=False)) as server:
        server.create_cluster(lambda n: 1 / n, callback=completed.append)
        server.submit(2)
        assert completed[0].result == 0.5
        job = server.submit_async(0)
        server.wait()
        assert completed[1].id == job.id
        assert "ZeroDivisionError" in completed[1].exception


def test_missing_worker_fails_before_submission(monkeypatch):
    inspect = SimpleNamespace(
        active_queues=lambda: {"web": [{"name": "celery"}]}, stats=lambda: {}
    )
    monkeypatch.setattr(compute.app.control, "inspect", lambda **_: inspect)
    with pytest.raises(RuntimeError, match="No Celery worker"):
        pyJobServer.JobServer(SimpleNamespace(run_parallel=True))
    with pytest.raises(ValueError, match="Unregistered"):
        compute.operation_name(os.system)


def test_gamit_execution_distinguishes_dry_runs_from_empty_solutions():
    operation = "com.ParallelGamit.run_gamit_session"
    assert compute.reported_failure(operation, ({}, False, "run"), [])
    assert not compute.reported_failure(operation, ({}, True, "run"), [])
    assert compute.reported_failure(operation, ({}, False, "run"), [{"success": False}])


def test_duplicate_delivery_never_executes(monkeypatch):
    outcomes = iter([True, False])
    monkeypatch.setattr(compute_receipts, "claim", lambda *_: next(outcomes))
    monkeypatch.setattr(compute, "_check_environment", lambda *_: None)
    finishes = []
    monkeypatch.setattr(
        compute_receipts, "finish", lambda *values: finishes.append(values)
    )
    from com import PlotETM

    called = []

    def run(*args):
        called.append(args)
        return "fixture-reported issue", None, "tst.abcd"

    monkeypatch.setattr(PlotETM, "process_etm_station", run)
    message = (
        "com.PlotETM.process_etm_station",
        compute_wire.encode(()),
        "batch",
        "[]",
    )
    compute.execute.run(*message)
    with pytest.raises(Ignore):
        compute.execute.run(*message)
    assert called == [()]
    assert finishes == [(None, "failed", "Processing function returned an error")]


@pytest.mark.skipif(
    not os.getenv("GEODE_TEST_REDIS_URL"),
    reason="Set GEODE_TEST_REDIS_URL to a disposable Redis database",
)
def test_plot_etm_serial_and_celery(postgres_connection, tmp_path, monkeypatch):
    """Run the same CLI on 180 days of observations and compare its model XYZ."""
    cnn = postgres_connection
    env = {
        **os.environ,
        "GEODE_BROKER_URL": os.environ["GEODE_TEST_REDIS_URL"],
        "GEODE_RESULT_BACKEND": os.environ["GEODE_TEST_REDIS_URL"],
        "POSTGRES_HOST": cnn.info.host,
        "POSTGRES_PORT": str(cnn.info.port),
        "POSTGRES_USER": cnn.info.user,
        "POSTGRES_DB": cnn.info.dbname,
        "POSTGRES_PASSWORD": "",
        "DJANGO_SECRET_KEY": "scientific-integration-fixture-only",
        "OPENBLAS_NUM_THREADS": "1",
        "MPLBACKEND": "Agg",
    }
    for key in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_DB",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.setenv(key, env[key])
    python = Path(sys.executable)
    subprocess.run(
        [str(python), str(ROOT / "web/backend/manage.py"), "migrate", "--noinput"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        timeout=90,
    )
    cnn.execute("""INSERT INTO networks ("NetworkCode") VALUES ('tst')""")
    cnn.execute("""INSERT INTO stations ("NetworkCode","StationCode","StationName","DateStart","DateEnd",auto_x,auto_y,auto_z,lat,lon,height,max_dist)
                   VALUES ('tst','abcd','Fixture',2020,2021,6378137,0,0,0,0,0,50)""")
    cnn.execute("""INSERT INTO ppp_soln ("NetworkCode","StationCode","Year","DOY","ReferenceFrame","X","Y","Z",hash)
                   SELECT 'tst','abcd',2020,d,'IGS20',6378137+0.001*sin(d),0.03*d/365+0.001*cos(d),0.002*sin(d*2),d
                   FROM generate_series(1,180) d""")
    shutil.copyfile(ROOT / "gnss_data.cfg.example", tmp_path / "gnss_data.cfg")
    command = [
        str(python),
        "-m",
        "com.PlotETM",
        "tst.abcd",
        "-no_save",
        "-plot",
        "no-plots",
        "-verbosity",
        "quiet",
        "-q",
        "model",
        "2020_090",
    ]

    def run(*args):
        proc = subprocess.run(
            command + list(args),
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        matches = [
            line
            for line in proc.stdout.splitlines()
            if " -> " in line and "tst.abcd" in line
        ]
        assert len(matches) == 1 and "NaN" not in matches[0], proc.stdout + proc.stderr
        return matches[0], proc.stdout

    local, _ = run()
    with (tmp_path / "worker.log").open("w") as log:
        worker = subprocess.Popen(
            [
                str(python),
                "-m",
                "celery",
                "-A",
                "geode.compute:app",
                "worker",
                "-Q",
                compute.QUEUE,
                "--pool=prefork",
                "--concurrency=1",
                "--hostname=geode-fixture@%h",
                "--without-mingle",
                "--without-gossip",
                "-l",
                "info",
            ],
            cwd=tmp_path,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                if " ready." in (tmp_path / "worker.log").read_text():
                    break
                assert worker.poll() is None, (tmp_path / "worker.log").read_text()
                time.sleep(0.1)
            parallel, output = run("--parallel")
            assert local == parallel
            job_id = re.search(
                r"process_etm_station job ([0-9a-f-]{36})", output
            ).group(1)
            assert cnn.execute(
                "SELECT state FROM geode_compute.jobs WHERE id=%s", (job_id,)
            ).fetchone() == ("succeeded",)
            check_interrupted_worker(cnn, worker, env)
        finally:
            worker.terminate()
            worker.wait(timeout=20)


def check_interrupted_worker(cnn, worker, env):
    """Stop the identified child after claim and prove queued duplicates are harmless."""
    from uuid import uuid4

    from celery import Celery
    from psutil import Process

    producer = Celery(
        "qualification",
        broker=env["GEODE_BROKER_URL"],
        backend=env["GEODE_RESULT_BACKEND"],
    )
    operation = "com.IntegrityCheck.check_rinex_stn"
    arguments = compute_wire.encode(
        ("tst", "abcd", Date(year=2020, doy=1), Date(year=2020, doy=2))
    )
    checks = json.dumps(compute_wire.encode((None, False, False, False)))
    digest = compute_wire.fingerprint(operation, arguments, checks)

    def register():
        job_id = str(uuid4())
        compute_receipts.register(job_id, operation, digest)
        return job_id

    def publish(job_id, encoded=arguments):
        return producer.send_task(
            "geode.compute.execute.v1",
            (operation, encoded, str(uuid4()), checks),
            task_id=job_id,
            queue=compute.QUEUE,
        )

    def receipt(job_id):
        return cnn.execute(
            "SELECT state, started_at, finished_at FROM geode_compute.jobs WHERE id=%s",
            (job_id,),
        ).fetchone()

    # Wait until the claim is visible while the child is still inside its
    # environment check, blocked on a disposable database table.
    job_id = register()
    with cnn.transaction():
        cnn.execute("LOCK TABLE networks IN ACCESS EXCLUSIVE MODE")
        publish(job_id)
        for _ in range(100):
            if receipt(job_id)[0] == "running":
                break
            time.sleep(0.1)
        before = receipt(job_id)
        assert before[0] == "running"
        children = Process(worker.pid).children()
        assert len(children) == 1
        publish(job_id)
        children[0].kill()

    # Replay the original after the child was lost. A different valid job acts
    # as a FIFO barrier showing that the replacement child actually consumed work.
    publish(job_id)
    other = register()
    publish(other).get(timeout=30)
    assert receipt(other)[0] == "succeeded"
    assert receipt(job_id) == before

    # Redelivery after success and a mismatched payload for a queued UUID.
    before_other = receipt(other)
    publish(other)
    tampered = register()
    publish(tampered, compute_wire.encode(("tst", "other", None, None)))
    cancelled = register()
    assert compute_receipts.cancel(cancelled)
    publish(cancelled)
    last = register()
    publish(last).get(timeout=30)
    assert receipt(other) == before_other
    assert receipt(tampered) == ("queued", None, None)
    assert receipt(cancelled)[0] == "cancelled"
    producer.close()


def test_qualified_workers_get_individual_preflights(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock

    queues = {host: [{"name": compute.QUEUE}] for host in ("good", "wrong")}
    monkeypatch.setattr(
        compute.app.control,
        "inspect",
        lambda **_: SimpleNamespace(active_queues=lambda: queues, stats=lambda: {}),
    )
    monkeypatch.setattr(
        compute_receipts, "preflight_challenge", lambda: nullcontext(17)
    )
    probes = []

    def send(args, queue, expires):
        assert args[-1] == 17 and expires == 60
        probes.append(queue.routing_key)
        return Mock(get=Mock(return_value="good"))

    monkeypatch.setattr(compute.preflight, "apply_async", send)
    with pytest.raises(RuntimeError, match="preflight.*wrong"):
        pyJobServer.JobServer(SimpleNamespace(run_parallel=True))
    assert probes == ["good", "wrong"]


def test_result_backend_recovers_before_callback(monkeypatch):
    from unittest.mock import Mock

    from redis.exceptions import ConnectionError

    # Keep this test independent of the broker by supplying the Celery result
    # handle directly. The collector should continue polling the same handle.
    monkeypatch.setattr(pyJobServer, "check_processing_environment", lambda *_: None)
    completed = []
    with pyJobServer.JobServer(SimpleNamespace(run_parallel=False)) as server:
        from com.PlotETM import process_etm_station

        server.run_parallel = True
        server.create_cluster(process_etm_station, callback=completed.append)
        job = pyJobServer.Job("fixture")
        handle = Mock()
        handle.ready.side_effect = [ConnectionError("reconnecting"), True]
        handle.get.return_value = {"worker": "fixture", "result": 3}
        with server.condition:
            server.jobs[job.id] = (job, handle, time.monotonic() + 5)
            server.condition.notify_all()
        server.wait()
        assert completed == [job]
        assert job.result == 3 and job.exception is None
        assert handle.ready.call_count == 2


def test_cancelling_serial_batch_skips_pending_call(monkeypatch):
    import threading

    monkeypatch.setattr(pyJobServer, "check_processing_environment", lambda *_: None)
    started = threading.Event()
    release = threading.Event()
    ran = []

    def run(index):
        ran.append(index)
        started.set()
        release.wait(timeout=2)

    with pyJobServer.JobServer(SimpleNamespace(run_parallel=False)) as server:
        server.create_cluster(run)
        server.submit_async(1)
        assert started.wait(timeout=2)
        server.submit_async(2)
        server._cancel_pending()
        with pytest.raises(RuntimeError, match="closed"):
            server.submit_async(3)
        release.set()
    assert ran == [1]
