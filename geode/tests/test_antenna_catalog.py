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
