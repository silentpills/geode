"""Escape report text while preserving paths used to load local image assets."""

from copy import deepcopy
from dataclasses import fields, is_dataclass
from html import escape


def escape_report_text(value, field_name=""):
    if field_name.endswith(("_path", "_paths", "_base64")):
        return value
    if field_name == "station_images":
        return [(path, escape(str(caption))) for path, caption in value]
    if isinstance(value, str):
        return escape(value)
    if is_dataclass(value) and not isinstance(value, type):
        result = deepcopy(value)
        for field in fields(value):
            setattr(
                result,
                field.name,
                escape_report_text(getattr(value, field.name), field.name),
            )
        return result
    if isinstance(value, dict):
        return {key: escape_report_text(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [escape_report_text(item) for item in value]
    return value
