"""
Project: Geodesy Database Engine (GeoDE)
Date: 4/3/17 6:57 PM
Author: Demian D. Gomez
"""

import fcntl
import math
import os
import re
import tempfile
from pathlib import Path
from shutil import copyfile, rmtree

# deps
import simplekml
from psycopg import sql
from tqdm import tqdm

# app
from geode import pyRinexName, snxParse
from geode.gamit.station import StationInstance
from geode.Utils import chmod_exec, determine_frame, file_open, stationID


class GamitSessionException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


PRODUCT_KEYS = {
    "gamit_stats": ("Project", "Year", "DOY", "subnet", "system"),
    "gamit_subnets": ("Project", "Year", "DOY", "subnet"),
    "gamit_ztd": ("NetworkCode", "StationCode", "Date", "Project", "Year", "DOY"),
    "gamit_soln": ("NetworkCode", "StationCode", "Project", "Year", "DOY"),
}


def replace_product(cnn, table, scope, rows):
    """Replace the selected rows atomically, keeping API IDs for retained primary keys."""
    keys = PRODUCT_KEYS[table]
    if not rows:
        raise ValueError("Expected at least one processing result")
    fields = list(rows[0])
    if not set(keys).issubset(fields) or "api_id" in fields:
        raise ValueError("Invalid primary key or API ID in processing product")
    target = sql.Identifier("public", table)
    temp_name = "incoming_" + table
    staging = sql.Identifier(temp_name)
    columns = sql.SQL(", ").join(map(sql.Identifier, fields))
    key_columns = sql.SQL(", ").join(map(sql.Identifier, keys))
    updates = sql.SQL(", ").join(
        sql.SQL("{0} = excluded.{0}").format(sql.Identifier(f))
        for f in fields
        if f not in keys
    )
    matches = sql.SQL(" AND ").join(
        sql.SQL("saved.{0} = incoming.{0}").format(sql.Identifier(k)) for k in keys
    )
    selected = sql.SQL(" AND ").join(
        sql.SQL("saved.{} = %s").format(sql.Identifier(k)) for k in scope
    )
    with cnn.cnn.transaction():
        cnn.cursor.execute(
            sql.SQL(
                "CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM {} WITH NO DATA"
            ).format(staging, columns, target)
        )
        cnn.insert_many(temp_name, rows)
        cnn.cursor.execute(
            sql.SQL(
                "INSERT INTO {} ({}) SELECT {} FROM {} "
                "ON CONFLICT ({}) DO UPDATE SET {}"
            ).format(target, columns, columns, staging, key_columns, updates)
        )
        cnn.cursor.execute(
            sql.SQL(
                "DELETE FROM {} AS saved WHERE {} AND NOT EXISTS "
                "(SELECT 1 FROM {} AS incoming WHERE {})"
            ).format(target, selected, staging, matches),
            list(scope.values()),
        )


def replace_day(cnn, table, project, date, rows):
    if table not in ("gamit_ztd", "gamit_soln") or not rows:
        raise ValueError("Expected daily GLOBK coordinates or zenith delays")
    replace_product(
        cnn, table, {"Project": project, "Year": date.year, "DOY": date.doy}, rows
    )


def publish_directory(staged, destination, confirm=None):
    """Install a complete staged tree, retaining the previous tree until it is replaced."""
    # Rename within one filesystem. Keep the previous complete tree
    # recoverable even if a worker is killed between the two renames.
    previous = destination.with_name(f".{destination.name}.previous")
    parent_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        if previous.exists():
            raise FileExistsError(
                f"Inspect unfinished publication at {previous} before retrying"
            )
        if destination.exists():
            destination.rename(previous)
        try:
            staged.rename(destination)
            if confirm is not None:
                confirm()
        except BaseException:
            if not staged.exists() and destination.exists():
                destination.rename(staged)
            if previous.exists():
                previous.rename(destination)
            raise
        if previous.exists():
            rmtree(previous)
    finally:
        os.close(parent_fd)


