# Reports and campaign planning

These tools run from the same `dev` checkout as the processing library and web
application. They do not require a separate upstream branch or a new web service.

## Station reports and KMZ export

Use the optional reports environment for PDF output and map tiles:

```bash
pixi install --locked -e reports
pixi run -e reports python -m com.StationReport net.station -o production/reports
pixi run -e reports python -m com.StationReport net.station --pdf -o production/reports
pixi run -e reports python -m com.StationKmz net.station -o production/reports
```

Reports include station metadata, equipment history, visits, and available ETM
and RINEX plots. KMZ files can be opened in Google Earth. HTML/KMZ generation is
also available in the default environment; PDF rendering requires WeasyPrint,
and map tile fetching requires StaticMap. For a pip source install, these are
available through `pip install '.[reports]'`.

Database credentials come from `.env`, as with the rest of this fork. Local media
files are resolved beneath `MEDIA_FOLDER_HOST_PATH`, falling back to `[archive]
`media` in `gnss_data.cfg`. Use `GNSS_CONFIG_FILE` to select another configuration
file for these report commands. Set the media path to a directory accessible on
the machine running the command.

`StationReport --no-maps` avoids fetching map tiles. `--no-timeseries` and
`--no-rinex` omit the corresponding plots. Run each command with `--help` for
available sections and options. The report commands read station data; normal
CLI connection initialization can apply the existing automatic schema migrations.

## Campaign planner

```bash
pixi run python -m com.CampaignPlanner --config example_campaign.json --output production/campaign.html
```

Copy and customize the example's start/end cities, start date, station list,
working hours, time on site, and cost assumptions. The planner orders visits
using a nearest-neighbour heuristic, requests driving routes, and produces a
multi-day schedule and HTML map. Treat it as a proposed itinerary to review;
the ordering is not guaranteed to be globally optimal.

The `new_sites` option also accepts explicit coordinates:

```json
{"name": "Proposed site", "lat": -34.1667, "lon": -69.7167}
```

A campaign containing only new sites does not need a database connection. Existing
station selections use the configured GeoDE database. Planning queries geocoding
and routing services; report generation may fetch map tiles and Leaflet assets.
The saved schedule is readable offline, while interactive background map tiles
still require network access.

The planner creates an itinerary file; it does not add stations, campaigns, or
visits to the database. It is currently a CLI/library tool, not a new web UI page.
