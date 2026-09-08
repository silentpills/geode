# Upstream integration: September 2026

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
- Database calibration-value import and selection, GAMIT project/reference-frame
  management tables, and LLM-assisted metadata planning remain deferred. The
  reporting tools do not require those features.

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
