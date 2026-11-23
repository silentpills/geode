"""Downloader fallback must distinguish an unsuccessful conversion from a lost worker."""

from types import SimpleNamespace

import pytest

from com import DownloadSources as downloads


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
