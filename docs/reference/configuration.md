# Configuration Reference

GeoDE uses two configuration methods:

- **CLI Tools**: Use `gnss_data.cfg` (copy from `gnss_data.cfg.example`)
- **Web Interface**: Uses `.env` file only (copy from `.env.example`)

## Configuration File (gnss_data.cfg)

The CLI configuration file uses INI format with multiple sections. Copy the example to get started:

```bash
cp gnss_data.cfg.example gnss_data.cfg
```

### [postgres] Section

Database connection settings.

```ini
[postgres]
hostname = your-db-server.example.com
username = geode
password = your_secure_password
database = geode
```

| Setting | Description | Required |
|---------|-------------|----------|
| `hostname` | PostgreSQL server hostname or IP | Yes |
| `username` | Database username | Yes |
| `password` | Database password | Yes |
| `database` | Database name | Yes |

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
node_list = node1,node2,node3
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
| `node_list` | Comma-separated list of processing nodes | Yes |
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
| `institution` | Institution name for headers | Yes |
| `info` | Group/division name | Yes |
| `frames` | Comma-separated reference frames | Yes |
| `{frame}` | Frame date range (e.g., `IGS20 = 1987_1,`) | Yes |
| `atx` | ATX antenna file path(s) | Yes |

---

## Environment Variables

Environment variables (typically set via the `.env` file) override `gnss_data.cfg` settings when both are present. This means you can put database credentials in `.env` once and have both the CLI tools and web interface use them, without duplicating values in `gnss_data.cfg`.

**Precedence (highest wins):** Environment variables (`.env`) > `gnss_data.cfg`

### Database Settings

| Variable | Config Equivalent | Description |
|----------|-------------------|-------------|
| `POSTGRES_HOST` | `postgres.hostname` | Database hostname |
| `POSTGRES_PORT` | `postgres.port` | Database port (default: 5432) |
| `POSTGRES_DB` | `postgres.database` | Database name |
| `POSTGRES_USER` | `postgres.username` | Database username |
| `POSTGRES_PASSWORD` | `postgres.password` | Database password |

### Django Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | Required |
| `DJANGO_DEBUG` | Enable debug mode | `False` |
| `DJANGO_HTTPS` | Enable HTTPS | `False` |

### Docker/Web Settings

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_PORT` | Port for web interface | Yes |
| `MEDIA_FOLDER_HOST_PATH` | Path for uploaded media | Yes |
| `USER_ID_TO_SAVE_FILES` | UID for file ownership | Yes |
| `GROUP_ID_TO_SAVE_FILES` | GID for file ownership | Yes |
| `VITE_API_URL` | Frontend API URL | Yes |

### File Upload Limits

| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_SIZE_IMAGE_MB` | Max image upload size (MB) | 75 |
| `MAX_SIZE_FILE_MB` | Max file upload size (MB) | 75 |
| `RINEX_STATUS_DATE_SPAN_SECONDS` | RINEX status date span | 1000 |

---

## Configuration by Component

| Component | Configuration Source |
|-----------|---------------------|
| **CLI Tools** | `gnss_data.cfg`, overridden by environment variables from `.env` |
| **Web Interface** | `.env` file (environment variables only) |

The web interface does not read `gnss_data.cfg`. Both components connect to the same PostgreSQL database — put shared database credentials in `.env` so they stay in sync.

---

## Sample .env File

```bash
# =============================================================================
# GeoDE Environment Configuration
# =============================================================================

# PostgreSQL Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=geode
POSTGRES_USER=geode
POSTGRES_PASSWORD=your_secure_password_here

# Django Settings
DJANGO_SECRET_KEY=generate-a-secure-key-here
DJANGO_DEBUG=False
DJANGO_HTTPS=False

# Docker/Web UI Settings
APP_PORT=8080
MEDIA_FOLDER_HOST_PATH=/path/to/media
USER_ID_TO_SAVE_FILES=1000
GROUP_ID_TO_SAVE_FILES=1000
VITE_API_URL=http://localhost:8080

# File Upload Limits
MAX_SIZE_IMAGE_MB=75
MAX_SIZE_FILE_MB=75
RINEX_STATUS_DATE_SPAN_SECONDS=1000
```
