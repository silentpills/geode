"""Portable ETM stacker sessions: a JSON record table and typed NumPy arrays."""

import json
import math
import os
import tempfile
import warnings
import zipfile
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path

import numpy as np
from scipy.spatial import KDTree

from ...metadata.station_info import StationInfoRecord
from ...pyDate import Date
from ...pyOkada import Mask
from ..core import data_classes as data
from ..core import type_declarations as types
from ..core.etm_config import EtmConfig
from ..core.etm_engine import EtmEngine
from ..core.jump_manager import JumpManager
from ..data.solution_data import (
    CoordinateTimeSeries,
    DRASolutionData,
    FileSolutionData,
    GAMITSolutionData,
    PPPSolutionData,
)
from ..etm_functions.jumps import JumpFunction
from ..etm_functions.periodic import PeriodicFunction
from ..etm_functions.polynomial import PolynomialFunction
from ..etm_functions.stochastic_signal import StochasticSignal
from ..least_squares.design_matrix import DesignMatrix
from ..least_squares.least_squares import EtmFit
from ..visualization.data_classes import PlotOutputConfig
from .constraints import (
    ConstraintRegistry,
    CoseismicConstraint,
    InterseismicConstraint,
    PostseismicConstraint,
)
from .constraints.fault_geometry import FaultGeometry, PatchGrid
from .data_classes import (
    ConstraintEquation,
    EtmStackerConfig,
    EtmStackerField,
    NormalEquations,
    Station,
)
from .grid_system import GridSystem
from .jump_functions import CoseismicJumpFunction, PostseismicJumpFunction
from .stacker import EtmStacker
from .types import ConstraintType


class SessionError(ValueError):
    """The file is incomplete or uses an unsupported session format."""


_FORMAT = "geode-etm-stacker"
_VERSION = 2
_CONVENTIONS = {
    "station_fit_components": ["north", "east", "up"],
    "stack_solution_components": ["east", "north", "up"],
    "displacement": "m",
    "velocity": "m/year",
    "relaxation": "years",
    "projected_coordinates": "km",
}
_FUNCTION = (
    "p config constrained param_count column_index format_str fit design _time_vector"
)
_JUMP = (
    _FUNCTION + " date earthquake epi_distance magnitude nr user_action was_modified"
)
_CONSTRAINT = "constraint_type event _station_list h_sigma v_sigma equations _is_collected is_collision relaxation"
_SEISMIC = (
    _CONSTRAINT
    + " grid spline_tension fault_geometry dislocation_model _constraint_coefficients grid_prediction_kernels sw_okada_h_weight sw_okada_v_weight _mask_index"
)
_OBSERVATIONS = "network_code station_code config solutions completion soln stack_name project frames coordinates metadata blunders excluded gaps time_vector_cont time_vector_cont_mjd time_vector_ns time_vector_blunders rnx_no_ppp"

