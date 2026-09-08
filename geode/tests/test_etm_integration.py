"""Regression coverage for upstream ETM integration, using synthetic observations."""

from types import SimpleNamespace

import numpy as np
import pytest

from geode.etm.core.etm_config import EtmConfig
from geode.etm.core.type_declarations import EtmException, FitStatus, JumpType
from geode.etm.etm_functions.auto_jumps import AutoJumps
from geode.etm.etm_functions.jumps import JumpFunction
from geode.etm.etm_functions.polynomial import PolynomialFunction
from geode.etm.least_squares.design_matrix import DesignMatrix
from geode.etm.least_squares.least_squares import EtmFit
from geode.pyDate import Date


def test_empty_fit_window_reports_useful_error():
    config = EtmConfig(silent=True)
    config.modeling.data_model_window = [[2020, 2021]]
    with pytest.raises(EtmException, match="Fit window"):
        config.modeling.get_observation_mask(np.array([2018.0, 2019.0]))


@pytest.mark.parametrize("method", ["angry", "dbscan"])
def test_auto_jump_detection_uses_matching_windowed_observations(method, monkeypatch):
    config = EtmConfig(silent=True)
    config.modeling.data_model_window = [[2020.2, 2020.8]]
    times = np.linspace(2020, 2021, 100)
    mask = config.modeling.get_observation_mask(times)
    observations = [np.zeros(mask.sum()) for _ in range(3)]
    detector = AutoJumps(config, method)
    calls = []

    def detect(windowed, obs, full):
        assert windowed.size == len(obs[0])
        np.testing.assert_array_equal(windowed, times[mask])
        np.testing.assert_array_equal(full, times)
        calls.append(True)

    monkeypatch.setattr(
        detector, "_angry_search" if method == "angry" else "_dbscan", detect
    )
    detector.detect(times, observations)
    assert calls == [True]


def test_windowed_fit_excludes_unobservable_jumps_and_saves_spectrum():
    config = EtmConfig(silent=True)
    config.modeling.data_model_window = [[2020.2, 2020.8]]
    times = np.linspace(2020, 2021, 160)
    mask = config.modeling.get_observation_mask(times)
    dates = [Date(fyear=t) for t in times]
    mjd = np.array([d.mjd for d in dates])
    polynomial = PolynomialFunction(config, time_vector=times)
    jumps = [
        JumpFunction(config, times, Date(fyear=t), jump_type=JumpType.MECHANICAL_MANUAL)
        for t in (2020.1, 2020.9)
    ]
    design = DesignMatrix(config, times, [polynomial, *jumps])
    rng = np.random.default_rng(10)
    observations = [
        (i + 1) * 0.01 * (times[mask] - 2020) + rng.normal(0, 0.001, mask.sum())
        for i in range(3)
    ]
    solution = SimpleNamespace(
        time_vector=times,
        time_vector_mjd=mjd,
        time_vector_cont_mjd=mjd,
        solutions=mask.sum(),
        transform_to_local=lambda: observations,
    )
    fit = EtmFit(config, design)
    fit.run_fit(solution)
    assert config.modeling.status == FitStatus.POSTFIT
    assert all(not jump.fit for jump in jumps)
    assert design.matrix.shape[1] == 2
    for result in fit.results:
        assert result.periodogram_frequencies.size > 0
        assert result.periodogram_frequencies.shape == result.periodogram_power.shape
        assert np.isfinite(result.parameters).all()


def test_stacker_compatibility_import_is_headless():
    from geode.etm.core.etm_stacker import EtmStacker as LegacyStacker
    from geode.etm.stacker import EtmStacker

    assert LegacyStacker is EtmStacker
