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

The API task starts isolated PostgreSQL clusters using Pixi's dev tools. It tests
empty and existing schemas, repeated migrations, model/migration consistency,
explicit administrator creation, readiness, backup/restore, antenna metadata,
and the historical Django suite. It does not connect to your configured database.
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
the README and root `AGENTS.md` provide entry points. Keep the dated
[upstream integration record](upstream-integration.md) for the rationale behind
fork decisions. Superseded root setup guides and the old all-in-one user manual
are available in Git history.

MkDocs uses `mkdocs.yml` and the `docs` environment. Add new maintained pages to
its navigation and validate links with the strict build. There is no separate
Sphinx build. The tracked workflows are `test.yml` (checks), `security.yml`
(secret/dependency scans), and `docker.yml` (container validation).
