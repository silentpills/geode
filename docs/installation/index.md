# Installation Overview

GeoDE requires Python 3.10 or later and several external dependencies.

## Prerequisites

Before installing GeoDE, ensure you have the following external dependencies. Some of these require licenses or specific academic access.

| Dependency | Source | Notes |
|------------|--------|-------|
| **GAMIT/GLOBK** | [MIT](http://www-gpsg.mit.edu/gg/) | Requires academic license |
| **GFZRNX** | [GFZ Potsdam](https://gnss.gfz-potsdam.de/services/gfzrnx) | Mac users: allow unsigned software in System Settings |
| **RNX2CRX / CRX2RNX** | [GSI Japan](https://terras.gsi.go.jp/ja/crx2rnx.html) | Often included with GAMIT |
| **GPSPACE** | [GitHub](https://github.com/demiangomez/GPSPACE) | Fork of lahayef/GPSPACE |

!!! important
    These programs must be installed and available in your PATH. You can verify installation by running `which <program>`. For example:
    ```bash
    which crx2rnx
    # Should return something like: /home/user/gg/gamit/bin/crx2rnx
    ```

## Installation Methods

### As a Python Package

For time series analysis and library usage:

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
```

This installs Python libraries and dependencies but does not set up database tools.

### Development Environment with Pixi

We recommend using [Pixi](https://prefix.dev/) to manage the Python environment and dependencies.

1. **Clone the repository:**
    ```bash
    git clone --branch dev https://github.com/silentpills/geode.git
    cd geode
    ```

2. **Install dependencies:**
    ```bash
    pixi install --locked
    ```

3. **Activate the shell:**
    ```bash
    pixi shell
    ```

## Complete Setup Order

For a full GeoDE installation with database and web interface:

1. **Install prerequisites** (GAMIT, GFZRNX, etc.)
2. **Set up PostgreSQL database** - See [Database Setup](database-setup.md)
3. **Configure GeoDE** - See [CLI Tools](cli-tools.md)
4. **Deploy web interface** (optional) - See [Web Interface](web-interface.md)

## Next Steps

- [Database Setup](database-setup.md) - Set up PostgreSQL with the GeoDE schema
- [CLI Tools](cli-tools.md) - Configure and run command-line tools
- [Web Interface](web-interface.md) - Deploy the Django/React web interface
