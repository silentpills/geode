# CLI tools setup

Complete the [installation](index.md) and [database setup](database-setup.md)
first. Pixi installs this checkout as an editable package in `.pixi/envs/default`.
Run commands from the repository root through `pixi run --locked`.

## Processing configuration

Copy `gnss_data.cfg.example` to `gnss_data.cfg` and set the archive, incoming-data
repository, orbit products, external executables, and compute nodes for your
installation. Commands normally look for this file in the working directory.
Database credentials belong in `.env` and override legacy `[postgres]` fields.
The [configuration reference](../reference/configuration.md) describes each
section; keep the example file as the starting template.

CLI processing and the web application must connect to the same database.
External processing programs must be installed on the machines that run jobs,
with access to the configured data and database. Processing still uses Dispy;
Celery migration is a proposal. The `legacy-cgi` dependency supports the current
Dispy monitoring server on Python 3.13.

## Run a command

Inspect help before starting a workflow:

```bash
pixi run --locked python -m com.PlotETM --help
pixi run --locked python -m com.ScanArchive --help
pixi run --locked python -m com.IntegrityCheck --help
```

Use `python -m com.<Tool>` for any CLI module with a main entry point. Some tools
also have installed entry points, such as `pixi run --locked PlotETM.py --help`;
the module form does not depend on an entry-point alias.

After configuring the intended database, plot a station's time series:

```bash
pixi run --locked python -m com.PlotETM net.station -gui
```

See the [processing workflow](../usage/processing-workflow.md) for download,
ingestion, PPP, and integrity review. The [CLI reference](../usage/cli-reference.md)
owns station selectors and command options; the
[antenna catalog guide](../usage/antenna-catalog.md) covers required equipment
identities before importing station history.
