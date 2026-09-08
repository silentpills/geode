# Antenna and radome catalog

Register the antenna **model and radome combination** before adding station
equipment history. A radome is the antenna's protective cover; use `NONE` only
when there is no radome. A blank or unknown code must not be guessed as `NONE`.

The fork keeps two related catalogs:

- `antennas` describes antenna models and retains their existing numeric API IDs.
  GAMIT height conversions in `gamit_htc` still belong to the antenna model.
- `antenna_radomes` registers combinations, each with its own stable numeric ID
  and a unique antenna/radome pair. Station history references that pair.

Registration records an equipment identity. It **does not confirm that a suitable
calibration is available**. Processing continues to use the configured ANTEX files;
calibration selection must still agree with the observation date and processing
reference frame. This change does not import correction values, select calibration
versions, or change computed coordinates by itself.

## Initial setup and upgrades

Fresh databases include the catalog in `database/schema.sql`. Existing databases
receive it through Django migration `0035_antenna_radomes` or the processing CLI's
normal database initialization. Both use the same immutable SQL migration;
applying the Django migration after CLI initialization is supported. Continue to
run the usual Django migrations to record their state and install the permissions
from migration `0036_antenna_catalog_permissions`.

Existing station histories are backfilled into the catalog exactly as stored,
including legacy blank or unknown codes. Antenna-model IDs and height conversions
are preserved. Catalog rows cannot be deleted while station history references
them. Renaming a model or a registered combination cascades to its references;
use station-history records, rather than renaming a catalog entry, to represent
an equipment replacement.

A fresh catalog has no station history to backfill. Loading `antennas.csv` alone
does not register radomes. Before importing station logs, register the combinations
in use, either explicitly or from a trusted ANTEX file. We do not create a `NONE`
combination for every antenna model.

## Register combinations with Pixi

Run from the repository root. Database access uses the normal `.env` configuration;
a local `gnss_data.cfg` can still supply legacy database settings if present.

```bash
# Preview without a database connection or configuration file.
pixi run AntennaCatalog.py --dry-run add ASH700936D_M SNOW

# Register a verified combination.
pixi run AntennaCatalog.py add ASH700936D_M SNOW

# Review the receiver combinations found in an ANTEX 1.4 file.
pixi run AntennaCatalog.py --dry-run import-antex /path/to/igs20.atx

# Register those combinations in one transaction.
pixi run AntennaCatalog.py import-antex /path/to/igs20.atx
```

Codes supplied to this command are trimmed and uppercased. Repeating a registration
preserves existing IDs and model descriptions. Missing antenna models are added,
but their height-conversion rows are not invented: maintain `gamit_htc` separately
before using those models with a height code.

The importer reads fixed-width receiver identities from **ANTEX 1.4**. Satellite
records and identities without explicit radomes are excluded. It rejects unsupported
versions and incomplete antenna sections before writing anything. It does not load
or validate the numerical calibration values. See the
[IGS ANTEX format description](https://files.igs.org/pub/data/format/antex14.txt).

Station-log imports and the terminal station editor validate the pair before
changing history. An unregistered pair produces an error identifying the combination;
register it after checking the source, then retry the import.

## Web editing and API

In the station-information editor, choose the antenna model and then select one of
its registered radomes. A missing combination requires a catalog administrator to
register it first. Changing only a comment or another unrelated field still works;
the API checks the resulting record, including values retained by a partial update.

The existing `/api/antennas` endpoints continue to manage antenna models. The new
endpoints manage combinations:

| Method and path | Purpose |
| --- | --- |
| `GET /api/antenna-radomes?antenna_code=ASH700936D_M` | List combinations for a model; `radome_code` filtering is also supported. |
| `POST /api/antenna-radomes` | Register a pair for an existing model. |
| `GET /api/antenna-radomes/{api_id}` | Retrieve a combination by its stable ID. |
| `PUT` or `PATCH /api/antenna-radomes/{api_id}` | Correct a catalog identity; references follow the correction. |
| `DELETE /api/antenna-radomes/{api_id}` | Remove an unused combination. |

For registration, send JSON such as:

```json
{"antenna_code": "ASH700936D_M", "radome_code": "SNOW"}
```

The API returns `api_id`, `antenna_code`, and `radome_code`. Existing station-info
payloads retain their separate antenna and radome fields; clients do not need to
replace them with the combination ID. Unknown combinations return a validation
error. Catalog writes participate in the existing Django audit log.

Existing endpoint clusters with antenna-catalog permissions receive the matching
combination permissions during migration. Station readers do not gain catalog-write
access. Administrators can assign the new endpoints through the existing role
configuration; this adds no new service or deployment branch.

## Development checks

All Python environments live under the repository's `.pixi` directory:

```bash
pixi run test geode/tests/test_antenna_catalog.py geode/tests/test_processing_diagnostics.py
pixi run -e web test:api
npm ci --prefix web/frontend
npm run build --prefix web/frontend
```

Database tests start their own isolated PostgreSQL server; they do not use a deployed
GeoDE database. The antenna migration is tested against an older schema and the
current SQL bootstrap, and its Django state is checked against the current model.
The repository-wide Django `makemigrations --check` also encounters existing
`SourcesStations` model/migration differences; that broader cleanup is separate
from the antenna migrations.

Database calibration management and the LLM metadata comparison/planning workflow
remain deferred.
