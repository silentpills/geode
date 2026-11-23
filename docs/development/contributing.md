# Development workflow

Use `dev` for this fork's development and deployment. Keep `main` as an upstream
mirror and review upstream changes before integrating them. Make logical commits
using Conventional Commit messages (`fix(db): ...`, `docs: ...`, etc.). There is
no package publication, release tagging, or changelog automation.

## Native environments

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
mise install
pixi install --locked --all
```

Use the Pixi version pinned in `mise.toml`. Pixi owns the environments under `.pixi/envs/` in the checkout;
do not create another uv/venv environment. `default` includes processing and dev
tools; `web` adds Django tests; `runtime` contains the production backend without
dev tools; `reports`, `docs`, `frontend`, and `audit` cover their named tasks.
The single committed `pixi.lock` records packages for Linux x86-64 and Apple
Silicon. The dedicated `postgres` environment supplies PostgreSQL 19 executables
such as `initdb`, `pg_ctl`, and `pg_dump`. Pixi resolves their native libraries
separately from GDAL and the other processing libraries. GeoDE connects to its
configured database through psycopg in the application environment. Installing
the tools does not start a database service. Apple Silicon installs require
macOS 13.3 or later for these binaries.

## Verification

Run checks relevant to the files and behavior changed. CI runs the full set
below; documentation-only changes need the strict documentation build. Use
`pixi run --locked test path/to/test.py` for a focused processing test while
developing, then run the relevant suite before committing.

```bash
pixi run --locked check
pixi run --locked -e web test:api
pixi run --locked -e reports test geode/tests/test_reports.py
pixi run --locked -e docs docs:build --strict
pixi run --locked -e frontend frontend:build
```

The processing and API test tasks automatically install the locked `postgres`
environment. Pytest starts temporary local database clusters with its binaries.
The API suite tests
empty and existing schemas, repeated migrations, model/migration consistency,
explicit administrator creation, readiness, backup/restore, antenna metadata,
and the historical Django suite. It does not connect to your configured database.
The worker integration test runs in `web` with `GEODE_TEST_REDIS_URL` set to
an isolated disposable Redis database. CI supplies that broker. The test
runs the station processing CLI on both a serial runner and a Celery worker.
Run these database tests as an unprivileged user because PostgreSQL refuses to
initialize a server as root.

`check` runs Ruff lint, formatting checks, and pytest. Ruff checks processing
code, CLI modules, maintenance tools, and backend management commands. The legacy
backend has a wider style/type backlog outside that scope.
`pixi run --locked typecheck` is informational in CI and manual locally; it is
not part of `check`.
`pixi run -e frontend frontend:lint` is available for working through the existing
frontend lint backlog. The TypeScript/Vite build is required in CI.

## Hooks

```bash
pixi run precommit:install
pixi run precommit:run
```

Hooks call the same locked Ruff tasks as CI. Install both pre-commit and
commit-msg hooks using the task above. The optional typecheck hook runs only
with `pre-commit run ty-check --hook-stage manual`. Gitleaks and basic file checks
also run locally. Checks do not change source files automatically; use
`pixi run lint:fix` and `pixi run format` deliberately.

## Schema and dependency changes

Change Django models and add migrations together. Run `pixi run -e web db:check`
against your configured database, then run the isolated API suite. Keep SQL-owned
processing primary keys and IDs stable. The bootstrap snapshot is immutable;
new processing SQL belongs in a new versioned migration, shared with CLI startup
where appropriate.

Edit dependency constraints in `pixi.toml`, refresh `pixi.lock`, and review both.
Python metadata in `pyproject.toml` describes the local package, while Pixi is the
installation authority. `web/backend/requirements.txt` has been removed to avoid
resolving a second, conflicting runtime. Use `npm ci` via the frontend Pixi tasks;
commit intentional changes to `web/frontend/package-lock.json`.

See [operations](operations.md) for deployment and restoration procedures.

## Documentation and automation

Maintain setup in `docs/installation/`, user workflows in `docs/usage/`, and
configuration details in `docs/reference/`. This page owns development commands;
the README and root `AGENTS.md` provide entry points. Update the relevant guide
in the same change as the behavior it describes. Record upstream port decisions
in `UPSTREAM.md` at the repository root. Use Git history for superseded guides
and completed or abandoned proposals.

MkDocs uses `mkdocs.yml` and the `docs` environment. Add new maintained pages to
its navigation and validate links with the strict build. There is no separate
Sphinx build. The tracked workflows are `test.yml` (checks), `security.yml`
(secret/dependency scans), and `docker.yml` (container validation).
