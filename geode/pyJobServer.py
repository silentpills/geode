"""Submit GeoDE processing jobs serially or on a dedicated Celery queue."""

import json
import math
import os
import socket
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import cycle
from uuid import uuid4

from tqdm import tqdm


def check_processing_environment(
    check_gamit_tables, check_archive, check_executables, check_atx
):
    """Check the same local configuration and prerequisites the processing code will use."""
    from contextlib import closing
    from pathlib import Path
    from shutil import which
    from tempfile import TemporaryDirectory

    from geode import dbConnection, pyDate, pyOptions, pyProducts

    config = pyOptions.ReadOptions("gnss_data.cfg")
    with closing(dbConnection.Cnn("gnss_data.cfg", migrate=False)) as cnn:
        cnn.query("SELECT count(*) FROM networks")

    Path("production").mkdir(exist_ok=True)
    with TemporaryDirectory(dir="production", prefix="node_test_") as scratch:
        if check_archive:
            for directory in (config.archive_path, config.repository):
                if not Path(directory).is_dir():
                    raise FileNotFoundError(
                        f"Cannot access the processing archive or repository: {directory}"
                    )
            date = pyDate.Date(year=2010, doy=1)
            with pyProducts.GetBrdcOrbits(config.brdc_path, date, scratch):
                pass
            with pyProducts.GetSp3Orbits(
                config.sp3_path, date, config.sp3types, scratch
            ):
                pass

    files = []
    if check_executables:
        for program in (
            "crz2rnx",
            "crx2rnx",
            "rnx2crx",
            "rnx2crz",
            "gfzrnx_lx",
            "svpos",
            "tform",
            "sh_rx2apr",
            "doy",
            "sed",
            "compress",
        ):
            if which(program) is None:
                raise FileNotFoundError(
                    f"Missing processing command on the worker PATH: {program}"
                )
        files.extend(
            Path(config.options[key]) for key in ("grdtab", "otlgrid", "ppp_exe")
        )
        files.extend(
            Path(config.options["ppp_path"]) / filename
            for filename in (
                "gpsppp.stc",
                "gpsppp.svb_gps_yrly",
                "gpsppp.flt",
                "gpsppp.met",
            )
        )
    if check_atx:
        files.extend(Path(frame["atx"]) for frame in config.Frames)
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(f"Cannot access required processing file: {path}")
    if check_gamit_tables is not None and not Path("~/gg/tables").expanduser().is_dir():
        raise FileNotFoundError("Cannot access GAMIT tables in ~/gg/tables")


@dataclass
class Job:
    id: str
    result: object = None
    exception: str | None = None
    ip_addr: str | None = None
    infrastructure_error: str | None = None


@dataclass
class Worker:
    name: str
    avail_cpus: int


