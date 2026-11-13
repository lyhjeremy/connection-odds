"""Itinerary parsing and validation: everything the language model does not do."""
import json
from pathlib import Path

import pytest

from agent import itinerary as it

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("s,want", [("7:05 PM", (1145, 0)), ("7:05p", (1145, 0)), ("19:05", (1145, 0)), ("1905", (1145, 0)),
                                    ("0640 hrs", (400, 0)), ("7pm", (1140, 0)), ("noon", (720, 0)), ("12:15 AM", (15, 0)),
                                    ("8:21 AM (+1)", (501, 1)), ("2:05 AM +1", (125, 1)), ("5:50 p.m.", (1070, 0))])
def test_parse_time(s, want):
    assert it.parse_time(s) == want


@pytest.mark.parametrize("s", ["", None, "25:00", "13:00 PM", "7", "soon"])
def test_parse_time_rejects(s):
    with pytest.raises(ValueError):
        it.parse_time(s)


@pytest.mark.parametrize("s,want", [("2026-03-04", (3, 4)), ("3/4/26", (3, 4)), ("Tue, Mar 10, 2026", (3, 10)), ("14APR", (4, 14)),
                                    ("04MAR26", (3, 4)), ("Sunday, November 22", (11, 22)), ("Sun 03 May", (5, 3)),
                                    ("March 4th 2026", (3, 4)), ("18 Dec", (12, 18))])
def test_parse_date(s, want):
    d, _ = it.parse_date(s)
    assert (d.month, d.day) == want


def test_parse_date_rejects_weekday_alone():
    with pytest.raises(ValueError):
        it.parse_date("Sat")


@pytest.mark.parametrize("airline,flight,want", [("United", "UA 1542", ("UA", "1542")), ("Southwest Airlines", "1452", ("WN", "1452")),
                                                 ("American Eagle", "4421", ("AA", "4421")), (None, "dl1196", ("DL", "1196")),
                                                 ("JetBlue", "B6 1123", ("B6", "1123")), ("Nowhere Air", "77", (None, "77"))])
def test_marketing_airline(airline, flight, want):
    assert it.marketing_airline(airline, flight) == want


def leg(a, f, o, d, dd, dt, ad, at):
    return dict(airline=a, flight_number=f, origin=o, destination=d, depart_date=dd, depart_time=dt, arrive_date=ad, arrive_time=at)


def test_layover_across_midnight_is_computed_in_code():
    r = it.resolve({"is_itinerary": True, "legs": [leg("AA", "AA 2871", "LGA", "DFW", "Fri Dec 4", "8:59 PM", None, "11:58 PM"),
                                                    leg("AA", "AA 3290", "DFW", "ELP", "Sat Dec 5", "12:50 AM", None, "1:45 AM")]})
    assert r["status"] == "ok"
    c = r["connections"][0]
    assert (c["hub"], c["layover_min"], c["arrival_hour"], c["month"]) == ("DFW", 52, 23, 12)
    assert r["assumptions"] == ["No year on the itinerary; read the dates as 2026."]


def test_missing_second_date_and_overnight_arrival():
    r = it.resolve({"is_itinerary": True, "legs": [leg("JetBlue", "515", "BOS", "FLL", "Fri, Jan 9, 2026", "5:59 PM", None, "9:17 PM"),
                                                    leg("JetBlue", "1691", "FLL", "SJU", None, "10:15 PM", None, "1:58 AM")]})
    assert r["legs"][1]["depart"] == "2026-01-09 22:15" and r["legs"][1]["arrive"] == "2026-01-10 01:58"
    assert r["connections"][0]["layover_min"] == 58


def test_stopover_is_not_a_connection_and_changes_are_flagged():
    r = it.resolve({"is_itinerary": True, "legs": [
        leg("UA", "UA 1", "SFO", "ORD", "May 13", "7:00a", None, "1:12p"), leg("UA", "UA 2", "ORD", "LGA", "May 13", "2:05p", None, "5:20p"),
        leg("UA", "UA 3", "LGA", "ORD", "May 17", "3:00p", None, "4:38p"), leg("AS", "AS 4", "ORD", "SEA", "May 17", "5:30p", None, "8:05p")]})
    assert [c["hub"] for c in r["connections"]] == ["ORD", "ORD"]
    assert "same-airline" in r["connections"][1]["not_covered"]
    r = it.resolve({"is_itinerary": True, "legs": [leg("DL", "DL 1", "ATL", "LGA", "Oct 12", "08:00", None, "10:20"),
                                                    leg("DL", "DL 2", "JFK", "LAX", "Oct 12", "12:30", None, "15:55")]})
    assert "changes airports" in r["connections"][0]["not_covered"]


def test_validation_errors():
    r = it.resolve({"is_itinerary": True, "legs": [leg("UA", "UA 1", "XQZ", "ORD", "May 13", "7:00a", None, "1:12p"),
                                                    leg("UA", "UA 2", "ORD", "LGA", "Sat", "2:05p", None, "17:20")]})
    assert r["status"] == "invalid"
    assert any("XQZ is not an airport" in e for e in r["errors"])
    assert any("cannot read date 'Sat'" in e for e in r["errors"])
    assert it.resolve({"is_itinerary": False, "legs": []})["status"] == "not_itinerary"


def test_frozen_set_is_consistent():
    rows = [json.loads(line) for line in (ROOT / "eval" / "itineraries.jsonl").read_text().splitlines()]
    assert len(rows) == 30 and sum(r["in_baseline"] for r in rows) == 20
