"""Atomic persistence of FixPlate coordinates and their fit provenance."""

from collections import Counter

import numpy as np
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from geode.Utils import lg2ct, stationID


def dominant(values):
    """Count observations, resolving equal counts by lexical identifier order."""
    counts = Counter(value for value in values if value is not None)
    return min(counts, key=lambda value: (-counts[value], value)) if counts else None


def frame_provenance(hdata, vdata, coefficients, source_stack, ppp=False):
    coefficients = np.asarray(coefficients, dtype=float).ravel()
    k = 1e-9 * 180 / np.pi * 3600 * 1000
    constraints = []
    for station in sorted(vdata, key=stationID):
        xyz = lg2ct(
            np.array([0.0]),
            np.array([0.0]),
            np.array([station["vu_external"]]),
            np.array([station["lat"]]),
            np.array([station["lon"]]),
        )
        constraints.append(
            dict(
                network_code=station["NetworkCode"],
                station_code=station["StationCode"],
                vx=float(xyz[0][0]),
                vy=float(xyz[1][0]),
                vz=float(xyz[2][0]),
            )
        )
    return dict(
        engine="ppp" if ppp else "gamit",
        source_stack=None if ppp else source_stack,
        fixed_plate=dominant(station.get("plate") for station in hdata),
        euler_pole=(coefficients[:3] * k).tolist(),
        euler_pole_stations=sorted(stationID(station) for station in hdata),
        translation_rate=coefficients[3:6].tolist() if len(coefficients) == 6 else None,
    ), constraints


def source_epochs(cnn, network, station, stack, ppp=False):
    """Retain the actual source identity of each saved station/day."""
    with cnn.cnn.cursor(row_factory=dict_row) as cursor:
        if ppp:
            cursor.execute(
                'SELECT "Year", "DOY", "ReferenceFrame" AS source FROM ppp_soln '
                'WHERE "NetworkCode" = %s AND "StationCode" = %s',
                (network, station),
            )
        else:
            cursor.execute(
                'SELECT "Year", "DOY", "Project" AS source FROM stacks '
                'WHERE "NetworkCode" = %s AND "StationCode" = %s AND name = %s '
                "AND engine = 'gamit'",
                (network, station, stack),
            )
        result = {}
        for row in cursor:
            key = (int(row["Year"]), int(row["DOY"]))
            if key in result:
                raise ValueError(
                    f"Ambiguous PPP reference frame for {network}.{station} {key}"
                )
            result[key] = row["source"]
        return result


def _same_vector(left, right):
    if left is None or right is None:
        return left is None and right is None
    return np.shape(left) == np.shape(right) and np.allclose(
        left, right, rtol=1e-10, atol=1e-12
    )


def _validate_sources(cursor, name, provenance):
    """Reject a changed/ambiguous source even when its old rows still exist."""
    if provenance["engine"] == "gamit":
        cursor.execute(
            "SELECT 1 FROM stacks saved WHERE saved.name = %s AND NOT EXISTS ("
            "SELECT 1 FROM stacks source WHERE source.name = %s "
            "AND source.engine = 'gamit' "
            'AND (source."NetworkCode", source."StationCode", source."Year", source."DOY", source."Project") = '
            '(saved."NetworkCode", saved."StationCode", saved."Year", saved."DOY", saved."Project")) LIMIT 1',
            (name, provenance["source_stack"]),
        )
    else:
        cursor.execute(
            "SELECT 1 FROM stacks saved WHERE saved.name = %s AND ("
            "SELECT count(*) FROM ppp_soln source WHERE "
            '(source."NetworkCode", source."StationCode", source."Year", source."DOY") = '
            '(saved."NetworkCode", saved."StationCode", saved."Year", saved."DOY")) <> 1 LIMIT 1',
            (name,),
        )
    if cursor.fetchone():
        raise ValueError(
            "Saved epochs have changed or ambiguous source provenance; rebuild the stack"
        )


