"""
Project: Geodesy Database Engine (GeoDE)
Date: 7/19/20 6:33 PM
Author: Demian D. Gomez
"""

import os
import re
import traceback
from datetime import datetime

# deps
import numpy

# app
from geode import dbConnection
from geode.gamit.gamit_session import replace_day, session_products
from geode.Utils import file_readlines


class ParseZtdTask:
    def __init__(self, GamitConfig, project, sessions, date):
        self.date = date
        self.project = project
        if isinstance(GamitConfig, str):
            self.sessions = sessions
            self.org = GamitConfig
        else:
            self.sessions = [session_products(s) for s in sessions]
            self.org = GamitConfig.gamitopt["org"]

    def execute(self, cnn=None):
        # atmospheric zenith delay list
        atmzen = []
        # a dictionary for the station aliases lookup table
        alias = {}
        err = []

        for GamitSession in self.sessions:
            try:
                znd = os.path.join(
                    GamitSession["directory"], self.org + self.date.wwwwd() + ".znd"
                )

                if os.path.isfile(znd):
                    # read the content of the file
                    output = file_readlines(znd)
                    v = re.findall(
                        r"ATM_ZEN X (\w+) .. (\d+)\s*(\d*)\s*(\d*)\s*(\d*)\s*(\d*)\s*\d*\s*([- ]?"
                        r"\d*.\d+)\s*[+-]*\s*(\d*.\d*)\s*(\d*.\d*)",
                        "".join(output),
                        re.MULTILINE,
                    )
                    # add the year doy tuple to the result
                    atmzen += [
                        i + (GamitSession["date"].year, GamitSession["date"].doy)
                        for i in v
                    ]

                    # create a lookup table for station aliases
                    for zd in v:
                        for name, network, station in GamitSession["stations"]:
                            if name.upper() == zd[0] and zd[0] not in alias:
                                alias[zd[0]] = [network, station]

            except:
                err.append(
                    " -- Error parsing zenith delays for session %s:\n%s"
                    % (GamitSession["network"], traceback.format_exc())
                )
                return err

        if not len(atmzen):
            err.append(
                " -- %s No sessions with usable atmospheric zenith delays were found for %s"
                % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.date.yyyyddd())
            )
        else:
            # turn atmzen into a numpy array
            atmzen = numpy.array(
                atmzen,
                dtype=[  # ('stn', 'S4'), # python2
                    ("stn", "U4"),
                    ("y", "i4"),
                    ("m", "i4"),
                    ("d", "i4"),
                    ("h", "i4"),
                    ("mm", "i4"),
                    ("mo", "float64"),
                    ("s", "float64"),
                    ("z", "float64"),
                    ("yr", "i4"),
                    ("doy", "i4"),
                ],
            )

            atmzen.sort(order=["stn", "y", "m", "d", "h", "mm"])

            # get the stations in the processing
            stations = [str(stn) for stn in numpy.unique(atmzen["stn"])]

            ztd = []
            for stn in stations:
                zd = atmzen[(atmzen["stn"] == stn)]
                # careful, don't do anything if there is no data for this station-day
                if zd.size > 0:
                    # find the unique knots
                    knots = numpy.unique(
                        numpy.array(
                            [zd["y"], zd["m"], zd["d"], zd["h"], zd["mm"]]
                        ).transpose(),
                        axis=0,
                    )
                    # average over the existing records
                    for d in knots:
                        rows = zd[
                            numpy.logical_and.reduce(
                                (
                                    zd["y"] == d[0],
                                    zd["m"] == d[1],
                                    zd["d"] == d[2],
                                    zd["h"] == d[3],
                                    zd["mm"] == d[4],
                                )
                            )
                        ]

                        try:
                            ztd.append(
                                alias[stn]
                                + [
                                    datetime(d[0], d[1], d[2], d[3], d[4]).strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    self.project.lower(),
                                    numpy.mean(rows["z"]) - numpy.mean(rows["mo"]),
                                    numpy.mean(rows["s"]),
                                    numpy.mean(rows["z"]),
                                    self.date.year,
                                    self.date.doy,
                                ]
                            )

                        except KeyError:
                            err.append(
                                " -- Key error: could not translate station alias %s"
                                % stn
                            )

            if not err:
                rows = [
                    dict(
                        NetworkCode=k[0],
                        StationCode=k[1],
                        Date=k[2],
                        Project=k[3],
                        model=numpy.round(k[4], 4),
                        sigma=numpy.round(k[5], 4),
                        ZTD=numpy.round(k[6], 4),
                        Year=k[7],
                        DOY=k[8],
                    )
                    for k in ztd
                ]
                if cnn is None:
                    cnn = dbConnection.Cnn("gnss_data.cfg")
                    try:
                        replace_day(
                            cnn, "gamit_ztd", self.project.lower(), self.date, rows
                        )
                    finally:
                        cnn.close()
                else:
                    replace_day(cnn, "gamit_ztd", self.project.lower(), self.date, rows)

        return err
