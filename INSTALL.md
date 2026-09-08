# Installation

Develop and deploy from this fork's `dev` branch. `main` is an upstream mirror.
The supported Pixi environment uses Python 3.13 and PostgreSQL 18; Docker installs
the backend and processing library from the same checkout and lock. This fork
does not publish to PyPI.

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
cp .env.example .env
```

Use **Pixi 0.80.0**, matching CI and Docker. Environments live inside this
repository at `.pixi/envs/`; no separate virtual environment is needed. Configure
database credentials in `.env` and processing paths in `gnss_data.cfg` (copy
`gnss_data.cfg.example`).

For a native database, create an empty database owned by your GeoDE user, then:

```bash
pixi run -e web db:migrate
pixi run -e web db:check
pixi run -e web admin:create --username yourname
```

For a complete Docker installation with bundled PostgreSQL, configure `.env`
and create the writable media folder as described in the
[web setup guide](docs/installation/web-interface.md), then:

```bash
docker compose --profile bundled-db up --build -d --wait
docker compose exec backend python manage.py createadmin --username yourname
```

Both paths use the same initialization procedure. There are no default login
accounts. For an external database, omit the bundled profile and configure the
container connection separately from the native connection.

- [Database setup](docs/installation/database-setup.md): new and existing schemas.
- [CLI setup](docs/installation/cli-tools.md): processing settings and commands.
- [Web setup](docs/installation/web-interface.md): Docker, login, and diagnostics.
- [Operations](docs/development/operations.md): backups, restore rehearsal, updates.
- [Development](docs/development/contributing.md): checks and dependency workflow.

GAMIT/GLOBK, GFZRNX, Hatanaka tools, and GPSPACE are external processing tools;
install the ones needed for your workloads separately. Basic web development
and repository tests do not require them. Historical institutional installers
are archived in `scripts/legacy/` and are not supported setup paths.

To build the backend alone, run
`docker build -f web/backend/Dockerfile -t gnss-backend .` from the repository root.
Docker build context excludes credentials, local environments, and uploaded
media. Its package metadata uses the source-archive fallback version `0.0.0`;
record the Git commit when deploying.
