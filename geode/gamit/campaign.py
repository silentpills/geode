"""Coordinate ParallelGamit invocations and fence queued work from a previous run."""

from contextlib import contextmanager
from uuid import uuid4

from geode import dbConnection


def _key(kind, project, year, doy):
    return f"geode.gamit.{kind}:{project.lower()}:{year}:{doy}"


@contextmanager
def campaign_run(cnn, project, dates):
    """Reserve every requested project/day before preparing files or dispatching jobs."""
    coordinator_keys = []
    run_id = str(uuid4())
    try:
        with cnn.cnn.transaction():
            for year, doy in sorted({(d.year, d.doy) for d in dates}):
                name = f"{project.lower()}:{year}:{doy}"
                coordinator = _key("coordinator", project, year, doy)
                row = cnn.cnn.execute(
                    "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS ok",
                    (coordinator,),
                ).fetchone()
                if not row["ok"]:
                    raise RuntimeError(f"Another campaign coordinates {name}")
                coordinator_keys.append(coordinator)
                row = cnn.cnn.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS ok",
                    (_key("worker", project, year, doy),),
                ).fetchone()
                if not row["ok"]:
                    raise RuntimeError(
                        f"A worker is still processing {name}; wait for it to finish"
                    )
                cnn.cnn.execute(
                    "INSERT INTO geode_compute.gamit_runs (project,year,doy,run_id) "
                    "VALUES (%s,%s,%s,%s) ON CONFLICT (project,year,doy) "
                    "DO UPDATE SET run_id=excluded.run_id",
                    (project.lower(), year, doy, run_id),
                )
        yield run_id
    finally:
        for key in reversed(coordinator_keys):
            cnn.cnn.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (key,)
            )


@contextmanager
def active_day(project, date, run_id):
    """Hold a shared lock while writing and reject messages from superseded campaigns."""
    cnn = dbConnection.Cnn("gnss_data.cfg", migrate=False)
    key = _key("worker", project, date.year, date.doy)
    try:
        cnn.cnn.execute(
            "SELECT pg_advisory_lock_shared(hashtextextended(%s, 0))",
            (key,),
        )

        def check_current():
            record = cnn.cnn.execute(
                "SELECT run_id FROM geode_compute.gamit_runs "
                "WHERE project=%s AND year=%s AND doy=%s",
                (project.lower(), date.year, date.doy),
            ).fetchone()
            if record is None or str(record["run_id"]) != run_id:
                raise RuntimeError(
                    f"Superseded campaign for {project} {date.yyyyddd()}"
                )

        check_current()
        yield cnn, check_current
    finally:
        try:
            if not cnn.cnn.closed:
                cnn.cnn.execute(
                    "SELECT pg_advisory_unlock_shared(hashtextextended(%s,0))", (key,)
                )
        finally:
            cnn.close()
