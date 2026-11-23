"""Downloader fallback must distinguish an unsuccessful conversion from a lost worker."""

from queue import Full, Queue
from threading import current_thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from com import DownloadSources as downloads
from geode import compute, compute_receipts, pyJobServer


@pytest.mark.parametrize("infrastructure_error", [None, "Check receipt 1234"])
def test_alternate_source_only_after_confirmed_conversion_failure(
    tmp_path, monkeypatch, infrastructure_error
):
    attempts = []
    sources = [
        downloads.Source(i, "HTTP", "example.org", None, None, "/data.rnx", None)
        for i in (1, 2)
    ]
    monkeypatch.setattr(downloads, "db_get_sources_for_station", lambda *args: sources)

    class Client:
        def __init__(self, on_result, on_stop, server_id, *args):
            self.on_result = on_result
            self.server_id = server_id

        def set_next_download(self, *args):
            attempts.append(self.server_id)
            self.on_result(self.server_id, None, elapsed_time=1, size=3)

        def start_thread(self):
            pass

        def finish(self):
            pass

    monkeypatch.setattr(downloads, "Client", Client)
    manager = downloads.JobsManager(SimpleNamespace(run_parallel=False), ".")

    def inject_failure(cnn, dates, stations, put_message):
        manager.jobs_submitted["1234"] = downloads.FileDescriptor(0, 0, dates[0])
        manager.on_job_result(
            SimpleNamespace(
                id="1234",
                exception="conversion failed",
                infrastructure_error=infrastructure_error,
            )
        )

    monkeypatch.setattr(downloads, "thread_queue_all_files", inject_failure)
    station = dict(NetworkCode="net", StationCode="abcd", marker=0, country_code="USA")
    args = (None, manager, str(tmp_path), [station], [60000])
    if infrastructure_error:
        with pytest.raises(RuntimeError, match="receipt 1234"):
            downloads.download_all_stations_data(*args)
        assert manager.halted
        assert not attempts
    else:
        downloads.download_all_stations_data(*args)
        assert attempts == [2]


@pytest.fixture
def bounded_inbox(monkeypatch):
    # A missing completion message should fail the test instead of hanging pytest.
    class TimedQueue(Queue):
        def get(self, *args, **kwargs):
            return super().get(timeout=2)

    monkeypatch.setattr(
        downloads, "queue", SimpleNamespace(Queue=TimedQueue, Full=Full)
    )


@pytest.mark.parametrize(
    "failure",
    ["Publication unconfirmed for test-id", "Could not register receipt test-id"],
)
def test_pending_submission_error_reaches_download_coordinator(
    tmp_path, monkeypatch, bounded_inbox, failure
):
    coordinator = current_thread()
    register_failed = failure.startswith("Could not register")

    def register(*args):
        assert current_thread() is coordinator
        if register_failed:
            raise ConnectionError("fixture database unavailable")

    publish = Mock(side_effect=ConnectionError("fixture broker unavailable"))
    monkeypatch.setattr(compute_receipts, "register", register)
    monkeypatch.setattr(compute.execute, "apply_async", publish)
    monkeypatch.setattr(pyJobServer, "uuid4", lambda: "test-id")
    server = pyJobServer.JobServer.__new__(pyJobServer.JobServer)
    server.run_parallel = server.open = True
    server.cancelling = False
    server.wire_checks = "[]"
    server.batch_id = "test-batch"
    server.operation = "com.DownloadSources.process_file"
    server.destinations = iter(["fixture-worker"])
    manager = downloads.JobsManager(server, ".")
    manager.on_nodes_changed([pyJobServer.Worker("fixture-worker", 1)])
    source = downloads.Source(
        1, "HTTPS", "example.org", None, None, "/daily.rnx", "convert"
    )
    monkeypatch.setattr(downloads, "db_get_sources_for_station", lambda *args: [source])

    def finish_first_job(cnn, dates, stations, put_message):
        manager.files_pending.push(downloads.FileDescriptor(0, 0, dates[1]))
        manager.jobs_submitted["first"] = downloads.FileDescriptor(0, 0, dates[0])
        manager.on_job_result(
            SimpleNamespace(id="first", infrastructure_error=None, exception=None)
        )

    monkeypatch.setattr(downloads, "thread_queue_all_files", finish_first_job)
    station = dict(NetworkCode="net", StationCode="abcd", marker=0, country_code="USA")
    with pytest.raises(RuntimeError, match=rf"net\.abcd.*daily\.rnx.*{failure}"):
        downloads.download_all_stations_data(
            None, manager, str(tmp_path), [station], [60000, 60001]
        )
    assert manager.halted
    assert publish.call_count == int(not register_failed)


def test_file_query_failure_reaches_coordinator(tmp_path, monkeypatch, bounded_inbox):
    def fail_query(*args):
        raise ConnectionError("processing database unavailable")

    source = downloads.Source(1, "HTTPS", "example.org", None, None, "/data", None)
    monkeypatch.setattr(downloads, "db_get_sources_for_station", lambda *args: [source])
    monkeypatch.setattr(downloads, "thread_queue_all_files", fail_query)
    manager = downloads.JobsManager(SimpleNamespace(run_parallel=False), ".")
    station = dict(NetworkCode="net", StationCode="abcd", marker=0, country_code="USA")
    with pytest.raises(RuntimeError, match="query the remaining downloads") as failure:
        downloads.download_all_stations_data(
            None, manager, str(tmp_path), [station], [60000]
        )
    assert isinstance(failure.value.__cause__, ConnectionError)