ZENITH_DELAY = re.compile(
    r"ATM_ZEN X\s+(\w{4})\s+\S+\s+(\d{4})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)"
    r"\s+(?:\d+\s+)?([+-]?\d*\.\d+)\s+[+-]*\s*(\d*\.\d+)\s+([+-]?\d*\.\d+)"
)


def zenith_delays(path):
    matches = []
    with file_open(str(path)) as source:
        for number, line in enumerate(source, 1):
            if "ATM_ZEN X" not in line or "q-file:" in line:
                continue
            match = ZENITH_DELAY.search(line)
            if match is None:
                raise ValueError(
                    f"Invalid atmospheric zenith delay in {path} at line {number}"
                )
            matches.append(match)
    if not matches:
        raise ValueError(f"No usable atmospheric zenith delays in {path}")
    return matches


def subnet_glx(directory):
    paths = list(Path(directory).glob("h*.glx"))
    if len(paths) != 1 or not paths[0].is_file() or not paths[0].stat().st_size:
        raise ValueError(f"Expected one nonempty subnet GLX in {directory}")
    return paths[0]


def read_solution(directory, org, date):
    path = Path(directory) / f"{org}{date.wwwwd()}.snx"
    snx = snxParse.snxFileParser(str(path))
    snx.parse()
    if not snx.stationDict:
        raise ValueError(f"No station estimates in {path}")
    for station, estimate in snx.stationDict.items():
        values = (
            estimate.X,
            estimate.Y,
            estimate.Z,
            estimate.sigX,
            estimate.sigY,
            estimate.sigZ,
            estimate.sigXY,
            estimate.sigXZ,
            estimate.sigYZ,
        )
        if any(value is None or not math.isfinite(value) for value in values):
            raise ValueError(
                f"Incomplete position or covariance for {station} in {path}"
            )
    return snx


def validate_subnet_products(directory, org, date):
    subnet_glx(directory)
    read_solution(directory, org, date)
    zenith_delays(Path(directory) / f"{org}{date.wwwwd()}.znd")


def completed_session(cnn, path, row_key, systems, org, date):
    """A missing completion record never authorizes deletion of an existing tree."""
    destination = Path(path)
    cnn.cursor.execute(
        'SELECT system FROM gamit_stats WHERE "Year"=%s AND "DOY"=%s '
        'AND "Project"=%s AND subnet=%s',
        (row_key["Year"], row_key["DOY"], row_key["Project"], row_key["subnet"]),
    )
    recorded = {row["system"] for row in cnn.cursor.fetchall()}
    previous = destination.with_name(f".{destination.name}.previous")
    pending = destination / ".geode-publish-pending"
    if (
        recorded
        and destination.is_dir()
        and not previous.exists()
        and not pending.exists()
    ):
        if recorded != set(systems):
            return False
        try:
            validate_subnet_products(destination / "glbf", org, date)
        except (OSError, ValueError):
            # A new attempt can repair incomplete output without modifying the old tree.
            return False
        return True
    if recorded or destination.exists() or previous.exists():
        raise GamitSessionException(
            f"Incomplete publication or inconsistent completion record for {path}. "
            "Inspect the job receipt, solution, and sibling .previous directory. "
            "If no statistics exist, move only this session tree aside and retry. "
            "If statistics exist, restore its matching completed tree before retrying."
        )
    return False


def session_products(session):
    """List the files and station aliases consumed by GLOBK and the ZTD reader."""
    return {
        "directory": session.pwd_glbf,
        "name": session.DirName,
        "network": session.NetName,
        "date": session.date,
        "stations": [
            (station.StationAlias, station.NetworkCode, station.StationCode)
            for station in session.StationInstances
        ],
    }


