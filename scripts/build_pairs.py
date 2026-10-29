"""Pick the 30 hubs and build sampled connection pairs, one month at a time.

Reads $CONN_CACHE/parquet/YYYY_MM.parquet (from fetch_bts.py) and writes
$CONN_CACHE/pairs/YYYY_MM.parquet plus, in the repo:
    tables/hubs.csv           the 30 busiest airports by departures, Sep 2023 to Aug 2026
    results/pair_counts.csv   candidates, same-tail drops and sampled pairs per hub and month

Each month's departures are joined with the first day of the next month, so a
23:40 arrival on the 31st still pairs with a 00:30 departure on the 1st.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.pairs import add_times, build_pairs  # noqa: E402

CACHE = Path(os.environ.get("CONN_CACHE", Path.home() / "data-cache" / "connection-odds"))
PARQ, PAIRS = CACHE / "parquet", CACHE / "pairs"
N_HUBS = 30
WINDOW = [(2023, m) for m in range(9, 13)] + [(y, m) for y in (2024, 2025) for m in range(1, 13)] + \
         [(2026, m) for m in range(1, 9)]
COMPARE = [(2019, m) for m in range(1, 13)]


def path(y, m):
    return PARQ / f"{y}_{m:02d}.parquet"


def hubs() -> list[str]:
    out = ROOT / "tables" / "hubs.csv"
    missing = [ym for ym in WINDOW if not path(*ym).exists()]
    if missing:
        raise SystemExit(f"missing months: {missing}")
    dep = (pl.scan_parquet([path(*ym) for ym in WINDOW])
           .group_by("origin").agg(departures=pl.len(),
                                   cancelled=pl.col("cancelled").sum())
           .sort("departures", descending=True).collect())
    top = dep.head(N_HUBS).with_row_index("rank", offset=1)
    top.write_csv(out)
    return top["origin"].to_list()


def month(y: int, m: int, hub_list: list[str]) -> list[dict]:
    out = PAIRS / f"{y}_{m:02d}.parquet"
    cur = pl.read_parquet(path(y, m))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    if path(ny, nm).exists():
        first = pl.date(ny, nm, 1)
        nxt = pl.scan_parquet(path(ny, nm)).filter(pl.col("date") == first).collect()
        deps_all = pl.concat([cur, nxt])
    else:
        deps_all = cur
    cur, deps_all = add_times(cur), add_times(deps_all)
    frames, counts = [], []
    for i, hub in enumerate(hub_list):
        seed = y * 10000 + m * 100 + i
        p, c = build_pairs(cur.filter(pl.col("dest") == hub), deps_all.filter(pl.col("origin") == hub), seed)
        frames.append(p.with_columns(hub=pl.lit(hub)))
        counts.append(dict(year=y, month=m, hub=hub, **c, sampled=p.height))
    allp = pl.concat(frames).with_columns(pl.col("hub", "mkt", "op_in", "op_out").cast(pl.Categorical))
    allp.write_parquet(out, compression="zstd")
    print(f"{y}-{m:02d}: {allp.height:,} pairs", flush=True)
    return counts


def main():
    PAIRS.mkdir(parents=True, exist_ok=True)
    hub_list = hubs()
    print("hubs:", " ".join(hub_list))
    counts = []
    for ym in WINDOW + COMPARE:
        if path(*ym).exists():
            counts += month(*ym, hub_list)
        else:
            print(f"skip {ym}: not cached")
    pl.DataFrame(counts).write_csv(ROOT / "results" / "pair_counts.csv")


if __name__ == "__main__":
    main()