# Only the scientific fields listed here can be set by a session file. Shared
# station, configuration, earthquake and normal-equation references matter: an
# interactive reweight or re-solve must update the same instances everywhere.
_RECORDS = {
    cls: set(names.split())
    for cls, names in {
        EtmStacker: "stations normal_equations earthquakes collided_earthquakes constraint_registry grids config total_parameters total_equations total_constraints variance solved solution covariance fields command_history filename",
        Date: "year month day doy hour minute second fyear mjd gpsWeek gpsWeekDay from_stninfo",
        ConstraintRegistry: "constraints _application_order",
        InterseismicConstraint: _CONSTRAINT,
        CoseismicConstraint: _SEISMIC,
        PostseismicConstraint: _SEISMIC,
        FaultGeometry: "event along_strike down_dip patches_h patches_v plane station_list",
        Mask: "lat lon depth mag strike dip rake dmax date location event_id along_strike_l downdip_l avg_disp rupture_area maximum_disp c_mx c_my c_mask c_score p_mx p_my p_mask p_score gx gy score_level score_quantity score_units c_kml cp_kml",
        EtmEngine: "config solution_data jump_manager design_matrix fit",
        EtmConfig: "network_code station_code solution modeling plotting_config validation metadata json_file language _language_dict",
        PPPSolutionData: _OBSERVATIONS,
        GAMITSolutionData: _OBSERVATIONS,
        DRASolutionData: _OBSERVATIONS,
        FileSolutionData: _OBSERVATIONS,
        JumpManager: "config solution_data date_min date_max jumps",
        PolynomialFunction: _FUNCTION,
        PeriodicFunction: _FUNCTION + " dt_max",
        JumpFunction: _JUMP,
        CoseismicJumpFunction: _JUMP,
        PostseismicJumpFunction: _JUMP,
        StochasticSignal: _FUNCTION + " _time_vector_cont_mjd",
        DesignMatrix: "time_vector functions config rank_deficient internal_constraints total_constraints condition_number",
        EtmFit: "config outlier_flags results design_matrix covar hash",
    }.items()
}
for _record in (
    ConstraintEquation,
    EtmStackerConfig,
    EtmStackerField,
    NormalEquations,
    Station,
    GridSystem,
    StationInfoRecord,
    CoordinateTimeSeries,
    PatchGrid,
    PlotOutputConfig,
    data.AdjustmentResults,
    data.EtmFunctionParameterVector,
    data.Earthquake,
    data.JumpParameters,
    data.LeastSquares,
    data.ModelingParameters,
    data.StationMetadata,
    data.SolutionOptions,
    data.ValidationRules,
):
    _RECORDS[_record] = {f.name for f in fields(_record)}
_BY_NAME = {cls.__name__: cls for cls in _RECORDS}
_ENUMS = {
    cls.__name__: cls
    for cls in (
        ConstraintType,
        types.FitStatus,
        types.PeriodicStatus,
        types.EtmSolutionType,
        types.JumpType,
        types.NoiseModels,
        types.AdjustmentModels,
        types.CovarianceFunction,
        types.SolutionType,
    )
}
_DERIVED = {"_allowed_attributes", "kd_c", "kd_p"}


class _Writer:
    def __init__(self, archive):
        self.archive = archive
        self.records = []
        self.seen = {}

    def encode(self, value):
        cls = type(value)
        if isinstance(value, Enum) and _ENUMS.get(cls.__name__) is cls:
            return {"enum": [cls.__name__, value.name]}
        if isinstance(value, np.generic):
            if value.dtype.kind not in "biufcSU":
                raise SessionError(f"Unsupported scalar dtype {value.dtype}")
            return {"scalar": [value.dtype.str, value.tobytes().hex()]}
        if cls is float and not math.isfinite(value):
            return {"float": str(value)}
        if value is None or cls in (str, int, float, bool):
            return value
        if cls in (datetime, date):
            return {cls.__name__: value.isoformat()}
        if cls is Decimal:
            return {"decimal": str(value)}
        if cls in (tuple, set):
            return {cls.__name__: [self.encode(v) for v in value]}
        if cls is dict:
            return {
                "mapping": [[self.encode(k), self.encode(v)] for k, v in value.items()]
            }

        # Lists also have meaningful identity: several constraints keep the
        # stacker's live station list and observe station removals through it.
        if id(value) in self.seen:
            return {"ref": self.seen[id(value)][0]}
        index = len(self.records)
        self.seen[id(value)] = (index, value)
        self.records.append(None)
        if cls is list:
            record = {"type": "list", "items": [self.encode(v) for v in value]}
        elif cls is np.ndarray and value.dtype.kind in "biufcSU":
            with self.archive.open(
                f"arrays/{index}.npy", "w", force_zip64=True
            ) as array:
                np.lib.format.write_array(
                    array, value, version=(2, 0), allow_pickle=False
                )
            record = {"type": "array"}
        elif cls in _RECORDS:
            state = vars(value)
            difference = (state.keys() - _DERIVED) ^ _RECORDS[cls]
            if difference:
                raise SessionError(
                    f"Unexpected {cls.__name__} fields: {sorted(difference)}"
                )
            attrs = {}
            for name in sorted(state.keys() & _RECORDS[cls]):
                item = state[name]
                if cls is EtmConfig and name == "json_file" and isinstance(item, str):
                    # Store the source snapshot so moving the session never
                    # points an adjustment at the old machine's filesystem.
                    with open(item, encoding="utf-8") as source:
                        item = json.load(source)
                attrs[name] = self.encode(item)
            record = {"type": cls.__name__, "fields": attrs}
        else:
            raise SessionError(f"Unsupported session value {cls.__name__}")
        self.records[index] = record
        return {"ref": index}


