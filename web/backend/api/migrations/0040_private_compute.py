"""Keep processing claims outside the web runtime's public-schema grants."""

from importlib.resources import files

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("api", "0039_compute_jobs")]
    operations = [
        migrations.RunSQL(files("geode").joinpath("sql/compute_private_v1.sql").read_text())
    ]
