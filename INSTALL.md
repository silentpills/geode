# Installation

GeoDE requires Python 3.10 or later.

Use the `dev` branch of this fork for development and deployment. `main` mirrors
upstream and does not contain the fork's complete deployment setup.

Commands run through Pixi from the repository root, for example:

```bash
pixi run python -m com.PlotETM --help
```

For a library installation outside Pixi, install the checked-out source with
`python -m pip install .`. The published `geode-gnss` package on PyPI may differ
from this fork.

## As a Development or Production Environment

We recommend using [Pixi](https://pixi.sh/) to manage the Python environment and dependencies.

### 1. Clone the Repository

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
```

### 2. Install Dependencies

```bash
pixi install --locked
```

### 3. Activate the Environment

```bash
pixi shell
```

You can deactivate the environment by typing `exit` or pressing Ctrl+D.

### 4. Database Setup

See [Database Setup](docs/installation/database-setup.md) for detailed instructions on:

- Installing and configuring PostgreSQL
- Loading the database schema (`database/schema.sql`)
- Loading seed data (`database/seed.sql`)

### 5. Configuration File

Create `gnss_data.cfg` in your working directory. See [CLI Tools Setup](docs/installation/cli-tools.md) for configuration details.

## External Dependencies

> [!IMPORTANT]
> GeoDE requires access to some executables which are not installed by default. These programs are not all needed if you are planning to just execute time series analysis. The external dependencies are:
> + GAMIT/GLOBK: http://www-gpsg.mit.edu/gg/
> + GFZRNX: https://gnss.gfz-potsdam.de/services/gfzrnx
> + rnx2crx / crx2rnx: https://terras.gsi.go.jp/ja/crx2rnx.html (although this is also installed with GAMIT/GLOBK)
> + GPSPACE: https://github.com/demiangomez/GPSPACE (forked from https://github.com/lahayef/GPSPACE)

## Web Interface (Optional)

To deploy the web interface, see [Web Interface Setup](docs/installation/web-interface.md).

## Backend source and Docker builds

`docker compose build backend` installs both the backend dependencies and the
GeoDE library from this checkout. To build the backend image directly, run from
the repository root:

```bash
docker build -f web/backend/Dockerfile -t gnss-backend .
```

The repository's Docker ignore rules exclude `.env`, local environments, and
media/log directories from the build context. Keep credentials in `.env` and pass
them at runtime through Compose. A source archive without Git metadata reports
package version `0.0.0`; builds from a Git checkout can use setuptools-scm metadata.
