"""
ETM Stacker package for geodetic time series stacking.

This package provides functionality for stacking multiple GNSS station
time series to constrain interseismic velocities, coseismic displacements,
and postseismic relaxation using spatial interpolation methods.
"""

from .constraints import (
    BaseConstraint,
    ConstraintRegistry,
    CoseismicConstraint,
    InterseismicConstraint,
    PostseismicConstraint,
)
from .data_classes import (
    ConstraintEquation,
    EtmStackerConfig,
    EtmStackerField,
    NormalEquations,
    Station,
)
from .exceptions import EtmStackerException
from .grid_system import (
    GridSystem,
    fill_region_with_grid,
    visualize_disks,
    visualize_vectors,
)
from .jump_functions import CoseismicJumpFunction, PostseismicJumpFunction
from .stacker import EtmStacker
from .types import ConstraintType

__all__ = [
    # Types
    "ConstraintType",
    # Exceptions
    "EtmStackerException",
    # Jump functions
    "CoseismicJumpFunction",
    "PostseismicJumpFunction",
    # Data classes
    "EtmStackerConfig",
    "NormalEquations",
    "Station",
    "ConstraintEquation",
    "EtmStackerField",
    # Grid system
    "GridSystem",
    "fill_region_with_grid",
    "visualize_disks",
    "visualize_vectors",
    # Main stacker
    "EtmStacker",
    # Constraints
    "BaseConstraint",
    "InterseismicConstraint",
    "CoseismicConstraint",
    "PostseismicConstraint",
    "ConstraintRegistry",
]
