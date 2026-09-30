from importlib.resources import files

import django.contrib.postgres.fields
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_reconcile_processing_state'),
    ]

    state_operations = [
        migrations.CreateModel(
            name='GamitProjects',
            fields=[
                ('project', models.CharField(max_length=20, unique=True)),
                ('api_id', models.AutoField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'gamit_projects',
            },
        ),
        migrations.CreateModel(
            name='ReferenceFrames',
            fields=[
                ('frame_name', models.CharField(max_length=20, unique=True)),
                ('engine', models.CharField(max_length=10)),
                ('project', models.CharField(max_length=20)),
                ('source_projects', models.JSONField(default=dict)),
                ('source_stack', models.CharField(blank=True, max_length=20, null=True)),
                ('fixed_plate', models.CharField(blank=True, max_length=2, null=True)),
                ('euler_pole', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), blank=True, null=True, size=3)),
                ('euler_pole_stations', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=8), blank=True, null=True, size=None)),
                ('translation_rate', django.contrib.postgres.fields.ArrayField(base_field=models.FloatField(), blank=True, null=True, size=3)),
                ('first_epoch', models.DateTimeField(blank=True, null=True)),
                ('last_epoch', models.DateTimeField(blank=True, null=True)),
                ('created', models.DateTimeField(default=django.utils.timezone.now)),
                ('modified', models.DateTimeField(default=django.utils.timezone.now)),
                ('api_id', models.AutoField(primary_key=True, serialize=False)),
            ],
            options={
                'db_table': 'reference_frames',
            },
        ),
        migrations.AddField(
            model_name='stacks',
            name='engine',
            field=models.CharField(default='gamit', max_length=10),
        ),
        migrations.AddField(
            model_name='stacks',
            name='ppp_reference_frame',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='stations',
            name='plate',
            field=models.CharField(blank=True, max_length=2, null=True),
        ),
        migrations.AlterField(
            model_name='stacks',
            name='project',
            field=models.CharField(blank=True, db_column='Project', max_length=20, null=True),
        ),
        migrations.CreateModel(
            name='ReferenceFrameConstraints',
            fields=[
                ('network_code', models.CharField(max_length=3)),
                ('station_code', models.CharField(max_length=4)),
                ('vx', models.FloatField()),
                ('vy', models.FloatField()),
                ('vz', models.FloatField()),
                ('api_id', models.AutoField(primary_key=True, serialize=False)),
                ('frame', models.ForeignKey(db_column='constraints_id', on_delete=django.db.models.deletion.PROTECT, to='api.referenceframes', to_field='frame_name')),
            ],
            options={
                'db_table': 'reference_frame_constraints',
                'unique_together': {('frame', 'network_code', 'station_code')},
            },
        ),
    ]

    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunSQL(
            files("geode").joinpath("sql/reference_frames_v1.sql").read_text(),
        )],
        state_operations=state_operations,
    )]
