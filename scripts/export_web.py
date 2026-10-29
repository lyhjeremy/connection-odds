"""Write assets/tool.json (the lookup tool's data) and assets/charts.json (page charts).

tool.json holds, for each W on the slider:
  - the logistic model refitted on a seeded sample of all 36 months, and
  - observed cell counts for every (hub, airline, arrival hour, month, 15-minute
    layover bucket) cell with at least 200 pairs.
The browser evaluates the model by summing coefficients; nothing is fetched from
anywhere but this repo.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.model import MissModel  # noqa: E402
from analysis.pairs import D_DEFAULT, W_DEFAULT, missed  # noqa: E402
from scripts.analyze import MIN_CELL, SEED, WINDOW, pairs_scan, sample  # noqa: E402

W_VALUES = [10, 15, 20, 25, 30]
N_FIT = int(os.environ.get("N_FIT", 3_000_000))
TAB = ROOT / "tables"

AIRPORTS = {  # city names for the 30 hubs; codes are what the data carries
    "ATL": "Atlanta", "ORD": "Chicago O'Hare", "DFW": "Dallas/Fort Worth", "DEN": "Denver",
    "CLT": "Charlotte", "LAX": "Los Angeles", "PHX": "Phoenix", "SEA": "Seattle",
    "IAH": "Houston Intercontinental", "DTW": "Detroit", "LGA": "New York LaGuardia",
    "SFO": "San Francisco", "LAS": "Las Vegas", "MSP": "Minneapolis", "EWR": "Newark",
    "PHL": "Philadelphia", "BOS": "Boston", "MCO": "Orlando", "DCA": "Washington National",
    "JFK": "New York JFK", "SLC": "Salt Lake City", "FLL": "Fort Lauderdale", "BWI": "Baltimore",
    "SAN": "San Diego", "MIA": "Miami", "IAD": "Washington Dulles", "MDW": "Chicago Midway",
    "TPA": "Tampa", "PDX": "Portland", "BNA": "Nashville", "AUS": "Austin", "HOU": "Houston Hobby",
    "DAL": "Dallas Love Field", "STL": "St. Louis", "RDU": "Raleigh-Durham", "SJC": "San Jose",
    "OAK": "Oakland", "SMF": "Sacramento", "MSY": "New Orleans", "HNL": "Honolulu", "SNA": "Orange County",
    "MCI": "Kansas City", "SAT": "San Antonio", "IND": "Indianapolis", "CLE": "Cleveland",
    "PIT": "Pittsburgh", "CMH": "Columbus", "RSW": "Fort Myers",
}
AIRLINES = {
    "AA": "American", "DL": "Delta", "UA": "United", "WN": "Southwest", "AS": "Alaska",
    "B6": "JetBlue", "NK": "Spirit", "F9": "Frontier", "G4": "Allegiant", "HA": "Hawaiian",
    "SY": "Sun Country", "MX": "Breeze", "XE": "JSX",
}


def pack_model(m: dict, ha_order: list[str], hubs: list[str]) -> dict:
    """Turn the keyed coefficient dict into arrays the browser indexes directly.
    lay bins 0..29 (30-34 ... 175-180 minutes), hours 0..23, months 1..12 at index
    0..11, weekdays 1..7 (Monday first) at index 0..6. A missing key is a zero."""
    g = lambda term, k: m.get(term, {}).get(str(k), 0)
    r2 = lambda x: round(x, 2)
    return dict(
        b0=m["b0"],
        ha=[r2(g("ha", h)) for h in ha_order],
        lay=[r2(g("lay", i)) for i in range(30)],
        hr=[r2(g("hr", i)) for i in range(24)],
        mo=[r2(g("mo", i)) for i in range(1, 13)],
        dw=[r2(g("dw", i)) for i in range(1, 8)],
        lay_ha=[[r2(g("lay_ha", f"{i}:{h}")) for i in range(30)] for h in ha_order],
        mo_hub={hub: [r2(g("mo_hub", f"{i}:{hub}")) for i in range(1, 13)] for hub in hubs},
        hr_hub={hub: [r2(g("hr_hub", f"{i}:{hub}")) for i in range(24)] for hub in hubs},
    )


def main():
    ha = pl.read_csv(TAB / "hub_airlines.csv")
    hubs_rank = pl.read_csv(TAB / "hubs.csv")
    summ = json.loads((ROOT / "results" / "summary.json").read_text())
    keep = ha.select("hub", "mkt")
    p = pairs_scan(WINDOW).join(keep.lazy(), on=["hub", "mkt"], how="semi").with_columns(
        month=pl.col("date").dt.month())

    # observed cells
    aggs = [pl.len().alias("n")] + [missed(w, D_DEFAULT).sum().alias(f"k{w}") for w in W_VALUES]
    cells = (p.group_by("hub", "mkt", "arr_hour", "month", "bucket").agg(aggs)
             .filter(pl.col("n") >= MIN_CELL).sort("hub", "mkt", "arr_hour", "month", "bucket").collect())
    # Packed per hub|airline as one flat list, seven numbers a cell:
    #   key step, n, k at W=20, then |k_W - k_20| for W = 10, 15, 25, 30
    # where key = hour*120 + (month-1)*10 + bucket, stored as the step from the
    # previous key (the first from -1). Misses rise with W, so the sign is implied.
    others = [w for w in W_VALUES if w != W_DEFAULT]
    cell_out: dict[str, list] = {}
    for (h, m), g in cells.group_by(["hub", "mkt"], maintain_order=True):
        flat, prev = [], -1
        for r in g.iter_rows(named=True):
            key = r["arr_hour"] * 120 + (r["month"] - 1) * 10 + r["bucket"]
            k20 = r[f"k{W_DEFAULT}"]
            flat += [key - prev, r["n"], k20] + [abs(r[f"k{w}"] - k20) for w in others]
            prev = key
        cell_out[f"{h}|{m}"] = flat
    print(f"cells kept: {cells.height:,}")

    # models, one per W, on the same seeded sample of the full window
    tr = sample(p, N_FIT, SEED + 10)
    models = {}
    for w in W_VALUES:
        y = tr.select(missed(w, D_DEFAULT)).to_series().to_numpy().astype(float)
        models[str(w)] = MissModel().fit(tr, y).export(digits=3)
        print("model W", w, "done", flush=True)
    ha_order = [f"{h}|{m}" for h, m in ha.select("hub", "mkt").rows()]
    hub_codes = hubs_rank["origin"].to_list()
    models = {w: pack_model(mm, ha_order, hub_codes) for w, mm in models.items()}

    hubs = []
    for r in hubs_rank.iter_rows(named=True):
        al = ha.filter(pl.col("hub") == r["origin"]).sort("n", descending=True)
        hubs.append(dict(code=r["origin"], name=AIRPORTS.get(r["origin"], r["origin"]),
                         airlines=al["mkt"].to_list(), pairs=al["n"].to_list()))
    tool = dict(
        built="Sep 2023 to Aug 2026", W_values=W_VALUES, W_default=W_DEFAULT, D=D_DEFAULT,
        min_cell=MIN_CELL, shipped=summ["evaluation"]["best"],
        airlines={k: v for k, v in AIRLINES.items() if k in set(ha["mkt"])},
        hubs=hubs, ha_order=ha_order, model=models, cells=cell_out,
    )
    raw = json.dumps(tool, separators=(",", ":"))
    (ROOT / "assets" / "tool.json").write_text(raw)
    gz = len(gzip.compress(raw.encode()))
    print(f"tool.json {len(raw)/1e6:.2f} MB, gzip {gz/1e6:.2f} MB")
    if len(raw) > 2_000_000:
        raise SystemExit("tool.json over the 2 MB budget")
    s = json.loads((ROOT / "results" / "summary.json").read_text())
    s["tool_json_bytes"] = len(raw)
    s["tool_json_gzip_bytes"] = gz
    s["tool_cells"] = cells.height
    s["tool_cells_pairs_share"] = float(cells["n"].sum() / p.select(pl.len()).collect().item())
    (ROOT / "results" / "summary.json").write_text(json.dumps(s, indent=1, default=str))


if __name__ == "__main__":
    main()
