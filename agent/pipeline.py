"""Pasted itinerary in, miss probability per connection out.

    python -m agent < itinerary.txt

Steps, each recorded in the returned trace:
  1. extract   claude -p (sonnet) copies legs into EXTRACTION_SCHEMA: codes, flight numbers and
               date and time strings exactly as written; no arithmetic
  2. resolve   code parses the times, checks every airport code against the BTS list, works out
               each layover in minutes (agent/itinerary.py); one repair call if validation fails
  3. model     connection_risk for every same-airline connection the model covers (agent/model.py,
               the Python port of the lookup tool's modelP)
  4. answer    claude -p (haiku) writes a short reply from the tool output
  5. check     every number and clock time in the reply must match one in the tool output or the
               parsed legs; if one does not, a template answer replaces the draft
"""
from __future__ import annotations

import json
import time

from . import itinerary, llm, model, numcheck

EXTRACT_MODEL = "sonnet"
ANSWER_MODEL = "haiku"

EXTRACT_SYSTEM = """You copy flight legs out of pasted travel text into JSON. Copy; do not calculate or convert.

- One entry per flight, in the order flown.
- airline: the airline name or code as written for that flight (carry it from a heading if the line itself has none). flight_number: as written, with its airline code if one is printed, e.g. "UA 1542" or "1452".
- origin, destination: three-letter IATA airport codes. If only a city or airport name is printed, write its code (Los Angeles is LAX, Chicago Midway is MDW).
- depart_date, arrive_date: the date text as printed for that flight, such as "Tue, Mar 10, 2026", "14APR" or "9/14/2026". If a date is printed once for the whole trip or a group of flights, copy it to each of those flights. Use null when no date is printed for that flight; never compute a date.
- depart_time, arrive_time: the time text as printed, such as "6:00 AM", "0715", "7:00a" or "8:21 AM (+1)", keeping any +1 marker. Do not convert to 24-hour time.
- is_itinerary: false when the text holds no flights."""

REPAIR_NOTE = """Your previous JSON failed validation in code:
{errors}
Previous JSON: {prev}
Re-read the itinerary and return corrected JSON. Copy date and time text only as printed; use null for a date that is not printed for that flight."""

ANSWER_SYSTEM = """You write the reply of a missed-connection checker. You get the parsed itinerary and the model's results for each connection.

Write at most 4 short sentences. For each connection give the airport, the layover in minutes and the model's chance of missing it. For a connection the model does not cover, say why in plain words. Rules:
- Use only numbers that appear in the input, copied exactly. Do not round, add, subtract or compute anything new.
- Mention that the figures assume a 20-minute walk between gates and come from US flights between September 2023 and August 2026.
- No advice beyond the numbers, no headings, no lists, no em dashes."""


def risk_calls(res: dict) -> list[dict]:
    calls = []
    for i, c in enumerate(res["connections"], start=1):
        if c.get("not_covered"):
            calls.append({"connection": i, "tool": None, "hub": c["hub"], "layover_min": c["layover_min"],
                          "covered": False, "reason": c["not_covered"]})
            continue
        t0 = time.perf_counter()
        r = model.connection_risk(c["hub"], c["airline_in"], c["arrival_hour"], c["month"], c["layover_min"])
        r["connection"] = i
        r["ms"] = round(1000 * (time.perf_counter() - t0), 2)
        calls.append(r)
    return calls


def template_answer(res: dict, calls: list[dict]) -> str:
    if res["status"] == "not_itinerary":
        return "I could not find any flights in that text. Paste the itinerary with flight numbers, airports and times."
    if res["status"] == "invalid":
        return "I could not read this itinerary reliably: " + "; ".join(res["errors"]) + "."
    if not res["connections"]:
        return "This itinerary has no connections: " + ", ".join(f"{l['origin']} to {l['destination']}" for l in res["legs"]) + "."
    parts = []
    for c in calls:
        if c["covered"]:
            parts.append(f"At {c['hub']}, a {c['layover_min']}-minute {c['airline']} connection has a "
                         f"{c['miss_probability_pct']}% chance of being missed.")
        else:
            parts.append(f"The {c['layover_min']}-minute connection at {c['hub']} is not covered: {c['reason']}.")
    parts.append("Figures assume a 20-minute walk between gates, from US flights September 2023 to August 2026.")
    return " ".join(parts + res["assumptions"])


def check_itinerary(text: str, extract_model: str = EXTRACT_MODEL, answer_model: str = ANSWER_MODEL) -> dict:
    t_start = time.perf_counter()
    steps = []
    r = llm.call(text, EXTRACT_SYSTEM, extract_model, itinerary.EXTRACTION_SCHEMA)
    steps.append({"step": "extract", "model": r.get("model"), "cost_usd": r.get("cost_usd"),
                  "duration_ms": r.get("duration_ms"), "output": r.get("structured"), "ok": r["ok"]})
    ex = r.get("structured") or {"is_itinerary": False, "legs": []}
    t0 = time.perf_counter()
    res = itinerary.resolve(ex)
    steps.append({"step": "resolve", "status": res["status"], "errors": res["errors"],
                  "ms": round(1000 * (time.perf_counter() - t0), 2)})
    first_status = res["status"]
    if res["status"] == "invalid":
        r2 = llm.call(text + "\n\n" + REPAIR_NOTE.format(errors="\n".join(res["errors"]), prev=json.dumps(ex)),
                      EXTRACT_SYSTEM, extract_model, itinerary.EXTRACTION_SCHEMA)
        steps.append({"step": "repair", "model": r2.get("model"), "cost_usd": r2.get("cost_usd"),
                      "duration_ms": r2.get("duration_ms"), "output": r2.get("structured"), "ok": r2["ok"]})
        if r2.get("structured"):
            ex = r2["structured"]
            res = itinerary.resolve(ex)
            steps.append({"step": "resolve", "status": res["status"], "errors": res["errors"]})
    t0 = time.perf_counter()
    calls = risk_calls(res) if res["status"] == "ok" else []
    steps.append({"step": "model", "calls": calls, "ms": round(1000 * (time.perf_counter() - t0), 2)})

    draft, check, used = None, None, "template"
    answer = template_answer(res, calls)
    if res["status"] == "ok" and res["connections"]:
        payload = {"legs": res["legs"], "connections": res["connections"], "model_results": calls,
                   "assumptions": res["assumptions"]}
        a = llm.call(json.dumps(payload, indent=1), ANSWER_SYSTEM, answer_model)
        draft = (a.get("text") or "").strip()
        allowed = numcheck.allowed_values(calls, res["legs"], res["connections"], res["assumptions"], [20, 2023, 2026])
        clocks = numcheck.clock_values(res["legs"], res["connections"])
        check = numcheck.check(draft, allowed, clocks)
        steps.append({"step": "answer", "model": a.get("model"), "cost_usd": a.get("cost_usd"),
                      "duration_ms": a.get("duration_ms"), "draft": draft, "check": check})
        if a["ok"] and draft and check["n_unsourced"] == 0:
            answer, used = draft, "model"
    cost = sum(s.get("cost_usd") or 0 for s in steps)
    return {"text": text, "extraction": ex, "first_status": first_status, "status": res["status"],
            "legs": res["legs"], "connections": res["connections"], "errors": res["errors"],
            "assumptions": res["assumptions"], "calls": calls, "draft": draft, "check": check, "answer": answer,
            "answer_source": used, "cost_usd": round(cost, 6), "wall_s": round(time.perf_counter() - t_start, 2),
            "steps": steps}
