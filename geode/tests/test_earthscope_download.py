"""Exercise both EarthScope download clients without contacting the archive."""

import base64
import json
import time
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
from requests.auth import HTTPBasicAuth

from com import DownloadSources
from geode import proto_download


def test_installed_sdk_reads_an_isolated_login(tmp_path, monkeypatch):
    from earthscope_sdk.config import settings

    monkeypatch.setattr(settings, "_LOCAL_APP_DIR", tmp_path)
    monkeypatch.setenv("ES_PROFILE", "fixture")
    (tmp_path / "config.toml").write_text("[profile.fixture]\n")
    profile = tmp_path / "fixture"
    profile.mkdir()
    now = int(time.time())
    claims = dict(
        sub="fixture",
        aud="fixture",
        iss="fixture",
        client_id="fixture",
        iat=now,
        exp=now + 3600,
    )
    payload = base64.b64encode(json.dumps(claims).encode()).decode()
    token = f"fixture.{payload}.fixture"
    (profile / "tokens.json").write_text(json.dumps({"access_token": token}))

    with proto_download.archive_http_session(
        "data.earthscope.org", None, None
    ) as session:
        request = session.prepare_request(
            Request("GET", "https://data.earthscope.org/data")
        )
        assert request.headers["Authorization"] == "Bearer " + token


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


@pytest.mark.parametrize("client", [DownloadSources, proto_download])
@pytest.mark.parametrize(
    ("origin", "target", "expected"),
    [
        ("example.org", "https://example.org/second", "source"),
        ("example.org", "https://storage.example/data", None),
        ("example.org", "http://example.org/second", None),
        ("example.org", "https://example.org:444/second", None),
        ("cddis.nasa.gov", "https://urs.earthdata.nasa.gov/login", "source"),
        ("cddis.nasa.gov", "http://urs.earthdata.nasa.gov/login", None),
        ("cddis.nasa.gov", "https://urs.earthdata.nasa.gov:444/login", None),
        ("example.org", "https://urs.earthdata.nasa.gov/login", "netrc"),
    ],
)
def test_basic_auth_redirects(tmp_path, monkeypatch, client, origin, target, expected):
    credentials = tmp_path / "netrc"
    credentials.write_text(
        "machine urs.earthdata.nasa.gov login netrc password fixture\n"
    )
    credentials.chmod(0o600)
    monkeypatch.setenv("NETRC", str(credentials))
    session = client.ProtocolHTTPS(origin, 443, "source", "fixture").session
    with session:
        initial = session.prepare_request(Request("GET", f"https://{origin}/first"))
        redirected = initial.copy()
        redirected.prepare_url(target, None)
        session.rebuild_auth(redirected, SimpleNamespace(request=initial))
        if expected:
            expected_header = HTTPBasicAuth(expected, "fixture")(
                Request("GET", target).prepare()
            )
            assert (
                redirected.headers["Authorization"]
                == expected_header.headers["Authorization"]
            )
        else:
            assert "Authorization" not in redirected.headers
        # Even a redirect from the login host to signed storage must drop credentials.
        storage = redirected.copy()
        storage.prepare_url("https://other-storage.example/item", None)
        session.rebuild_auth(storage, SimpleNamespace(request=redirected))
        assert "Authorization" not in storage.headers
