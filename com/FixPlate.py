#!/usr/bin/env python
"""
Project: Geodesy Database Engine (GeoDE)
Date: 6/15/24 10:29 AM
Author: Demian D. Gomez

Description goes here

"""

import argparse
import datetime
import json
import os
import tempfile

import numpy as np
import simplekml
from tqdm import tqdm

from geode import dbConnection, pyETM
from geode.pyDate import Date
from geode.pyLeastSquares import adjust_lsq
from geode.pyOkada import ScoreTable, cosd, sind
from geode.reference_frames import frame_provenance, save_frame, source_epochs
from geode.Utils import (
    add_version_argument,
    cart2euler,
    file_write,
    get_stack_stations,
    print_columns,
    process_stnlist,
    required_length,
    stationID,
    xyz2sphere_lla,
)


def build_design(hdata, vdata):
    An, Ae = build_design_href(hdata)

    if "v" in hdata[0].keys():
        # test to see if velocity was passed
        Lh = np.array([[d["v"][0]] for d in hdata] + [[d["v"][1]] for d in hdata])
    else:
        Lh = []

    if len(vdata) > 0:
        # stack the horizontal components for the Euler pole
        Ah = np.row_stack((An, Ae))
        # design matrix for the effect of vref on href
        Anv, Aev, _ = build_design_vref(hdata)
        A = np.column_stack((Ah, np.row_stack((Anv, Aev))))
        # actual vref
        _, _, Auv = build_design_vref(vdata)
        Av = np.column_stack((np.zeros((Auv.shape[0], 3)), Auv))
        A = np.row_stack((A, Av))

        if "v" in vdata[0].keys():
            # test to see if velocity was passed
            L = np.row_stack((Lh, np.array([[d["v"][2]] for d in vdata])))
        else:
            L = Lh
    else:
        A = np.row_stack((An, Ae))
        L = Lh

    return A, L


def build_design_href(data):
    slat = sind(np.array([d["lat"] for d in data]))
    slon = sind(np.array([d["lon"] for d in data]))
    clat = cosd(np.array([d["lat"] for d in data]))
    clon = cosd(np.array([d["lon"] for d in data]))

    slatslon = slat * slon
    slatclon = slat * clon

    Re = 6378137

    An = Re * 1e-9 * np.column_stack((slon, -clon, np.zeros_like(slon)))
    Ae = Re * 1e-9 * np.column_stack((-slatclon, -slatslon, clat))

    return An, Ae


def build_design_vref(data):
    lat = np.array([d["lat"] for d in data])
    lon = np.array([d["lon"] for d in data])

    An = np.column_stack((-(sind(lat) * cosd(lon)), -sind(lon), cosd(lat) * cosd(lon)))
    Ae = np.column_stack((-(sind(lat) * sind(lon)), cosd(lon), cosd(lat) * sind(lon)))
    Au = np.column_stack((cosd(lat), np.zeros_like(lat), sind(lat)))

    return An, Ae, Au


