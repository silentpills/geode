# CLI Reference

This page documents the main command-line tools available in GeoDE. Run examples
from the checkout with `pixi run --locked python -m com.<Tool>`. Some tools
also have installed `.py` entry points. Use a tool's
`--help` for its complete interface. The
[processing workflow](processing-workflow.md) explains data flow and repair
boundaries.

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

A file path containing station specifications can also be provided, one per line
(without an `@` prefix). In files, `*` can be replaced with `-` for exclusions.
Quote shell arguments containing `*`, brackets, or `|` to prevent shell expansion.

### Station type and geographic filters

Station type filters require the web tables `api_stationtype` and
`api_stationmeta`. Geographic filters use station coordinates or plate metadata.
Combine filters with `:`:

| Selection | Meaning |
| --- | --- |
| `ARG:CONTINUOUS` | Continuous stations in Argentina |
| `all:CONTINUOUS` | Continuous stations in all countries |
| `ARG:LAT[-35,-40]` | Latitude range |
| `CHL:LON[-72,-70]` | Longitude range |
| `ARG:BBOX[-30,-40,-70,-60]` | Latitude/longitude bounds |
| `ARG:PLATE[SC]` | Stations with the Scotia plate code |
| `ARG:CAMPAIGN:RADIUS[-35.5,-65.2,500]` | Campaign stations within 500 km of the center |

For example: `pixi run --locked python -m com.PlotETM 'ARG:LAT[-35,-40]' -gui`.

---

## AntennaCatalog.py

Register antenna/radome combinations explicitly or import their identities from
ANTEX 1.4. Run `pixi run AntennaCatalog.py --help` and see the
[antenna catalog guide](antenna-catalog.md) for setup, previews, and examples.
Registration does not import calibration values.

---

## ArchiveService.py

Archive operations service.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `-purge`, `--purge_locks` | Delete temporary networks starting with '?', locks, and associated files in `data_in` |
| `-visits`, `--process_visits` | Check and convert GNSS visit files to RINEX |
| `-np`, `--noparallel` | Execute without parallelization |

**Usage:**
```bash
pixi run --locked python -m com.ArchiveService [options]
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
pixi run --locked python -m com.DownloadSources net.all -date 2024/01/01 2024/04/09
pixi run --locked python -m com.DownloadSources net.all -win 30
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
| `-import net zipfiles...` | Import station ZIP files into the default network when needed |
| `-get date` | Copy a station observation from the archive, normalizing its header |
| `-ppp [start] [end]` | Run PPP on RINEX files |
| `-rehash` | Rehash PPP solutions |
| `-tol {hours}` | Station info gap tolerance (default: 0) |

**Usage:**
```bash
# Scan and add RINEX to database
pixi run --locked python -m com.ScanArchive net.all -rinex 0

# Run PPP for date range
pixi run --locked python -m com.ScanArchive net.all -ppp 2024/01/01 2024/04/09

# Export station metadata without observation files
pixi run --locked python -m com.ScanArchive net.stnm -export true
```

---

## IntegrityCheck.py

Inspect archive/database consistency, metadata, and PPP solutions. Report modes
and a review workflow are described in
[processing and integrity checks](processing-workflow.md#review-integrity-before-repairs).

| Option | Effect |
| --- | --- |
| `-d start [end]` | Bound operations by date; `-stnc` ignores this filter |
| `-rinex report` | Report archive files missing for database records |
| `-rinex fix` | Remove missing-file records and associated PPP/GAMIT solutions |
| `-rnx_count` | Count unique station-days per day |
| `-stnc` | Check equipment-history consistency and observation coverage |
| `-stnr` | Compare receiver serial numbers with RINEX metadata |
| `-stns` | Check PPP hashes against station-info hashes |
| `-stnp [days]` | Output proposed station.info; ignore records no longer than the specified days |
| `-g [days]`, `-gg` | Report gaps or show them graphically |
| `-sc noop` | Report spatial-coherence problems |
| `-sc exclude`, `-sc delete` | Exclude or delete PPP solutions with coherence problems |
| `-print short`, `-print long` | Output station.info |
| `-r net.station` | Rename/merge one source station and its archive files into the destination |
| `-del_stn` | With `-r`, delete the source station if it becomes empty |
| `-es start end` | Exclude PPP solutions in a date range |
| `-del start end completion` | Delete RINEX and associated solutions at or below the completion threshold |
| `-np` | Execute without parallelization |

Inspect help and back up affected data before mutation operations. For date
examples, use explicit calendar dates such as `2024/01/01 2024/12/31`.

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
pixi run --locked python -m com.PlotETM station -gui

# Save all stations to directory
pixi run --locked python -m com.PlotETM net.all -dir /output/path

# Plot GAMIT time series
pixi run --locked python -m com.PlotETM station -gamit stack_name

# Query model at specific dates
pixi run --locked python -m com.PlotETM station -q model -win 2024/01/01 2024/12/31
```
