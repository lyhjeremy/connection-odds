#!/bin/sh
# Rebuild everything from the cached parquet files. Run from the repo root.
set -e
python -m pytest -q tests
python scripts/build_pairs.py      # tables/hubs.csv, results/pair_counts.csv, $CONN_CACHE/pairs/
python scripts/analyze.py          # tables/*.csv, results/summary.json
python scripts/export_web.py       # assets/tool.json
python scripts/make_figures.py     # figures/*.svg
python scripts/export_numbers.py   # site/numbers.json
python scripts/build_site.py       # index.html, README.md, overview fragment
