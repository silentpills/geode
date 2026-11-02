"""Numerical and allocation regressions for diagonal robust-fit weights."""

import tracemalloc
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import chi2

from geode.etm.least_squares.least_squares import RobustLeastSquares, WhiteNoise


def dense_reference(a, y, initial_weights, iterations, limit, normal, rhs, constraints):
    """Frozen dense-weight equations used before upstream commit fcfd6b2.

    Keep this independent of WhiteNoise and RobustLeastSquares so a change to
    weighting, variance scaling, or stopping behavior cannot change both sides.
    """
    p = np.diag(initial_weights)
    dof = len(y) - a.shape[1] + constraints
    lower, upper = chi2.ppf([0.025, 0.975], dof)
    wrms = 1.0
    converged = False
    for iteration in range(iterations):
        square_root = np.sqrt(np.diag(p))
        aw = square_root[:, None] * a
        yw = square_root * y
        parameters = np.linalg.solve(aw.T @ aw + normal, aw.T @ yw + rhs)
        residuals = y - a @ parameters
        sigma0 = float(np.sqrt((residuals @ p @ residuals) / dof))
        statistic = sigma0**2 * dof
        wrms *= sigma0
        normalized = np.abs(residuals / wrms)
        factors = np.ones(len(y))
        factors[normalized > limit] = np.maximum(
            10 ** (limit - normalized[normalized > limit]), np.finfo(float).eps
        )
        diagonal = np.maximum((factors / wrms) ** 2, np.finfo(float).eps)
        p = np.diag(diagonal)
        if lower <= statistic <= upper:
            converged = True
            break
    covariance = np.linalg.inv(a.T @ p @ a) * sigma0**2
    return SimpleNamespace(
        parameters=parameters,
        residuals=residuals,
        covariance_matrix=covariance,
        parameter_sigmas=np.sqrt(np.diag(covariance)),
        obs_sigmas=np.sqrt(1 / np.diag(p)),
        outlier_flags=normalized <= limit,
        variance_factor=sigma0**2,
        wrms=wrms,
        iterations=iteration + 1,
        converged=converged,
        statistic=statistic,
        dof=dof,
        bounds=(lower, upper),
    )


@pytest.mark.parametrize(
    "case", ["ordinary", "outliers", "weighted", "constrained", "one_iteration"]
)
def test_robust_fit_matches_dense_reference(case, monkeypatch):
    rng = np.random.default_rng(721)
    times = np.linspace(0, 3, 96)
    a = np.column_stack((np.ones(times.size), times, np.sin(2 * np.pi * times)))
    y = a @ np.array([0.5, 0.025, -0.013]) + rng.normal(0, 0.002, times.size)
    if case in ("outliers", "weighted", "constrained"):
        y[[7, 35, 71]] += [0.04, -0.06, 0.08]
    initial = (
        np.linspace(0.5, 2, times.size) if case == "weighted" else np.ones(times.size)
    )
    normal = np.diag([0.0, 0.0, 2e4]) if case == "constrained" else np.zeros((3, 3))
    rhs = normal @ np.array([0.0, 0.0, -0.013])
    constraints = int(case == "constrained")
    iterations = 1 if case == "one_iteration" else 10
    expected = dense_reference(a, y, initial, iterations, 2.5, normal, rhs, constraints)
    config = SimpleNamespace(
        modeling=SimpleNamespace(
            least_squares_strategy=SimpleNamespace(
                sigma_filter_limit=2.5, iterations=iterations
            )
        )
    )
    design = SimpleNamespace(matrix=a, total_constraints=constraints, functions=[])
    original_diag = np.diag

    def no_observation_matrix(values, *args, **kwargs):
        values = np.asarray(values)
        assert values.ndim != 1 or values.size != len(y), (
            "allocated dense observation weights"
        )
        return original_diag(values, *args, **kwargs)

    monkeypatch.setattr(np, "diag", no_observation_matrix)
    weights = WhiteNoise(len(y))
    weights.update_weights(initial.copy())
    strategy = RobustLeastSquares(config)
    mjd = 58000 + times * 365.25
    actual = strategy.adjust(design, y, weights, mjd, normal, rhs)
    for field in (
        "parameters",
        "residuals",
        "covariance_matrix",
        "parameter_sigmas",
        "obs_sigmas",
        "variance_factor",
        "wrms",
    ):
        np.testing.assert_allclose(
            getattr(actual, field),
            getattr(expected, field),
            rtol=1e-10,
            atol=1e-13,
            err_msg=field,
        )
    np.testing.assert_array_equal(actual.outlier_flags, expected.outlier_flags)
    assert actual.iterations == expected.iterations
    assert actual.converged == expected.converged
    assert strategy.dof == expected.dof
    np.testing.assert_allclose([strategy.x1, strategy.x2], expected.bounds, rtol=1e-13)
    assert strategy.so**2 * strategy.dof == pytest.approx(expected.statistic, rel=1e-10)
    if case in ("outliers", "weighted", "constrained"):
        assert not actual.outlier_flags[[7, 35, 71]].any()
    # The optimization must retain the existing spectral diagnostics.
    spectral_index, frequencies, power = strategy.compute_plomb(
        expected.residuals[expected.outlier_flags], mjd[expected.outlier_flags]
    )
    assert actual.periodogram_frequencies.size > 0
    np.testing.assert_array_equal(actual.periodogram_frequencies, frequencies)
    np.testing.assert_allclose(actual.periodogram_power, power, rtol=1e-9, atol=1e-15)
    assert actual.spectral_index_random_noise == pytest.approx(
        spectral_index, abs=1e-10
    )


def test_white_noise_storage_and_updates_have_linear_memory(monkeypatch):
    n = 8192
    original_diag = np.diag

    def no_dense_weights(values, *args, **kwargs):
        values = np.asarray(values)
        assert values.ndim != 1 or values.size != n, (
            "allocated dense observation weights"
        )
        return original_diag(values, *args, **kwargs)

    monkeypatch.setattr(np, "diag", no_dense_weights)
    tracemalloc.start()
    try:
        weights = WhiteNoise(n)
        weights.update_weights(np.linspace(0.5, 2, n))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Generous O(N) ceiling: old dense weights alone need 512 MiB here.
    assert peak < 128 * n
    assert weights.diag.shape == (n,)
    np.testing.assert_allclose(
        weights.weight_observations(np.ones(n)) ** 2, weights.diag
    )


def test_white_noise_accepts_diagonal_matrix_and_clamps_small_weights():
    diagonal = np.array([0.0, 1e-30, 0.25, 4.0])
    weights = WhiteNoise(len(diagonal))
    weights.update_weights(np.diag(diagonal))
    expected = np.maximum(diagonal, np.finfo(float).eps)
    np.testing.assert_array_equal(weights.diag, expected)
    design = np.arange(8).reshape(4, 2)
    np.testing.assert_allclose(
        weights.weight_design(design), np.sqrt(expected)[:, None] * design
    )
