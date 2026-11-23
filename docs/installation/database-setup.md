# Database setup

Use PostgreSQL 19 for this fork. The native Pixi test tools and bundled Docker
server use the same major version. CLI processing and the web application must
connect to the same database.

## One initialization command

For a new installation, create an empty database owned by your GeoDE database
user, configure `.env`, and run from the repository root:

```bash
pixi install --locked -e web
pixi run -e web db:migrate
pixi run -e web db:check
```

`migrate` creates the processing tables, loads reference CSVs, and installs the
web tables, roles, permissions, and triggers. It creates **no login accounts**.
Docker runs the same command at startup; see [Web interface](web-interface.md).
Even a CLI-only installation can use this initialization command and then run
processing in the default Pixi environment.

The packaged `geode/sql/bootstrap_v1/` directory is an immutable bootstrap
snapshot. `database/schema.sql` is a compatibility wrapper that loads the
snapshot and later processing SQL migrations; `database/csv` remains a symlink
to its seed data. Do not edit the snapshot for later schema changes: add a
versioned migration.
`database/seed.sql` remains a manual-import compatibility script; run it from
`database/` only when deliberately creating a SQL-only schema. Do not import the
snapshot or CSVs over a database that has already been initialized.

The antenna model CSV contains model identities and height conversions. Before
importing equipment histories, register the required
[antenna/radome combinations](../usage/antenna-catalog.md).

## Existing databases

Back up the database and media first. `migrate` recognizes an existing complete
processing schema and adds the web migrations without recreating those tables
or replacing processing IDs. An incomplete schema stops initialization and must
be repaired or restored deliberately.

Migration 0037 reconciles Django's model history with columns and constraints
already present in the processing schema. It checks required columns before
recording that state and adds the explicitly named station-history uniqueness
constraint if needed. Keep the historical migrations: already recorded migrations
remain recorded, while fresh installations need the corrected bootstrap path.
Do not use `--fake` to silence an unexplained mismatch.

The old migrations installed accounts with publicly known passwords. New
installations no longer receive them. If adopting an older installation, review
`admin`, `underprivileged_front`, `underprivileged_api`, and `update-gaps-status`;
disable unused accounts or change their passwords before serving the application.
Existing users and custom passwords are preserved by this update.

## Connection settings

| Setting | Used by |
| --- | --- |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Native Pixi / CLI commands |
| `POSTGRES_CONTAINER_HOST`, `POSTGRES_CONTAINER_PORT` | Docker backend |
| `POSTGRES_PUBLISHED_PORT` | Host-side port for bundled PostgreSQL |
| `POSTGRES_DB` | Database shared by processing and the web service |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Native CLI and Django credentials, schema owner for Compose migrations |
| `POSTGRES_APP_USER`, `POSTGRES_APP_PASSWORD` | Restricted web/worker login selected by Compose |
| `POSTGRES_ADMIN_PASSWORD` | Bundled cluster administrator, `postgres` |

Defaults connect native commands to `127.0.0.1:5432` and Docker to
`postgres:5432`. Changing a published host port does not change the container's
internal port. If you choose another published port, set the native
`POSTGRES_PORT` to match it.

For an external server, create the database/user there and set both connection
pairs appropriately. A database on the Docker host is reachable from the backend
through `host.docker.internal`; Compose includes the Linux host-gateway mapping.
Configure PostgreSQL to accept the actual Docker subnet and intended database
user using SCRAM authentication. For remote access use a private network or
restricted server access; the bundled server publishes only on loopback.

Fresh bundled installations create the owner and runtime roles during initial
database setup. The API and workers use the runtime login. It can change table
data and use sequences. Schema upgrades run in the separate `migrate`
service as the owner. Both application roles have ordinary login privileges.
The database container alone receives the cluster administrator password.
Native Django reads `POSTGRES_USER` and `POSTGRES_PASSWORD` from its process
environment. Supply the owner credentials to `pixi run -e web db:migrate`,
and the restricted credentials when starting a native web process.
Changing initialization variables after a volume is created does not rotate a
PostgreSQL role's password. Coordinate `ALTER ROLE` with the consuming services.

For an external deployment, have the administrator provision both logins and
make the migration role the database and GeoDE schema object owner. As the
owner, run the following in the target database, substituting the role names
from your installation and using normal psql connection settings:

```bash
GEODE_OWNER=pgamit GEODE_APP=geode_app psql -U pgamit -d pgamit -v ON_ERROR_STOP=1 -f database/grant-app-access.sql
```

The script sets privileges on existing objects and default privileges for future
tables and sequences created by the migration owner. Compose requires both
`POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD`. For an existing external
installation that intentionally shares one login, explicitly set this pair to
that login until a restricted role is provisioned.

Compose forwards libpq settings `PGSSLMODE`, `PGSSLROOTCERT`, `PGSSLCERT`,
`PGSSLKEY`, `PGCHANNELBINDING`, and `PGOPTIONS` to migration and runtime
connections when set. For an external TLS server, use `PGSSLMODE=verify-full`
and mount its CA certificate read-only at the configured path in both services.

PostgreSQL 19's official image stores its volume at `/var/lib/postgresql`.
An existing PostgreSQL 18 data directory needs a major-version migration.
Use a logical dump and restore into a fresh volume. See the
[official image documentation](https://hub.docker.com/_/postgres) and the
[backup procedure](../development/operations.md).
