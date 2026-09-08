"""Offline checks for reporting and campaign planning."""

import zipfile

import pytest

from geode.campaign_planner import planner, report, services
from geode.reports.station_kmz import KmzStation, build_kmz
from geode.reports.station_report import StationReport, build_report, render_pdf


def station_data():
    return dict(
        network="tst",
        station="test",
        country="USA",
        status="Active",
        comms=False,
        station_type="Continuous",
        lat=40.0,
        lon=-100.0,
        height=100.0,
        x_ecef=1.0,
        y_ecef=2.0,
        z_ecef=3.0,
        location_desc='<script>alert("location")</script>',
        monument="Test pin",
        comments="A & B <script>alert(1)</script>",
    )


def test_station_report_escapes_text_without_mutating_input():
    station = StationReport(**station_data())
    html = build_report(station)
    assert '<script>alert("location")</script>' not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html
    assert station.location_desc.startswith("<script>")


def test_kmz_contains_station_and_escaped_balloon(tmp_path):
    station = KmzStation(**station_data(), status_color=None)
    path = tmp_path / "stations.kmz"
    build_kmz([station], str(path))
    with zipfile.ZipFile(path) as archive:
        kml = archive.read("doc.kml").decode()
        assert "tst.test" in kml
        assert '<script>alert("location")</script>' not in kml
        assert "&lt;script&gt;" in kml or "&amp;lt;script&amp;gt;" in kml


def test_pdf_export(tmp_path):
    pytest.importorskip("weasyprint")
    path = tmp_path / "station.pdf"
    render_pdf(build_report(StationReport(**station_data())), str(path))
    assert path.read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize(
    "start,stop", [("25:00", "26:00"), ("20:00", "08:00"), ("08:00", "08:00")]
)
def test_invalid_campaign_day_is_rejected_before_network(start, stop):
    with pytest.raises(planner.CampaignPlannerError):
        planner.plan_campaign(
            dict(
                start_city="A",
                end_city="B",
                start_date="2026-09-01",
                new_sites=[{"name": "Site", "lat": 0, "lon": 0}],
                day_start=start,
                hard_stop=stop,
            )
        )


def test_new_site_campaign_needs_no_database_and_escapes_html(monkeypatch):
    def unexpected_db(*args, **kwargs):
        pytest.fail("New-site-only planning should not open a database")

    monkeypatch.setattr(planner.dbConnection, "Cnn", unexpected_db)
    monkeypatch.setattr(
        services, "geocode_city", lambda name: {"name": name, "lat": 0, "lon": 0}
    )
    monkeypatch.setattr(
        services,
        "fetch_osrm_leg",
        lambda a, b: {
            "distance_km": 10.0,
            "drive_minutes": 30,
            "geometry": [[0, 0], [1, 1]],
        },
    )
    monkeypatch.setattr(planner.time, "sleep", lambda _: None)
    monkeypatch.setattr(report, "_fetch_leaflet", lambda: ("", ""))
    monkeypatch.setattr(report, "_generate_static_map", lambda plan: "")
    result = planner.plan_campaign(
        dict(
            start_city="A",
            end_city="B",
            start_date="2026-09-01",
            new_sites=[
                {"name": "</script><script>alert(1)</script>", "lat": 1, "lon": 1}
            ],
        )
    )
    assert result["plan"]["summary"]["total_stations"] == 1
    assert result["plan"]["summary"]["total_km"] == 20.0
    assert "</script><script>alert(1)</script>" not in result["html"]
    assert "&lt;script&gt;" in result["html"]
