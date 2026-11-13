"""The Python port of the browser's model, and the number check on answers."""
import json
from pathlib import Path

from agent import model, numcheck

ROOT = Path(__file__).resolve().parents[1]


def test_port_matches_recorded_browser_values():
    """results/model_port_check.json: scripts/check_model_port.py ran app.js and the port on 2,000 inputs."""
    chk = json.loads((ROOT / "results" / "model_port_check.json").read_text())
    assert chk["max_abs_difference"] < 1e-12
    for s in chk["sample"]:
        assert abs(model.model_p(*s["inputs"]) - s["js"]) < 1e-12


def test_connection_risk_coverage():
    r = model.connection_risk("atl", "dl", 17, 7, 45)
    assert r["covered"] and 0 < r["miss_probability_pct"] < 100
    assert not model.connection_risk("ABQ", "WN", 10, 11, 45)["covered"]
    assert "outside" in model.connection_risk("IAD", "UA", 8, 6, 25)["reason"]
    assert "too few" in model.connection_risk("MDW", "UA", 8, 6, 60)["reason"]


def test_more_layover_means_less_risk_on_average():
    a = model.connection_risk("ORD", "UA", 13, 5, 35)["miss_probability_pct"]
    b = model.connection_risk("ORD", "UA", 13, 5, 120)["miss_probability_pct"]
    assert a > b


def test_numcheck_clocks_and_numbers():
    allowed = numcheck.allowed_values({"layover_min": 53, "miss_probability_pct": 8.6}, [{"depart": "2026-04-14 11:05"}])
    clocks = numcheck.clock_values([{"arrive": "2026-04-14 10:12", "depart": "2026-04-14 11:05"}])
    c = numcheck.check("Your 53-minute ATL connection (land 10:12 am, leave 11:05) has an 8.6% chance of a miss, 15% at worst.", allowed, clocks)
    assert c["unsourced"] == ["15%"]
    c = numcheck.check("You land at 10:30 on April 14.", allowed, clocks)
    assert c["unsourced"] == ["10:30"]
