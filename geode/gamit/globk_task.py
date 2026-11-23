"""
Project: Geodesy Database Engine (GeoDE)
Date: Dic-03-2016
Author: Demian D. Gomez
"""

import gzip
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# app
from geode.gamit.gamit_session import (
    publish_directory,
    read_solution,
    session_products,
    subnet_glx,
)
from geode.Utils import chmod_exec, file_open


class GlobkException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def verify_globk_inputs(report, inputs):
    """GLOBK may exit successfully after rejecting one or more input solutions."""
    used = set()
    opener = gzip.open if report.suffix == ".gz" else open
    with opener(report, "rt", errors="replace") as stream:
        for line in stream:
            fields = line.split()
            if (
                len(fields) == 7
                and fields[0].isdigit()
                and fields[-1] == "USED"
                and fields[1].lower().endswith(".glx")
            ):
                used.add(os.path.normpath(fields[1]))
    missing = set(map(os.path.normpath, inputs)) - used
    if missing:
        raise GlobkException(
            f"GLOBK did not use all expected inputs: {', '.join(sorted(missing))}"
        )


class Globk(object):
    def __init__(self, pwd_comb, date, Sessions, net_type="regional", *, options=None):
        self.polyhedron = None
        self.VarianceFactor = None
        self.date = date
        if options is None:
            options = Sessions[0].GamitOpts
            Sessions = [session_products(s) for s in Sessions]
        self.eop = options["eop_type"]
        self.org = options["org"]
        self.expt = options["expt"]
        self.pwd_comb = pwd_comb
        self.Sessions = Sessions  # type: list
        self.h_files = []
        self.stdout = None
        self.stderr = None
        self.p = None
        self.polyhedron = None
        self.variance = None
        self.net_type = net_type

    def linktables(self, year, eop_type):
        script_path = os.path.join(self.pwd_comb, "link_tables.sh")
        try:
            link_tables = file_open(script_path, "w")
        except:
            raise GlobkException("could not open file link_tables.sh")

        # link the apr file as the lfile.
        with link_tables:
            contents = """#!/bin/bash
                set -e
                # set up links
                sh_links.tables -frame J2000 -year %s -eop %s -topt none &> sh_links.out;
                # link the bulletin A
                ln -s ~/gg/tables/pmu.usno .
                """ % (year, eop_type)

            link_tables.write(contents)

        chmod_exec(script_path)

    def execute(self, parse_sinex=True, *, check_current=None, store_result=None):
        if len(self.Sessions) == 1:
            result = self.parse_sinex() if parse_sinex else None
            if store_result is not None:
                store_result(result)
            return result
        # Combination rewrites its working directory. Install only a completed
        # combination so a failed attempt cannot truncate an earlier result.
        destination = Path(self.pwd_comb)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".globk-", dir=destination.parent
        ) as temp:
            staged = Path(temp) / "glbf"
            staged.mkdir()
            self.pwd_comb = str(staged)
            try:
                self._combine()
                result = self.parse_sinex() if parse_sinex else None
                if parse_sinex and not result[0]:
                    raise GlobkException("GLOBK produced no station coordinates")
                if check_current is not None:
                    check_current()
                publish_directory(
                    staged,
                    destination,
                    confirm=(lambda: store_result(result))
                    if store_result is not None
                    else None,
                )
            finally:
                self.pwd_comb = str(destination)
        return result

    def _combine(self):
        inputs = []
        for session in self.Sessions:
            glx = subnet_glx(session["directory"])
            h_file = (
                f"h{session['name']}{self.date.yyyy()}{self.date.ddd()}_{self.expt}.glx"
            )
            target = Path(self.pwd_comb) / h_file
            if target.exists():
                raise GlobkException(f"Duplicate subnet input {h_file}")
            shutil.copyfile(glx, target)
            inputs.append("../" + h_file)
        if not inputs:
            raise GlobkException("No subnet inputs for GLOBK")
        tables = Path(self.pwd_comb) / "tables"
        tables.mkdir()
        (tables / "globk.gdl").write_text("".join(path + "\n" for path in inputs))

        self.linktables(self.date.yyyy(), self.eop)
        self.create_combination_script(self.date, self.org)

        # multiple sessions execute globk
        self.p = subprocess.Popen(
            "./globk.sh",
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.pwd_comb,
        )

        self.stdout, self.stderr = self.p.communicate()
        if self.p.returncode:
            raise GlobkException(
                f"GLOBK command exited with status {self.p.returncode}: {self.stderr!r}"
            )

        report = Path(self.pwd_comb) / f"{self.org}{self.date.wwwwd()}.out.gz"
        verify_globk_inputs(report, inputs)

    def create_combination_script(self, date, org):
        # extract the gps week and convert to string
        gpsWeek_str = date.wwww()

        # set the path and name for the run script
        run_file_path = os.path.join(self.pwd_comb, "globk.sh")

        try:
            run_file = file_open(run_file_path, "w")
        except:
            raise GlobkException("could not open file " + run_file_path)

        with run_file:
            contents = r"""#!/bin/bash

            set -e
            export INSTITUTE=%s

            # data product file names
            OUT_FILE=%s%s%s;
            
            cd tables
            ../link_tables.sh

            # create the globk cmd file
            echo " app_ptid all"                                                          > globk.cmd
            echo " prt_opt GDLF MIDP CMDS"                                               >> globk.cmd
            echo " out_glb ../file.GLX"                                                  >> globk.cmd
            echo " in_pmu pmu.usno"                                                      >> globk.cmd
            echo " descript Daily combination of global and regional solutions"          >> globk.cmd
            """ % (org, org, gpsWeek_str, str(date.gpsWeekDay))

            if self.net_type == "global":
                contents += """
                echo "# activated for global network merge"                                  >> globk.cmd
                echo " apr_wob    10 10  10 10 "                                             >> globk.cmd
                echo " apr_ut1    10 10        "                                             >> globk.cmd
                echo " apr_svs all 0.05 0.05 0.05 0.005 0.005 0.005 0.01 0.01 0.00 0.01 FR"  >> globk.cmd
                """
            contents += r"""
            echo " max_chii  1. 0.6"                                                     >> globk.cmd
            echo " apr_neu  all 1 1 1 0 0 0"                                             >> globk.cmd
            echo "#apr_atm  all 1 1 1"                                                   >> globk.cmd

            # create the sinex header file
            echo "+FILE/REFERENCE                               " >  head.snx
            echo " DESCRIPTION   Instituto Geografico Nacional  " >> head.snx
            echo " OUTPUT        Solucion GPS combinada         " >> head.snx
            echo " CONTACT       dgomez@ign.gob.ar              " >> head.snx
            echo " SOFTWARE      glbtosnx Version               " >> head.snx
            echo " HARDWARE      .                              " >> head.snx
            echo " INPUT         Archivos binarios Globk        " >> head.snx
            echo "-FILE/REFERENCE                               " >> head.snx

            # run globk
            globk 0 ../file.prt ../globk.log globk.gdl globk.cmd > ../globk.out 2>&1

            # convert the GLX file into sinex
            glbtosnx . ./head.snx ../file.GLX ../${OUT_FILE}.snx > ../glbtosnx.out 2>&1

            # restore original directory
            cd ..;

            # figure out where the parameters start in the prt file
            LINE=`grep -n "PARAMETER ESTIMATES" file.prt | cut -d ":" -f1`

            # reduce line by one to make a little cleaner
            let LINE--;

            # print prt header
            sed -n 1,${LINE}p file.prt > ${OUT_FILE}.out

            # append the log file
            cat globk.log >> ${OUT_FILE}.out

            # create the fsnx file which contains only the solution estimate
            lineNumber=`grep --binary-file=text -m 1 -n "\-SOLUTION/ESTIMATE" ${OUT_FILE}.snx | cut -d : -f 1`

            # extract the solution estimate
            head -$lineNumber ${OUT_FILE}.snx > ${OUT_FILE}.fsnx;

            # move the H file to a meaningful name
            mv file.GLX ${OUT_FILE}.GLX

            # clear out log files
            rm -rf tables
            rm -f file*
            rm -f globk*
            rm -f glb*
            rm -f *.sh

            # compress sinex file
            # gzip --force *.snx
            gzip --force *.fsnx
            gzip --force *.out
            gzip --force *.glx
            gzip --force *.GLX

            """

            run_file.write(contents)
            # all done

        # add executable permissions
        chmod_exec(run_file_path)

    def parse_sinex(self):
        snx = read_solution(self.pwd_comb, self.org, self.date)
        stations = {}
        for session in self.Sessions:
            for alias, network, station in session["stations"]:
                identity = f"{network}.{station}"
                previous = stations.setdefault(alias.upper(), identity)
                if previous != identity:
                    raise GlobkException(f"Conflicting station identity for {alias}")

        self.polyhedron = {
            stations[alias]: estimate for alias, estimate in snx.stationDict.items()
        }
        self.VarianceFactor = snx.varianceFactor
        return self.polyhedron, self.VarianceFactor
