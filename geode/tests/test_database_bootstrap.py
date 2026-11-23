"""Exercise the complete Django history on isolated PostgreSQL databases."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("django", reason="Use the Pixi web environment")
ROOT = Path(__file__).resolve().parents[2]


def manage(cnn, *arguments, check=True, env=None):
    environment = {
        **os.environ,
        "POSTGRES_HOST": cnn.info.host,
        "POSTGRES_PORT": str(cnn.info.port),
        "POSTGRES_USER": cnn.info.user,
        "POSTGRES_DB": cnn.info.dbname,
        "POSTGRES_PASSWORD": "",
        "DJANGO_SECRET_KEY": "isolated-bootstrap-tests-secret-over-32-characters",
        "PGOPTIONS": "-c lock_timeout=5000",
        **(env or {}),
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "web/backend/manage.py"), *arguments],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if check and result.returncode:
        pytest.fail(result.stdout[-2000:] + result.stderr[-5000:])
    return result


@pytest.mark.parametrize("starting_point", ["empty", "sql"])
def test_complete_migration_chain(postgres_connection, postgres_bin, starting_point):
    cnn = postgres_connection
    if starting_point == "sql":
        subprocess.run(
            [
                postgres_bin / "psql",
                "-h",
                cnn.info.host,
                "-p",
                str(cnn.info.port),
                "-U",
                cnn.info.user,
                "-d",
                cnn.info.dbname,
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(ROOT / "database/schema.sql"),
            ],
            check=True,
            capture_output=True,
        )
        cnn.execute(
            "INSERT INTO antennas (\"AntennaCode\", api_id) VALUES ('PRESERVED', 9001)"
        )
    manage(cnn, "migrate", "--noinput")
    manage(cnn, "migrate", "--noinput")
    manage(cnn, "makemigrations", "--check", "--dry-run")
    manage(cnn, "migrate", "--check")
    assert cnn.execute("SELECT count(*) FROM api_user").fetchone() == (0,)
    assert cnn.execute(
        "SELECT to_regclass('antenna_radomes') IS NOT NULL"
    ).fetchone() == (True,)
    if starting_point == "sql":
        assert cnn.execute(
            "SELECT api_id FROM antennas WHERE \"AntennaCode\" = 'PRESERVED'"
        ).fetchone() == (9001,)
    else:
        assert cnn.execute("SELECT count(*) FROM antennas").fetchone()[0] > 100


def test_incomplete_schema_is_not_replaced(postgres_connection):
    cnn = postgres_connection
    cnn.execute("CREATE TABLE antennas (sentinel text)")
    cnn.execute("INSERT INTO antennas VALUES ('preserved')")
    result = manage(cnn, "migrate", "--noinput", check=False)
    assert result.returncode != 0
    assert "Incomplete processing schema" in result.stderr
    assert cnn.execute("SELECT sentinel FROM antennas").fetchall() == [("preserved",)]


def test_historical_django_suite(postgres_connection):
    manage(postgres_connection, "test", "api", "--noinput", "--verbosity", "1")


def test_admin_readiness_and_backup(postgres_connection, postgres_bin, tmp_path):
    cnn = postgres_connection
    manage(cnn, "migrate", "--noinput")
    missing = manage(
        cnn,
        "createadmin",
        "--username",
        "operator",
        "--noinput",
        check=False,
        env={"DJANGO_SUPERUSER_PASSWORD": ""},
    )
    assert missing.returncode != 0
    assert cnn.execute("SELECT count(*) FROM api_user").fetchone() == (0,)
    credentials = {"DJANGO_SUPERUSER_PASSWORD": "isolated-test-operator-92!"}
    manage(cnn, "createadmin", "--username", "operator", "--noinput", env=credentials)
    assert cnn.execute("SELECT is_superuser, is_staff FROM api_user").fetchone() == (
        True,
        True,
    )
    duplicate = manage(
        cnn,
        "createadmin",
        "--username",
        "operator",
        "--noinput",
        env=credentials,
        check=False,
    )
    assert duplicate.returncode != 0
    probe = "from django.test import Client; assert Client().get('/api/health-check', HTTP_HOST='localhost').status_code == {}"
    manage(cnn, "shell", "-c", probe.format(200))
    manage(cnn, "shell", "-c", probe.format(200), env={"DJANGO_HTTPS": "True"})
    # The readiness view must be reachable without opening an ATOMIC_REQUESTS
    # transaction first, so it can report a dead database as 503 instead of 500.
    unavailable = (
        "from django.test import Client; from django.db import connection; "
        "connection.close(); connection.settings_dict['HOST'] = '/no-geode-database'; "
        "connection.settings_dict['OPTIONS']['connect_timeout'] = 1; "
        "assert Client().get('/api/health-check', HTTP_HOST='localhost').status_code == 503"
    )
    manage(cnn, "shell", "-c", unavailable)
    manage(cnn, "wait_for_database", "--timeout", "0")
    waiting = manage(
        cnn,
        "wait_for_database",
        "--timeout",
        "0",
        check=False,
        env={"POSTGRES_HOST": "/no-geode-database"},
    )
    assert waiting.returncode != 0
    doctor = (
        "from django.conf import settings; from django.core.management import call_command; "
        f"settings.MEDIA_ROOT = {str(tmp_path)!r}; call_command('doctor')"
    )
    checked = manage(
        cnn, "shell", "-c", doctor, env={"POSTGRES_PASSWORD": "doctor-test-password"}
    )
    assert "Configuration checks passed" in checked.stdout
    assert "doctor-test-password" not in checked.stdout + checked.stderr

    cnn.execute(
        "DELETE FROM django_migrations WHERE id = ("
        "SELECT id FROM django_migrations WHERE app='api' ORDER BY id DESC LIMIT 1)"
    )
    manage(cnn, "shell", "-c", probe.format(503))
    manage(cnn, "migrate", "--noinput")
    cnn.execute("""INSERT INTO networks ("NetworkCode") VALUES ('tst')""")
    cnn.execute("""INSERT INTO stations ("NetworkCode", "StationCode", api_id)
                   VALUES ('tst', 'keep', 9012)""")
    archive = tmp_path / "backup.dump"
    connection_args = [
        "-h",
        cnn.info.host,
        "-p",
        str(cnn.info.port),
        "-U",
        cnn.info.user,
    ]
    subprocess.run(
        [
            postgres_bin / "pg_dump",
            *connection_args,
            "-d",
            cnn.info.dbname,
            "-Fc",
            "-f",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )
    cnn.execute("CREATE ROLE restore_owner LOGIN")
    cnn.execute("CREATE ROLE restore_web LOGIN")
    cnn.execute("CREATE DATABASE restore_check OWNER restore_owner")
    restore_args = [
        "-h",
        cnn.info.host,
        "-p",
        str(cnn.info.port),
        "-U",
        "restore_owner",
    ]
    subprocess.run(
        [
            postgres_bin / "pg_restore",
            *restore_args,
            "-d",
            "restore_check",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            postgres_bin / "psql",
            *restore_args,
            "-d",
            "restore_check",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            ROOT / "database/grant-app-access.sql",
        ],
        env={**os.environ, "GEODE_OWNER": "restore_owner", "GEODE_APP": "restore_web"},
        check=True,
        capture_output=True,
    )
    restored = {"POSTGRES_DB": "restore_check", "POSTGRES_USER": "restore_web"}
    manage(cnn, "migrate", "--check", env=restored)
    manage(
        cnn,
        "shell",
        "-c",
        "from api.models import Stations; from django.test import Client; "
        "from django.db import connection; "
        "assert Stations.objects.get(station_code='keep').pk == 9012; "
        "assert Client().login(username='operator', password='isolated-test-operator-92!'); "
        "c = connection.cursor(); "
        "c.execute(\"SELECT has_schema_privilege(current_user, 'geode_compute', 'USAGE')\"); "
        "assert c.fetchone() == (False,)",
        env=restored,
    )
