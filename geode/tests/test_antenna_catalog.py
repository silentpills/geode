"""Catalog migrations and station constraints against a real PostgreSQL server."""

from importlib.resources import files

import psycopg
import pytest

LEGACY_SCHEMA = """
CREATE TABLE antennas (
    "AntennaCode" varchar(22) PRIMARY KEY,
    "AntennaDescription" text,
    api_id serial UNIQUE
);
CREATE TABLE gamit_htc (
    "AntennaCode" varchar(22) REFERENCES antennas("AntennaCode")
        ON UPDATE CASCADE ON DELETE CASCADE,
    "HeightCode" varchar(5),
    PRIMARY KEY ("AntennaCode", "HeightCode")
);
CREATE TABLE stationinfo (
    api_id serial PRIMARY KEY,
    "AntennaCode" varchar(22) REFERENCES antennas("AntennaCode")
        ON UPDATE CASCADE ON DELETE RESTRICT,
    "RadomeCode" varchar(7) NOT NULL
);
INSERT INTO antennas ("AntennaCode", api_id) VALUES ('TEST', 42), ('UNUSED', 43);
INSERT INTO gamit_htc VALUES ('TEST', 'DHARP');
INSERT INTO stationinfo ("AntennaCode", "RadomeCode")
    VALUES ('TEST', 'NONE'), ('TEST', 'SCIS'), ('TEST', 'SCIS'), ('TEST', '');
"""


@pytest.fixture
def catalog_db(postgres_connection):
    cnn = postgres_connection
    cnn.execute(LEGACY_SCHEMA)
    with cnn.transaction():
        cnn.execute(files("geode").joinpath("sql/antenna_radomes_v1.sql").read_text())
    return cnn


def test_migration_preserves_history_and_ids_and_is_repeatable(catalog_db):
    cnn = catalog_db
    rows = cnn.execute("SELECT * FROM antenna_radomes ORDER BY api_id").fetchall()
    assert {row[1:] for row in rows} == {
        ("TEST", "NONE"),
        ("TEST", "SCIS"),
        ("TEST", ""),
    }
    with cnn.transaction():
        cnn.execute(files("geode").joinpath("sql/antenna_radomes_v1.sql").read_text())
    assert (
        cnn.execute("SELECT * FROM antenna_radomes ORDER BY api_id").fetchall() == rows
    )
    assert cnn.execute(
        "SELECT api_id FROM antennas WHERE \"AntennaCode\" = 'TEST'"
    ).fetchone() == (42,)
    assert cnn.execute("SELECT count(*) FROM stationinfo").fetchone() == (4,)
    # Unused models do not gain an invented NONE combination.
    assert cnn.execute(
        "SELECT count(*) FROM antenna_radomes WHERE \"AntennaCode\" = 'UNUSED'"
    ).fetchone() == (0,)