class _Reader:
    def __init__(self, archive, records):
        self.archive = archive
        self.records = records
        self.loaded = {}

    def decode(self, item):
        if item is None or type(item) in (bool, str, int, float):
            return item
        if not isinstance(item, dict) or len(item) != 1:
            raise SessionError("Invalid session value")
        tag, value = next(iter(item.items()))
        if tag == "ref":
            if type(value) is not int or not 0 <= value < len(self.records):
                raise SessionError("Invalid session reference")
            return self.read_record(value)
        if tag == "scalar":
            dtype = np.dtype(value[0])
            raw = bytes.fromhex(value[1])
            if dtype.kind not in "biufcSU" or len(raw) != dtype.itemsize:
                raise SessionError("Invalid scalar dtype or size")
            return np.frombuffer(raw, dtype=dtype, count=1)[0]
        if tag == "enum":
            return _ENUMS[value[0]][value[1]]
        if tag == "mapping":
            return {self.decode(k): self.decode(v) for k, v in value}
        if tag in ("tuple", "set"):
            return (tuple if tag == "tuple" else set)(self.decode(v) for v in value)
        if tag == "float" and value in ("nan", "inf", "-inf"):
            return float(value)
        if tag == "datetime":
            return datetime.fromisoformat(value)
        if tag == "date":
            return date.fromisoformat(value)
        if tag == "decimal":
            return Decimal(value)
        raise SessionError(f"Unknown session value type {tag}")

    def read_array(self, index):
        info = self.archive.getinfo(f"arrays/{index}.npy")
        with self.archive.open(info) as member:
            if np.lib.format.read_magic(member) != (2, 0):
                raise SessionError("Unsupported array format")
            shape, fortran, dtype = np.lib.format.read_array_header_2_0(member)
            if (
                dtype.kind not in "biufcSU"
                or math.prod(shape) * dtype.itemsize != info.file_size - member.tell()
            ):
                raise SessionError("Invalid session array dtype or size")
            return (
                np.frombuffer(member.read(), dtype=dtype)
                .reshape(shape, order="F" if fortran else "C")
                .copy(order="K")
            )

    def read_record(self, index):
        if index in self.loaded:
            return self.loaded[index]
        record = self.records[index]
        name = record["type"]
        if name == "array":
            obj = self.read_array(index)
        elif name == "list":
            obj = []
            self.loaded[index] = obj
            obj.extend(self.decode(v) for v in record["items"])
        else:
            cls = _BY_NAME[name]
            attrs = record["fields"]
            if not isinstance(attrs, dict) or attrs.keys() != _RECORDS[cls]:
                raise SessionError(f"Incomplete or unknown fields for {name}")
            obj = object.__new__(cls)
            self.loaded[index] = obj
            for attr, value in attrs.items():
                decoded = self.decode(value)
                if (
                    cls is EtmConfig
                    and attr == "json_file"
                    and decoded is not None
                    and not isinstance(decoded, dict)
                ):
                    raise SessionError("A session must embed its ETM input")
                vars(obj)[attr] = decoded
            if isinstance(obj, data.BaseDataClass):
                data.BaseDataClass.__post_init__(obj)
            if cls is Mask:
                for suffix in ("c", "p"):
                    coords = [
                        getattr(obj, suffix + key).ravel() for key in ("_mx", "_my")
                    ]
                    setattr(obj, "kd_" + suffix, KDTree(np.column_stack(coords)))
        self.loaded[index] = obj
        return obj