def analize_candidates(cnn, args):
    llat = float(args.candidate_sites[0])
    ulat = float(args.candidate_sites[1])
    llon = float(args.candidate_sites[2])
    ulon = float(args.candidate_sites[3])
    myrs = float(args.candidate_sites[4])

    if llat > ulat:
        print(" >> Latitude range invalid")
        exit(1)

    if llon > ulon:
        print(" >> Latitude range invalid")
        exit(1)

    " >> Obtaining the station stack list of stations..."
    # get all stations in the requested stack
    stations = get_stack_stations(cnn, args.stack_name[0])

    sites = "'" + "','".join(["%s" % (stationID(stn)) for stn in stations]) + "'"

    rs = cnn.query_float(
        'SELECT "NetworkCode", "StationCode", lat, lon FROM stations '
        'WHERE "NetworkCode" || \'.\' || "StationCode" IN (%s) '
        "AND lat BETWEEN %f AND %f "
        "AND lon BETWEEN %f AND %f "
        'AND "DateEnd" - "DateStart" >= %f' % (sites, llat, ulat, llon, ulon, myrs),
        as_dict=True,
    )

    print(" -- Preliminary station list:")
    print_columns(["%s" % (stationID(stn)) for stn in rs])

    final_list = []
    rejected = []
    # now get a table of jumps and see if any of the stations are affected by earthquakes
    for stn in tqdm(rs, "Stations S-Scores", ncols=160):
        tqdm.write(" -- Processing %s" % stationID(stn))
        st = ScoreTable(
            cnn,
            stn["lat"],
            stn["lon"],
            Date(year=1970, doy=1),
            Date(datetime=datetime.datetime.now()),
        )

        if len(st.table) > 0:
            tqdm.write(
                "    Station %s is unsuitable for Euler pole determination"
                % stationID(stn)
            )
            rejected.append(stn)
        else:
            tqdm.write(
                "    Station %s added to Euler pole determination" % stationID(stn)
            )
            final_list.append(stn)

    if len(args.candidate_sites) == 6:
        kmz_file = args.candidate_sites[5]

        kml = simplekml.Kml()
        folder = kml.newfolder(name="Euler pole stations")
        folder_rejected = kml.newfolder(name="Rejected stations")
        ICON_SQUARE = "http://maps.google.com/mapfiles/kml/shapes/placemark_square.png"

        styles_ok = simplekml.StyleMap()
        styles_ok.normalstyle.iconstyle.icon.href = ICON_SQUARE
        styles_ok.normalstyle.iconstyle.color = "ff00ff00"
        styles_ok.normalstyle.iconstyle.scale = 1.5
        styles_ok.normalstyle.labelstyle.scale = 0

        styles_ok.highlightstyle.iconstyle.icon.href = ICON_SQUARE
        styles_ok.highlightstyle.iconstyle.color = "ff00ff00"
        styles_ok.highlightstyle.iconstyle.scale = 2
        styles_ok.highlightstyle.labelstyle.scale = 2

        styles_nok = simplekml.StyleMap()
        styles_nok.normalstyle.iconstyle.icon.href = ICON_SQUARE
        styles_nok.normalstyle.iconstyle.color = "ff0000ff"
        styles_nok.normalstyle.iconstyle.scale = 1.5
        styles_nok.normalstyle.labelstyle.scale = 0

        styles_nok.highlightstyle.iconstyle.icon.href = ICON_SQUARE
        styles_nok.highlightstyle.iconstyle.color = "ff0000ff"
        styles_nok.highlightstyle.iconstyle.scale = 2
        styles_nok.highlightstyle.labelstyle.scale = 2

        for stn in final_list:
            pt = folder.newpoint(name=stationID(stn), coords=[(stn["lon"], stn["lat"])])
            pt.stylemap = styles_ok

        for stn in rejected:
            pt = folder_rejected.newpoint(
                name=stationID(stn), coords=[(stn["lon"], stn["lat"])]
            )
            pt.stylemap = styles_nok

        # DDG Jun 17 2025: the wrong version of simplekml was being used, now using latest
        # import cgi
        # import html
        # cgi.escape = html.escape

        kml.savekmz(kmz_file + ".kmz")


def vertical_reference_tokens(tokens):
    """Accept station/velocity pairs, quoted rows, or a station-list file."""
    rows = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if len(token.split()) > 1 or os.path.isfile(token):
            rows.append(token)
            i += 1
        else:
            if i + 1 >= len(tokens):
                raise ValueError("VREF requires a velocity in mm/yr for each station")
            try:
                float(tokens[i + 1])
            except ValueError as error:
                raise ValueError(
                    "VREF requires station/velocity pairs in mm/yr"
                ) from error
            rows.append(f"{token} {tokens[i + 1]}")
            i += 2
    return rows


