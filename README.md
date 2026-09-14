![GeoDE logo](logos/Highres-GeoDe-Logo-final-05-Black.png)

# GeoDE (Geodesy Database Engine)

GeoDE manages GNSS observations, station metadata, processing, and time series
analysis. Originally developed by [Demian Gomez](https://github.com/demiangomez)
and contributors, it combines a Python library and command-line tools with a
Django API, React web interface, and a shared PostgreSQL database.

## This fork

Develop and deploy from `dev` in [silentpills/geode](https://github.com/silentpills/geode).
`main` is an upstream mirror; selected upstream changes and retained scientific
defaults are documented in the [integration record](docs/development/upstream-integration.md).
The backend image builds the processing library from the same checkout. This
fork has no PyPI publication or release automation.

## Capabilities

- Download, validate, and archive RINEX observations using station identity and
  coordinate checks.
- Run PPP and GAMIT/GLOBK processing with external geodetic tools and Dispy workers.
- Manage equipment history, antenna/radome combinations, site visits, and data gaps.
- Fit and plot Extended Trajectory Models, stack solutions, and export station
  reports and campaign-planning products.
- Inspect stations and edit metadata through the map-based web interface.

## Get started

Use Pixi 0.80.0 to reproduce the committed Python 3.13 environments:

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
pixi run --locked python -m com.PlotETM --help
```

Follow the [installation guide](docs/installation/index.md) for native or Docker
setup. Credentials belong in `.env`; archive paths, executables, and compute nodes
belong in `gnss_data.cfg`. Database initialization uses Django migrations and
creates no default login accounts. Install GAMIT/GLOBK, GFZRNX, Hatanaka tools,
and GPSPACE separately when your processing workload needs them.

## Documentation

The maintained documentation lives in [`docs/`](docs/index.md):

- [Installation](docs/installation/index.md), [database setup](docs/installation/database-setup.md),
  and [configuration](docs/reference/configuration.md).
- [Processing workflow](docs/usage/processing-workflow.md) and [CLI reference](docs/usage/cli-reference.md).
- [Web interface](docs/usage/web-interface.md), [antenna catalog](docs/usage/antenna-catalog.md),
  and [reports and campaigns](docs/usage/reports-and-campaigns.md).
- [Development and checks](docs/development/contributing.md) and [operations](docs/development/operations.md).
- [Agent instructions](AGENTS.md).

Preview with `pixi run --locked -e docs docs:serve`; validate with
`pixi run --locked -e docs docs:build --strict`.

## Citation and license

If you use GeoDE in research, cite the upstream project and record the fork
revision used for reproducibility:

> Gomez, D.D., et al. (2024). GeoDE: Geodesy Database Engine for automated GNSS
> processing and analysis. [GitHub repository](https://github.com/demiangomez/geode).

GeoDE uses the [BSD 3-Clause License](LICENSE). Report fork issues in
[silentpills/geode](https://github.com/silentpills/geode/issues).
