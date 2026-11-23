from concurrent.futures import ThreadPoolExecutor
from importlib.resources import files
from uuid import uuid4

import pytest

from geode import compute_receipts as receipts


def test_duplicate_deliveries_share_exactly_one_claim(postgres_connection, monkeypatch):
    db = postgres_connection
    db.execute(files("geode").joinpath("sql/compute_jobs_v1.sql").read_text())
    db.execute("CREATE ROLE runtime_test")
    db.execute("GRANT ALL ON public.geode_compute_jobs TO runtime_test")
    db.execute(files("geode").joinpath("sql/compute_private_v1.sql").read_text())
    assert db.execute(
        "SELECT has_schema_privilege('runtime_test', 'geode_compute', 'USAGE'), "
        "has_table_privilege('runtime_test', 'geode_compute.jobs', 'UPDATE')"
    ).fetchone() == (False, False)
    # A CLI-first installation can subsequently run the full Django chain.
    for name in ("compute_jobs_v1.sql", "compute_private_v1.sql"):
        db.execute(files("geode").joinpath("sql", name).read_text())
    assert db.execute("SELECT to_regclass('public.geode_compute_jobs')").fetchone() == (
        None,
    )
    for key, value in (
        ("HOST", db.info.host),
        ("PORT", str(db.info.port)),
        ("USER", db.info.user),
        ("DB", db.info.dbname),
    ):
        monkeypatch.setenv("POSTGRES_" + key, value)
    with receipts.preflight_challenge() as key:
        assert receipts.verify_preflight(key)
    assert not receipts.verify_preflight(key)
    fingerprint = "a" * 64
    job_id = uuid4()
    receipts.register(job_id, "plot_station", fingerprint)
    assert not receipts.claim(job_id, "other_task", fingerprint)
    assert not receipts.claim(job_id, "plot_station", "b" * 64)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: receipts.claim(job_id, "plot_station", fingerprint), range(4)
            )
        )
    assert sorted(results) == [False, False, False, True]
    assert receipts.status(job_id)["state"] == "running"
    assert not receipts.cancel(job_id)
    receipts.finish(job_id, "succeeded")
    assert not receipts.claim(job_id, "plot_station", fingerprint)
    with pytest.raises(ValueError, match="no running claim"):
        receipts.finish(job_id, "failed")
    assert receipts.status(job_id)["state"] == "succeeded"

    cancelled = uuid4()
    receipts.register(cancelled, "plot_station", fingerprint)
    assert receipts.cancel(cancelled)
    assert not receipts.claim(cancelled, "plot_station", fingerprint)
    assert receipts.status(cancelled)["state"] == "cancelled"
