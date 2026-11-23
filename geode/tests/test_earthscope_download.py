"""Exercise both EarthScope download clients without contacting the archive."""

from contextlib import nullcontext
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import earthscope_sdk
import pytest
from earthscope_sdk.auth.error import NoTokensError
from requests import Request, Response
from requests.adapters import BaseAdapter

from com import DownloadSources
from geode import proto_download


@pytest.mark.parametrize("client", [DownloadSources, proto_download])
def test_earthscope_download_refreshes_token_and_restricts_redirects(
    tmp_path, monkeypatch, client
):
    refresh = Mock()
    fixture_token = "test"
    sdk = SimpleNamespace(
        ctx=SimpleNamespace(
            auth_flow=SimpleNamespace(
                refresh_if_necessary=refresh, access_token=fixture_token
            )
        )
    )
    monkeypatch.setattr(earthscope_sdk, "EarthScopeClient", lambda: nullcontext(sdk))
    seen = []

    class Archive(BaseAdapter):
        def send(self, request, **kwargs):
            host = urlsplit(request.url).hostname
            seen.append((host, request.headers.get("Authorization")))
            response = Response()
            response.request = request
            response.url = request.url
            response.status_code = 200
            response.raw = BytesIO(b"observations")
            targets = {
                "gage-data.earthscope.org": "data.earthscope.org",
                "data.earthscope.org": "storage.example",
            }
            if host in targets:
                response.status_code = 302
                response.headers["Location"] = f"https://{targets[host]}/data"
            return response

        def close(self):
            pass

    downloader = client.ProtocolHTTPS("gage-data.earthscope.org", 443, None, None)
    downloader.session.mount("https://", Archive())
    output = tmp_path / "download"
    try:
        assert downloader.download("/data", output) is None
    finally:
        downloader.disconnect()
    assert output.read_bytes() == b"observations"
    assert seen == [
        ("gage-data.earthscope.org", "Bearer test"),
        ("data.earthscope.org", "Bearer test"),
        ("storage.example", None),
    ]
    refresh.assert_called_once_with()


def test_earthscope_login_failure_stops_before_request(monkeypatch):
    sdk = Mock()
    sdk.ctx.auth_flow.refresh_if_necessary.side_effect = NoTokensError()
    monkeypatch.setattr(earthscope_sdk, "EarthScopeClient", lambda: nullcontext(sdk))
    with proto_download.archive_http_session(
        "data.earthscope.org", None, None
    ) as session:
        with pytest.raises(RuntimeError, match="es login"):
            session.prepare_request(Request("GET", "https://data.earthscope.org/data"))
        with pytest.raises(ValueError, match="HTTPS"):
            session.prepare_request(Request("GET", "http://data.earthscope.org/data"))