def euler_pole(args, cnn):
    # stations to use
    if args.include_stations:
        include_stn = process_stnlist(
            cnn,
            args.include_stations,
            summary_title="User selected list of stations to include:",
        )
    else:
        include_stn = []

    # create folder for plots
    if args.directory:
        if not os.path.exists(args.directory):
            os.mkdir(args.directory)
    else:
        if not os.path.exists("production"):
            os.mkdir("production")
        args.directory = "production"

    # vertical reference frame transformation
    if len(args.vertical_ref):
        vref = process_stnlist(
            cnn,
            vertical_reference_tokens(args.vertical_ref),
            summary_title="Stations for VREF:",
        )
        for station in vref:
            if not station.get("parameters") or not np.isfinite(
                float(station["parameters"][0])
            ):
                raise ValueError(
                    f"VREF requires a finite velocity for {stationID(station)}"
                )
    else:
        vref = []

    if args.save_stack:
        save_stack = args.save_stack.lower()
    else:
        save_stack = None

    stack = args.stack_name[0]
    hdata = []

    for stn in tqdm(include_stn, ncols=80, disable=None):
        tqdm.write(" >> Processing HREF station " + stationID(stn))
        station = stn["StationCode"]
        network = stn["NetworkCode"]

        if not args.ppp_solutions:
            # use a GAMIT stack
            rs = cnn.query_float(
                f"""SELECT etms.*, 
                                     stations.auto_x, stations.auto_y, stations.auto_z, stations.plate
                                     FROM etms INNER JOIN stations
                                     USING ("NetworkCode", "StationCode")
                                     WHERE ("NetworkCode", "StationCode", "stack",
                                     "object") =
                                     (\'{network}\', \'{station}\', \'{stack}\',
                                     \'polynomial\')""",
                as_dict=True,
            )
        else:
            # use PPP solutions
            rs = cnn.query_float(
                f"""SELECT etms.*, 
                                                 stations.auto_x, stations.auto_y, stations.auto_z, stations.plate
                                                 FROM etms INNER JOIN stations
                                                 USING ("NetworkCode", "StationCode")
                                                 WHERE ("NetworkCode", "StationCode", "soln",
                                                 "object") =
                                                 (\'{network}\', \'{station}\', \'ppp\',
                                                 \'polynomial\')""",
                as_dict=True,
            )

        if len(rs):
            lla = xyz2sphere_lla([rs[0]["auto_x"], rs[0]["auto_y"], rs[0]["auto_z"]])
            params = np.asarray(rs[0]["params"], dtype=float).reshape(3, -1)
            if params.shape[1] < 2:
                raise ValueError(f"Missing fitted velocity for {network}.{station}")
            hdata.append(
                {
                    "NetworkCode": stn["NetworkCode"],
                    "StationCode": stn["StationCode"],
                    "lat": lla[0][0],
                    "lon": lla[0][1],
                    "v": params[:, 1],
                    "plate": rs[0]["plate"],
                }
            )

    # now gather the data for the VREF, if any
    vdata = []
    if len(vref):
        for stn in tqdm(vref, ncols=80, disable=None):
            tqdm.write(" >> Processing VREF station " + stationID(stn))
            station = stn["StationCode"]
            network = stn["NetworkCode"]

            if not args.ppp_solutions:
                # use a GAMIT stack
                rs = cnn.query_float(
                    f"""SELECT etms.*,
                                         stations.auto_x, stations.auto_y, stations.auto_z, stations.plate
                                         FROM etms INNER JOIN stations
                                         USING ("NetworkCode", "StationCode")
                                         WHERE ("NetworkCode", "StationCode",
                                         "stack", "object") =
                                         (\'{network}\', \'{station}\', \'{stack}\',
                                         \'polynomial\')""",
                    as_dict=True,
                )
            else:
                # use PPP solutions
                rs = cnn.query_float(
                    f"""SELECT etms.*,
                                                     stations.auto_x, stations.auto_y, stations.auto_z, stations.plate
                                                     FROM etms INNER JOIN stations
                                                     USING ("NetworkCode", "StationCode")
                                                     WHERE ("NetworkCode", "StationCode",
                                                     "soln", "object") =
                                                     (\'{network}\', \'{station}\', \'ppp\',
                                                     \'polynomial\')""",
                    as_dict=True,
                )

            if len(rs):
                lla = xyz2sphere_lla(
                    [rs[0]["auto_x"], rs[0]["auto_y"], rs[0]["auto_z"]]
                )
                params = np.asarray(rs[0]["params"], dtype=float).reshape(3, -1)
                if params.shape[1] < 2:
                    raise ValueError(f"Missing fitted velocity for {network}.{station}")
                vdata.append(
                    {
                        "NetworkCode": stn["NetworkCode"],
                        "StationCode": stn["StationCode"],
                        "lat": lla[0][0],
                        "lon": lla[0][1],
                        "v": params[:, 1],
                        "vu_external": float(stn["parameters"][0]) / 1000.0,
                    }
                )
                vdata[-1]["v"][2] -= vdata[-1]["vu_external"]

    if not hdata:
        raise ValueError("No fitted HREF station velocities were found")
    if vref and len(vdata) != len(vref):
        raise ValueError("Every requested VREF station must have a fitted velocity")

    A, L = build_design(hdata, vdata)

    C, sigma, index, v, factor, _, cov = adjust_lsq(A, L)

    # summery of the Euler pole calculation
    iNE = index[0 : len(hdata) * 2].reshape((2, len(hdata)))
    rNE = v[0 : len(hdata) * 2].reshape((2, len(hdata)))
    fNE = (A @ C)[0 : len(hdata) * 2].reshape((2, len(hdata)))
    tqdm.write("HREF residuals")
    tqdm.write("Station  NE-Used EP Vn[mm/yr] Ve[mm/yr] Rn[mm/yr] Re[mm/yr]")
    for i, stn in enumerate(hdata):
        tqdm.write(
            "%s %-3s %-3s   %9.3f %9.3f %9.3f %9.3f"
            % (
                stationID(stn),
                "OK" if iNE[0, i] else "NOK",
                "OK" if iNE[1, i] else "NOK",
                fNE[0, i] * 1000.0,
                fNE[1, i] * 1000.0,
                rNE[0, i] * 1000.0,
                rNE[1, i] * 1000.0,
            )
        )
    tqdm.write("----------------------------------------------------------")
    tqdm.write(
        "RMS of residuals (NE)                  %9.3f %9.3f"
        % (
            np.sqrt(np.sum(np.square(rNE[0, :] * 1000.0)) / len(hdata)),
            np.sqrt(np.sum(np.square(rNE[1, :] * 1000.0)) / len(hdata)),
        )
    )

    # summery of VREF calculation
    if len(vref):
        iNE = index[len(hdata) * 2 :]
        rNE = v[len(hdata) * 2 :]
        fNE = (A @ C)[len(hdata) * 2 :]
        tqdm.write("\nVREF residuals")
        tqdm.write("Station  Vu-Used Vu[mm/yr] Ru[mm/yr]")
        for i, stn in enumerate(vdata):
            tqdm.write(
                "%s %-4s %9.3f %9.3f"
                % (
                    stationID(stn),
                    "OK" if iNE[i, 0] else "NOK",
                    fNE[i, 0] * 1000.0,
                    rNE[i, 0] * 1000.0,
                )
            )
        tqdm.write("---------------------------------")
        tqdm.write(
            "RMS of residuals       %9.3f"
            % (np.sqrt(np.sum(np.square(rNE[:, 0] * 1000.0)) / len(vdata)))
        )

    lat, lon, rot = cart2euler(C[0, 0], C[1, 0], C[2, 0])
    # to convert to mas/yr
    k = 1e-9 * 180 / np.pi * 3600 * 1000

    # Euler vector covariance to lla
    mT_ = np.sqrt(np.sum(C**2))
    mXY = np.sqrt(C[0, 0] ** 2 + C[1, 0] ** 2)
    pXZ = C[0, 0] * C[2, 0]
    pYZ = C[1, 0] * C[2, 0]

    G = np.array(
        [
            [C[0, 0] / mT_, C[1, 0] / mT_, C[1, 0] / mT_],
            [-1 / mT_**2 * pXZ / mXY, -1 / mT_**2 * pYZ / mXY, 1 / mT_**2 * mXY],
            [-C[1, 0] / (mXY**2), C[0, 0] / (mXY**2), 0],
        ]
    )

    cov_lla = G @ cov[0:3, 0:3] @ G.transpose()

    tqdm.write("")
    tqdm.write(" -- Total obs.: %i" % index.shape[0])
    tqdm.write(" -- Obs. ok   : %i" % index[index].shape[0])
    tqdm.write(" -- Obs. nok  : %i" % index[~index].shape[0])
    tqdm.write(" -- wrms      : %.3f mm/yr" % (factor[0, 0] * 1000.0))
    tqdm.write(" ==== EULER POLE SUMMARY ====")
    tqdm.write(
        """ -- XYZ (mas/yr mas/yr mas/yr) : %8.4f \xb1 %.3f %9.4f \xb1 %.3f %7.4f \xb1 %.3f"""
        % (
            C[0, 0] * k,
            sigma[0, 0] * k,
            C[1, 0] * k,
            sigma[0, 1] * k,
            C[2, 0] * k,
            sigma[0, 2] * k,
        )
    )
    tqdm.write(
        """ -- llr (deg deg deg/Myr)      : %8.4f \xb1 %.3f %9.4f \xb1 %.3f %7.4f \xb1 %.3f"""
        % (
            lat,
            np.rad2deg(np.sqrt(cov_lla[1, 1])),
            lon,
            np.rad2deg(np.sqrt(cov_lla[2, 2])),
            rot,
            np.rad2deg(np.sqrt(cov_lla[0, 0])) * 1e-9 * 1e6,
        )
    )

    if args.plot_etms:
        for stn in tqdm(hdata, ncols=80, disable=None):
            A, _ = build_design([stn], [stn] if len(vref) > 0 else [])
            v = np.zeros((3, 1))
            v[0 : 3 if len(vref) > 0 else 2] = A @ C
            model = pyETM.Model(pyETM.Model.VEL, velocity=v, fit=True)

            if not args.ppp_solutions:
                etm = pyETM.GamitETM(
                    cnn,
                    stn["NetworkCode"],
                    stn["StationCode"],
                    stack_name=stack,
                    models=[model],
                    plot_remove_jumps=True,
                )
            else:
                etm = pyETM.PPPETM(
                    cnn,
                    stn["NetworkCode"],
                    stn["StationCode"],
                    models=[model],
                    plot_remove_jumps=True,
                )

            xfile = os.path.join(
                args.directory,
                "%s.%s_%s" % (etm.NetworkCode, etm.StationCode, "plate-fixed"),
            )
            etm.plot(xfile + ".png", plot_missing=False)

            if args.save_json:
                obj = etm.todictionary(time_series=True, model=True)
                file_write(xfile + ".json", json.dumps(obj, indent=4, sort_keys=False))

    if save_stack:
        save_corrected_stack(cnn, args, hdata, vdata, C)


