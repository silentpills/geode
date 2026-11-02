"""GPSPACE setup preserves validated working observations and bounds execution."""

import datetime
import gzip
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from geode import pyOptions, pyPPP, pyRinex
from geode.pyDate import Date


@pytest.fixture
def setup_ppp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    working = tmp_path / "test0010.26o"
    working.write_text("validated short window\n")
    original = tmp_path / "original.26o"
    original.write_text("unfiltered full day\n")
    reopened = []
    windows = []

    def read_working(self, network, station, path, **kwargs):
        pyRinex.RinexRecord.__init__(self, network, station)
        self.no_cleanup = True
        self.allow_multiday = False
        self.rootdir = str(tmp_path)
        self.rinex_path = str(path)
        self.origin_file = str(path)
        self.origin_type = pyRinex.TYPE_RINEX
        self.rinex_name_format = pyRinex.pyRinexName.RinexNameFormat(str(path))
        self.rinex = Path(path).name
        self.date = Date(year=2026, doy=1)
        self.rinex_version = 3
        self.interval = 30
        self.header = [
            f"{0:14.4f}{0:14.4f}{0:14.4f}{'':18s}APPROX POSITION XYZ\n",
            "END OF HEADER\n",
        ]
        self.data = [Path(path).read_text()]
        self.datetime_firstObs = datetime.datetime(2026, 1, 1, 6)
        self.datetime_lastObs = datetime.datetime(2026, 1, 1, 6, 15)
        reopened.append((str(path), kwargs))
        if kwargs.get("min_time_seconds", 3600) > 900:
            raise pyRinex.pyRinexExceptionBadFile("short input rejected")

    def window(self, start, end):
        windows.append((start, end))
        self.datetime_firstObs, self.datetime_lastObs = start, end

    monkeypatch.setattr(pyRinex.ReadRinex, "__init__", read_working)
    monkeypatch.setattr(pyRinex.ReadRinex, "window_data", window)
    monkeypatch.setattr(
        pyRinex.ReadRinex,
        "ConvertRinex",
        lambda self, version: setattr(self, "rinex_version", version),
    )
    monkeypatch.setattr(
        pyPPP, "determine_frame", lambda frames, epoch: ("IGS20", "test.atx")
    )
    for method in ("get_orbits", "write_otl", "copyfiles", "config_session"):
        monkeypatch.setattr(pyPPP.RunPPP, method, lambda *args: None)

    source = pyRinex.ReadRinex("tst", "test", working, min_time_seconds=0)
    source.origin_file = str(original)
    reopened.clear()

    def create(**options):
        return pyPPP.RunPPP(
            source,
            "",
            {"ppp_path": "unused", "ppp_exe": "gpspace", "frames": [], **options},
            [],
            (),
            0,
        )

    return SimpleNamespace(
        source=source,
        create=create,
        reopened=reopened,
        windows=windows,
        original=original,
        working=working,
    )


def test_rinex3_conversion_uses_validated_working_copy(setup_ppp):
    setup = setup_ppp
    with setup.create() as ppp:
        assert setup.reopened == [
            (
                str(setup.working),
                {"no_cleanup": True, "allow_multiday": False, "min_time_seconds": 0},
            )
        ]
        assert ppp.rinex.origin_file == str(setup.original)
        assert ppp.rinex.rinex_version == 2
        assert setup.windows == [
            (datetime.datetime(2026, 1, 1, 6), datetime.datetime(2026, 1, 1, 6, 15))
        ]
        assert (
            Path(ppp.rootdir) / ppp.rinex.rinex
        ).read_text() == "validated short window\n"
        assert setup.original.read_text() == "unfiltered full day\n"


def test_rinex2_window_clips_only_extra_midnight_epoch(setup_ppp):
    setup = setup_ppp
    setup.source.rinex_version = 2
    setup.source.datetime_lastObs = datetime.datetime(2026, 1, 2)
    with setup.create() as ppp:
        assert setup.reopened == []
        assert setup.windows == [
            (
                datetime.datetime(2026, 1, 1, 6),
                datetime.datetime(2026, 1, 1, 23, 59, 59),
            )
        ]
        assert ppp.rinex is setup.source


@pytest.mark.parametrize("value", [0, -1, "nan", "inf", "-inf", "invalid", None])
def test_invalid_timeout_fails_before_rinex_or_staging(setup_ppp, value):
    with pytest.raises(pyPPP.pyRunPPPException, match="ppp_timeout"):
        setup_ppp.create(ppp_timeout=value)
    assert setup_ppp.reopened == []
    assert not Path("production").exists()


@pytest.mark.parametrize(
    "options, expected", [({}, 900), ({"ppp_timeout": "12.5"}, 12.5)]
)
def test_timeout_reaches_subprocess_and_retries_remain_bounded(
    setup_ppp, monkeypatch, options, expected
):
    calls = []

    def timeout(command, **kwargs):
        calls.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with setup_ppp.create(**options) as ppp:
        (Path(ppp.rootdir) / "input.inp").write_text("input\n")
        success, message = ppp.__exec_ppp__(False)
        assert not success
        assert "Timeout after 3" in message
    assert calls == [expected] * 3


def test_no_overlap_fails_before_staging(setup_ppp):
    setup = setup_ppp
    setup.source.rinex_version = 2
    setup.source.datetime_firstObs = datetime.datetime(2026, 1, 2)
    setup.source.datetime_lastObs = datetime.datetime(2026, 1, 2, 1)
    with pytest.raises(pyPPP.pyRunPPPException, match="do not overlap"):
        setup.create()
    assert setup.windows == []
    assert not Path("production").exists()


def test_bootstrap_reopens_validated_short_working_copy(setup_ppp, monkeypatch):
    setup = setup_ppp
    calls = []

    def bootstrap(rinex, otl, options, sp3, alternate, height, **kwargs):
        calls.append((rinex.rinex_path, kwargs["observations"]))
        return SimpleNamespace(x=6378137.0, y=0.0, z=0.0, exec_ppp=lambda: None)

    monkeypatch.setattr(pyPPP, "RunPPP", bootstrap)
    monkeypatch.setattr(
        pyOptions, "ReadOptions", lambda path: SimpleNamespace(options={})
    )
    coordinates, _ = setup.source.auto_coord(None)
    assert coordinates == (6378137.0, 0.0, 0.0)
    assert setup.reopened == [
        (str(setup.working), {"allow_multiday": True, "min_time_seconds": 0})
    ]
    assert calls == [(str(setup.working), pyPPP.OBSERV_CODE_ONLY)]


def test_converted_working_copy_preserves_compressed_origin_for_archive_move(
    setup_ppp, tmp_path
):
    setup = setup_ppp
    compressed = tmp_path / "test0010.26d.gz"
    original_bytes = gzip.compress(b"unfiltered full day\n")
    compressed.write_bytes(original_bytes)
    setup.source.origin_file = str(compressed)
    setup.source.origin_type = pyRinex.TYPE_CRINEZ_2

    with setup.create() as ppp:
        assert ppp.rinex.origin_type == pyRinex.TYPE_CRINEZ_2
        # Moving the origin in its existing format must preserve its bytes,
        # rather than recompressing the filtered working observations.
        moved = Path(
            ppp.rinex.move_origin_file(
                str(tmp_path / "archive"), destiny_type=pyRinex.TYPE_CRINEZ_2
            )
        )
        assert moved.read_bytes() == original_bytes
        assert not compressed.exists()
        assert setup.working.read_text() == "validated short window\n"
