"""Backend integration tests; run with pixi run -e web pytest."""

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("django", reason="Use the Pixi web environment for backend tests")


@pytest.fixture
def api_db(postgres_connection, monkeypatch):
    import django
    from django.conf import settings

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "web/backend"))
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "local-antenna-tests")
    monkeypatch.setenv("POSTGRES_HOST", postgres_connection.info.host)
    monkeypatch.setenv("POSTGRES_PORT", "55439")
    monkeypatch.setenv("POSTGRES_USER", "geode_test")
    monkeypatch.setenv("POSTGRES_DB", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "")
    django.setup()
    from auditlog.context import disable_auditlog
    from django.db import connection

    connection.close()
    settings.DATABASES["default"].update(
        HOST=postgres_connection.info.host,
        PORT="55439",
        USER="geode_test",
        NAME="postgres",
        PASSWORD="",
    )
    subprocess.run(
        [
            shutil.which("psql"),
            "-h",
            postgres_connection.info.host,
            "-p",
            "55439",
            "-U",
            "geode_test",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(root / "database/schema.sql"),
        ],
        check=True,
        capture_output=True,
    )
    postgres_connection.execute("""
        CREATE TABLE api_stationmeta (station_id integer, has_gaps_update_needed boolean, has_stationinfo boolean);
        INSERT INTO antennas ("AntennaCode") VALUES ('TEST');
        INSERT INTO antenna_radomes ("AntennaCode", "RadomeCode") VALUES ('TEST', 'NONE'), ('TEST', 'SCIS');
        INSERT INTO gamit_htc ("AntennaCode", "HeightCode") VALUES ('TEST', 'DHARP');
        INSERT INTO receivers ("ReceiverCode") VALUES ('RECEIVER');
        INSERT INTO networks ("NetworkCode") VALUES ('tst');
        INSERT INTO stations ("NetworkCode", "StationCode") VALUES ('tst', 'test');
    """)
    # The processing bootstrap does not include the Django auth/audit tables.
    with disable_auditlog():
        yield connection
    connection.close()


def station_payload():
    return dict(
        network_code="tst",
        station_code="test",
        antenna_code="TEST",
        radome_code="NONE",
        receiver_code="RECEIVER",
        height_code="DHARP",
        date_start="2020-01-01T00:00:00",
        antenna_height=0,
        antenna_north=0,
        antenna_east=0,
    )


def test_station_serializer_create_and_partial_updates(api_db):
    from api.serializers import StationinfoSerializer

    serializer = StationinfoSerializer(data=station_payload())
    assert serializer.is_valid(), serializer.errors
    record = serializer.save()
    partial = StationinfoSerializer(
        record, data={"comments": "Only a comment"}, partial=True
    )
    assert partial.is_valid(), partial.errors
    partial.save()
    changed = StationinfoSerializer(record, data={"radome_code": "SCIS"}, partial=True)
    assert changed.is_valid(), changed.errors
    changed.save()
    invalid = StationinfoSerializer(record, data={"radome_code": "BOGU"}, partial=True)
    assert not invalid.is_valid()
    assert "radome_code" in invalid.errors
    record.refresh_from_db()
    assert record.radome_code == "SCIS"
    invalid_height = StationinfoSerializer(
        record, data={"height_code": "BOGU"}, partial=True
    )
    assert not invalid_height.is_valid()
    assert "height_code" in invalid_height.errors
    invalid_date = StationinfoSerializer(
        record, data={"date_end": "2019-01-01T00:00:00"}, partial=True
    )
    assert not invalid_date.is_valid()


def test_unknown_or_missing_radome_is_not_silently_registered(api_db):
    from api.models import AntennaRadomes
    from api.serializers import StationinfoSerializer

    for radome in ("BOGU", ""):
        serializer = StationinfoSerializer(
            data={**station_payload(), "radome_code": radome}
        )
        assert not serializer.is_valid()
        assert "radome_code" in serializer.errors
        assert not AntennaRadomes.objects.filter(radome_code=radome).exists()


