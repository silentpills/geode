# Welcome to GeoDE

**GeoDE** (Geodesy Database Engine) is a powerful Python package designed to streamline and accelerate the processing of GNSS data for geodetic applications, using MIT's GAMIT/GLOBK software. This repository focuses on parallelizing the workflow, allowing for efficient utilization of computing resources and significantly reducing the time required for complex data analyses.

Developed by [Demian Gomez](https://github.com/demiangomez) and contributors, GeoDE provides a framework to manage and run multiple GAMIT jobs in parallel, optimizing processing times and enabling researchers to handle large datasets with ease.

## Key Features

- **Parallel Execution**: Run GAMIT processing tasks concurrently to maximize computational throughput using [dispy](https://github.com/pgiri/dispy).
- **Database Integration**: Store and manage data in PostgreSQL for enhanced accessibility and organization. The relational database guarantees data consistency and can handle very large datasets (tested with ~14M station-days).
- **Data Preparation**: Efficiently prepare data for parallel processing with GAMIT/GLOBK. The web interface and REST-API allow easy visualization of data and metadata.
- **Error Handling and Monitoring**: Built-in tools for error detection and log management.
- **Station Name Duplicate-Tolerance**: Uses a three-letter network code to handle duplicate station codes across networks.
- **Automatic Network Splitting**: Splits large networks (>50 stations) into subnetworks for GAMIT processing.

## Capabilities

- Scan directory structures containing RINEX files and add them to the database
- Manage station metadata in GAMIT's station info format with consistency checks
- Add new RINEX data by geolocation (PPP-based, avoiding duplicate station codes)
- Handle ocean loading coefficients for PPP and GAMIT coordinates
- Plot PPP time series using Bevis and Brown's (2014) extended trajectory model
- Manage GNSS stations (add, merge, delete)
- Parse zenith tropospheric delays and store them in the database
- Stack GAMIT solutions to produce regional or global reference frames

## Quick Start

```bash
git clone --branch dev https://github.com/silentpills/geode.git
cd geode
pixi install --locked
pixi shell
```

See the [Installation Guide](installation/index.md) for detailed setup instructions.

## Components

GeoDE has two main components:

1. **Command Line Interface (CLI)**: Execute parallel jobs for GNSS processing
2. **Web Interface (web-ui)**: Visualize results and manage station metadata

## License

BSD-3-Clause

## Citation

See [CITATION.cff](https://github.com/demiangomez/Parallel.GAMIT/blob/main/CITATION.cff) for citation information.
