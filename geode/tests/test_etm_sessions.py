"""Complete ETM sessions can travel with their observations and adjusted matrices."""

import json
import zipfile

import numpy as np
import pytest

from geode.etm.core.data_classes import Earthquake
from geode.etm.core.etm_config import EtmConfig
from geode.etm.core.etm_engine import EtmEngine
from geode.etm.core.etm_stacker_vce import EtmStackerVCEEnhanced
from geode.etm.core.type_declarations import SolutionType
from geode.etm.stacker.constraints import (
    CoseismicConstraint,
    InterseismicConstraint,
    PostseismicConstraint,
)
from geode.etm.stacker.constraints.fault_geometry import FaultGeometry
from geode.etm.stacker.data_classes import EtmStackerField
from geode.etm.stacker.session import SessionError, load_session, save_session
from geode.etm.stacker.stacker import EtmStacker
from geode.etm.stacker.types import ConstraintType
from geode.metadata.station_info import StationInfoRecord
from geode.pyDate import Date
from geode.pyOkada import Mask


def fitted_stacker(tmp_path):
    config = EtmConfig("test", "abcd", silent=True)
    config.solution.solution_type = SolutionType.NGL
    filename = tmp_path / "observations.txt"
    config.solution.filename = str(filename)
    days = np.arange(160)
    rng = np.random.default_rng(17)
    xyz = days[:, None] * np.array([0.0002, 0.0003, 0.0001]) + rng.normal(
        0, 0.001, (160, 3)
    )
    xyz[:, 0] += config.metadata.auto_x[0]
    config.solution.format = ("mjd", "x", "y", "z")
    np.savetxt(filename, np.column_stack((days + 59000, xyz)))
    engine = EtmEngine(config, silent=True)
    engine.run_adjustment(try_loading_db=False, try_save_to_db=False)
    filename.unlink()
    engine.config.metadata.station_information.append(
        StationInfoRecord(
            "test",
            "abcd",
            DateStart=Date(stninfo="2020 001 00 00 00"),
            DateEnd=Date(stninfo=None),
            AntennaCode="TEST",
            RadomeCode="NONE",
            AntennaHeight=0.12345,
        )
    )
    stacker = EtmStacker()
    station = stacker._create_station(engine)
    stacker.stations.append(station)
    stacker.normal_equations.append(stacker._create_normal_equations(station))
    stacker.constraint_registry.add_constraint(InterseismicConstraint(stacker.stations))
    return stacker


@pytest.mark.parametrize("solved", [False, True])
def test_session_restores_fitted_observations_weights_and_stack_solution(
    tmp_path, solved
):
    stacker = fitted_stacker(tmp_path)
    if solved:
        stacker.solve(interpolate_fields=False)
    stacker.command_history.append("reweight_station test.abcd 3")
    stacker.collided_earthquakes.add("excluded")
    stacker.fields = [
        EtmStackerField(
            ConstraintType.INTERSEISMIC,
            stacker.grids,
            enu_field=np.array([[np.nan, -0.0, np.inf]]),
            constrain_stations=stacker.stations,
        )
    ]
    name = save_session(stacker, tmp_path / "sample")
    with zipfile.ZipFile(name) as archive:
        assert "arrays/" in ",".join(archive.namelist())
    restored = load_session(name)
    station = restored.stations[0]
    assert restored.solved is solved
    assert station.normal_equations is restored.normal_equations[0]
    assert station.etm.design_matrix is station.etm.fit.design_matrix
    assert station.etm.jump_manager.config is station.etm.config
    assert station.etm.solution_data.metadata is station.etm.config.metadata
    assert (
        restored.constraint_registry.constraints["interseismic"][0].station_list
        is restored.stations
    )
    assert station.etm.config.metadata.station_information[0].DateEnd.year == 9999
    assert station.etm.config.metadata.station_information[0].AntennaHeight == 0.12345
    assert restored.collided_earthquakes == {"excluded"}
    assert restored.command_history == stacker.command_history
    assert restored.fields[0].grids is restored.grids
    assert restored.fields[0].constrain_stations is restored.stations
    assert (
        restored.fields[0].enu_field.tobytes() == stacker.fields[0].enu_field.tobytes()
    )
    for a, b in zip(stacker.stations[0].etm.fit.results, station.etm.fit.results):
        for field in (
            "parameters",
            "covariance_matrix",
            "residuals",
            "outlier_flags",
            "obs_sigmas",
        ):
            np.testing.assert_array_equal(getattr(a, field), getattr(b, field))
    for session in (stacker, restored):
        session.change_station_weight("test.abcd", 3)
        session.solve(interpolate_fields=False)
    reopened = load_session(save_session(restored, tmp_path / "renamed.etms"))
    for session in (restored, reopened):
        np.testing.assert_array_equal(stacker.solution, session.solution)
        np.testing.assert_array_equal(stacker.covariance, session.covariance)
        assert stacker.variance == session.variance
        assert session._extract_results() == stacker._extract_results()


