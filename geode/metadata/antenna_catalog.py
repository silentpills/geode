"""Registration of equipment identities, independent of calibration selection."""

from pathlib import Path


def normalize_pair(antenna_code: str, radome_code: str) -> tuple[str, str]:
    """Normalize explicit codes; a missing radome must never imply NONE."""
    pair = (antenna_code.strip().upper(), radome_code.strip().upper())
    for value, limit, name in zip(pair, (22, 7), ("antenna", "radome")):
        if (
            not value
            or len(value) > limit
            or not value.isascii()
            or any(c.isspace() for c in value)
        ):
            raise ValueError(
                f"Invalid {name} code: use 1–{limit} non-space ASCII characters."
            )
    return pair


def parse_antex_pairs(path: str | Path) -> list[tuple[str, str]]:
    """Read explicitly coded receiver antenna/radome pairs from ANTEX 1.4.

    Fixed columns distinguish the model (1–15), separator (16), and radome
    (17–20). Satellite records have no radome and/or satellite IDs in 41–60.
    No calibration values are imported or evaluated. Validate section boundaries
    before returning so truncated files cannot cause partial catalog imports.
    """
    pairs = set()
    in_antenna = False
    type_seen = False
    header_done = False
    with Path(path).open(encoding="ascii") as stream:
        for number, line in enumerate(stream, 1):
            label = line[60:80].strip()
            if number == 1:
                if label != "ANTEX VERSION / SYST" or line[:8].strip() != "1.4":
                    raise ValueError("Expected an ANTEX 1.4 file.")
            if label == "END OF HEADER":
                header_done = True
            elif label == "START OF ANTENNA":
                if not header_done or in_antenna:
                    raise ValueError(f"Unexpected antenna section at line {number}.")
                in_antenna, type_seen = True, False
            elif label == "TYPE / SERIAL NO":
                if not in_antenna or type_seen:
                    raise ValueError(f"Unexpected antenna identity at line {number}.")
                type_seen = True
                radome = line[16:20].strip()
                if radome and not line[40:60].strip():
                    if line[15:16] != " ":
                        raise ValueError(
                            f"Invalid antenna/radome separator at line {number}."
                        )
                    pairs.add(normalize_pair(line[:15], radome))
            elif label == "END OF ANTENNA":
                if not in_antenna or not type_seen:
                    raise ValueError(f"Incomplete antenna section at line {number}.")
                in_antenna = False
    if in_antenna or not header_done:
        raise ValueError("Incomplete ANTEX file.")
    if not pairs:
        raise ValueError("No explicit receiver antenna/radome combinations found.")
    return sorted(pairs)


def register_pairs(connection, pairs) -> int:
    """Atomically register explicit pairs and missing models; retain existing IDs."""
    pairs = sorted({normalize_pair(*pair) for pair in pairs})
    added = 0
    with connection.transaction():
        with connection.cursor() as cursor:
            for antenna, radome in pairs:
                cursor.execute(
                    'INSERT INTO antennas ("AntennaCode") VALUES (%s) '
                    'ON CONFLICT ("AntennaCode") DO NOTHING',
                    (antenna,),
                )
                cursor.execute(
                    'INSERT INTO antenna_radomes ("AntennaCode", "RadomeCode") '
                    'VALUES (%s, %s) ON CONFLICT ("AntennaCode", "RadomeCode") DO NOTHING',
                    (antenna, radome),
                )
                added += cursor.rowcount
    return added