class JobServer:
    def __init__(
        self,
        Config,
        check_gamit_tables=None,
        check_archive=True,
        check_executables=True,
        check_atx=True,
        run_parallel=True,
        software_sync=(),
    ):
        self.run_parallel = Config.run_parallel and run_parallel
        self.checks = (check_gamit_tables, check_archive, check_executables, check_atx)
        self.jobs = {}
        self.condition = threading.Condition()
        self.executor = None
        self.collector = None
        self.failures = []
        self.open = False
        self.cancelling = False
        self.batch_id = str(uuid4())
        self.timeout = float(os.getenv("GEODE_JOB_TIMEOUT_SECONDS", "86400"))
        if self.timeout <= 0 or not math.isfinite(self.timeout):
            raise ValueError("GEODE_JOB_TIMEOUT_SECONDS must be positive")
        if self.run_parallel:
            if software_sync:
                raise ValueError(
                    "Provision GAMIT tools on the worker and remove gamit_remote_local mappings"
                )
            from geode import compute_wire
            from geode.compute import QUEUE, app

            self.wire_checks = json.dumps(
                compute_wire.encode(self.checks), allow_nan=False
            )

            inspect = app.control.inspect(timeout=2)
            queues = inspect.active_queues() or {}
            stats = inspect.stats() or {}
            self.nodes = [
                Worker(
                    name, stats.get(name, {}).get("pool", {}).get("max-concurrency", 1)
                )
                for name, subscriptions in queues.items()
                if any(q["name"] == QUEUE for q in subscriptions)
            ]
            if not self.nodes:
                raise RuntimeError(f"No Celery worker is consuming the {QUEUE} queue")
            self._verify_workers()
            self.destinations = cycle(
                node.name for node in self.nodes for _ in range(max(node.avail_cpus, 1))
            )
        else:
            self.nodes = [Worker(socket.gethostname(), 1)]
            check_processing_environment(*self.checks)

    def _verify_workers(self):
        from celery.utils.nodenames import worker_direct

        from geode import compute_receipts
        from geode.compute import preflight

        with compute_receipts.preflight_challenge() as challenge:
            deadline = time.monotonic() + 60
            handles = [
                (
                    node,
                    preflight.apply_async(
                        args=(self.batch_id, self.wire_checks, challenge),
                        queue=worker_direct(node.name),
                        expires=60,
                    ),
                )
                for node in self.nodes
            ]
            for node, handle in handles:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or handle.get(timeout=remaining) != node.name:
                    raise RuntimeError(
                        f"Worker preflight failed or timed out for {node.name}"
                    )

    def create_cluster(
        self,
        function,
        deps=(),
        callback=None,
        progress_bar=None,
        verbose=False,
        modules=(),
        on_nodes_changed=None,
        node_setup=None,
        node_cleanup=None,
        dependencies=(),
    ):
        # Existing CLI commands can run several different operations in sequence.
        self.close_cluster()
        self.function = function
        self.callback = callback
        self.progress_bar = progress_bar
        self.verbose = verbose
        self.node_cleanup = node_cleanup
        if self.run_parallel:
            from geode.compute import operation_name

            self.operation = operation_name(function)
            if node_setup or node_cleanup:
                raise ValueError(
                    "Configure worker setup/cleanup in the worker installation"
                )
        elif node_setup:
            node_setup()
        self.cancelling = False
        self.open = True
        if self.run_parallel:
            self.collector = threading.Thread(
                target=self._collect, name="geode-results", daemon=True
            )
            self.collector.start()
        if on_nodes_changed:
            on_nodes_changed(self.nodes)

    def _complete(self, job, infrastructure_error=None):
        try:
            if self.cancelling:
                return
            if infrastructure_error:
                job.infrastructure_error = str(infrastructure_error)
                with self.condition:
                    self.failures.append(infrastructure_error)
            if self.progress_bar is not None:
                self.progress_bar.update()
            if self.callback:
                self.callback(job)
            elif job.exception and not infrastructure_error:
                raise RuntimeError(f"Processing job {job.id} failed: {job.exception}")
        except Exception as exc:
            with self.condition:
                self.failures.append(exc)
        finally:
            with self.condition:
                self.jobs.pop(job.id, None)
                self.condition.notify_all()

    def _local(self, job, arguments):
        try:
            job.result = self.function(*arguments)
        except Exception:
            job.exception = traceback.format_exc()
        self._complete(job)

    def _remote(self, arguments):
        from celery.utils.nodenames import worker_direct

        from geode import compute_receipts, compute_wire
        from geode.compute import execute

        encoded = compute_wire.encode(arguments)
        job = Job(str(uuid4()))
        fingerprint = compute_wire.fingerprint(
            self.operation, encoded, self.wire_checks
        )
        label = None
        if self.operation == "com.PlotETM.process_etm_station":
            station = arguments[0]
            label = f"{station['NetworkCode']}.{station['StationCode']}"
        elif self.operation == "com.ParallelGamit.run_gamit_session":
            label = arguments[0]["date"].yyyyddd()
        compute_receipts.register(job.id, self.operation, fingerprint, label)
        tqdm.write(f" >> {self.operation} job {job.id}")
        try:
            handle = execute.apply_async(
                args=(self.operation, encoded, self.batch_id, self.wire_checks),
                task_id=job.id,
                queue=worker_direct(next(self.destinations)),
                argsrepr=f"({self.operation}, <processing data>)",
            )
        except Exception as exc:
            # Publishing can fail *after* Redis has accepted the message.
            raise RuntimeError(
                f"Publication unconfirmed for {job.id}; check its PostgreSQL receipt"
            ) from exc
        with self.condition:
            if self.cancelling or not self.open:
                self._cancel_remote(job, handle)
                raise RuntimeError(f"Processing batch closed while publishing {job.id}")
            self.jobs[job.id] = (job, handle, time.monotonic() + self.timeout)
            self.condition.notify_all()
        return job

    def _collect(self):
        from celery.exceptions import TimeoutError as CeleryTimeout
        from kombu.exceptions import OperationalError
        from redis.exceptions import ConnectionError as RedisConnectionError
        from redis.exceptions import TimeoutError as RedisTimeout

        from geode.compute import ProcessingFunctionError
        from geode.compute_wire import decode

        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.jobs or not self.open)
                if not self.open:
                    return
                items = list(self.jobs.values())
            for job, handle, deadline in items:
                if self.cancelling:
                    break
                error = None
                try:
                    if time.monotonic() >= deadline:
                        self._cancel_remote(job, handle)
                        raise TimeoutError(
                            f"Timed out waiting for {job.id}; inspect its PostgreSQL receipt before resubmitting"
                        )
                    if not handle.ready():
                        continue
                    output = handle.get(propagate=True, timeout=1)
                    job.ip_addr = output["worker"]
                    job.result = decode(output["result"])
                except ProcessingFunctionError as exc:
                    # Download conversion callbacks may recover using another source.
                    job.exception = str(exc)
                except (
                    CeleryTimeout,
                    OperationalError,
                    RedisConnectionError,
                    RedisTimeout,
                ):
                    if time.monotonic() < deadline:
                        continue
                    job.exception = traceback.format_exc()
                    error = RuntimeError(
                        f"Result unavailable for {job.id}; check its PostgreSQL receipt"
                    )
                except Exception:
                    job.exception = traceback.format_exc()
                    error = RuntimeError(
                        f"Unable to confirm successful execution of job {job.id}: {job.exception}"
                    )
                self._complete(job, error)
            with self.condition:
                if self.open and self.jobs:
                    self.condition.wait(timeout=0.25)

    def submit(self, *args):
        if self.cancelling or not self.open:
            raise RuntimeError("Processing batch is closed")
        if self.run_parallel:
            return self._remote(args)
        job = Job(str(uuid4()), ip_addr=socket.gethostname())
        if not self.callback:
            job.result = self.function(*args)
            if self.progress_bar is not None:
                self.progress_bar.update()
            return job
        self._local(job, args)
        return job

    def submit_async(self, *args):
        if self.cancelling or not self.open:
            raise RuntimeError("Processing batch is closed")
        if self.run_parallel:
            return self._remote(args)
        job = Job(str(uuid4()), ip_addr=socket.gethostname())
        with self.condition:
            if self.cancelling or not self.open:
                raise RuntimeError("Processing batch is closed")
            if self.executor is None:
                self.executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="geode-local"
                )
            self.jobs[job.id] = self.executor.submit(self._local, job, args)
        return job

    def wait(self):
        try:
            with self.condition:
                self.condition.wait_for(lambda: not self.jobs)
                if self.failures:
                    exc, *others = self.failures
                    self.failures.clear()
                    if others:
                        details = "\n".join(str(error) for error in (exc, *others))
                        raise RuntimeError(
                            f"Multiple processing jobs failed:\n{details}"
                        ) from exc
                    raise exc
        except KeyboardInterrupt:
            self._cancel_pending()
            raise

    @staticmethod
    def _cancel_remote(job, handle):
        from geode import compute_receipts

        if compute_receipts.cancel(job.id):
            handle.revoke(terminate=False)
        tqdm.write(
            f" >> Check PostgreSQL receipt {job.id} for the cancellation outcome"
        )

    def _cancel_pending(self):
        with self.condition:
            self.cancelling = True
            pending = list(self.jobs.values())
            self.jobs.clear()
            self.condition.notify_all()
        if self.run_parallel:
            for job, handle, _deadline in pending:
                # Do not terminate an in-flight archive write or GAMIT process.
                self._cancel_remote(job, handle)
        else:
            for future in pending:
                future.cancel()

    def close_cluster(self):
        if not self.open:
            return
        try:
            self.wait()
        finally:
            with self.condition:
                self.open = False
                self.condition.notify_all()
            if self.collector:
                self.collector.join()
                self.collector = None
            if self.executor:
                self.executor.shutdown()
                self.executor = None
            if self.node_cleanup:
                self.node_cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._cancel_pending()
        self.close_cluster()
