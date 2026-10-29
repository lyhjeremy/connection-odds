"""Download BTS marketing-carrier on-time zips and convert each month to parquet.

Usage:
    python scripts/fetch_bts.py            # the study window plus calendar 2019
    python scripts/fetch_bts.py 2026-8     # one month

Files go to $CONN_CACHE (default ~/data-cache/connection-odds), never into the repo.
Downloads resume with curl -C -, and a month whose parquet already exists is skipped.
The zip is deleted after a successful conversion unless KEEP_ZIPS=1, because three
years of zips is about 1.8 GB. Row counts go to results/fetch_manifest.csv.
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("CONN_CACHE", Path.home() / "data-cache" / "connection-odds"))
ZIPS = CACHE / "zips"
PARQ = CACHE / "parquet"
MANIFEST = ROOT / "results" / "fetch_manifest.csv"
URL = ("https://transtats.bts.gov/PREZIP/"
       "On_Time_Marketing_Carrier_On_Time_Performance_Beginning_January_2018_{y}_{m}.zip")

# Column name in the file -> name in the parquet. Note the trailing space BTS puts
# after Operating_Airline.
COLUMNS = {
    "FlightDate": "date",
    "DayOfWeek": "dow",
    "Marketing_Airline_Network": "mkt",
    "Operating_Airline ": "op",
    "Tail_Number": "tail",
    "Flight_Number_Marketing_Airline": "flight",
    "Origin": "origin",
    "Dest": "dest",
    "CRSDepTime": "crs_dep",
    "DepTime": "dep",
    "DepDelay": "dep_delay",
    "CRSArrTime": "crs_arr",
    "ArrTime": "arr",
    "ArrDelay": "arr_delay",
    "Cancelled": "cancelled",
    "Diverted": "diverted",
    "CRSElapsedTime": "crs_elapsed",
    "Duplicate": "duplicate",
}


def months() -> list[tuple[int, int]]:
    out = [(2019, m) for m in range(1, 13)]
    y, m = 2023, 9
    while (y, m) <= (2026, 8):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def download(y: int, m: int) -> Path:
    z = ZIPS / f"{y}_{m}.zip"
    done = ZIPS / f"{y}_{m}.zip.done"
    if done.exists():
        return z
    for attempt in range(6):
        r = subprocess.run(["curl", "-sS", "-f", "-C", "-", "--retry", "5", "--speed-limit", "1000", "--speed-time", "60",
                            "-o", str(z), URL.format(y=y, m=m)])
        if r.returncode in (0, 33):  # 33: server refused range on an already complete file
            try:
                with zipfile.ZipFile(z) as zf:
                    if zf.testzip() is None:
                        done.touch()
                        return z
            except zipfile.BadZipFile:
                pass
            if attempt >= 3:
                z.unlink(missing_ok=True)
    raise RuntimeError(f"download failed {y}-{m}")


def convert(y: int, m: int, z: Path) -> int:
    out = PARQ / f"{y}_{m:02d}.parquet"
    with zipfile.ZipFile(z) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        raw = zf.read(name)
    df = pl.read_csv(io.BytesIO(raw), columns=list(COLUMNS), infer_schema_length=0)
    del raw
    df = df.rename(COLUMNS).with_columns(
        pl.col("date").str.to_date(),
        pl.col("dow").cast(pl.Int8),
        *[pl.col(c).replace("", None).cast(pl.Float64).cast(pl.Int16)
          for c in ("crs_dep", "dep", "crs_arr", "arr", "dep_delay", "arr_delay", "crs_elapsed")],
        *[pl.col(c).replace("", None).cast(pl.Float64).cast(pl.Int8) for c in ("cancelled", "diverted")],
        pl.col("flight").replace("", None).cast(pl.Int32),
        pl.col("tail").replace("", None),
    )
    tmp = out.with_suffix(".tmp")
    df.write_parquet(tmp, compression="zstd")
    tmp.rename(out)
    return df.height


def one(ym: tuple[int, int]) -> tuple[int, int, int]:
    y, m = ym
    out = PARQ / f"{y}_{m:02d}.parquet"
    if out.exists():
        return y, m, pl.scan_parquet(out).select(pl.len()).collect().item()
    z = download(y, m)
    n = convert(y, m, z)
    if os.environ.get("KEEP_ZIPS") != "1":
        z.unlink(missing_ok=True)
    print(f"{y}-{m:02d}: {n:,} rows", flush=True)
    return y, m, n


def main() -> None:
    ZIPS.mkdir(parents=True, exist_ok=True)
    PARQ.mkdir(parents=True, exist_ok=True)
    todo = months()
    if len(sys.argv) > 1:
        todo = [tuple(int(x) for x in a.split("-")) for a in sys.argv[1:]]
    workers = int(os.environ.get("FETCH_WORKERS", "4"))
    # Downloads run in parallel; conversions hold a 335 MB CSV in memory each, so
    # the worker count also caps memory at roughly workers x 2 GB.
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, todo))
    rows += [r for r in (read_manifest()) if (r[0], r[1]) not in {(a, b) for a, b, _ in rows}]
    rows.sort()
    MANIFEST.parent.mkdir(exist_ok=True)
    with open(MANIFEST, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "rows"])
        w.writerows(rows)


def read_manifest() -> list[tuple[int, int, int]]:
    if not MANIFEST.exists():
        return []
    with open(MANIFEST) as f:
        return [(int(r["year"]), int(r["month"]), int(r["rows"])) for r in csv.DictReader(f)]


if __name__ == "__main__":
    main()
