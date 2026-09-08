"""Register equipment combinations without replacing antenna-model IDs."""

from importlib.resources import files

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0034_processing_diagnostics")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(
                files("geode").joinpath("sql/antenna_radomes_v1.sql").read_text(),
                # Deliberately irreversible: removing this catalog loses registrations.
            )],
            state_operations=[migrations.CreateModel(
                name="AntennaRadomes",
                fields=[
                    ("antenna_code", models.CharField(db_column="AntennaCode", max_length=22)),
                    ("radome_code", models.CharField(db_column="RadomeCode", max_length=7)),
                    ("api_id", models.AutoField(primary_key=True, serialize=False)),
                ],
                options={
                    "db_table": "antenna_radomes",
                    "ordering": ["antenna_code", "radome_code"],
                    "managed": True,
                    "constraints": [models.UniqueConstraint(
                        fields=("antenna_code", "radome_code"), name="antenna_radomes_pair_key")],
                },
            )],
        ),
    ]
