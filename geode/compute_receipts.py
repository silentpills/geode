"""Durable state for scientific jobs that may have filesystem side effects."""

import argparse
import configparser
import secrets
from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from geode.config import get_db_config, get_gnss_data_cfg_path


def _connect():
    legacy = configparser.ConfigParser(interpolation=None)
    legacy.read(get_gnss_data_cfg_path())
    db = get_db_config(legacy["postgres"] if legacy.has_section("postgres") else None)
    return psycopg.connect(
        host=db["hostname"],
        port=db["port"],
        dbname=db["database"],
        user=db["username"],
        password=db["password"],
        connect_timeout=10,
        row_factory=dict_row,
    )


@contextmanager
def preflight_challenge():
    """Hold a random transaction lock while the chosen workers verify this database."""
    key = secrets.randbits(63)
    with _connect() as cnn:
        cnn.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        yield key


def verify_preflight(key):
    with _connect() as cnn:
        row = cnn.execute(
            "SELECT NOT pg_try_advisory_xact_lock(%s) AS same_database", (key,)
        ).fetchone()
        return row["same_database"]


def register(job_id, operation, fingerprint, label=None):
    """Record a new UUID before publishing its message."""
    with _connect() as cnn:
        cnn.execute(
            "INSERT INTO public.geode_compute_jobs (id, operation, fingerprint, label) "
            "VALUES (%s, %s, %s, %s)",
            (job_id, operation, fingerprint, label),
        )


def claim(job_id, operation, fingerprint):
    """Only the first delivery of a registered operation can run it."""
    with _connect() as cnn:
        return (
            cnn.execute(
                "UPDATE public.geode_compute_jobs SET state='running', started_at=now() "
                "WHERE id=%s AND operation=%s AND fingerprint=%s AND state='queued'",
                (job_id, operation, fingerprint),
            ).rowcount
            == 1
        )


def cancel(job_id):
    """Revoke a queued job without interrupting a claimed filesystem write."""
    with _connect() as cnn:
        return (
            cnn.execute(
                "UPDATE public.geode_compute_jobs SET state='cancelled', finished_at=now() "
                "WHERE id=%s AND state='queued'",
                (job_id,),
            ).rowcount
            == 1
        )


def finish(job_id, state, detail=None):
    if state not in ("succeeded", "failed"):
        raise ValueError("Expected a terminal execution state")
    with _connect() as cnn:
        changed = cnn.execute(
            "UPDATE public.geode_compute_jobs SET state=%s, finished_at=now(), detail=%s "
            "WHERE id=%s AND state='running'",
            (state, detail, job_id),
        ).rowcount
        if changed != 1:
            raise ValueError(f"Job {job_id} has no running claim")


def status(job_id):
    with _connect() as cnn:
        return cnn.execute(
            "SELECT * FROM public.geode_compute_jobs WHERE id=%s", (job_id,)
        ).fetchone()


def main():
    parser = argparse.ArgumentParser(
        description="Inspect durable scientific job receipts."
    )
    parser.add_argument(
        "job_id", type=UUID, nargs="?", help="omit to see the latest 25 jobs"
    )
    args = parser.parse_args()
    if args.job_id:
        record = status(args.job_id)
        if record is None:
            parser.exit(1, f"No job with ID {args.job_id}\n")
        for field, value in record.items():
            if value is not None:
                print(f"{field}: {value}")
    else:
        with _connect() as cnn:
            for row in cnn.execute(
                "SELECT id, operation, label, state, submitted_at FROM public.geode_compute_jobs "
                "ORDER BY submitted_at DESC LIMIT 25"
            ):
                print(
                    row["id"],
                    row["state"],
                    row["operation"],
                    row["label"] or "",
                    row["submitted_at"],
                )


if __name__ == "__main__":
    main()
