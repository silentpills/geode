"""Add PPP diagnostics and lookup indexes without changing existing web models."""

from django.db import migrations


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("api", "0033_alter_sourcesservers_options")]
    operations = [
        migrations.RunSQL(
            'CREATE TABLE IF NOT EXISTS public.ppp_antenna_residuals (\n                network_code    VARCHAR(3)  NOT NULL,\n                station_code    VARCHAR(4)  NOT NULL,\n                reference_frame VARCHAR(20) NOT NULL,\n                system          CHARACTER(1),\n                year            SMALLINT NOT NULL,\n                doy             SMALLINT NOT NULL,\n                antenna_code    VARCHAR(22) NOT NULL,\n                radome_code     VARCHAR(7)  NOT NULL,\n                residuals       DOUBLE PRECISION[91],  -- elevation-dependent residuals, index 1=0deg to 91=90deg\n                CONSTRAINT ppp_antenna_residuals_pkey\n                    PRIMARY KEY (network_code, station_code, year, doy, reference_frame),\n                FOREIGN KEY (network_code, station_code)\n                    REFERENCES public.stations("NetworkCode", "StationCode")\n                    ON DELETE CASCADE,\n                FOREIGN KEY (network_code, station_code, year, doy, reference_frame)\n                    REFERENCES public.ppp_soln("NetworkCode", "StationCode", "Year", "DOY", "ReferenceFrame")\n                    ON DELETE CASCADE\n            ) WITH (\n                autovacuum_enabled = TRUE);',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_ppp_antenna_residuals_station ON public.ppp_antenna_residuals(network_code, station_code);",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_ppp_antenna_residuals_date ON public.ppp_antenna_residuals(year, doy);",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS idx_ppp_antenna_residuals_antenna ON public.ppp_antenna_residuals(antenna_code, radome_code);",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            'CREATE INDEX CONCURRENTLY IF NOT EXISTS events_event_date_index\n                     ON public.events ("EventDate");',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS stacks_name_index\n                     ON public.stacks (name);",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