def save_frame(cnn, name, provenance, constraints, batches, preserve=False):
    """Save all station batches or none, preserving the frame's public ID.

    Batches may be spooled to disk by the caller. Fit/ETM work must be completed
    before entry: legacy ETM writers commit their own database operations.
    """
    if not name or len(name) > 20:
        raise ValueError("Frame names must contain 1 to 20 characters")
    if provenance["source_stack"] == name:
        raise ValueError("Use a different output name from the source stack")
    engine = provenance["engine"]
    with cnn.cnn.transaction():
        with cnn.cnn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 73501927))", (name,)
            )
            cursor.execute(
                "SELECT * FROM reference_frames WHERE frame_name = %s FOR UPDATE",
                (name,),
            )
            existing = cursor.fetchone()
            cursor.execute(
                "SELECT DISTINCT engine FROM stacks WHERE name = %s", (name,)
            )
            owners = {row["engine"] for row in cursor}
            if (existing and existing["engine"] != engine) or owners - {engine}:
                raise ValueError(f"Stack {name} is owned by another processing engine")
            if preserve and (existing or owners):
                if not existing or existing["euler_pole"] is None:
                    raise ValueError(
                        "Cannot append without saved fit provenance; rebuild the stack"
                    )
                for field in ("source_stack", "fixed_plate", "euler_pole_stations"):
                    if existing[field] != provenance[field]:
                        raise ValueError(
                            f"Preserved frame has different {field}; rebuild the stack"
                        )
                for field in ("euler_pole", "translation_rate"):
                    if not _same_vector(existing[field], provenance[field]):
                        raise ValueError(
                            f"Preserved frame has different {field}; rebuild the stack"
                        )
                cursor.execute(
                    "SELECT network_code, station_code, vx, vy, vz FROM reference_frame_constraints "
                    "WHERE constraints_id = %s ORDER BY network_code, station_code",
                    (name,),
                )
                old_constraints = cursor.fetchall()
                new_constraints = sorted(
                    constraints,
                    key=lambda row: (row["network_code"], row["station_code"]),
                )
                if len(old_constraints) != len(new_constraints) or any(
                    old["network_code"] != new["network_code"]
                    or old["station_code"] != new["station_code"]
                    or not _same_vector(
                        [old[c] for c in ("vx", "vy", "vz")],
                        [new[c] for c in ("vx", "vy", "vz")],
                    )
                    for old, new in zip(old_constraints, new_constraints)
                ):
                    raise ValueError(
                        "Preserved frame has different VREF constraints; rebuild the stack"
                    )
            if preserve:
                cursor.execute(
                    'SELECT DISTINCT "NetworkCode", "StationCode" FROM stacks WHERE name = %s',
                    (name,),
                )
                retained = {(row["NetworkCode"], row["StationCode"]) for row in cursor}
                _validate_sources(cursor, name, provenance)
            else:
                retained = set()
                cursor.execute("DELETE FROM stacks WHERE name = %s", (name,))
            saved = 0
            for batch in batches:
                rows = [
                    dict(row, name=name, engine=engine)
                    for row in batch
                    if (row["NetworkCode"], row["StationCode"]) not in retained
                ]
                cnn.insert_many("stacks", rows)
                saved += len(rows)
            _validate_sources(cursor, name, provenance)
            cursor.execute(
                "SELECT COALESCE(\"Project\", 'gpspace') AS project, count(*) AS count "
                'FROM stacks WHERE name = %s GROUP BY "Project" ORDER BY count(*) DESC, "Project"',
                (name,),
            )
            projects = {row["project"]: row["count"] for row in cursor}
            if not projects:
                raise ValueError(
                    "No corrected coordinates were produced; existing frame was retained"
                )
            project = min(projects, key=lambda value: (-projects[value], value))
            if engine == "gamit":
                cursor.executemany(
                    "INSERT INTO gamit_projects(project) VALUES (%s) ON CONFLICT DO NOTHING",
                    [(project,) for project in projects],
                )
            cursor.execute(
                'SELECT min(make_date("Year"::int, 1, 1) + ("DOY"::int - 1)) AS first, '
                'max(make_date("Year"::int, 1, 1) + ("DOY"::int - 1)) AS last FROM stacks WHERE name = %s',
                (name,),
            )
            epochs = cursor.fetchone()
            cursor.execute(
                "INSERT INTO reference_frames (frame_name, engine, project, source_projects, source_stack, "
                "fixed_plate, euler_pole, euler_pole_stations, translation_rate, first_epoch, last_epoch) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (frame_name) DO UPDATE SET project=EXCLUDED.project, source_projects=EXCLUDED.source_projects, "
                "source_stack=EXCLUDED.source_stack, fixed_plate=EXCLUDED.fixed_plate, euler_pole=EXCLUDED.euler_pole, "
                "euler_pole_stations=EXCLUDED.euler_pole_stations, translation_rate=EXCLUDED.translation_rate, "
                "first_epoch=EXCLUDED.first_epoch, last_epoch=EXCLUDED.last_epoch",
                (
                    name,
                    engine,
                    project,
                    Jsonb(projects),
                    provenance["source_stack"],
                    provenance["fixed_plate"],
                    provenance["euler_pole"],
                    provenance["euler_pole_stations"],
                    provenance["translation_rate"],
                    epochs["first"],
                    epochs["last"],
                ),
            )
            if not preserve or not existing:
                # Keep public IDs for constraints that survive a replacement.
                keys = [
                    (row["network_code"], row["station_code"]) for row in constraints
                ]
                cursor.execute(
                    "SELECT network_code, station_code FROM reference_frame_constraints "
                    "WHERE constraints_id = %s",
                    (name,),
                )
                for old in cursor.fetchall():
                    key = (old["network_code"], old["station_code"])
                    if key not in keys:
                        cursor.execute(
                            "DELETE FROM reference_frame_constraints WHERE constraints_id = %s "
                            "AND network_code = %s AND station_code = %s",
                            (name, *key),
                        )
                cursor.executemany(
                    "INSERT INTO reference_frame_constraints "
                    "(constraints_id, network_code, station_code, vx, vy, vz) VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (constraints_id, network_code, station_code) "
                    "DO UPDATE SET vx=EXCLUDED.vx, vy=EXCLUDED.vy, vz=EXCLUDED.vz",
                    [
                        (
                            name,
                            row["network_code"],
                            row["station_code"],
                            row["vx"],
                            row["vy"],
                            row["vz"],
                        )
                        for row in constraints
                    ],
                )
            return saved
