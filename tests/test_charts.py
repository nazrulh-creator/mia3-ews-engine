"""Server-rendered SVG chart kit — pure-function rendering."""
from app.core import charts


def test_rm_short():
    assert charts.rm_short(1_200_000) == "RM 1.2m"
    assert charts.rm_short(50_000) == "RM 50k"
    assert charts.rm_short(500) == "RM 500"
    assert charts.rm_short(0) == "RM 0"


def test_donut_renders_with_total():
    svg = charts.donut({"Very High Risk": 2, "High Risk": 5,
                        "Moderate Risk": 10, "Low Risk": 20})
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert ">37</text>" in svg          # total in the centre
    assert "<circle" in svg


def test_donut_empty_no_division_error():
    svg = charts.donut({})
    assert "<svg" in svg and ">0</text>" in svg


def test_hbars_formats_values():
    svg = charts.hbars([("Very High", 1_500_000, "#c0392b"),
                        ("Low", 50_000, "#27ae60")])
    assert "<svg" in svg and "RM 1.5m" in svg and "RM 50k" in svg
    assert svg.count("<rect") == 2


def test_stacked_area_needs_two_points():
    assert charts.stacked_area([{"created_at": "2026-06-01", "Low Risk": 5}]) == ""
    svg = charts.stacked_area([
        {"created_at": "2026-05-01", "Low Risk": 5, "High Risk": 1, "Moderate Risk": 2, "Very High Risk": 0},
        {"created_at": "2026-06-01", "Low Risk": 3, "High Risk": 4, "Moderate Risk": 2, "Very High Risk": 1}])
    assert svg.count("<polygon") == 4   # one layer per band


def test_scatter_renders_and_shades_quadrant():
    pts = [(0.1, 20_000, 0.2, "Low Risk"), (0.9, 800_000, 1.1, "Very High Risk")]
    svg = charts.scatter(pts)
    assert "<svg" in svg and svg.count("<circle") == 2 and "act first" in svg


def test_scatter_caps_points():
    pts = [(0.5, 100_000, 0.5, "Moderate Risk")] * 2000
    assert charts.scatter(pts, cap=300).count("<circle") == 300


def test_scatter_empty():
    assert charts.scatter([]) == ""


def test_lines_renders_with_goals_and_gaps():
    svg = charts.lines(
        [{"name": "Recall", "color": "#27ae60", "values": [0.7, 0.8, None, 0.9]}],
        ["a", "b", "c", "d"],
        goals=[{"label": "goal 0.75", "y": 0.75, "color": "#000"}])
    assert "<svg" in svg and "<polyline" in svg and "goal 0.75" in svg


def test_lines_single_point_empty():
    assert charts.lines([{"name": "x", "color": "#000", "values": [0.5]}], ["a"]) == ""


def test_gauge_zone_and_label():
    g = charts.gauge(0.40)   # >= halt
    assert "<svg" in g and "40%" in g and "halt" in g and "watch" in g
    assert charts.gauge(0.05).count("<rect") == 2  # track + fill


def test_histogram_renders_with_cutoffs():
    svg = charts.histogram([0.05, 0.1, 0.6, 0.9, 0.95, 0.3], bins=10)
    assert "<svg" in svg and "<rect" in svg and "25%" in svg and "75%" in svg


def test_histogram_empty():
    assert charts.histogram([]) == ""
