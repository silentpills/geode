"""Regression checks for the security workflow's dependency selection."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "audit_requirements",
    Path(__file__).resolve().parents[2] / "tools/audit_requirements.py",
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_pixi_kind_selects_runtime_dependencies():
    assert (
        exporter.requirements(
            [
                {"name": "django", "version": "5.2.17", "kind": "pypi"},
                {"name": "geode_gnss", "version": None, "kind": "pypi"},
                {"name": "numpy", "version": "2.4.1", "kind": "conda"},
            ]
        )
        == "django==5.2.17\n"
    )


def test_empty_or_changed_schema_cannot_pass_audit():
    with pytest.raises(ValueError, match="empty audit"):
        exporter.requirements([{"name": "django", "version": "5.2.17", "type": "pypi"}])
