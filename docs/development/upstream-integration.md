# Upstream integration

## September 2026

This update ports selected changes from `demiangomez/geode` through
`fbfca0b` (upstream `master`, mirrored by this fork's `main`). The starting fork
revision was `86dd1c3`. The changes are grouped into commits on `dev`; this is a
selective integration, not a merge of upstream's complete history. Git may still
list the original upstream commits as absent even where their code was ported.

## Included

- Command timeouts and retries, bounded cluster checks, RINEX header normalization,
  longer GFZRNX timeouts, PPP exception fixes, archive summaries, station dates,
  and ASCII-compatible GAMIT station-info exports.
- The connected ETM fitting, parameter-management, visualization, and modular
  stacker changes; fit-window fixes; periodogram output; parallel plotting; and
  improved diagnostic logging. The old stacker import path remains available.
- PPP elevation residual storage and export, and event-date/stack-name indexes.
  Fresh SQL installs, Django migration 0034, and CLI initialization support the
  additive schema changes.
- Station HTML/PDF reports, KMZ export, and campaign planning, with optional PDF/map
  dependencies in the `reports` Pixi environment.
- Local editable installation in Pixi, recursive package/data discovery, CLI
  entry points, and backend Docker builds using this checkout's processing code.

## Fork decisions retained

- `.env` supplies database credentials; psycopg3 remains the database driver.
- Pixi, the single Compose deployment, Django/React integration, existing CI, and
  the fork's clustering compatibility changes remain in place.
- Relaxation defaults remain `[0.05, 1]`, with earthquake and jump spacing both
  at 3 days. Upstream's changed scientific defaults are not adopted implicitly.
- Quoted command arguments and argument lists remain supported.
- Antenna/radome identity is implemented with a separate combination catalog,
  preserving the model table, API IDs, and height conversions. CLI imports,
  station editing, and the web API enforce the pair. See the
  [antenna catalog guide](../usage/antenna-catalog.md).
- FixPlate saves bounded reference-frame provenance with atomic corrected
  stacks, per-epoch source identities, and a minimal GAMIT project identifier
  catalog. See [saved reference frames](../usage/reference-frames.md).
- Database calibration-value import and selection, full GAMIT project
  configuration management, and LLM-assisted metadata planning remain deferred.
  The reporting tools do not require those features.

## Validation

Use the repository environments:

```bash
pixi run lint
pixi run format:check
pixi run test
pixi run -e reports test geode/tests/test_reports.py
pixi run -e web test:api
pixi run -e docs docs:build
```

The tests include synthetic ETM fitting, subprocess behavior, station-info
round trips, PPP residual parsing, an isolated PostgreSQL schema/migration test,
HTML escaping, PDF/KMZ export, and offline campaign-planning checks. PostgreSQL
executables are part of the Pixi dev feature; the database test creates and shuts
down its own temporary server using a local Unix socket.

The existing typecheck job remains informational and still reports issues; lint,
formatting, and runtime tests are separate checks. CLI help smoke tests also
verify that the installed commands load outside the checkout without a database
or a GNSS configuration file.

Real GAMIT/GFZRNX/GPSPACE processing, an operational Dispy cluster, and an actual
Docker deployment require their respective external tools and infrastructure.


## Fork maintenance after integration

The follow-up maintenance keeps Django on 5.2 LTS and reconciles its processing
model history in migration 0037. Empty and existing processing databases now
share one initialization command. Fresh migrations create no login accounts;
use the explicit administrator command.

Docker and API tests share the locked Pixi runtime, including the patched DRF
3.17 series. Startup stops on migration failures, and readiness checks the actual
database/migration state. CI now includes the complete historical Django suite,
frontend and documentation builds, and a fresh Docker deployment smoke test.
The repaired Python audit found vulnerable dependencies that were updated;
public release and package publication automation has been removed from `dev`.
See [operations](operations.md) for backup/restore and update procedures.

## November 2026: correctness and robust-fit memory

The fork's `main` was fast-forwarded from `33883a8` to upstream `643cb77`.
The first selective port to `dev` takes the following fixes from that range:

- `7f5fd65` and `0943193`: refresh cached RINEX headers and observations after
  conversion, windowing, decimation and constellation removal. Later header
  rewrites must preserve the processed observations. Successful edits to a
  separate output file leave the original object intact.
- `7f5fd65`: GPSPACE converts the current working RINEX file rather than reopening
  the original input. A validated short window remains valid when copied for
  processing, while initial input validation retains its duration requirement.
  The fork makes the upstream timeout increase configurable as `ppp_timeout`,
  defaulting to 900 seconds per attempt; timed-out commands retain two retries.
- `f54b93a`: extract coseismic offsets from the stored component layout instead
  of the relaxation count, which can be stale after decay removal. Empty,
  malformed or unfit coseismic parameters are excluded without changing the
  earthquake scoring model.
- `fcfd6b2`: store robust-fit weights as diagonal vectors instead of allocating
  an observation-by-observation matrix. Preserve the existing fit thresholds,
  uncertainty scaling, outlier flags and spectral diagnostics.

Regression coverage uses synthetic RINEX edits with a mocked GFZRNX boundary,
GPSPACE setup and subprocess timeout checks, flat and nested earthquake fit
records, and comparisons against the previous dense-weight fit equations.
The weight tests cover outliers, unequal weights, constraints and an exhausted
iteration budget, with an allocation check for linear weight storage.

These ports do not add PRIDE, GLS noise fitting, station merging or new product
selection. Those remain separate integrations requiring validation against the
fork's scientific and database contracts. Real GFZRNX/GPSPACE processing still
requires operational tools and representative observation data.
