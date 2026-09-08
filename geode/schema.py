"""Versioned processing-schema bootstrap used by Django's initial migration."""

from importlib.resources import files

from psycopg import sql

CORE_TABLES = (
    "antennas",
    "receivers",
    "networks",
    "stations",
    "stationinfo",
    "sources_servers",
    "sources_stations",
)


def bootstrap_processing_schema(apps, schema_editor):
    """Create an empty database's core once; adopt an existing core without replacing it."""
    from django.db import transaction

    connection = schema_editor.connection
    with transaction.atomic(using=connection.alias):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(73501926)")
            existing = set(connection.introspection.table_names(cursor))
            present = existing.intersection(CORE_TABLES)
            if present and present != set(CORE_TABLES):
                raise RuntimeError(
                    "Incomplete processing schema. Restore a complete schema before migrating; no existing tables were replaced."
                )
            if present:
                return
            source = files("geode").joinpath("sql/bootstrap_v1/schema.sql").read_text()
            # psql guards and session settings are for manual imports. The Django
            # transaction owns commit/rollback and retains its connection settings.
            statements = "\n".join(
                line
                for line in source.splitlines()
                if not line.startswith(("\\", "SET ", "SELECT pg_catalog.set_config"))
                and line.strip() not in ("BEGIN;", "COMMIT;")
            )
            cursor.execute("SET LOCAL check_function_bodies = false")
            cursor.execute(statements)
            seed_reference_tables(cursor)


def seed_reference_tables(cursor):
    """Seed only a newly-created core, preserving the reference CSV identifiers."""
    for table in ("antennas", "gamit_htc", "keys", "receivers", "rinex_tank_struct"):
        source = files("geode").joinpath(f"sql/bootstrap_v1/csv/{table}.csv")
        query = sql.SQL("COPY {} FROM STDIN WITH CSV HEADER").format(
            sql.Identifier(table)
        )
        with cursor.cursor.copy(query) as copy:
            copy.write(source.read_bytes())
        cursor.execute(
            sql.SQL(
                "SELECT setval(pg_get_serial_sequence(%s, 'api_id'), COALESCE(MAX(api_id), 1), MAX(api_id) IS NOT NULL) FROM {}"
            ).format(sql.Identifier(table)),
            [table],
        )