def test_catalog_foreign_keys_and_model_height_conversions(catalog_db):
    cnn = catalog_db
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cnn.execute(
            "INSERT INTO stationinfo (\"AntennaCode\", \"RadomeCode\") VALUES ('TEST', 'BOGU')"
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cnn.execute("UPDATE stationinfo SET \"RadomeCode\" = 'BOGU' WHERE api_id = 1")
    with pytest.raises(psycopg.IntegrityError):
        cnn.execute("DELETE FROM antenna_radomes WHERE \"RadomeCode\" = 'SCIS'")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        cnn.execute(
            "INSERT INTO antenna_radomes (\"AntennaCode\", \"RadomeCode\") VALUES ('MISSING', 'NONE')"
        )
    with pytest.raises(psycopg.errors.UniqueViolation):
        cnn.execute(
            "INSERT INTO antenna_radomes (\"AntennaCode\", \"RadomeCode\") VALUES ('TEST', 'NONE')"
        )
    ids = cnn.execute("SELECT api_id FROM antenna_radomes ORDER BY api_id").fetchall()
    cnn.execute("UPDATE antennas SET \"AntennaCode\" = 'RENAMED' WHERE api_id = 42")
    assert cnn.execute('SELECT DISTINCT "AntennaCode" FROM stationinfo').fetchall() == [
        ("RENAMED",)
    ]
    assert cnn.execute('SELECT "AntennaCode" FROM gamit_htc').fetchall() == [
        ("RENAMED",)
    ]
    assert (
        cnn.execute("SELECT api_id FROM antenna_radomes ORDER BY api_id").fetchall()
        == ids
    )
    with pytest.raises(psycopg.IntegrityError):
        cnn.execute("DELETE FROM antennas WHERE api_id = 42")


def atx_record(value, label):
    return f"{value:<60}{label}\n"


def sample_antex():
    return (
        atx_record("     1.4            M", "ANTEX VERSION / SYST")
        + atx_record("", "END OF HEADER")
        + atx_record("", "START OF ANTENNA")
        + atx_record("TEST            NONE", "TYPE / SERIAL NO")
        + atx_record("", "END OF ANTENNA")
        + atx_record("", "START OF ANTENNA")
        + atx_record("TEST            SCIS", "TYPE / SERIAL NO")
        + atx_record("", "END OF ANTENNA")
        + atx_record("", "START OF ANTENNA")
        + atx_record("BLOCK IIA           G01                 G032", "TYPE / SERIAL NO")
        + atx_record("", "END OF ANTENNA")
    )


def test_import_preserves_pair_identity_and_descriptions(catalog_db, tmp_path):
    from geode.metadata.antenna_catalog import parse_antex_pairs, register_pairs

    path = tmp_path / "test.atx"
    path.write_text(sample_antex())
    assert parse_antex_pairs(path) == [("TEST", "NONE"), ("TEST", "SCIS")]
    before = catalog_db.execute(
        "SELECT * FROM antenna_radomes ORDER BY api_id"
    ).fetchall()
    assert register_pairs(catalog_db, parse_antex_pairs(path)) == 0
    assert (
        catalog_db.execute("SELECT * FROM antenna_radomes ORDER BY api_id").fetchall()
        == before
    )
    catalog_db.execute(
        "UPDATE antennas SET \"AntennaDescription\" = 'Existing description'"
    )
    assert register_pairs(catalog_db, [(" test ", " snow "), ("NEW", "NONE")]) == 2
    assert catalog_db.execute(
        'SELECT "AntennaDescription" FROM antennas WHERE "AntennaCode" = \'TEST\''
    ).fetchone() == ("Existing description",)
    # A bad code rejects the entire batch before any model or combination is added.
    with pytest.raises(ValueError):
        register_pairs(catalog_db, [("UNWRITTEN", "NONE"), ("TEST", "")])
    assert catalog_db.execute(
        "SELECT count(*) FROM antennas WHERE \"AntennaCode\" = 'UNWRITTEN'"
    ).fetchone() == (0,)


@pytest.mark.parametrize(
    "content",
    [
        "not an ANTEX file",
        sample_antex().replace("     1.4", "     2.0"),
        sample_antex().rsplit("END OF ANTENNA", 1)[0],
    ],
)
def test_invalid_antex_is_rejected(tmp_path, content):
    from geode.metadata.antenna_catalog import parse_antex_pairs

    path = tmp_path / "bad.atx"
    path.write_text(content)
    with pytest.raises(ValueError):
        parse_antex_pairs(path)


def test_cli_preview_needs_no_database(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "com.AntennaCatalog",
            "--dry-run",
            "add",
            "test",
            "none",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "TEST NONE\n"


def test_station_import_rejects_unregistered_pair_before_edits(catalog_db):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from geode.metadata.station_info import (
        StationInfo,
        StationInfoException,
        StationInfoRecord,
    )

    station = StationInfo.__new__(StationInfo)
    station.NetworkCode, station.StationCode = "tst", "test"
    station.cnn = SimpleNamespace(
        cursor=catalog_db.cursor(), insert_event=Mock(), update=Mock()
    )
    record = StationInfoRecord("tst", "test", AntennaCode="TEST", RadomeCode="BOGU")
    with pytest.raises(StationInfoException, match="Unregistered antenna/radome"):
        station.insert_station_info(record)
    with pytest.raises(StationInfoException, match="Unregistered antenna/radome"):
        station.update_station_info(record, record)
    station.cnn.insert_event.assert_not_called()
    station.cnn.update.assert_not_called()
    assert catalog_db.execute(
        "SELECT count(*) FROM antenna_radomes WHERE \"RadomeCode\" = 'BOGU'"
    ).fetchone() == (0,)
