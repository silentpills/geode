# Development workflow

Use `dev` for this fork's development and deployment. Keep `main` as an upstream
mirror and review upstream changes before integrating them. Make logical commits
using Conventional Commit messages (`fix(db): ...`, `docs: ...`, etc.). There is
no package publication, release tagging, or changelog automation.

## Native environments

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
```

Use Pixi 0.80.0. Pixi owns the environments under `.pixi/envs/` in the checkout;
do not create another uv/venv environment. `default` includes processing and dev
tools; `web` adds Django tests; `runtime` contains the production backend without
dev tools; `reports`, `docs`, `frontend`, and `audit` cover their named tasks.

## Required checks

```bash
pixi run check
pixi run -e web test:api
pixi run -e reports test geode/tests/test_reports.py
pixi run -e docs docs:build --strict
pixi run -e frontend frontend:build
```

The API task starts isolated PostgreSQL clusters using Pixi's dev tools. It tests
empty and existing schemas, repeated migrations, model/migration consistency,
explicit administrator creation, readiness, backup/restore, antenna metadata,
and the historical Django suite. It does not connect to your configured database.
Run these database tests as an unprivileged user because PostgreSQL refuses to
initialize a server as root.

Ruff checks processing code, CLI modules, maintenance tools, and backend
management commands. The legacy backend's wider style/type backlog is not
silently reformatted as part of this maintenance work. `pixi run typecheck` is
informational in CI and manual locally; it is not part of `check`.
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
