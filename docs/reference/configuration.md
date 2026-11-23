# Configuration Reference

Use `.env` for installation settings and `gnss_data.cfg` for GNSS
processing. Set database credentials once in the environment so the CLI and
Django use the same database. The [database setup guide](../installation/database-setup.md)
covers connection addresses, roles and migration credentials.

| Component | Configuration |
|-----------|---------------|
| Django API and web worker | Read database and application settings from the environment. Compose loads the repository's `.env`. |
| Processing CLI | Reads database settings from the environment and processing settings from `gnss_data.cfg` in the working directory. |
| Station reports and KMZ exports | Use database settings from the environment. `MEDIA_FOLDER_HOST_PATH` can supply the media directory. See [reports and campaigns](../usage/reports-and-campaigns.md). |

## Processing configuration

Copy the tracked template, then set archive paths, external executables,
reference frames and worker settings for the intended workload.

```bash
cp gnss_data.cfg.example gnss_data.cfg
```

### [archive] Section

RINEX and orbit file locations.

```ini
[archive]
path = /path/to/archive
repository = /path/to/repository
format_scripts_path = /path/to/format_scripts
ionex = /path/to/orbits/ionex/$year
brdc = /path/to/orbits/brdc/$year
sp3 = /path/to/orbits/sp3/$gpsweek
parallel = False
sp3_ac = COD,IGS
sp3_cs = OPS,R03,MGX
sp3_st = FIN,SNX,RAP
```

| Setting | Description | Required |
|---------|-------------|----------|
| `path` | RINEX tank location | Yes |
| `repository` | Incoming RINEX files location | Yes |
| `format_scripts_path` | Directory for [custom download converters](../usage/processing-workflow.md#custom-download-converters) | No |
| `ionex` | IONEX files path (supports variables) | Yes |
| `brdc` | Broadcast orbits path (supports variables) | Yes |
| `sp3` | SP3 orbits path (supports variables) | Yes |
| `parallel` | `True` submits processing to the Celery worker, `False` runs locally. | No |
| `sp3_ac` | Analysis center precedence | No |
| `sp3_cs` | Campaign code precedence | No |
| `sp3_st` | Solution type precedence | No |

**Path Variables:**
- `$year` - 4-digit year
- `$doy` - Day of year
- `$month` - Month
- `$day` - Day
- `$gpsweek` - GPS week number
- `$gpswkday` - GPS week day

### [otl] Section

Ocean tide loading configuration.

```ini
[otl]
grdtab = /path/to/gamit/bin/grdtab
otlgrid = /path/to/gamit/tables/otl.grid
otlmodel = FES2014b
```

| Setting | Description | Required |
|---------|-------------|----------|
| `grdtab` | Path to GAMIT grdtab binary | Yes |
| `otlgrid` | Path to OTL grid file | Yes |
| `otlmodel` | OTL model name (e.g., FES2014b) | Yes |

### [ppp] Section

PPP processing configuration.

```ini
[ppp]
ppp_path = /path/to/PPP_NRCAN
ppp_exe = /path/to/PPP_NRCAN/source/ppp
ppp_timeout = 900
institution = Your Institution
info = Your Group Name
frames = IGS20,
IGS20 = 1987_1,
atx = /path/to/resources/atx/igs20_2335_plus.atx
```

| Setting | Description | Required |
|---------|-------------|----------|
| `ppp_path` | PPP program directory | Yes |
| `ppp_exe` | PPP executable path | Yes |
| `ppp_timeout` | Positive, finite seconds per GPSPACE attempt; defaults to 900. Timed-out commands are retried twice. | No |
| `institution` | Institution name for headers | Yes |
| `info` | Group/division name | Yes |
| `frames` | Comma-separated reference frames | Yes |
| `{frame}` | Frame date range (e.g., `IGS20 = 1987_1,`) | Yes |
| `atx` | ATX antenna file path(s) | Yes |

---

## Environment Variables

Copy the repository's `.env.example` to `.env` and fill in deployment-specific
values. For native runs, exported environment variables take precedence over
values loaded from `.env`. CLI callers that supply a legacy config file can
still use its `[postgres]` section as a fallback for unset connection values.

### Database settings

Use `POSTGRES_HOST` and `POSTGRES_PORT` for the native CLI. Compose uses
`POSTGRES_CONTAINER_HOST` and `POSTGRES_CONTAINER_PORT` for connections from
inside the backend container. Use the same database name (`POSTGRES_DB`) in
both.

| Bundled database credentials | Used by |
|------------------------------|---------|
| `POSTGRES_USER` and `POSTGRES_PASSWORD` | Database credentials read by native CLI and Django processes. Use the owner for migrations and the restricted login for a native web process. |
| `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` | Restricted runtime login that Compose supplies to the web process and its worker |
| `POSTGRES_ADMIN_PASSWORD` | Bootstrap password for the bundled PostgreSQL `postgres` administrator |

See the [database setup guide](../installation/database-setup.md) for role
provisioning and the [web setup guide](../installation/web-interface.md)
for the bundled and external database options.

### Django Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | Required |
| `DJANGO_DEBUG` | Enable debug mode | `False` |
| `DJANGO_HTTPS` | Enable HTTPS | `False` |

### Docker/Web Settings

| Variable | Description | Compose default |
|----------|-------------|-----------------|
| `APP_BIND_HOST` | Host address on which the frontend listens | `127.0.0.1` |
| `APP_PORT` | Host port for the frontend | `8080` |
| `MEDIA_FOLDER_HOST_PATH` | Host path for uploaded media | `./var/media` |
| `USER_ID_TO_SAVE_FILES` | UID owning backend files | `1000` |
| `GROUP_ID_TO_SAVE_FILES` | GID owning backend files | `1000` |
| `VITE_API_URL` | API origin compiled into the frontend | `http://localhost:8080` |

### File Upload Limits

| Variable | Description | Default |
|
