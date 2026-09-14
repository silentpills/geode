# Working in GeoDE

GeoDE combines a Python GNSS processing library and CLI with a Django API and
React application. Develop on this fork's `dev` branch; `main` mirrors upstream.
Review upstream changes selectively, including scientific defaults, before
integrating them. This fork develops and deploys from source without PyPI
publication or release automation.

Delegate independent work to subagents when it improves speed or quality.

## Orientation

- `geode/`: processing, archive/database access, ETM fitting, and Dispy jobs.
- `com/`: command-line entry points; `geode/tests/`: processing and API tests.
- `web/backend/`: Django models, API, management commands, and migrations.
- `web/frontend/`: React/TypeScript application.
- `docs/`: canonical setup, usage, reference, and development guides, built by
  MkDocs. Start with [development](docs/development/contributing.md) and the
  [upstream integration record](docs/development/upstream-integration.md).

The processing backend still uses Dispy. `CeleryMigrationPlan.md` is a proposal,
not implemented architecture or a standing instruction to migrate it.

## Environments and verification

Use Pixi 0.80.0 and `pixi install --locked`. Environments live in `.pixi/envs/`;
use the existing tasks instead of creating another virtual environment.
`pixi.toml` and `pixi.lock` govern Python installation; frontend tasks use `npm ci`
with `web/frontend/package-lock.json`.

Run checks relevant to the change; the development guide describes the full CI
surface and existing informational checks:

| Change | Check |
| --- | --- |
| Processing or CLI code | `pixi run --locked check` |
| API, schema, bootstrap, or backend management | `pixi run --locked -e web test:api` |
| Optional report exports | `pixi run --locked -e reports test geode/tests/test_reports.py` |
| Documentation | `pixi run --locked -e docs docs:build --strict` |
| Frontend | `pixi run --locked -e frontend frontend:build` |

`check` runs Ruff lint, formatting checks, and pytest. Typechecking is currently
informational and separate (`pixi run --locked typecheck`). Hooks check source;
they do not format or fix it automatically.

The API and PostgreSQL tests create temporary local clusters and do not use the
configured application database. Run them as an unprivileged user with the Pixi
PostgreSQL tools available. `db:migrate`, `db:check`, and `doctor` instead use the
configured database; they are not substitutes for isolated tests. Real GNSS
processing and deployment validation require external tools and infrastructure;
state when these were not exercised.

## Data and schema boundaries

- Keep the processing schema and web models compatible: preserve SQL-owned
  primary keys, station identity, and public API IDs. Add model changes and
  migrations together. `geode/sql/bootstrap_v1/` is immutable; later processing
  SQL belongs in a new versioned migration, shared with CLI startup as needed.
- Preserve antenna/radome identities and height conversions. See the
  [catalog contract](docs/usage/antenna-catalog.md) before changing metadata.
- Archive files, field observations, station histories, and numerical defaults
  are scientific inputs. Use fixtures for development and make intended changes
  to those inputs explicit; do not repair them as a side effect of code cleanup.
- Keep credentials in local `.env` and processing paths in `gnss_data.cfg`.
  Use the [operations guide](docs/development/operations.md) for database/media
  backups and migrations of an existing installation.

Keep current instructions in these entry points and the relevant `docs/` page.
Use Git history for superseded setup guides. Make focused Conventional Commits
and report the checks performed and any remaining limitations.
