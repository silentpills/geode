# CLI Tools Setup

This guide covers configuring and running GeoDE command-line tools for GNSS processing.

## Installation

Use this fork's `dev` checkout for both development and deployment:

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
```

Pixi installs the local source as an editable package in `.pixi/envs/default`.
Use `pixi run python -m com.<Tool>` from the repository root. Installing
`geode-gnss` from PyPI installs the published package, which may differ from this fork.

## Configuration File

Copy the example configuration file to your working directory and customize it:

```bash
cp gnss_data.cfg.example gnss_data.cfg
# Set database credentials in .env; set processing paths in gnss_data.cfg
```

Database credentials belong in `.env` (`POSTGRES_HOST`, `POSTGRES_PORT`,
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`). They take precedence over
legacy `[postgres]` credentials. Keep processing paths in `gnss_data.cfg`.
GeoDE commands normally look for that file in the current working directory.

### Configuration Sections

```ini
[postgres]
# Legacy database fields may be omitted when using .env.

# Directory for format scripts (data download processing)
format_scripts_path = /path/to/format_scripts

[archive]
# Absolute location of the RINEX tank
path = /path/to/archive
repository = /path/to/repository

# Orbit file locations (use $year, $doy, $gpsweek, $gpswkday variables)
ionex = /path/to/orbits/ionex/$year
brdc = /path/to/orbits/brdc/$year
sp3 = /path/to/orbits/sp3/$gpsweek

# Hostnames for parallel processing nodes
node_list = node1,node2,node3

# Orbit center type precedence (AC=Analysis Center, CS=campaign, ST=solution type)
sp3_ac = COD,IGS
sp3_cs = OPS,R03,MGX
sp3_st = FIN,SNX,RAP

[otl]
# Ocean tide loading configuration
grdtab = /path/to/gamit/bin/grdtab
otlgrid = /path/to/gamit/tables/otl.grid
otlmodel = FES2014b

[ppp]
# PPP processing configuration
ppp_path = /path/to/PPP_NRCAN
ppp_exe = /path/to/PPP_NRCAN/source/ppp
institution = Your Institution
info = Your Group Name

# Reference frames (comma-separated list)
frames = IGS20,
IGS20 = 1987_1,

# ATX files (same order as frames)
atx = /path/to/resources/atx/igs20_2335_plus.atx
```

## Running Commands

Once configured, run GeoDE from the repository root:

```bash
# Plot ETM for a station
pixi run python -m com.PlotETM igm1

# Scan archive for RINEX files
pixi run python -m com.ScanArchive igs.all -rinex 1

# Download data for stations
pixi run python -m com.DownloadSources rms.all -date 2024.001 2024.365

# Run archive service
pixi run python -m com.ArchiveService
```

## Station List Syntax

Most commands accept a station list argument with flexible syntax:

| Format | Description |
|--------|-------------|
| `stnm` | Single station (all networks) |
| `net.stnm` | Station in specific network |
| `net.all` | All stations in network |
| `all` | All stations in database |
| `ARG` | All stations in country (3-letter ISO code) |
| `*net.stnm` | Exclude station from list |
| `ars.at1[3-5]` | Regex range (at13, at14, at15) |
| `ars.at%` | Wildcard (any string) |

## Common Workflows

### Adding RINEX to Database

```bash
# Scan archive and add RINEX files
pixi run python -m com.ScanArchive net.all -rinex 0

# Or scan everything (ignore station list)
pixi run python -m com.ScanArchive net.all -rinex 1
```

### Running PPP

```bash
# Run PPP for date range
pixi run python -m com.ScanArchive net.all -ppp 2024.001 2024.100
```

### Plotting Time Series

```bash
# Interactive plot
pixi run python -m com.PlotETM station_code -gui

# Save to directory
pixi run python -m com.PlotETM net.all -dir /path/to/output
```

### Downloading Data

```bash
# Download for last 30 days
pixi run python -m com.DownloadSources net.all -win 30

# Download specific date range
pixi run python -m com.DownloadSources net.all -date 2024/01/01 2024/12/31
```

## Next Steps

- See [CLI Reference](../usage/cli-reference.md) for detailed command documentation
- See [Configuration](../reference/configuration.md) for all configuration options
