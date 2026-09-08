"""
ETM Stacker - Backward compatibility wrapper.

This module re-exports all classes from geode.etm.stacker for backward compatibility.
All implementation has been moved to geode/etm/stacker/.
"""

# Re-export all public classes from the stacker package
from ..stacker import (
    # Constraints
    BaseConstraint,
    ConstraintEquation,
    ConstraintRegistry,
    # Types
    ConstraintType,
    CoseismicConstraint,
    # Jump functions
    CoseismicJumpFunction,
    # Main stacker
    EtmStacker,
    # Data classes
    EtmStackerConfig,
    # Exceptions
    EtmStackerException,
    EtmStackerField,
    # Grid system
    GridSystem,
    InterseismicConstraint,
    NormalEquations,
    PostseismicConstraint,
    PostseismicJumpFunction,
    Station,
    fill_region_with_grid,
    visualize_disks,
    visualize_vectors,
)

# For backward compatibility with older import statements
__all__ = [
    "ConstraintType",
    "EtmStackerException",
    "CoseismicJumpFunction",
    "PostseismicJumpFunction",
    "EtmStackerConfig",
    "NormalEquations",
    "Station",
    "ConstraintEquation",
    "EtmStackerField",
    "GridSystem",
    "fill_region_with_grid",
    "visualize_disks",
    "visualize_vectors",
    "EtmStacker",
    "BaseConstraint",
    "InterseismicConstraint",
    "CoseismicConstraint",
    "PostseismicConstraint",
    "ConstraintRegistry",
]
