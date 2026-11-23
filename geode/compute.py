"""Celery application for trusted GeoDE scientific workers using the processing environment."""

import json
import os
import socket
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from urllib.parse import quote

from celery import Celery
from celery.exceptions import Ignore

from geode import compute_wire
from geode import config as _config  # noqa: F401 - load the operator's .env

QUEUE = "geode.compute"
OPERATIONS = {
    "com.ArchiveService.process_crinex_file",
    "com.ArchiveService.process_visit_file",
    "com.ArchiveService.merge_rinex_files",
    "com.DRA.compute_dra",
    "com.DownloadSources.process_file",
    "com.GenerateKml.description_content",
    "com.IntegrityCheck.check_rinex_stn",
    "com.IntegrityCheck.compare_stninfo_rinex",
    "com.ParallelGamit.purge_solution",
    "com.ParallelGamit.run_gamit_session",
    "com.ParallelGamit.run_globk",
    "com.ParallelGamit.run_parse_ztd",
    "com.PlotETM.process_etm_station",
    "com.ScanArchive.try_insert",
    "com.ScanArchive.obtain_otl",
    "com.ScanArchive.insert_stninfo",
    "com.ScanArchive.execute_ppp",
    "com.Stacker.station_etm",
}


def operation_name(function):
    module = function.__module__
    if module == "__main__":
        # Support both python -m com.Tool and python com/Tool.py.
        module = "com." + Path(function.__code__.co_filename).stem
    name = f"{module}.{function.__name__}"
    if name not in OPERATIONS:
        raise ValueError(f"Unregistered GeoDE processing operation: {name}")
    return name


def broker_url():
    if os.environ.get("GEODE_BROKER_URL"):
        return os.environ["GEODE_BROKER_URL"]
    password = quote(os.getenv("GEODE_REDIS_PASSWORD", ""), safe="")
    auth = f":{password}@" if password else ""
    port = int(os.getenv("GEODE_REDIS_PORT", "6380"))
    return f"redis://{auth}127.0.0.1:{port}/2"


app = Celery(
    "geode.compute",
    broker=broker_url(),
    backend=os.getenv("GEODE_RESULT_BACKEND") or broker_url(),
)
app.conf.update(
    accept_content=["json"],
    result_accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_default_queue=QUEUE,
    redis_socket_connect_timeout=5,
    redis_socket_timeout=5,
    # Handle a lost worker as an interrupted scientific attempt. Some operations
    # append measurements or replace files and cannot be automatically replayed.
    task_acks_late=False,
    task_publish_retry=False,
    task_track_started=False,
    worker_direct=True,
    worker_prefetch_multiplier=1,
    result_expires=7 * 86400,
)


@lru_cache(maxsize=32)
def _check_environment(batch_id, settings):
    from geode.pyJobServer import check_processing_environment

    check_processing_environment(*compute_wire.decode(json.loads(settings)))


@app.task(bind=True, name="geode.compute.preflight.v1", max_retries=0)
def preflight(self, batch_id, settings, challenge):
    from geode import compute_receipts

    if not compute_receipts.verify_preflight(challenge):
        raise RuntimeError(
            "Worker uses a different processing database from the submitting CLI"
        )
    _check_environment(batch_id, settings)
    return self.request.hostname


def reported_failure(operation, args, result):
    """Interpret the commands' explicit error returns while preserving their callback payload."""
    if operation in {
        "com.PlotETM.process_etm_station",
        "com.ArchiveService.process_crinex_file",
        "com.ArchiveService.process_visit_file",
        "com.ArchiveService.merge_rinex_files",
        "com.IntegrityCheck.check_rinex_stn",
        "com.IntegrityCheck.compare_stninfo_rinex",
    }:
        return bool(result[0])
    if operation in {
        "com.ParallelGamit.run_globk",
        "com.ParallelGamit.run_parse_ztd",
        "com.ScanArchive.try_insert",
        "com.ScanArchive.obtain_otl",
        "com.ScanArchive.insert_stninfo",
        "com.ScanArchive.execute_ppp",
    }:
        return bool(result)
    if operation == "com.ParallelGamit.run_gamit_session":
        _, dry_run, _run_id = args
        return (not result and not dry_run) or any(
            not system["success"] for system in result
        )
    return False


@app.task(bind=True, name="geode.compute.execute.v1", max_retries=0)
def execute(self, operation, arguments, batch_id, checks):
    from geode import compute_receipts

    if operation not in OPERATIONS:
        raise Ignore()
    job_id = self.request.id
    # An unregistered, corrupted or duplicate message must never overwrite
    # the authentic attempt's result in the Celery backend.
    try:
        digest = compute_wire.fingerprint(operation, arguments, checks)
    except (TypeError, ValueError):
        raise Ignore() from None
    if not compute_receipts.claim(job_id, operation, digest):
        raise Ignore()
    try:
        args = compute_wire.decode(arguments)
        if not isinstance(args, tuple):
            raise ValueError("Expected positional processing arguments")
        _check_environment(batch_id, checks)
        module_name, function_name = operation.rsplit(".", 1)
        function = getattr(import_module(module_name), function_name)
        result = function(*args)
        failed = reported_failure(operation, args, result)
        output = {"result": compute_wire.encode(result), "worker": socket.gethostname()}
    except Exception as exc:
        compute_receipts.finish(job_id, "failed", type(exc).__name__)
        raise
    if failed:
        compute_receipts.finish(
            job_id, "failed", "Processing function returned an error"
        )
    else:
        compute_receipts.finish(job_id, "succeeded")
    return output
