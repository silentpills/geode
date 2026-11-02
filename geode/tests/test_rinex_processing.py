"""Keep external RINEX edits intact through subsequent header rewrites."""

import datetime
import shlex
from pathlib import Path

import pytest

from geode import pyRinex


@pytest.fixture
def rinex(tmp_path, monkeypatch):
    record = pyRinex.ReadRinex.__new__(pyRinex.ReadRinex)
    pyRinex.RinexRecord.__init__(record, "tst", "test")
    record.no_cleanup = True
    record.rootdir = str(tmp_path)
    record.rinex = "test0010.26o"
    record.rinex_path = str(tmp_path / record.rinex)
    record.datetime_firstObs = datetime.datetime(2026, 1, 1)
    record.datetime_lastObs = datetime.datetime(2026, 1, 1, 2)
    record.rinex_version = 3
    record.interval = 15
    Path(record.rinex_path).write_text(
        "original header\nold comment COMMENT\nEND OF HEADER\noriginal observations\n"
    )
    record.header = record.get_header()
    record.read_data()

    class EditCommand:
        """Stand in only for GFZRNX, which rewrites header and observations."""

        def __init__(self, command, timeout, cwd=None):
            args = shlex.split(command)
            self.output = Path(args[args.index("-fout") + 1])
            if not self.output.is_absolute():
                self.output = Path(cwd) / self.output

        def run_shell(self):
            self.output.write_text(
                "edited header\nnew comment COMMENT\nEND OF HEADER\nedited observations\n"
            )
            return "", ""

    monkeypatch.setattr(pyRinex.pyRunWithRetry, "RunCommand", EditCommand)
    monkeypatch.setattr(
        record,
        "RunGfzrnx",
        lambda: {
            "data": {
                "epoch": {
                    "interval": 30,
                    "number": 240,
                    "number_extra": 0,
                    "first": "2026 01 01 00 00 00",
                    "last": "2026 01 01 02 00 00",
                }
            }
        },
    )
    return record


@pytest.mark.parametrize("operation", ["window", "convert", "decimate", "systems"])
def test_edit_survives_subsequent_header_rewrite(rinex, operation):
    if operation == "window":
        rinex.window_data()
    elif operation == "convert":
        rinex.ConvertRinex(2)
    elif operation == "decimate":
        rinex.decimate(30)
    else:
        rinex.remove_systems()

    # This real call rewrites from the in-memory header and observations.
    rinex.purge_comments()
    assert Path(rinex.rinex_path).read_text() == (
        "edited header\nEND OF HEADER\nedited observations\n"
    )


@pytest.mark.parametrize("operation", ["window", "decimate", "systems"])
def test_editing_a_copy_preserves_original_and_cache(rinex, tmp_path, operation):
    original = Path(rinex.rinex_path).read_text()
    original_header = rinex.header.copy()
    original_data = rinex.data.copy()
    copy = str(tmp_path / "copy.rnx")
    if operation == "window":
        rinex.window_data(copyto=copy)
    elif operation == "decimate":
        rinex.decimate(30, copyto=copy)
    else:
        rinex.remove_systems(copyto=copy)

    assert "edited observations" in Path(copy).read_text()
    assert Path(rinex.rinex_path).read_text() == original
    assert rinex.header == original_header
    assert rinex.data == original_data
    assert rinex.interval == 15


def test_original_input_duration_guard_is_retained(rinex):
    output = rinex.RunGfzrnx()
    output["data"]["epoch"]["number"] = 10
    with pytest.raises(pyRinex.pyRinexExceptionBadFile, match="3600"):
        rinex.parse_output(output)
