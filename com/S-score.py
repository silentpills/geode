#!/usr/bin/env python
"""
Project: Geodesy Database Engine (GeoDE)
Date: 9/25/24 11:29AM
Author: Demian D. Gomez

Description goes here

"""

import argparse

import numpy as np

# app
from geode import dbConnection, pyOkada
from geode.Utils import add_version_argument, file_readlines, print_columns, stationID


def read_station_file(filename):
    """Read name/latitude/longitude rows, ignoring comments and extra columns."""
    names, lats, lons = [], [], []
    for line_no, line in enumerate(file_readlines(filename), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.replace(",", " ").split()
        try:
            lat, lon = float(fields[1]), float(fields[2])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("coordinates out of range")
        except (IndexError, ValueError):
            print(
                " -- Skipping line %i: expected name lat lon with finite coordinates "
                "in [-90, 90] and [-180, 180]" % line_no
            )
            continue
        names.append(fields[0])
        lats.append(lat)
        lons.append(lon)
    return names, np.array(lats), np.array(lons)


def print_station_scores(mask, event, names, lats, lons):
    """Report classifications separately from the explicitly identified values."""
    c_mask, p_mask, c_value, p_value = mask.score_values(lats, lons)
    print(" >> S-score values for %s (id %s)" % (event["location"], event["id"]))
    print(
        " >> Level %i; quantity=%s; units=%s; nearest mask grid point"
        % (mask.score_level, mask.score_quantity, mask.score_units)
    )
    if mask.score_level == 2:
        print(
            " >> Values are mean nodal-plane displacement magnitudes minus 0.001 m "
            "on the rescaled mask grid, not physical station displacements."
        )
        print(
            " >> Masks use any nodal plane exceeding the threshold; "
            "a negative mean margin can still have mask=1."
        )
    print(
        "%-16s %10s %11s %6s %6s %12s %12s"
        % ("Station", "Lat", "Lon", "c_mask", "p_mask", "c_value", "p_value")
    )
    for i, name in enumerate(names):
        print(
            "%-16s %10.4f %11.4f %6i %6i %12.6f %12.6f"
            % (name, lats[i], lons[i], c_mask[i], p_mask[i], c_value[i], p_value[i])
        )


def main():
    parser = argparse.ArgumentParser(
        description="Output S-score kmz files for a set of earthquakes. Output is produced"
        " on the current folder with a kmz file named using the USGS code."
    )

    parser.add_argument(
        "earthquakes",
        type=str,
        nargs="+",
        help="USGS codes of specific earthquake to produce kmz files",
    )

    parser.add_argument(
        "-post",
        "--postseismic",
        action="store_true",
        help="Include the postseismic S-score",
        default=False,
    )

    parser.add_argument(
        "-disp",
        "--output_displacements",
        nargs="?",
        type=str,
        metavar="[stack_name]",
        const="ppp",
        help="Output the displacements produced by the requested earthquake. "
        "By default, the ppp ETM solution is printed. To output another stack ETM, specify "
        "provide a stack_name.",
    )

    parser.add_argument(
        "-table",
        "--output_table",
        action="store_true",
        help="Output the list of stations affected by the requested earthquake.",
        default=False,
    )

    parser.add_argument(
        "-ad",
        "--azimuth_distance",
        action="store_true",
        help="Output the list of stations affected by the requested earthquake with "
        "the azimuth and distance to epicenter.",
        default=False,
    )

    parser.add_argument(
        "-scores",
        "--score_stations",
        type=str,
        metavar="station_file",
        help="Print mask classifications and numerical values for stations in a "
        "name lat lon text file (whitespace or comma separated). Values are "
        "dimensionless isotropic S-scores without a focal mechanism, or mean "
        "Okada margins in metres on the rescaled mask grid with one. "
        "Comments starting with # and extra columns are ignored.",
    )

    parser.add_argument(
        "-density",
        "--mask_density",
        nargs=1,
        type=int,
        metavar="{mask_density}",
        default=[750],
        help="A value to control the quality of the output mask. "
        "Recommended for high quality is 1000. For low quality use 250. Default is 750.",
    )

    add_version_argument(parser)

    args = parser.parse_args()

    cnn = dbConnection.Cnn("gnss_data.cfg")

    for eq in args.earthquakes:
        event = cnn.query("SELECT * FROM earthquakes WHERE id = '%s'" % eq)
        if len(event):
            event = event.dictresult()[0]

            mask = pyOkada.Mask(cnn, event["id"])
            mask.save_masks(kmz_file=eq + ".kmz", include_postseismic=args.postseismic)

            if args.output_table:
                table = pyOkada.EarthquakeTable(cnn, event["id"], args.postseismic)
                print(
                    " >> Stations affected by %s (id %s, co+post-seismic)"
                    % (event["location"], event["id"])
                )
                print_columns([stationID(stn) for stn in table.c_stations])

                if args.postseismic:
                    print(
                        " >> Stations affected by %s (id %s, post-seismic only)"
                        % (event["location"], event["id"])
                    )
                    print_columns([stationID(stn) for stn in table.p_stations])
                else:
                    print(" >> Post-seismic affected stations not requested")

            if args.output_displacements:
                table = pyOkada.EarthquakeTable(cnn, event["id"], args.postseismic)
                print(
                    " >> Co-seismic displacements produced by %s "
                    "(id %s, NEU, stack name %s)"
                    % (event["location"], event["id"], args.output_displacements)
                )

                for stn in table.get_coseismic_displacements(args.output_displacements):
                    print(
                        "%s : %6.3f %6.3f %6.3f"
                        % (stationID(stn), stn["n"], stn["e"], stn["u"])
                    )

            if args.azimuth_distance:
                table = pyOkada.EarthquakeTable(cnn, event["id"], args.postseismic)
                print(
                    " >> Azimuth and distance to %s "
                    "(id %s)" % (event["location"], event["id"])
                )

                for stn in table.c_stations:
                    print(
                        "%s : %6.1f deg %6.1f km"
                        % (stationID(stn), stn["azimuth"], stn["distance"])
                    )

            if args.score_stations:
                names, lats, lons = read_station_file(args.score_stations)
                if names:
                    print_station_scores(mask, event, names, lats, lons)
                else:
                    print(" -- No valid stations found in %s" % args.score_stations)

        else:
            print(" -- Event %s not found" % eq)


if __name__ == "__main__":
    main()