def test_catalog_api_filter_create_update_delete(api_db):
    from api.models import AntennaRadomes
    from api.serializers import StationinfoSerializer
    from api.views import AntennaRadomeDetail, AntennaRadomeList
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    listing = AntennaRadomeList.as_view(
        authentication_classes=[], permission_classes=[]
    )
    detail = AntennaRadomeDetail.as_view(
        authentication_classes=[], permission_classes=[]
    )
    response = listing(
        factory.get(
            "/api/antenna-radomes", {"antenna_code": "TEST", "radome_code": "SCIS"}
        )
    )
    assert response.status_code == 200
    assert [row["radome_code"] for row in response.data["data"]] == ["SCIS"]
    response = listing(
        factory.post(
            "/api/antenna-radomes",
            {"antenna_code": "test", "radome_code": "snow"},
            format="json",
        )
    )
    assert response.status_code == 201, response.data
    pk = response.data["api_id"]
    duplicate = listing(
        factory.post(
            "/api/antenna-radomes",
            {"antenna_code": "TEST", "radome_code": "SNOW"},
            format="json",
        )
    )
    assert duplicate.status_code == 400
    update = detail(
        factory.patch(
            f"/api/antenna-radomes/{pk}", {"radome_code": "SCIT"}, format="json"
        ),
        pk=pk,
    )
    assert update.status_code == 200, update.data
    assert update.data["api_id"] == pk
    deleted = detail(factory.delete(f"/api/antenna-radomes/{pk}"), pk=pk)
    assert deleted.status_code == 204
    serializer = StationinfoSerializer(data=station_payload())
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    used_pk = AntennaRadomes.objects.get(radome_code="NONE").pk
    protected = detail(factory.delete(f"/api/antenna-radomes/{used_pk}"), pk=used_pk)
    assert protected.status_code == 400
    assert AntennaRadomes.objects.filter(pk=used_pk).exists()


def test_django_migration_matches_model_and_reuses_processing_schema(api_db):
    from api.models import AntennaRadomes
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.state import ModelState

    loader = MigrationLoader(None)
    state = loader.project_state([("api", "0034_processing_diagnostics")])
    migration = loader.get_migration("api", "0035_antenna_radomes")
    from api.models import AntennaRadomes

    before = list(AntennaRadomes.objects.values_list("api_id", flat=True))
    with api_db.schema_editor() as editor:
        new_state = migration.apply(state, editor)
    assert list(AntennaRadomes.objects.values_list("api_id", flat=True)) == before
    migrated = new_state.models["api", "antennaradomes"]
    current = ModelState.from_model(AntennaRadomes)
    assert migrated.fields.keys() == current.fields.keys()
    for name in current.fields:
        assert migrated.fields[name].deconstruct() == current.fields[name].deconstruct()
    assert migrated.options == current.options


def test_permissions_migration_preserves_read_and_write_boundaries(api_db):
    from api import models
    from django.apps import apps

    with api_db.schema_editor() as editor:
        for model in (
            models.Endpoint,
            models.Resource,
            models.ClusterType,
            models.EndPointsCluster,
        ):
            editor.create_model(model)
    resource = models.Resource.objects.create(name="Station")
    kind = models.ClusterType.objects.create(name="Read")
    read = models.EndPointsCluster.objects.create(
        resource=resource, cluster_type=kind, role_type="FRONT", description="Reader"
    )
    edit = models.EndPointsCluster.objects.create(
        resource=resource,
        cluster_type=kind,
        role_type="API",
        description="Catalog editor",
    )
    unrelated = models.EndPointsCluster.objects.create(
        resource=resource,
        cluster_type=models.ClusterType.objects.create(name="Write"),
        role_type="FRONT",
        description="Station editor",
    )
    read.endpoints.add(
        models.Endpoint.objects.create(path="/api/antennas", method="GET")
    )
    edit.endpoints.add(
        models.Endpoint.objects.create(path="/api/antennas", method="POST")
    )
    unrelated.endpoints.add(
        models.Endpoint.objects.create(path="/api/station-info", method="POST")
    )
    migration = importlib.import_module(
        "api.migrations.0036_antenna_catalog_permissions"
    )
    with api_db.schema_editor() as editor:
        migration.add_catalog_endpoints(apps, editor)
        migration.add_catalog_endpoints(apps, editor)
    assert read.endpoints.filter(path="/api/antenna-radomes", method="GET").exists()
    assert not read.endpoints.filter(
        path="/api/antenna-radomes", method="POST"
    ).exists()
    assert edit.endpoints.filter(path="/api/antenna-radomes", method="POST").exists()
    assert not unrelated.endpoints.filter(path="/api/antenna-radomes").exists()
    assert (
        models.Endpoint.objects.filter(path__startswith="/api/antenna-radomes").count()
        == 6
    )


def test_legacy_blank_radome_can_be_retained_on_existing_history(api_db):
    from api.serializers import StationinfoSerializer

    serializer = StationinfoSerializer(data=station_payload())
    assert serializer.is_valid(), serializer.errors
    record = serializer.save()
    # Simulate a blank value preserved by migration from pre-catalog history.
    with api_db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO antenna_radomes (\"AntennaCode\", \"RadomeCode\") VALUES ('TEST', '')"
        )
        cursor.execute(
            "UPDATE stationinfo SET \"RadomeCode\" = '' WHERE api_id = %s", [record.pk]
        )
    record.refresh_from_db()
    update = StationinfoSerializer(
        record, data={"comments": "Retain historical metadata"}, partial=True
    )
    assert update.is_valid(), update.errors
    update.save()
    record.refresh_from_db()
    assert record.radome_code == ""
