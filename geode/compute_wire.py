"""Version-one processing message values. Only known scientific data types cross Redis."""

import base64
import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from enum import IntEnum
from io import BytesIO

import numpy as np

from geode.pyDate import Date


def _etm_enums():
    from geode.etm.core import type_declarations as enums

    return {
        cls.__name__: cls
        for cls in (
            enums.FitStatus,
            enums.PeriodicStatus,
            enums.EtmSolutionType,
            enums.JumpType,
            enums.NoiseModels,
            enums.AdjustmentModels,
            enums.CovarianceFunction,
            enums.SolutionType,
        )
    }


def encode(value):
    if isinstance(value, IntEnum):
        name = type(value).__name__
        if _etm_enums().get(name) is not type(value):
            raise TypeError(f"Unsupported processing enum {name}")
        return {"enum": [name, value.name]}
    if isinstance(value, np.ndarray):
        stream = BytesIO()
        np.save(stream, value, allow_pickle=False)
        return {"array": base64.b64encode(stream.getvalue()).decode("ascii")}
    if isinstance(value, np.generic):
        return {"scalar": encode(np.asarray(value))}
    if isinstance(value, Date):
        # Dates created from a fractional year can retain subsecond precision
        # beyond the calendar fields in Date.to_json().
        return {"gnss_date": [value.to_json(), encode(value.fyear)]}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    if isinstance(value, bytes):
        return {"bytes": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        # Preserve non-string keys and avoid collisions with type tags.
        return {"map": [[encode(key), encode(val)] for key, val in value.items()]}
    if isinstance(value, tuple):
        return {"tuple": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return {"float": str(value)}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported processing message value: {type(value).__name__}")


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if len(value) != 1:
        raise ValueError("Invalid processing value")
    tag, data = next(iter(value.items()))
    if tag == "enum":
        name, member = data
        return _etm_enums()[name][member]
    if tag == "map":
        return {decode(key): decode(val) for key, val in data}
    if tag == "tuple":
        return tuple(decode(item) for item in data)
    if tag == "scalar":
        array = decode(data)
        if not isinstance(array, np.ndarray) or array.shape != ():
            raise ValueError("Invalid processing scalar")
        return array[()]
    if tag == "gnss_date":
        parts, fyear = data
        result = Date(**parts)
        result.fyear = decode(fyear)
        return result
    if tag == "date":
        return date.fromisoformat(data)
    if tag == "datetime":
        return datetime.fromisoformat(data)
    if tag == "decimal":
        return Decimal(data)
    if tag == "float":
        return float(data)
    if tag == "bytes":
        return base64.b64decode(data, validate=True)
    if tag == "array":
        stream = BytesIO(base64.b64decode(data, validate=True))
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise ValueError(f"Unsupported processing array version {version}")
        raw = stream.read()
        if dtype.hasobject or math.prod(shape) * dtype.itemsize != len(raw):
            raise ValueError("Invalid fixed-width processing array")
        array = np.frombuffer(raw, dtype=dtype).reshape(
            shape, order="F" if fortran else "C"
        )
        return array.copy(order="K")
    raise ValueError(f"Unknown processing data type {tag!r}")


def fingerprint(operation, encoded, checks):
    data = json.dumps(
        [operation, encoded, json.loads(checks)],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