class GamitSession(object):
    def __init__(
        self,
        cnn,
        archive,
        name,
        org,
        subnet,
        date,
        GamitConfig,
        stations,
        ties=(),
        centroid=(),
        *,
        rebuild=False,
    ):
        """
        The GAMIT session object creates all the directory structure and configuration files according to the parameters
        set in GamitConfig. Two stations list are passed and merged to create the session
        :param cnn: connection to database object
        :param archive: archive object to find rinex files in archive structure
        :param name: name of the project/network
        :param org: name of the organization
        :param subnet: subnet number (may be None, in which case the directory name will not show ORGXX
        :param date: date that is being processed
        :param GamitConfig: configuration to run gamit
        :param stations: list of stations to be processed
        :param ties: tie stations as obtained by pyNetwork
        """
        self.NetName = name
        self.org = org
        self.subnet = subnet

        if subnet is not None:
            # DDG: support up to 999 subnetworks
            self.DirName = "%s.%s%03i" % (self.NetName, self.org, self.subnet)
        else:
            self.DirName = self.NetName

        self.date = date
        self.GamitOpts = GamitConfig.gamitopt
        self.Config = GamitConfig
        self.frame = None
        self.params = None
        # to store the polyhedron read from the final SINEX
        self.polyhedron = None
        self.VarianceFactor = None
        # gamit task will be filled with the GamitTask object
        self.GamitTask = None

        self.solution_base = self.GamitOpts["solutions_dir"].rstrip("/")

        # Temporary 'hotfix' to restart production
        # DDG: this should be a list, not a StationCollection object
        stations_ = [stn for stn in stations if stn not in ties]
        # Code is replicated from lines 338-340 in pyNetwork
        stations = stations_

        # tie station dictionary (to build KMLs, do not change)
        self.tie_dict = [
            {"name": stationID(stn), "coords": [(stn.lon, stn.lat)]} for stn in ties
        ]

        # station dictionary (to build KMLs, do not change)
        self.stations_dict = [
            {"name": stationID(stn), "coords": [(stn.lon, stn.lat)]} for stn in stations
        ]

        # make StationInstances
        station_instances = []
        for stn in stations:
            try:
                station_instances += [
                    StationInstance(cnn, archive, stn, date, GamitConfig)
                ]
            except pyRinexName.RinexNameException:
                tqdm.write(
                    " -- WARNING (station instance): station %s on day %s appears to have a badly formed RINEX "
                    "filename. Please check the archive and make sure all filenames follow the RINEX 2/3 "
                    "convention. Station has been excluded from the GAMIT session."
                    % (stationID(stn), date.yyyyddd())
                )

        # do the same with ties
        for stn in ties:
            try:
                station_instances += [
                    StationInstance(cnn, archive, stn, date, GamitConfig, is_tie=True)
                ]
            except pyRinexName.RinexNameException:
                tqdm.write(
                    " -- WARNING (tie instance): station %s on day %s appears to have a badly formed RINEX "
                    "filename. Please check the archive and make sure all filenames follow the RINEX 2/3 "
                    "convention. Station has been excluded from the GAMIT session."
                    % (stationID(stn), date.yyyyddd())
                )

        self.StationInstances = station_instances

        # create working dirs for this session
        last_path = "/%s/%s/%s" % (date.yyyy(), date.ddd(), self.DirName)
        self.solution_pwd = self.solution_base + last_path
        # the remote pwd is the directory where the processing will be performed
        self.remote_pwd = "production/gamit" + last_path

        row_key = {
            "Year": date.year,
            "DOY": date.doy,
            "Project": self.NetName,
            "subnet": 0 if subnet is None else subnet,
        }

        self.ready = (
            completed_session(
                cnn,
                self.solution_pwd,
                row_key,
                self.GamitOpts["systems"],
                self.GamitOpts["org"],
                date,
            )
            and not rebuild
        )
        self.missing_data = []
        self.subnet_record = {
            **row_key,
            "stations": [stationID(s) for s in stations + list(ties)],
            "alias": [s.StationAlias for s in stations + list(ties)],
            "ties": [s["name"] for s in self.tie_dict],
            "centroid": [round(float(c), 1) for c in centroid],
        }

        # Produce fresh input outside the published session. Check-mode and
        # missing-station reruns continue to address the previous completed day.
        self.prepared_pwd = self.solution_pwd
        if not self.ready:
            parent = Path(self.solution_pwd).parent
            parent.mkdir(parents=True, exist_ok=True)
            self.prepared_pwd = tempfile.mkdtemp(
                prefix=f".{self.DirName}-attempt-", dir=parent
            )
        self.pwd_igs = os.path.join(self.prepared_pwd, "igs")
        self.pwd_brdc = os.path.join(self.prepared_pwd, "brdc")
        self.pwd_rinex = os.path.join(self.prepared_pwd, "rinex")
        self.pwd_tables = os.path.join(self.prepared_pwd, "tables")
        self.pwd_glbf = os.path.join(self.solution_pwd, "glbf")
        self.pwd_proc = os.path.join(self.prepared_pwd, date.ddd())

        if not self.ready:
            for folder in (
                self.pwd_igs,
                self.pwd_brdc,
                self.pwd_rinex,
                self.pwd_tables,
            ):
                os.makedirs(folder)
            self.generate_kml()

    def initialize(self):
        if not self.ready:
            # create the station.info
            self.create_station_info()

            self.create_apr_sittbl_file()

            self.copy_sestbl_procdef_atx()

            self.link_tables()

            self.create_sitedef()

            self.create_otl_list()

        # ready to copy the RINEX files
        rinex_list = self.get_rinex_filenames()

        self.params = {
            "solution_pwd": self.solution_pwd,
            "prepared_pwd": self.prepared_pwd,
            "subnet_record": self.subnet_record,
            "remote_pwd": self.remote_pwd,
            "NetName": self.NetName,
            "DirName": self.DirName,
            "subnet": self.subnet if self.subnet is not None else 0,
            "rinex": rinex_list,
            "date": self.date,
            "gamitopts": {
                key: self.GamitOpts[key]
                for key in (
                    "systems",
                    "org",
                    "expt",
                    "eop_type",
                    "noftp",
                    "overconst_action",
                )
            },
            "orbits": {
                "sp3_path": self.Config.sp3_path,
                "sp3types": self.Config.sp3types,
                "sp3altrn": (),
                "brdc_path": self.Config.brdc_path,
                "ionex_path": self.Config.ionex_path,
            },
        }

    def create_otl_list(self):
        otl_path = os.path.join(self.pwd_tables, "otl.list")
        if os.path.isfile(otl_path):
            os.remove(otl_path)

        with file_open(otl_path, "w") as otl_list:
            otl_list.write(
                "%s   8-character GAMIT ID read by grdtab (M -> CM)\n"
                % (self.Config.options["otlmodel"])
            )
            otl_list.write(
                """$$ Ocean loading displacement
$$
$$ Calculated on holt using olfg/olmpp of H.-G. Scherneck
$$
$$ COLUMN ORDER:  M2  S2  N2  K2  K1  O1  P1  Q1  MF  MM SSA
$$
$$ ROW ORDER:
$$ AMPLITUDES (m)
$$   RADIAL
$$   TANGENTL    EW
$$   TANGENTL    NS
$$ PHASES (degrees)
$$   RADIAL
$$   TANGENTL    EW
$$   TANGENTL    NS
$$
$$ Displacement is defined positive in upwards, South and West direction.
$$ The phase lag is relative to Greenwich and lags positive. The
$$ Gutenberg-Bullen Greens function is used. In the ocean tide model the
$$ deficit of tidal water mass has been corrected by subtracting a uniform
$$ layer of water with a certain phase lag globally.
$$
$$ Complete <model name> : No interpolation of ocean model was necessary
$$ <model name>_PP       : Ocean model has been interpolated near the station
$$                         (PP = Post-Processing)
$$
$$ CMC:  YES  (corr.tide centre of mass)
$$
$$ Ocean tide model: %s
$$
$$ END HEADER
$$\n"""
                % (self.Config.options["otlmodel"])
            )

            for stn in self.StationInstances:
                otl = stn.otl_H.split("\n")
                # remove BLQ header
                # DDG: there is a new header for the OTL, so go line by line checking if line starts with $
                for i, line in enumerate(otl):
                    if line[0] == " ":
                        start_line = i
                        break

                otl = otl[start_line:]  # previous value here was 29
                # need to change the station record for GAMIT to take it
                otl[0] = "  %s" % stn.StationAlias.upper()
                if stn.lon < 0:
                    lon = 360 + stn.lon
                else:
                    lon = stn.lon
                otl[3] = (
                    "$$ %s                                 RADI TANG lon/lat:%10.4f%10.4f"
                    % (stn.StationAlias.upper(), lon, stn.lat)
                )

                otl_list.write("\n".join(otl))

            # write BLQ format termination
            otl_list.write("$$ END TABLE\n")

    def create_station_info(self):
        # delete any current station.info files
        station_path = os.path.join(self.pwd_tables, "station.info")
        if os.path.isfile(station_path):
            os.remove(station_path)

        with file_open(station_path, "w") as stninfo_file:
            stninfo_file.write(
                "*SITE  Station Name      Session Start      Session Stop       Ant Ht   HtCod  Ant N    Ant E    "
                "Receiver Type         Vers                  SwVer  Receiver SN           Antenna Type     "
                "Dome   Antenna SN            AntDAZ  \n"
            )

            for stn in self.StationInstances:
                # stninfo_file.write(stn.StationInfo.return_stninfo() + '\n')
                stninfo_file.write(stn.GetStationInformation() + "\n")

    def create_apr_sittbl_file(self):
        lfile_path = os.path.join(self.pwd_tables, "lfile.")
        sittbl_path = os.path.join(self.pwd_tables, "sittbl.")
        log_path = os.path.join(self.pwd_tables, "debug.log")

        for f in (lfile_path, sittbl_path):
            if os.path.isfile(f):
                os.remove(f)

        with file_open(lfile_path, "w") as lfile:
            with file_open(sittbl_path, "w") as sittbl:
                with file_open(log_path, "w") as debug:
                    sittbl.write("SITE              FIX    --COORD.CONSTR.--  \n")
                    sittbl.write("      << default for regional sites >>\n")
                    sittbl.write("ALL               NNN    100.  100.   100. \n")

                    for stn in self.StationInstances:
                        lfile.write(stn.GetApr() + "\n")
                        sittbl.write(stn.GetSittbl() + "\n")
                        debug.write(stn.DebugCoord() + "\n")

    def copy_sestbl_procdef_atx(self):
        self.frame, atx = determine_frame(self.Config.options["frames"], self.date)

        # copy process.defaults and sestbl.
        copyfile(
            self.GamitOpts["process_defaults"],
            os.path.join(self.pwd_tables, "process.defaults"),
        )
        # copyfile(self.GamitOpts['atx'], os.path.join(self.pwd_tables, 'antmod.dat'))
        copyfile(atx, os.path.join(self.pwd_tables, "antmod.dat"))

        # change the scratch directory in the sestbl. file
        with file_open(os.path.join(self.pwd_tables, "sestbl."), "w") as sestbl:
            with file_open(self.GamitOpts["sestbl"]) as orig_sestbl:
                for line in orig_sestbl:
                    if "Scratch directory" in line:
                        # empty means local directory! LA RE PU...
                        sestbl.write("Scratch directory = \n")
                    else:
                        sestbl.write(line)

    def link_tables(self):
        script_path = "link_tables.sh"
        try:
            link_tables = file_open(script_path, "w")
        except (OSError, IOError):
            raise GamitSessionException("Could not create script file link_tables.sh")

        # link the apr file as the lfile.
        contents = """#!/bin/bash
            # set up links
            cd %s;
            sh_links.tables -frame J2000 -year %s -eop %s -topt none &> sh_links.out;
            # kill the earthquake rename file
            rm eq_rename
            # create an empty rename file
            echo "" > eq_rename
            cd ..;
            """ % (self.pwd_tables, self.date.yyyy(), self.GamitOpts["eop_type"])

        link_tables.write(contents)
        link_tables.close()

        chmod_exec(script_path)
        os.system("./" + script_path)

    def get_rinex_filenames(self):
        return [stn.GetRinexFilename() for stn in self.StationInstances]

    def create_sitedef(self):
        sitedefFile = os.path.join(self.pwd_tables, "sites.defaults")
        try:
            with file_open(sitedefFile, "w") as sitedef:
                sitedef.write(" all_sites %s xstinfo\n" % (self.GamitOpts["expt"]))

                for StationInstance in self.StationInstances:
                    sitedef.write(
                        " %s_GPS  %s localrx\n"
                        % (StationInstance.StationAlias.upper(), self.GamitOpts["expt"])
                    )

        except Exception as e:
            raise GamitSessionException(e)

    def parse_sinex(self):
        for sinex in os.listdir(self.pwd_glbf):
            if sinex.endswith(".snx"):
                snx = snxParse.snxFileParser(os.path.join(self.pwd_glbf, sinex))
                snx.parse()
                self.polyhedron = snx.stationDict
                self.VarianceFactor = snx.varianceFactor

        if self.polyhedron:
            # remame any aliases and change keys to net.stn
            for stn in self.StationInstances:
                # replace the key
                try:
                    self.polyhedron[stationID(stn)] = self.polyhedron.pop(
                        stn.StationAlias.upper()
                    )
                except KeyError:
                    # maybe the station didn't have a solution
                    pass
        return self.polyhedron, self.VarianceFactor

    def generate_kml(self):
        # save this session as a kml
        kml = simplekml.Kml()

        ICON_SQUARE = "http://maps.google.com/mapfiles/kml/shapes/placemark_square.png"

        # define styles
        styles_stn = simplekml.StyleMap()
        styles_stn.normalstyle.iconstyle.icon.href = ICON_SQUARE
        styles_stn.normalstyle.iconstyle.color = "ff00ff00"
        styles_stn.normalstyle.iconstyle.scale = 4
        styles_stn.normalstyle.labelstyle.scale = 0
        styles_stn.highlightstyle.iconstyle.icon.href = ICON_SQUARE
        styles_stn.highlightstyle.iconstyle.color = "ff00ff00"
        styles_stn.highlightstyle.iconstyle.scale = 5
        styles_stn.highlightstyle.labelstyle.scale = 2

        styles_tie = simplekml.StyleMap()
        styles_tie.normalstyle.iconstyle.icon.href = ICON_SQUARE
        styles_tie.normalstyle.iconstyle.color = "ff0000ff"
        styles_tie.normalstyle.iconstyle.scale = 4
        styles_tie.normalstyle.labelstyle.scale = 0
        styles_tie.highlightstyle.iconstyle.icon.href = ICON_SQUARE
        styles_tie.highlightstyle.iconstyle.color = "ff0000ff"
        styles_tie.highlightstyle.iconstyle.scale = 5
        styles_tie.highlightstyle.labelstyle.scale = 3

        ties_net = kml.newfolder(name=self.DirName + "-ties")
        rstn_net = kml.newfolder(name=self.DirName + "-non_ties")

        for stn in self.stations_dict + self.tie_dict:
            if stn in self.tie_dict:
                pt = ties_net.newpoint(**stn)
                pt.stylemap = styles_tie
            else:
                pt = rstn_net.newpoint(**stn)
                pt.stylemap = styles_stn

        # DDG Jun 17 2025: the wrong version of simplekml was being used, now using latest
        # to fix the issue from simple kml
        # AttributeError: module 'cgi' has no attribute 'escape'
        # see: https://github.com/tjlang/simplekml/issues/38
        # import cgi
        # import html
        # cgi.escape = html.escape

        kml.savekmz(os.path.join(self.prepared_pwd, self.DirName) + ".kmz")
