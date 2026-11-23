"""Durable execution receipts for processing workers, owned by processing SQL."""

from importlib.resources import files

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("api", "0038_reference_frames")]
    operations = [
        migrations.RunSQL(files("geode").joinpath("sql/compute_jobs_v1.sql").read_text())
    ]
