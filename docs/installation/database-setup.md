# Database Setup

GeoDE relies heavily on a PostgreSQL database. The CLI tools and web interface both operate on the same database — the web UI manages station metadata and monitoring while the CLI tools handle GNSS processing. They should always be configured to point at the same PostgreSQL instance.

Ideally, use two systems: one for the PostgreSQL database engine and another for running GeoDE. While running both on the same computer is possible, it's not recommended for high-efficiency processing.

## Install PostgreSQL

On your database server (can be remote or local):

```bash
sudo apt update
sudo apt install postgresql
```

## Network Configuration

Choose the appropriate configuration based on your setup:

- **Local Setup (Docker on same machine)**: See [Local Development Setup](#local-development-setup)
- **Remote Setup (database on separate server)**: See [Remote Server Setup](#remote-server-setup)

### Local Development Setup

When running PostgreSQL and Docker on the same machine, you need to configure PostgreSQL to accept connections from Docker containers.

#### PostgreSQL Listen Address

Edit `/etc/postgresql/XX/main/postgresql.conf` (replace `XX` with your version):

```bash
# Find your PostgreSQL version
ls /etc/postgresql/

# Edit the config
sudo nano /etc/postgresql/XX/main/postgresql.conf
```

Change:

```
#listen_addresses = 'localhost'
```

To:

```
listen_addresses = 'localhost,172.17.0.1'
```

This allows PostgreSQL to accept connections from the Docker bridge gateway while keeping it off public interfaces.

#### PostgreSQL Client Authentication

Edit `/etc/postgresql/XX/main/pg_hba.conf`:

```bash
sudo nano /etc/postgresql/XX/main/pg_hba.conf
```

Add this line to allow Docker containers to connect:

```
# Docker networks (172.16.x.x - 172.31.x.x)
host    all    geode    172.16.0.0/12    md5
```

!!! note
    We use `172.16.0.0/12` instead of `172.17.0.0/16` because Docker Compose creates its own networks in the `172.18.x.x` range, not just the default bridge network.

#### Apply Changes

```bash
sudo systemctl restart postgresql
```

#### Docker Configuration

In your `.env` file, use `host.docker.internal` to reach PostgreSQL on the host:

```
POSTGRES_HOST=host.docker.internal
```

### Remote Server Setup

If using a remote server, secure the connection instead of exposing port 5432 to the public internet. Options include a VPN like [Tailscale](https://tailscale.com/), an SSH tunnel (`ssh -L 5432:localhost:5432 user@db-server`), or firewall rules restricting access to known IPs.

#### Tailscale Setup (Recommended)

```bash
sudo tailscale serve --bg --tcp=5432 tcp://127.0.0.1:5432
```

#### PostgreSQL Configuration

Edit `pg_hba.conf` to allow connections from your Tailscale network:

```
# Allow Tailscale subnet
host    all    geode    100.64.0.0/10    md5
```

## Create User and Database

```sql
CREATE USER geode WITH PASSWORD 'your_secure_password';
CREATE DATABASE geode OWNER geode;
```

## Load Schema

Use the clean schema file provided in `database/schema.sql`:

```bash
psql -U geode -d geode -f database/schema.sql
```

## Load Seed Data

Populate reference tables with initial data:

```bash
psql -U geode -d geode -f database/seed.sql
```

The seed data includes:

| Table | Description | Source |
|-------|-------------|--------|
| `keys` | Key names used in GeoDE | `csv/keys.csv` |
| `rinex_tank_struct` | RINEX archive structure | `csv/rinex_tank_struct.csv` |
| `antennas` | IGS antenna codes | `csv/antennas.csv` |
| `receivers` | IGS receiver codes | `csv/receivers.csv` |
| `gamit_htc` | Antenna height/offset codes | `csv/gamit_htc.csv` |

## Complete Setup Order

1. **Load schema** (creates core GNSS tables):
    ```bash
    psql -U geode -d geode -f database/schema.sql
    ```

2. **Load seed data** (populates reference tables):
    ```bash
    psql -U geode -d geode -f database/seed.sql
    ```

3. **Start the web interface** (migrations run automatically):
    ```bash
    docker compose up -d
    ```
    Django migrations run automatically on container startup, adding web UI tables and `api_id` columns.

4. **Login** at `http://localhost:${APP_PORT}` with `admin/admin`

## Recommended RINEX Archive Structure

The `rinex_tank_struct` table defines how RINEX files are organized. The recommended structure is:

| Level | KeyCode |
|-------|---------|
| 1 | network |
| 2 | year |
| 3 | doy |

This organizes files as: `archive/network/year/doy/`

## Troubleshooting

### Permission Issues

Ensure the `geode` user has appropriate permissions:

```sql
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO geode;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO geode;
```

### Connection Issues

1. Check PostgreSQL is listening on the correct interface
2. Verify `pg_hba.conf` allows your connection
3. Test with: `psql -h hostname -U geode -d geode`

## Processing diagnostics update

This fork adds `ppp_antenna_residuals` and indexes on `events("EventDate")` and
`stacks(name)`. Fresh SQL installs include them in `database/schema.sql`;
Django migration `0034_processing_diagnostics` adds them to web deployments.
The CLI connection's existing migration routine also creates them when needed.
The operations tolerate an existing installation from either path.

PPP runs store 91 elevation bins (0–90 degrees) when a residual file is available.
They prefer backward-substitution observations and fall back to forward results.
Deleting a PPP solution also deletes its residual row. `LocateRinex` can export
these diagnostics; no residual row is required for older solutions.

The upstream antenna/radome primary-key redesign, project tables, and
reference-frame management tables are not part of this update. Existing Django
models, psycopg3 access, and `.env` database configuration remain authoritative.
