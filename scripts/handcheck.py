"""Hand check of the pair builder on one real arrival: ATL, Delta, 10 August 2026.

Prints the arrival, every unsampled candidate departure with its scheduled gap, the
same-tail flag and the slack, so each line can be checked against the raw flights.
Output: results/handcheck.txt
"""
import os
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.pairs import add_times, build_pairs, missed  # noqa: E402

CACHE = Path(os.environ.get("CONN_CACHE", Path.home() / "data-cache" / "connection-odds"))
f = add_times(pl.read_parquet(CACHE / "parquet" / "2026_08.parquet"))
day = pl.date(2026, 8, 10)
arr = f.filter((pl.col("dest") == "ATL") & (pl.col("mkt") == "DL") & (pl.col("date") == day)
               & (pl.col("crs_arr") >= 1500) & (pl.col("crs_arr") < 1505)).sort("crs_arr", "origin").head(1)
deps = f.filter((pl.col("origin") == "ATL") & (pl.col("mkt") == "DL") & pl.col("date").is_between(day, pl.date(2026, 8, 11)))
p, c = build_pairs(arr, deps, seed=0, sample=False)
lines = ["Arrival:", str(arr.select("date", "origin", "dest", "flight", "tail", "crs_dep", "crs_arr", "arr", "arr_delay", "cancelled", "diverted")),
         f"Counts: {c}",
         "Raw departures in the window (scheduled 30 to 180 minutes after the arrival):"]
a0 = arr["sched_arr"][0]
raw = deps.filter(pl.col("sched_dep").is_between(a0 + 30, a0 + 180)).with_columns(
    gap=pl.col("sched_dep") - a0, same_tail=pl.col("tail") == arr["tail"][0],
    back_to_origin=pl.col("dest") == arr["origin"][0]).sort("sched_dep")
lines.append(f"{raw.height} departures, {int(raw['same_tail'].sum())} same tail, {int(raw['back_to_origin'].sum())} back to origin")
lines.append(str(raw.select("dest", "flight", "tail", "crs_dep", "dep", "dep_delay", "cancelled", "gap", "same_tail", "back_to_origin").head(12)))
lines.append("Pairs from build_pairs (first 12), slack = actual departure minus actual arrival:")
lines.append(str(p.with_columns(missed=missed()).select("layover", "bucket", "status", "slack", "arr_delay", "dep_delay", "missed").sort("layover").head(12)))
out = "\n".join(lines)
pl.Config.set_tbl_rows(20)
(ROOT / "results" / "handcheck.txt").write_text(out + "\n")
print(out)
