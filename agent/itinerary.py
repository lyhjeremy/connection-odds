"""Itinerary contract: what the language model extracts, and the code that checks and times it.

The model only copies: airline and flight number as written, airport codes, and each date and
time string exactly as it appears. Everything else happens here, deterministically:

  parse_time / parse_date   turn "7:05p", "19:05", "Tue, Mar 4" or "04MAR" into clock values
  marketing_airline         "UA 1234", "United", "Delta Connection" to a two-letter code
  resolve                   validate every leg (codes exist in the BTS airport list, times parse,
                            arrival after departure), then pair consecutive legs at the same
                            airport into connections and compute each layover in minutes

Both times of a connection are local at the connecting airport, so the layover needs no
time-zone table (the same reasoning as analysis/pairs.py).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import model

DEFAULT_YEAR = 2026
MAX_CONNECTION_GAP = 24 * 60  # a longer gap is a stopover or a separate trip, not a connection

_s = {"type": ["string", "null"]}
EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_itinerary": {"type": "boolean"},
        "legs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "airline": _s, "flight_number": _s, "origin": _s, "destination": _s,
                    "depart_date": _s, "depart_time": _s, "arrive_date": _s, "arrive_time": _s,
                },
                "required": ["airline", "flight_number", "origin", "destination", "depart_date",
                             "depart_time", "arrive_date", "arrive_time"],
            },
        },
    },
    "required": ["is_itinerary", "legs"],
}

AIRLINE_NAMES = {
    "american": "AA", "american airlines": "AA", "american eagle": "AA",
    "delta": "DL", "delta air lines": "DL", "delta airlines": "DL", "delta connection": "DL",
    "united": "UA", "united airlines": "UA", "united express": "UA",
    "southwest": "WN", "southwest airlines": "WN",
    "alaska": "AS", "alaska airlines": "AS", "horizon": "AS",
    "jetblue": "B6", "jetblue airways": "B6",
    "spirit": "NK", "spirit airlines": "NK",
    "frontier": "F9", "frontier airlines": "F9",
    "allegiant": "G4", "allegiant air": "G4",
    "hawaiian": "HA", "hawaiian airlines": "HA",
    "sun country": "SY", "sun country airlines": "SY",
    "breeze": "MX", "breeze airways": "MX",
}
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


# ---------------------------------------------------------------- times and dates

_TIME = re.compile(r"^\s*(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?|a|p)?\s*$", re.I)
_TIME4 = re.compile(r"^\s*(?P<h>\d{2})(?P<m>\d{2})\s*(?P<ap>a\.?m\.?|p\.?m\.?|a|p)?\s*$", re.I)
_PLUS = re.compile(r"\(?\s*\+\s*(\d)\s*(?:day|days)?\s*\)?", re.I)


def parse_time(s: str | None) -> tuple[int, int]:
    """Clock string to (minutes after midnight, day offset). Raises ValueError if it does not parse.
    Accepts 7:05 PM, 7:05p, 7.05pm, 19:05, 1905, 7pm, noon, midnight, and a trailing +1 or (+1 day)."""
    if s is None or not str(s).strip():
        raise ValueError("missing time")
    t = str(s).strip()
    off = 0
    m = _PLUS.search(t)
    if m:
        off = int(m.group(1))
        t = (t[:m.start()] + t[m.end():]).strip()
    low = t.lower().replace("hrs", "").strip()
    if low == "noon":
        return 720, off
    if low == "midnight":
        return 0, off
    m = _TIME.match(low) or _TIME4.match(low)
    if not m:
        raise ValueError(f"cannot read time {s!r}")
    h, mi = int(m.group("h")), int(m.group("m") or 0)
    ap = (m.group("ap") or "").replace(".", "").lower()
    if ap:
        if not 1 <= h <= 12:
            raise ValueError(f"hour {h} with am/pm in {s!r}")
        h = h % 12 + (12 if ap.startswith("p") else 0)
    elif m.group("m") is None:
        raise ValueError(f"bare number {s!r} is not a time")
    if h > 23 or mi > 59:
        raise ValueError(f"cannot read time {s!r}")
    return h * 60 + mi, off


_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")
_US = re.compile(r"^\s*(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\s*$")
_DDMON = re.compile(r"^\s*(\d{1,2})\s*([a-z]{3,9})\.?,?\s*(\d{2,4})?\s*$", re.I)
_MONDD = re.compile(r"^\s*([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\s*$", re.I)
_DOW = re.compile(r"^\s*(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s+", re.I)


def _year(y: str | None, default: int) -> int:
    if not y:
        return default
    y = int(y)
    return y + 2000 if y < 100 else y


def _mon(name: str) -> int:
    k = name[:3].lower()
    if k not in MONTHS:
        raise ValueError(f"unknown month {name!r}")
    return MONTHS[k]


def parse_date(s: str | None, default_year: int = DEFAULT_YEAR) -> tuple[date, bool]:
    """Date string to (date, year_was_given). US order for slashes (3/4 is March 4).
    Accepts 2026-03-04, 3/4/26, 3/4, Mar 4, March 4th 2026, Tue, Mar 4, 04MAR, 4 Mar 2026, 04MAR26."""
    if s is None or not str(s).strip():
        raise ValueError("missing date")
    t = _DOW.sub("", str(s).strip())
    m = _ISO.match(t)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), True
    m = _US.match(t)
    if m:
        return date(_year(m.group(3), default_year), int(m.group(1)), int(m.group(2))), m.group(3) is not None
    m = re.match(r"^\s*(\d{1,2})([a-z]{3})(\d{2,4})?\s*$", t, re.I)  # 04MAR, 04MAR26
    if m:
        return date(_year(m.group(3), default_year), _mon(m.group(2)), int(m.group(1))), m.group(3) is not None
    m = _MONDD.match(t)
    if m:
        return date(_year(m.group(3), default_year), _mon(m.group(1)), int(m.group(2))), m.group(3) is not None
    m = _DDMON.match(t)
    if m:
        return date(_year(m.group(3), default_year), _mon(m.group(2)), int(m.group(1))), m.group(3) is not None
    raise ValueError(f"cannot read date {s!r}")


# ---------------------------------------------------------------- airlines

_FLT = re.compile(r"^\s*([A-Z][A-Z0-9]|[0-9][A-Z])\s*-?\s*(\d{1,4})\s*$")


def marketing_airline(airline: str | None, flight: str | None) -> tuple[str | None, str | None]:
    """(two-letter code, flight digits). The flight number prefix wins over the airline name."""
    code, digits = None, None
    if flight:
        f = str(flight).upper().replace("FLIGHT", "").strip()
        m = _FLT.match(f)
        if m:
            code, digits = m.group(1), m.group(2)
        else:
            d = re.sub(r"\D", "", f)
            digits = d or None
    if code is None and airline:
        a = re.sub(r"[^a-z ]", "", str(airline).lower()).strip()
        if a.upper() in model.tool()["airlines"] or re.fullmatch(r"[a-z0-9]{2}", a):
            code = a.upper()
        else:
            for name in sorted(AIRLINE_NAMES, key=len, reverse=True):
                if a == name or a.startswith(name + " ") or a.startswith(name):
                    code = AIRLINE_NAMES[name]
                    break
    return code, digits


# ---------------------------------------------------------------- legs and connections

def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def resolve(ex: dict, default_year: int = DEFAULT_YEAR) -> dict:
    """Extraction JSON to validated legs and timed connections. Never raises; errors are listed."""
    if not ex or not ex.get("is_itinerary") or not ex.get("legs"):
        return {"status": "not_itinerary", "legs": [], "connections": [], "errors": [], "assumptions": []}
    known = model.airports()
    legs, errors, notes = [], [], []
    year_missing = False
    prev_arr = None
    for i, lg in enumerate(ex["legs"], start=1):
        e = []
        org = (lg.get("origin") or "").strip().upper()
        dst = (lg.get("destination") or "").strip().upper()
        for label, c in (("origin", org), ("destination", dst)):
            if not re.fullmatch(r"[A-Z]{3}", c or ""):
                e.append(f"leg {i}: {label} {c or 'missing'} is not a three-letter airport code")
            elif c not in known:
                e.append(f"leg {i}: {label} {c} is not an airport in the BTS data")
        code, digits = marketing_airline(lg.get("airline"), lg.get("flight_number"))
        if code is None:
            e.append(f"leg {i}: airline not recognized")
        dep_dt = arr_dt = None
        try:
            if lg.get("depart_date"):
                d0, has_y = parse_date(lg["depart_date"], default_year)
                year_missing |= not has_y
            elif prev_arr is not None:
                d0 = prev_arr.date()  # same day as the previous arrival unless the clock says otherwise
            else:
                raise ValueError("missing departure date")
            t0, off0 = parse_time(lg.get("depart_time"))
            dep_dt = datetime(d0.year, d0.month, d0.day) + timedelta(days=off0, minutes=t0)
            if not lg.get("depart_date") and prev_arr is not None and dep_dt < prev_arr:
                dep_dt += timedelta(days=1)
        except ValueError as err:
            e.append(f"leg {i}: departure {err}")
        try:
            t1, off1 = parse_time(lg.get("arrive_time"))
            if lg.get("arrive_date"):
                d1, has_y = parse_date(lg["arrive_date"], default_year)
                year_missing |= not has_y
                arr_dt = datetime(d1.year, d1.month, d1.day) + timedelta(minutes=t1)
            elif dep_dt is not None:
                arr_dt = datetime(dep_dt.year, dep_dt.month, dep_dt.day) + timedelta(days=off1, minutes=t1)
                if off1 == 0 and arr_dt < dep_dt:
                    arr_dt += timedelta(days=1)  # an overnight flight printed without +1
        except ValueError as err:
            e.append(f"leg {i}: arrival {err}")
        if dep_dt and arr_dt and arr_dt - dep_dt > timedelta(hours=20):
            e.append(f"leg {i}: arrival is more than 20 hours after departure")
        errors += e
        legs.append({"leg": i, "airline": code, "flight": digits, "origin": org, "destination": dst,
                     "depart": _fmt(dep_dt) if dep_dt else None, "arrive": _fmt(arr_dt) if arr_dt else None})
        prev_arr = arr_dt
    if year_missing:
        notes.append(f"No year on the itinerary; read the dates as {default_year}.")

    conns = []
    for a, b in zip(legs, legs[1:]):
        if not (a["arrive"] and b["depart"]):
            continue
        t_arr = datetime.strptime(a["arrive"], "%Y-%m-%d %H:%M")
        t_dep = datetime.strptime(b["depart"], "%Y-%m-%d %H:%M")
        gap = int((t_dep - t_arr).total_seconds() // 60)
        if gap > MAX_CONNECTION_GAP:
            continue  # stopover or return trip
        if gap < 0:
            errors.append(f"leg {b['leg']} departs before leg {a['leg']} arrives")
            continue
        c = {"after_leg": a["leg"], "hub": a["destination"], "depart_airport": b["origin"],
             "airline_in": a["airline"], "airline_out": b["airline"], "arrive": a["arrive"],
             "depart": b["depart"], "arrival_hour": t_arr.hour, "month": t_arr.month, "layover_min": gap}
        if a["destination"] != b["origin"]:
            c["not_covered"] = f"changes airports ({a['destination']} to {b['origin']}), which the model does not cover"
        elif a["airline"] != b["airline"]:
            c["not_covered"] = f"changes airlines ({a['airline']} to {b['airline']}); the model covers same-airline connections only"
        conns.append(c)
    status = "ok" if not errors else "invalid"
    return {"status": status, "legs": legs, "connections": conns, "errors": errors, "assumptions": notes}
