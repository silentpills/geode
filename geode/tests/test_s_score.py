"""Numerical S-score output without changing the event classification masks."""

import hashlib
import importlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from geode import pyOkada


@pytest.fixture(scope="module")
def isotropic():
    return pyOkada.Score(0, 0, 10, 7, density=750)


def test_isotropic_values_use_kilometres_and_expand_postseismic_radius(isotropic):
    # About 111, 400, and 600 km: inside both radii, postseismic only, outside.
    lat = np.array([1.0, 3.6, 5.4])
    c_mask, p_mask, c_value, p_value = isotropic.score_values(lat, np.zeros(3))
    np.testing.assert_array_equal(c_mask, [1, 0, 0])
    np.testing.assert_array_equal(p_mask, [1, 1, 0])
    # At 111.1949 km the analytic score is +0.488815. Nearest-grid sampling
    # accounts for ~0.004; upstream's metre bug instead gave -2.507087.
    assert c_value[0] == pytest.approx(0.488815, abs=0.005)
    np.testing.assert_array_equal(c_value > 0, c_mask)
    np.testing.assert_array_equal(p_value > 0, p_mask)
    # The postseismic score must increase at a given distance, not decrease.
    np.testing.assert_allclose(p_value - c_value, np.log10(1.5))
    assert isotropic.score_level == 1
    assert isotropic.score_quantity == "isotropic_s_score"
    assert isotropic.score_units == "dimensionless"
    for old, new in zip(isotropic.score(lat, np.zeros(3)), (c_mask, p_mask)):
        np.testing.assert_array_equal(old, new)


def test_isotropic_epicenter_has_infinite_score_without_runtime_warning():
    # An odd grid includes zero distance, where the logarithmic score is +inf.
    with np.errstate(all="raise"):
        score = pyOkada.Score(0, 0, 10, 7, density=101)
        c_mask, p_mask, c_value, p_value = score.score_values(0, 0)
    np.testing.assert_array_equal(c_mask, [1])
    np.testing.assert_array_equal(p_mask, [1])
    assert np.isposinf(c_value[0]) and np.isposinf(p_value[0])


def test_real_focal_mechanism_preserves_legacy_masks_and_reports_margins():
    score = pyOkada.Score(
        -36.122, -72.898, 22.9, 8.8, [178, 17], [77, 14], [86, 108], density=80
    )
    # Whole-mask snapshots from dev 8aea567, before numerical output was added.
    # Co/post use the same Boolean grid but different geographic scaling.
    legacy_digest = "900071f72d767d57ce5c969213d51ae89d6e676093cfdbd511de92ad82def7ec"
    for mask in (score.c_mask, score.p_mask):
        assert hashlib.sha256(np.packbits(mask)).hexdigest() == legacy_digest
    lat = np.array([-36.0, -30.0, -20.0])
    lon = np.array([-73.0, -70.0, -70.0])
    c_mask, p_mask, c_value, p_value = score.score_values(lat, lon)
    np.testing.assert_array_equal(c_mask, [1, 1, 0])
    np.testing.assert_array_equal(p_mask, [1, 1, 1])
    assert np.all(np.isfinite(c_value)) and np.all(np.isfinite(p_value))
    assert c_value[-1] < 0 < p_value[-1]
    assert score.score_level == 2
    assert score.score_quantity == "rescaled_okada_mean_margin"
    assert score.score_units == "m"
    for old, new in zip(score.score(lat, lon), (c_mask, p_mask)):
        np.testing.assert_array_equal(old, new)
    # Existing callers of this public method still receive three arrays.
    assert len(score.compute_disp_field()) == 3


def test_focal_mean_margin_does_not_replace_any_plane_classification(monkeypatch):
    def displacement(alpha, x, y, depth, l1, l2, w1, w2, snd, csd, b1, b2, b3):
        # Plane 1 is above the 1 mm threshold, plane 2 below it. The mean
        # is below threshold but the legacy classification must remain true.
        magnitude = 0.0012 if b1 > b2 else 0.0002
        return np.full_like(x, magnitude), np.zeros_like(x), np.zeros_like(x)

    monkeypatch.setattr(pyOkada, "okada", displacement)
    score = pyOkada.Score(0, 0, 10, 7, [0, 90], [45, 45], [0, 90], density=10)
    c_mask, p_mask, c_value, p_value = score.score_values(1, 0)
    np.testing.assert_array_equal(c_mask, [1])
    np.testing.assert_array_equal(p_mask, [1])
    np.testing.assert_allclose(c_value, [-0.0003])
    np.testing.assert_allclose(p_value, [-0.0003])


def test_station_file_formats_and_invalid_coordinates(tmp_path, capsys):
    cli = importlib.import_module("com.S-score")
    stations = tmp_path / "stations.txt"
    stations.write_text(
        "# name latitude longitude\n\n"
        "net.aaaa 1 2 ignored\nnet.bbbb,-3,4,extra\n"
        "missing 2\nbad nope 1\nnan nan 0\ninf 0 inf\nrange 91 0\n"
    )
    names, lats, lons = cli.read_station_file(str(stations))
    assert names == ["net.aaaa", "net.bbbb"]
    np.testing.assert_array_equal(lats, [1, -3])
    np.testing.assert_array_equal(lons, [2, 4])
    assert capsys.readouterr().out.count("Skipping line") == 5


def test_cli_reports_isotropic_values_without_focal_mechanism(
    isotropic, monkeypatch, tmp_path, capsys
):
    cli = importlib.import_module("com.S-score")
    stations = tmp_path / "stations.txt"
    stations.write_text("net.test 1 0\n")
    event = {"id": "synthetic", "location": "Synthetic event"}

    class Records(list):
        def dictresult(self):
            return self

    monkeypatch.setattr(
        cli.dbConnection,
        "Cnn",
        lambda _: SimpleNamespace(query=lambda _: Records([event])),
    )
    monkeypatch.setattr(cli.pyOkada, "Mask", lambda *_: isotropic)
    monkeypatch.setattr(isotropic, "save_masks", lambda **_: None)
    monkeypatch.setattr(sys, "argv", ["S-score", "synthetic", "-scores", str(stations)])
    cli.main()
    output = capsys.readouterr().out
    assert "quantity=isotropic_s_score; units=dimensionless" in output
    assert "c_mask" in output and "p_mask" in output
    assert "net.test" in output and "0.492913" in output
    assert "not available" not in output


def test_cli_identifies_rescaled_focal_margin(capsys):
    cli = importlib.import_module("com.S-score")
    score = pyOkada.Score(0, 0, 10, 7, [0], [45], [90], density=40)
    cli.print_station_scores(
        score, {"id": "synthetic", "location": "Synthetic event"}, ["test"], [1], [0]
    )
    output = capsys.readouterr().out
    assert "quantity=rescaled_okada_mean_margin; units=m" in output
    assert "not physical station displacements" in output
    assert "a negative mean margin can still have mask=1" in output
