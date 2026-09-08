"""Expose catalog endpoints while retaining existing role boundaries."""

from django.db import migrations


def add_catalog_endpoints(apps, schema_editor):
    Endpoint = apps.get_model('api', 'Endpoint')
    Cluster = apps.get_model('api', 'EndPointsCluster')
    db = schema_editor.connection.alias
    for suffix, methods in [('', ['GET', 'POST']), ('/<PATH_PARAM>', ['GET', 'PUT', 'PATCH', 'DELETE'])]:
        for method in methods:
            endpoint, _ = Endpoint.objects.using(db).get_or_create(
                path='/api/antenna-radomes' + suffix, method=method)
            # Existing antenna-catalog readers/writers gain the matching operation
            # on combinations. Do not grant writes to station-only editors.
            for cluster in Cluster.objects.using(db).filter(
                endpoints__path='/api/antennas' + suffix,
                endpoints__method__in=[method, 'ALL'],
            ).distinct():
                cluster.endpoints.add(endpoint)


class Migration(migrations.Migration):
    dependencies = [('api', '0035_antenna_radomes')]
    operations = [migrations.RunPython(add_catalog_endpoints, migrations.RunPython.noop)]