def session_path(name):
    path = Path(name)
    if path.suffix.lower() == ".pkl":
        raise SessionError(
            "Legacy pickle sessions cannot be opened. Rebuild from station ETMs."
        )
    return path if path.suffix == ".etms" else Path(str(path) + ".etms")


def save_session(stacker: EtmStacker, name):
    """Atomically publish the complete session to the destination filesystem."""
    path = session_path(name)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            with zipfile.ZipFile(f, "w") as archive:
                writer = _Writer(archive)
                root = writer.encode(stacker)
                manifest = {
                    "format": _FORMAT,
                    "version": _VERSION,
                    "conventions": _CONVENTIONS,
                    "root": root,
                    "records": writer.records,
                }
                archive.writestr(
                    "session.json",
                    json.dumps(manifest, allow_nan=False, separators=(",", ":")),
                )
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return path


def _validate_stacker(stacker):
    if not isinstance(stacker, EtmStacker) or not isinstance(
        stacker.config, EtmStackerConfig
    ):
        raise SessionError("Missing stacker or configuration")
    if not isinstance(stacker.command_history, list) or not all(
        isinstance(cmd, str) for cmd in stacker.command_history
    ):
        raise SessionError("Invalid stacker command history")
    if type(stacker.solved) is not bool or not isinstance(stacker.grids, GridSystem):
        raise SessionError("Invalid stacker state")
    if not isinstance(stacker.constraint_registry, ConstraintRegistry):
        raise SessionError("Invalid constraint registry")
    if len(stacker.stations) != len(stacker.normal_equations):
        raise SessionError("Incomplete station equations")
    for station, equations in zip(stacker.stations, stacker.normal_equations):
        if (
            not isinstance(station, Station)
            or not isinstance(station.etm, EtmEngine)
            or not isinstance(equations, NormalEquations)
            or station.normal_equations is not equations
            or equations.station != str(station)
        ):
            raise SessionError("Inconsistent station or normal-equation identity")
    parameters = stacker.total_parameters
    if stacker.solved and (
        stacker.solution.shape != (3, parameters)
        or stacker.covariance.shape != (3 * parameters, 3 * parameters)
    ):
        raise SessionError("Stacked solution and covariance dimensions disagree")


def load_session(name) -> EtmStacker:
    path = session_path(name)
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len({m.filename for m in members}) != len(members) or any(
                m.compress_type != zipfile.ZIP_STORED for m in members
            ):
                raise SessionError("Invalid session archive members")
            manifest = json.loads(archive.read("session.json"))
            if manifest["format"] != _FORMAT or manifest["version"] not in (
                1,
                _VERSION,
            ):
                raise SessionError("Unsupported ETM session format or version")
            if manifest.get("conventions") != _CONVENTIONS:
                raise SessionError("Unknown component order or units in session")
            stacker = _Reader(archive, manifest["records"]).decode(manifest["root"])
            _validate_stacker(stacker)
            if manifest["version"] == 1:
                # Older writers kept cached results after station weights changed.
                # A file cannot tell us which weights produced its saved covariance.
                if stacker.solved:
                    warnings.warn(
                        "Version 1 session loaded. Run solve to recompute the stack "
                        "from its saved inputs and weights.",
                        UserWarning,
                        stacklevel=2,
                    )
                stacker._invalidate_solution()
            stacker.filename = str(path.with_suffix(""))
            return stacker
    except SessionError:
        raise
    except (
        zipfile.BadZipFile,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        AttributeError,
        InvalidOperation,
        OverflowError,
        RecursionError,
        EOFError,
    ) as exc:
        raise SessionError(f"Invalid ETM session {path}: {exc}") from exc
