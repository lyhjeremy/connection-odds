"""Write assets/airports.json: every airport code that appears as an origin or destination in
the BTS window (September 2023 to August 2026), with its flight count. The itinerary checker
rejects any code not in this list. Needs the parquet cache from scripts/fetch_bts.py.

    python scripts/export_airports.py
"""
import json
import os
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("CONN_CACHE", Path.home() / "data-cache" / "connection-odds")) / "parquet"


def main():
    files = sorted(f for f in CACHE.glob("*.parquet") if "2023_09" <= f.stem <= "2026_08")
    lf = pl.scan_parquet(files)
    codes = (pl.concat([lf.select(code=pl.col("origin")), lf.select(code=pl.col("dest"))])
             .group_by("code").agg(n=pl.len()).sort("code").collect())
    out = dict(source=f"BTS marketing-carrier on-time data, {files[0].stem} to {files[-1].stem}, {len(files)} months",
               airports={r["code"]: r["n"] for r in codes.iter_rows(named=True)})
    (ROOT / "assets" / "airports.json").write_text(json.dumps(out, separators=(",", ":")))
    print(len(out["airports"]), "airports from", len(files), "files")


if __name__ == "__main__":
    main()