@pytest.mark.parametrize("weights", ["constraints", "observations", "stations"])
def test_variance_estimation_solves_with_the_applied_weights(tmp_path, weights):
    stacker = fitted_stacker(tmp_path)
    stacker.solve(interpolate_fields=False)
    vce = EtmStackerVCEEnhanced(stacker, max_iterations=1)
    if weights == "constraints":
        result = vce.run_vce()
    else:
        result = vce.run_vce_with_observation_scaling(
            initial_obs_variance=4, scale_per_station=(weights == "stations")
        )
    assert stacker.solved
    assert result is vce.history[-1]
    if weights != "constraints":
        assert stacker.normal_equations[0].weight_scale == 0.25
    stacker.solve(interpolate_fields=False)
    assert result.global_variance == stacker.variance
    np.testing.assert_array_equal(result.solution, stacker.solution)


def test_version_one_session_retains_inputs_but_requires_new_solve(tmp_path):
    stacker = fitted_stacker(tmp_path)
    stacker.solve(interpolate_fields=False)
    old_solution = stacker.solution
    old_covariance = stacker.covariance
    stacker.change_station_weight("test.abcd", 3)
    # Reproduce the old writer's inconsistent state.
    stacker.solved = True
    stacker.solution = old_solution
    stacker.covariance = old_covariance
    source = save_session(stacker, tmp_path / "cache")
    old_file = tmp_path / "v1.etms"
    with zipfile.ZipFile(source) as current, zipfile.ZipFile(old_file, "w") as old:
        for name in current.namelist():
            payload = current.read(name)
            if name == "session.json":
                manifest = json.loads(payload)
                manifest["version"] = 1
                payload = json.dumps(manifest)
            old.writestr(name, payload)

    with pytest.warns(UserWarning, match="Run solve"):
        restored = load_session(old_file)
    assert not restored.solved
    assert not restored.solution.size and not restored.covariance.size
    assert restored.normal_equations[0].weight_scale == 3
    restored.solve(interpolate_fields=False)
    stacker.solve(interpolate_fields=False)
    np.testing.assert_array_equal(stacker.covariance, restored.covariance)


