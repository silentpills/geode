# Database setup

Use PostgreSQL 18 for this fork. The native Pixi test tools and bundled Docker
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
snapshot. `database/schema.sql` and `database/csv` are compatibility symlinks to
it. Do not edit the snapshot for later schema changes: add a versioned migration.
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
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Both native and Docker connections |

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

PostgreSQL 18's official image stores its volume at `/var/lib/postgresql`.
A PostgreSQL 16 data directory cannot be reused directly with 18: use a logical
dump and restore into a fresh volume. See the
[official image documentation](https://hub.docker.com/_/postgres) and the
[backup procedure](../development/operations.md).
