# CLI Reference

This page documents the command-line interface tools available in GeoDE.

## Station List Syntax

Most commands accept a station list argument with the following syntax:

- `stnm` - Single station (if unique, otherwise all matching stations)
- `net.stnm` - Station in specific network
- `net.all` - All stations in network
- `all` - All stations in database
- `ARG` - All stations in country (3-letter ISO 3166 code, uppercase)
- `*net.stnm` or `*stnm` - Exclude station from list
- `*net.all` or `*ARG` - Exclude all stations from network/country

### Wildcards (PostgreSQL regex convention)

- `[]` - Character ranges (e.g., `ars.at1[3-5]` matches at13, at14, at15)
- `%` - Match any string (e.g., `ars.at%`)
- `|` - OR operator (e.g., `ars.at1[1|2]` matches at11 and at12)
- `_` - Single character wildcard (equivalent to POSIX `?`)

A file with station list can also be provided (using same conventions). In files, `*` can be replaced with `-` for clarity.

---

## ArchiveService.py

Archive operations service.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `-purge`, `--purge_locks` | Delete networks starting with '?' and purge locks table |
| `-np`, `--noparallel` | Execute without parallelization |

**Usage:**
```bash
ArchiveService.py [options]
```

---

## AlterETM.py

Manage trajectory parameters with subcommands. The previous `-fun`, `-soln`, and
`-print` interface has been replaced; update saved commands accordingly.

Run from the repository root in the Pixi environment:

```bash
pixi run python -m com.AlterETM net.station polynomial --terms 2
pixi run python -m com.AlterETM net.station periodic --periods 365.25 182.625
pixi run python -m com.AlterETM net.station jump --add --type coseismic --date 2024/01/15 --relaxation 0.05 1
pixi run python -m com.AlterETM net.station print
```

Use `--solution ppp` or `--solution gamit` on the subcommand to restrict changes;
the default is both. Relaxation times are in **years**. Run a subcommand with
`--help` for its options. These commands modify database parameters.

The fork retains relaxation defaults `[0.05, 1]`, a minimum earthquake spacing
of 3 days, and a minimum jump spacing of 3 days. Upstream's newer defaults are
not applied implicitly. Fit-window fixes remove jumps that cannot be estimated
within the selected observations and reject an empty observation window.

### Parallel plotting

`pixi run python -m com.PlotETM net.station --parallel` enables Dispy processing.
Without this flag, plotting runs serially. Parallel workers still need the GNSS
configuration, dependencies, and database access described in the CLI setup guide.

---

## DownloadSources.py

Download RINEX data from configured sources.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `stnlist` | List of stations |
| `-date`, `--date_range` | Date range: `[date_start]` or `[date_start] [date_end]` |
| `-win`, `--window` | Download from `today - {days}` |
| `-np`, `--noparallel` | Execute without parallelization |

**Usage:**
```bash
DownloadSources.py net.all -date 2024.001 2024.100
DownloadSources.py net.all -win 30
```

---

## ScanArchive.py

Archive operations for RINEX scanning, PPP processing, and station management.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `stnlist` | List of stations |
| `-rinex {0\|1}` | Scan archive for RINEX. 0=filter by station list, 1=ignore station list |
| `-otl` | Calculate ocean loading coefficients (FES2004) |
| `-stninfo [file] [net]` | Insert station information |
| `-export [dataless]` | Export station to zip file |
| `-import [file] [net]` | Import station from zip file |
| `-get` | Get station from archive to current directory |
| `-ppp [start] [end]` | Run PPP on RINEX files |
| `-rehash` | Rehash PPP solutions |
| `-tol {hours}` | Station info gap tolerance (default: 0) |

**Usage:**
```bash
# Scan and add RINEX to database
ScanArchive.py net.all -rinex 0

# Run PPP for date range
ScanArchive.py net.all -ppp 2024.001 2024.100

# Export station
ScanArchive.py net.stnm -export true
```

---

## PlotETM.py

Plot Extended Trajectory Model (ETM) for stations.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `stnlist` | List of stations |
| `-nop`, `--no_plots` | Don't produce plots |
| `-nom`, `--no_missing_data` | Don't show missing days |
| `-nm`, `--no_model` | Plot without fitting a model |
| `-r`, `--residuals` | Plot residuals |
| `-dir {path}` | Output directory for PNG files |
| `-json {0\|1\|2}` | Export to JSON: 0=params, 1=time series, 2=both |
| `-gui`, `--interactive` | Interactive mode (zoom, pan) |
| `-rj`, `--remove_jumps` | Remove jumps before plotting |
| `-rp`, `--remove_polynomial` | Remove polynomial terms |
| `-win {range}` | Time window (yyyy/mm/dd, yyyy.doy, or integer N for last N epochs) |
| `-q {type}` | Query ETM: "model" or "solution" (output in XYZ) |
| `-gamit {stack}` | Plot GAMIT time series for specified stack |
| `-lang {ENG\|ESP}` | Plot language |
| `-hist` | Plot histogram of residuals |
| `-file {path}` | External data file (supports {net}, {stn} variables) |
| `-format {fields}` | Field order for external file |
| `-outliers` | Plot additional panel with outliers |
| `-dj` | Plot unmodeled detected jumps |
| `-vel` | Output velocity in XYZ |
| `-seasonal` | Output seasonal terms in NEU |
| `-quiet` | Suppress information messages |

**Usage:**
```bash
# Interactive plot
PlotETM.py station -gui

# Save all stations to directory
PlotETM.py net.all -dir /output/path

# Plot GAMIT time series
PlotETM.py station -gamit stack_name

# Query model at specific dates
PlotETM.py station -q model -win 2024/01/01 2024/12/31
```
