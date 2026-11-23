# Installation

Develop and deploy from this fork's `dev` branch. `main` is an upstream mirror.
Use the Pixi version pinned in `mise.toml`, matching CI and Docker, with the
committed Python 3.13 environments. This fork is installed from source and does not
publish to PyPI.

## Checkout and configuration

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
mise install
pixi install --locked
cp .env.example .env
cp gnss_data.cfg.example gnss_data.cfg
```

With [mise activated](https://mise.jdx.dev/getting-started.html), `mise install`
installs Pixi for the checkout. For an unactivated shell, prefix Pixi commands
with `mise exec --`. To make every environment available locally, use
`pixi install --locked --all`. Environments live in `.pixi/envs/`.
Configure database credentials in `.env` and processing paths in `gnss_data.cfg`.
See the [configuration reference](../reference/configuration.md).

## Native installation

Create an empty PostgreSQL database owned by your GeoDE user, configure `.env`,
then initialize it and create an administrator explicitly:

```bash
pixi install --locked -e web
pixi run --locked -e web db:migrate
pixi run --locked -e web db:check
pixi run --locked -e web admin:create --username yourname
```

CLI processing and the web application share this database. There are no default
login accounts. Follow [database setup](database-setup.md) for existing databases
and [CLI setup](cli-tools.md) for processing configuration and commands.

## Docker installation

Configure `.env` and create the writable media folder as described in the
[web setup guide](web-interface.md), then start with bundled PostgreSQL:

```bash
docker compose --profile bundled-db up --build -d --wait
docker compose exec backend python manage.py createadmin --username yourname
```

Docker runs the same database initialization command and builds both the backend
and processing library from this checkout and lock. For an external database,
omit the bundled profile and configure the container connection separately from
the native connection.

To build the backend alone, run
`docker build -f web/backend/Dockerfile -t gnss-backend .` from the repository root.
The build context excludes credentials, local environments, and uploaded media.
Package metadata uses the source-archive fallback version `0.0.0`; record the Git
commit when deploying. See [operations](../development/operations.md) for backups,
restore rehearsal, and updates.

## External processing tools

Install the tools needed by your workload separately and make their executables
available through the configured paths. Basic web development and repository
tests do not require these programs.

| Tool | Source |
| --- | --- |
| GAMIT/GLOBK | [MIT](http://www-gpsg.mit.edu/gg/) |
| GFZRNX | [GFZ Potsdam](https://gnss.gfz-potsdam.de/services/gfzrnx) |
| RNX2CRX / CRX2RNX | [GSI Japan](https://terras.gsi.go.jp/ja/crx2rnx.html) |
| GPSPACE | [GitHub](https://github.com/demiangomez/GPSPACE) |

Historical institutional installers in `scripts/legacy/` are not supported setup
paths. For repository development, use the
[development workflow](../development/contributing.md).
