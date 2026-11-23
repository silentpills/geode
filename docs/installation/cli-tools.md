# CLI tools setup

Complete the [installation](index.md) and [database setup](database-setup.md)
first. Pixi installs this checkout as an editable package in `.pixi/envs/default`.
Run commands from the repository root through `pixi run --locked`.

## Processing configuration

Copy `gnss_data.cfg.example` to `gnss_data.cfg` and set the archive, incoming-data
repository, orbit products, external executables, and processing mode for your
installation. Commands normally look for this file in the working directory.
Database credentials belong in `.env` and override legacy `[postgres]` fields.
The [configuration reference](../reference/configuration.md) describes each
section; keep the example file as the starting template.

CLI processing and the web application must connect to the same database.
External processing programs must be installed on the machines that run jobs,
with access to the configured data and database.

## Scientific workers

For one-machine processing, keep `parallel = False` in `gnss_data.cfg` to run
the computation directly. To queue work on the same machine, configure the
database and processing paths, apply the database migrations, and set a distinct
`GEODE_REDIS_PASSWORD` in `.env`. From the configured checkout:

```bash
docker compose -f compose.compute.yml up -d --wait compute-redis
pixi run --locked compute:worker
```

The first command starts a persistent Redis broker on loopback port 6380. It
reads the compute password from `.env`. The web stack can also include this
service with the `compute-broker` profile. The second command starts a scientific worker in the foreground with
one process. Set `parallel = True` and run the processing CLI in another
terminal. `PlotETM` selects the worker with its own `--parallel` flag.
Use the same checkout, working directory, paths, external programs,
and database for the worker and CLI. Relative paths refer to that working
directory. Provision external GAMIT software and tables on the worker beforehand.
For an independently managed Redis, set `GEODE_BROKER_URL` on both sides.
The web worker handles scheduled web tasks using its own broker.

```bash
pixi run --locked compute:status
pixi run --locked compute:status JOB_UUID
```

PostgreSQL records queued, running, cancelled and completed jobs. Each receipt
identifies the operation and fingerprints its inputs. One matching delivery can
claim each job ID. The coordinator verifies the worker can reach the same
database before starting parallel work. If a worker dies after claiming a job,
inspect the receipt, logs, database writes and output files before submitting
another run. The receipt cannot prove whether an external program finished before the worker stopped.
The broker volume retains messages on a normal restart. A queued receipt can
also indicate publication was interrupted. Stop the worker with Ctrl-C and let
active processing finish before shutting down the broker.

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