def test_earthquake_mask_and_event_references_survive(tmp_path):
    class Catalog:
        def get(self, *_):
            return dict(
                id="sample",
                lat=0,
                lon=0,
                depth=10,
                mag=7,
                strike1=float("nan"),
                date=Date(year=2020, doy=1).datetime(),
                location="fixture",
                density=25,
                c_kml="c",
                cp_kml="cp",
            )

    stacker = EtmStacker()
    mask = Mask(Catalog(), "sample", density=25)
    event = Earthquake(
        id="sample",
        date=Date(year=2020, doy=1),
        magnitude=7,
        depth=10,
        strike=[0, 45],
        dip=[45, 60],
        rake=[0, 90],
    )
    geometry = FaultGeometry(event, [], 1.0, stacker.grids)
    coseismic = CoseismicConstraint(event, geometry, [], stacker.grids)
    postseismic = PostseismicConstraint(event, geometry, [], 1.0, stacker.grids)
    postseismic.sw_okada_h_weight = 2.5
    stacker.constraint_registry.add_constraint(coseismic)
    stacker.constraint_registry.add_constraint(postseismic)
    stacker.earthquakes.append(event)
    stacker.grids.earthquake_masks["sample"] = (mask.c_mask, mask.p_mask, mask)
    stacker.fields.append(
        EtmStackerField(ConstraintType.COSEISMIC, stacker.grids, event=event)
    )
    restored = load_session(save_session(stacker, tmp_path / "earthquake"))
    (co,) = restored.constraint_registry.constraints["coseismic"]
    (post,) = restored.constraint_registry.constraints["postseismic"]
    assert co.event is post.event is restored.fields[0].event is restored.earthquakes[0]
    assert co.fault_geometry is post.fault_geometry
    assert post.sw_okada_h_weight == 2.5
    np.testing.assert_array_equal(
        co.fault_geometry.patches_h.grid_dd, geometry.patches_h.grid_dd
    )
    assert restored.grids.earthquake_masks["sample"][2].score(0, 0) == mask.score(0, 0)


def test_session_rejects_unsupported_types_and_preserves_previous_save(tmp_path):
    stacker = EtmStacker()
    name = save_session(stacker, tmp_path / "sample")
    previous = name.read_bytes()
    stacker.solution = np.array([object()], dtype=object)
    with pytest.raises(SessionError, match="Unsupported session value"):
        save_session(stacker, name)
    assert name.read_bytes() == previous
    with pytest.raises(SessionError, match="Legacy pickle"):
        load_session(tmp_path / "old.pkl")
    with zipfile.ZipFile(name) as archive:
        manifest = json.loads(archive.read("session.json"))
    manifest["records"][0]["type"] = "unregistered"
    with zipfile.ZipFile(name, "w") as archive:
        archive.writestr("session.json", json.dumps(manifest))
    with pytest.raises(SessionError, match="unregistered"):
        load_session(name)


def test_shell_round_trip_without_processing_database(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    original = fitted_stacker(tmp_path)
    original.solve(interpolate_fields=False)
    original.fields.append(EtmStackerField(ConstraintType.INTERSEISMIC, original.grids))
    name = save_session(original, tmp_path / "native")
    env_python = Path(sys.executable)
    run = subprocess.run(
        [str(env_python), "-m", "com.EtmStacker", "--load_from_file", str(name)],
        cwd=tmp_path,
        input=(
            "load native.etms\nreweight_station TEST.ABCD 3\n"
            "print vel\nexport interseismic\nsave dirty\nload dirty\n"
            "list stations\nsolve false\nprint vel\nsave copy\nquit\n"
        ),
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert run.returncode == 0, run.stderr
    assert "Saved to copy.etms" in run.stdout
    assert "System is not solved" in run.stdout
    assert "test.abcd weight 3" in run.stdout
    assert "constrained" in run.stdout
    dirty = load_session(tmp_path / "dirty")
    assert not dirty.solved
    assert dirty.normal_equations[0].weight_scale == 3
    assert not dirty.solution.size and not dirty.covariance.size
    assert dirty.fields == []
    assert dirty.stations[0].etm_constraints is None
    assert dirty.stations[0].posterior_wrms is None
    assert not (tmp_path / "export_interseismic.txt").exists()

    reopened = load_session(tmp_path / "copy")
    assert reopened.command_history[-1] == "save copy"
    assert reopened.solved
    original.change_station_weight("test.abcd", 3)
    original.solve(interpolate_fields=False)
    np.testing.assert_array_equal(reopened.solution, original.solution)
    np.testing.assert_array_equal(reopened.covariance, original.covariance)
    assert not (tmp_path / "gnss_data.cfg").exists()
