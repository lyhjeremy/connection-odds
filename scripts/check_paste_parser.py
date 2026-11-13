"""Score the in-browser itinerary reader (assets/paste.js) on the 30 frozen itineraries.

    python scripts/check_paste_parser.py      # needs playwright and its Chromium

Runs the shipped paste.js in headless Chromium and compares its connections (hub, airlines,
arrival hour, month, layover) with eval/itineraries.jsonl. The reader only reports connections
that stay at one airport, so an expected change of airports (i18) is left out of the comparison. Writes results/paste_parser_check.json.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
KEYS = ["hub", "airline_in", "airline_out", "arrival_hour", "month", "layover_min"]


def main():
    rows = [json.loads(l) for l in (ROOT / "eval" / "itineraries.jsonl").read_text().splitlines()]
    airports = json.loads((ROOT / "assets" / "airports.json").read_text())["airports"]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.set_content("<!DOCTYPE html><title>paste parser check</title>")
        pg.add_script_tag(path=str(ROOT / "assets" / "paste.js"))
        got = pg.evaluate("([texts, ap]) => texts.map(t => parseItinerary(t, ap))", [[r["text"] for r in rows], airports])
        b.close()
    out, exact, read, wrong = [], 0, 0, 0
    for r, g in zip(rows, got):
        legs = r["expected"]["legs"]
        want = [{k: c[k] for k in KEYS} for c in r["expected"]["connections"] if c["hub"] in [l["origin"] for l in legs]]
        have = [{k: c[k] for k in KEYS} for c in g.get("connections", [])] if "error" not in g else None
        ok = have == want
        if have is not None and want:
            read += 1
            exact += ok
            wrong += not ok
        out.append(dict(id=r["id"], expected=want, parsed=have, error=g.get("error"), exact=ok))
    with_conn = sum(1 for r in rows if r["expected"]["connections"])
    res = dict(itineraries=len(rows), with_connections=with_conn, read=read, read_and_exact=exact, read_but_wrong=wrong,
               declined=with_conn - read, rows=out)
    (ROOT / "results" / "paste_parser_check.json").write_text(json.dumps(res, indent=1) + "\n")
    print({k: v for k, v in res.items() if k != "rows"})
    for o in out:
        if not o["exact"]:
            print(o["id"], o["error"] or o["parsed"], "want", o["expected"])


if __name__ == "__main__":
    main()
