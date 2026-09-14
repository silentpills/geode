# Processing workflow and integrity checks

GeoDE separates incoming observations from the permanent archive. The
`repository` setting in `gnss_data.cfg` names an incoming-data directory, not the
Git checkout. The `path` setting names the archive. Configure these and the
database using the [installation guides](../installation/index.md).

## From observations to solutions

```text
DownloadSources.py -> repository/data_in -> ArchiveService.py
                                              |
                            station identity and coordinate checks
                                              |
                          archive + database, or retry/rejection
                                              |
                          ScanArchive.py -> PPP solutions
                                              |
                          IntegrityCheck.py -> PlotETM.py
```

1. `DownloadSources.py` reads station/source mappings from `sources_stations`,
   server settings from `sources_servers`, and conversion formats from
   `sources_formats`. It downloads observations into `data_in`. Format scripts
   configured through `format_scripts_path` convert supported receiver formats
   before ingestion; see [custom download converters](#custom-download-converters).
2. `ArchiveService.py` reads incoming files, checks RINEX metadata, and uses PPP
   or autonomous coordinates to check station identity. A matching filename
   alone does not establish that a file belongs to a station. New stations can
   create temporary `?` networks and locks pending identity resolution.
3. Accepted observations enter the archive and `rinex` records. Archive paths
   are derived from the database's `rinex_tank_struct` and `keys` tables; do not
   assume a universal directory layout or change it independently of the files.
4. `ScanArchive.py` manages archived observations, equipment histories, ocean
   loading, and PPP solutions. PPP processing depends on equipment metadata for
   the observation date, configured antenna calibration/reference frames, and
   orbit products. Station-info hashes track whether solutions reflect the
   metadata used to compute them.
5. Review integrity reports and time series before accepting processing results.
   Changes to equipment histories or scientific parameters can require
   reprocessing; a successful command alone is not scientific validation.

After configuring a station, source, metadata, and external executables, a
typical sequence from the checkout is:

```bash
pixi run --locked python -m com.DownloadSources net.station -win 7
pixi run --locked python -m com.ArchiveService
pixi run --locked python -m com.ScanArchive net.station -ppp 2024/01/01 2024/01/07
pixi run --locked python -m com.PlotETM net.station -gui
```

Replace station/date examples with the intended dataset. Downloading and archive
processing write files and database records. `ArchiveService.py` scans the
configured repository, rather than accepting a station filter.

## Custom download converters

Set `format_scripts_path` in the `[archive]` section of `gnss_data.cfg` to the
converter directory. A non-null `sources_stations.format` overrides
`sources_servers.format`. For a custom format such as `CUSTOM_FORMAT`,
`DownloadSources.py` lowercases the format and uses the first file found in this
order: `custom_format`, `custom_format.sh`, `custom_format.py`. The file must be
executable, with a valid interpreter shebang for a script: GeoDE executes it
directly. Make the converter available at the configured path, with its
dependencies installed, on each node that runs download post-processing.
`DEFAULT_FORMAT` and `RNX2CRZ` do not invoke a custom converter.

The converter receives three positional arguments after its executable path:

| Argument | Value |
| --- | --- |
| 1 | Absolute path to the downloaded input file. |
| 2 | Downloaded filename, without its directory. |
| 3 | Existing temporary directory in which to write the converted files. |

Write one or more readable RINEX observation files directly into argument 3,
using RINEX 2-style filenames such as `abcd0010.24o` or `abcd0010.24d.Z`.
The output selector is `*.??[oOdD]*`; it includes compressed suffixes but does
not select standard long RINEX 3 filenames or search subdirectories. GeoDE then
reads the selected files, normalizes their names, and compresses them into the
station's download directory for ingestion.

Exit with status zero on success. A missing or non-executable script, a nonzero
exit status, or unreadable RINEX output fails post-processing. If no output
matches the selector, the error is `No files found after processing`. GeoDE
reports the processing error and tries the next configured download source,
if available. The temporary directory and downloaded input are removed after
the processing attempt, including on failure.

## Retry, rejection, and evidence

Inspect the command's reported error and accompanying logs before retrying. The
ingestion service uses these directories below the configured repository:

| Location | Meaning and next check |
| --- | --- |
| `data_in_retry/coord_conflicts` | Coordinates do not resolve to the claimed station. Check station identity and field metadata. |
| `data_in_retry/station_info_exception` | Required equipment history is missing or inconsistent. Check date coverage and antenna/radome combinations. |
| `data_in_retry/sp3_exception` | Precise orbit products could not be obtained or read. Check product availability and configured paths. |
| `data_in_retry/multidays_found` | A multiday observation was split for daily processing. Review the resulting files and dates. |
| `data_rejected/no_ppp_solution` | Position determination failed. Inspect observation quality, approximate coordinates, and processing logs. |

These are examples; the error path and log identify the actual failure.
`ArchiveService.py` revisits retry files on subsequent runs. Preserve original
observations and error evidence while resolving identity or metadata problems.
The `-purge` option deletes temporary networks, locks, and associated `data_in`
files; it is a deliberate cleanup operation, not a routine retry step.

Recent processing errors can be inspected through PostgreSQL:

```sql
SELECT "EventDate", "NetworkCode", "StationCode", "Description"
FROM events
WHERE "EventType" = 'error'
  AND "EventDate" >= NOW() - INTERVAL '1 day'
ORDER BY "EventDate" DESC;
```

For failed downloads, inspect source mappings and credentials. For PPP failures,
check RINEX quality, equipment-history coverage, orbit/clock products, ANTEX files,
and executable paths. For missing archive files, check mounted storage and the
configured archive root before considering database repair. Web/database startup
diagnostics and backup/restore procedures are in
[web setup](../installation/web-interface.md) and
[operations](../development/operations.md).

## Review integrity before repairs

Start with report modes and a bounded station/date selection:

```bash
pixi run --locked python -m com.IntegrityCheck net.station -rinex report -d 2024/01/01 2024/12/31
pixi run --locked python -m com.IntegrityCheck net.station -stnc
pixi run --locked python -m com.IntegrityCheck net.station -stnr -d 2024/01/01 2024/12/31
pixi run --locked python -m com.IntegrityCheck net.station -stns -d 2024/01/01 2024/12/31
pixi run --locked python -m com.IntegrityCheck net.station -sc noop -d 2024/01/01 2024/12/31
pixi run --locked python -m com.IntegrityCheck net.station -g 5 -d 2024/01/01 2024/12/31
```

These respectively check archive-file existence, station-info consistency,
receiver serial numbers, PPP metadata hashes, coordinate coherence, and data gaps.
`-stnc` checks the station's complete history and ignores the date filter. Report
modes can still write execution/event logs; they do not perform the requested
repair or exclusion operations.

Before changing station history, compare source field records, RINEX headers,
and the [antenna catalog](antenna-catalog.md). Inspect a proposed station.info
from `-stnp` before importing it. Do not use `ScanArchive.py -rehash` to conceal a
metadata change that requires recomputing PPP.

Mutation options have different effects: `-rinex fix` removes missing-file
records and dependent solutions; `-sc exclude` excludes PPP solutions; `-sc delete`
deletes them; `-del` removes observations and associated solutions. A station
rename/merge (`-r`) also moves archive files and handles duplicate observations.
Back up the database and affected archive files and establish the intended
station identity before these operations. See the
[CLI reference](cli-reference.md#integritycheckpy) for the option map.

The full schema and migrations define database relationships. Processing tables
use network/station identity alongside dates and filenames; equipment metadata
and the web API also have IDs that must remain stable. Use the
[database setup guide](../installation/database-setup.md) for schema changes,
rather than importing a fresh schema over an existing installation.
