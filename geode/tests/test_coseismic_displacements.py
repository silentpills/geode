"""Extract fitted coseismic offsets without relying on stale decay metadata."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from geode.pyOkada import (
    CO_SEISMIC_JUMP,
    CO_SEISMIC_JUMP_DECAY,
    EarthquakeTable,
)


def displacement_rows(records):
    # Exercise extraction without constructing earthquake masks or using a DB.
    table = EarthquakeTable.__new__(EarthquakeTable)
    table.earthquake_id = "synthetic-event"
    table.cnn = SimpleNamespace(query_float=lambda *args, **kwargs: records)
    return table.get_coseismic_displacements()


def fitted_record(params, jump_type=CO_SEISMIC_JUMP_DECAY, station="test", length=2):
    return {
        "NetworkCode": "tst",
        "StationCode": station,
        "params": params,
        "jump_type": jump_type,
        "relaxation": [0.05, 1.0],
        "len": length,
    }


@pytest.mark.parametrize("jump_type", [CO_SEISMIC_JUMP, CO_SEISMIC_JUMP_DECAY])
@pytest.mark.parametrize(
    "params",
    [
        [0.01, -0.02, 0.03],
        [[0.01], [-0.02], [0.03]],
        [0.01, 0.11, -0.02, 0.22, 0.03, 0.33],
        [[0.01, 0.11], [-0.02, 0.22], [0.03, 0.33]],
        [0.01, 0.11, 0.12, -0.02, 0.21, 0.22, 0.03, 0.31, 0.32],
        [[0.01, 0.11, 0.12], [-0.02, 0.21, 0.22], [0.03, 0.31, 0.32]],
    ],
)
@pytest.mark.parametrize("length", [None, 0, 2, 5])
def test_extracts_component_offsets_independently_of_relaxation_length(
    params, jump_type, length
):
    record = fitted_record(params, jump_type, length=length)
    before = deepcopy(record)
    assert displacement_rows([record]) == [
        {"NetworkCode": "tst", "StationCode": "test", "n": 0.01, "e": -0.02, "u": 0.03}
    ]
    assert record == before


@pytest.mark.parametrize(
    "params",
    [
        None,
        [],
        [[], [], []],
        [None, 0.02, 0.03],
        [[0.01], [None], [0.03]],
        [0.01, 0.02, np.nan],
        [[np.nan, 0.11], [0.02, 0.22], [0.03, 0.33]],
        [[np.nan], [np.nan], [np.nan]],
        1.0,
        [1, 2],
        [1, 2, 3, 4],
        [[1, 2, 3]],
        [[1, 2], [3, 4]],
        [[1], [2], [3], [4]],
        [[1], [2, 3], [4]],
        [[[1]], [[2]], [[3]]],
        [1, [2], 3],
        ["unfit", 2, 3],
    ],
)
def test_skips_unfit_or_malformed_parameters_and_keeps_valid_stations(params):
    assert displacement_rows(
        [fitted_record(params, station="bad"), fitted_record([1, 2, 3], station="good")]
    ) == [{"NetworkCode": "tst", "StationCode": "good", "n": 1, "e": 2, "u": 3}]


def test_unfit_decay_does_not_hide_fitted_coseismic_offset_and_results_are_sorted():
    records = [
        fitted_record([[1, np.nan], [2, None], [3, np.nan]], station="zzzz"),
        fitted_record(np.array([[4], [5], [6]]), station="aaaa"),
    ]
    assert displacement_rows(records) == [
        {"NetworkCode": "tst", "StationCode": "aaaa", "n": 4, "e": 5, "u": 6},
        {"NetworkCode": "tst", "StationCode": "zzzz", "n": 1, "e": 2, "u": 3},
    ]