def save_corrected_stack(cnn, args, hdata, vdata, coefficients):
    """Finish ETM work before atomically replacing coordinates and provenance."""
    stack = args.stack_name[0]
    name = args.save_stack.lower()
    provenance, constraints = frame_provenance(
        hdata, vdata, coefficients, stack, args.ppp_solutions
    )
    if name == provenance["source_stack"]:
        raise ValueError("Use a different output name from the source stack")
    if args.ppp_solutions:
        # PPP has no input stack. Enumerate its actual stations, then reject
        # ambiguous source reference frames before asking PPPETM to fit them.
        stations = cnn.query_float(
            'SELECT DISTINCT "NetworkCode", "StationCode", auto_x, auto_y, auto_z '
            'FROM ppp_soln JOIN stations USING ("NetworkCode", "StationCode")',
            as_dict=True,
        )
        for station in stations:
            lla = xyz2sphere_lla([station[k] for k in ("auto_x", "auto_y", "auto_z")])
            station["lat"], station["lon"] = lla[0][:2]
    else:
        stations = get_stack_stations(cnn, stack)

    if args.save_filter:
        selected = {
            stationID(station)
            for station in process_stnlist(
                cnn,
                args.save_filter,
                summary_title="Stations to save:",
            )
        }
        stations = [station for station in stations if stationID(station) in selected]
    if args.preserve_stack:
        retained = {stationID(station) for station in get_stack_stations(cnn, name)}
        stations = [
            station for station in stations if stationID(station) not in retained
        ]

    # One JSON record per station limits memory to a single ETM time series.
    # Exceptions leave the existing saved stack completely untouched.
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as spool:
        for station in tqdm(stations, ncols=80, disable=None):
            network, code = station["NetworkCode"], station["StationCode"]
            epochs = source_epochs(cnn, network, code, stack, args.ppp_solutions)
            design, _ = build_design([station], [station] if vdata else [])
            velocity = np.zeros((3, 1))
            velocity[: 3 if vdata else 2] = design @ coefficients
            model = pyETM.Model(pyETM.Model.VEL, velocity=velocity, fit=True)
            kwargs = dict(models=[model], plot_remove_jumps=True)
            if args.ppp_solutions:
                etm = pyETM.PPPETM(cnn, network, code, **kwargs)
            else:
                etm = pyETM.GamitETM(cnn, network, code, stack_name=stack, **kwargs)
            if len(etm.soln.date) != etm.L.shape[1]:
                raise ValueError(
                    f"Coordinate/date length mismatch for {network}.{code}"
                )
            rows = []
            for x, y, z, date in zip(*etm.L, etm.soln.date):
                source = epochs[(int(date.year), int(date.doy))]
                rows.append(
                    dict(
                        Project=None if args.ppp_solutions else source,
                        ppp_reference_frame=source if args.ppp_solutions else None,
                        NetworkCode=network,
                        StationCode=code,
                        X=float(x),
                        Y=float(y),
                        Z=float(z),
                        sigmax=0.0,
                        sigmay=0.0,
                        sigmaz=0.0,
                        FYear=float(date.fyear),
                        Year=int(date.year),
                        DOY=int(date.doy),
                    )
                )
            spool.write(json.dumps(rows) + "\n")
            etm.soln.stack_name = name
            if args.plot_etms:
                path = os.path.join(args.directory, f"{network}.{code}_plate-fixed.png")
                etm.plot(path, plot_missing=False)
        spool.seek(0)
        count = save_frame(
            cnn,
            name,
            provenance,
            constraints,
            (json.loads(line) for line in spool),
            preserve=args.preserve_stack,
        )
    tqdm.write(f" -- Saved {count} corrected station-days to frame {name}")


def main():
    parser = argparse.ArgumentParser(
        description="""Script to compute Euler pole given a set of stations.
                    Program can be invoked in two different ways: 1) to produce 
                    a list of candidate sites (obtained from the provided stack_name) 
                    to compute the Euler pole 2) obtain Euler vector parameters and
                    (optionally) produce time series in the resulting fixed-plate frame."""
    )

    parser.add_argument(
        "stack_name",
        type=str,
        nargs=1,
        metavar="{stack name}",
        help="""Stack name to work with. The Euler pole
                             will be calculated so as to fix the velocities
                             of the selected sites in this stack. To use PPP 
                             solutions, provide any name for this argument and 
                             pass the -ppp switch.""",
    )

    parser.add_argument(
        "-include",
        "--include_stations",
        nargs="+",
        type=str,
        metavar="{net.stnm}",
        help="""Specify which stations
                             to use for Euler pole computation.""",
    )

    parser.add_argument(
        "-vref",
        "--vertical_ref",
        nargs="+",
        metavar=("station", "[mm/yr]]"),
        default=[],
        help="""Transform/align to a given vertical reference
                             frame using the provided station list
                             and velocities, given as [net.stnm] [vu],
                             where vu is the vertical velocity in mm/yr.""",
    )

    parser.add_argument(
        "-plot",
        "--plot_etms",
        action="store_true",
        default=False,
        help="""Plot the fixed-plate ETMs
                             after computation is done.""",
    )

    parser.add_argument(
        "-dir",
        "--directory",
        type=str,
        metavar="{dir name}",
        help="""Directory to save the resulting PNG files.
                             If not specified, assumed to be the
                             production directory.""",
    )

    parser.add_argument(
        "-ppp",
        "--ppp_solutions",
        action="store_true",
        default=False,
        help="""Use PPP solutions instead of GAMIT. The 
                        input stack name will be ignored.""",
    )

    parser.add_argument(
        "-preserve",
        "--preserve_stack",
        action="store_true",
        default=False,
        help="""Do not erase stack when saving stations. This is useful for 
                        adding new stations to the stack, when the saved fit and source provenance match. Incompatible
                        fits and legacy stacks require rebuilding.""",
    )

    parser.add_argument(
        "-json",
        "--save_json",
        action="store_true",
        default=False,
        help="""Save json files for the plotted ETMs. 
                        Needs -plot to work.""",
    )

    parser.add_argument(
        "-save",
        "--save_stack",
        type=str,
        metavar="{new stack name}",
        help="""Save the time series in the plate-fixed
                             frame as new stack.
                             Switch requires a stack name to use. WARNING!
                             If stack exists it will be overwritten.""",
    )

    parser.add_argument(
        "-save_filter",
        "--save_filter",
        nargs="+",
        type=str,
        help="Stations to save from the source stack or PPP solutions (default: all).",
    )

    parser.add_argument(
        "-candidates",
        "--candidate_sites",
        nargs="+",
        action=required_length(5, 6),
        help="""Provide a lat and lon range and a minimum year 
                        span to select sites to participate in an Euler pole 
                        determination. Final site selection will be output as 
                        a list of station names and coordinates or, alternatively 
                        as a kmz file (if filename given as 6th argument, do not 
                        include extension).""",
    )

    add_version_argument(parser)

    args = parser.parse_args()

    cnn = dbConnection.Cnn("gnss_data.cfg")

    if args.candidate_sites:
        analize_candidates(cnn, args)
    else:
        euler_pole(args, cnn)


if __name__ == "__main__":
    main()
