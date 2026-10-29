"""Every analysis result the site quotes: EDA tables, miss-rate curves, the layover
needed for 90/95/99%, the naive shortcut, the logistic model and the calibration test.

Reads $CONN_CACHE/parquet and $CONN_CACHE/pairs. Writes tables/*.csv and
results/summary.json. Run after build_pairs.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from analysis.model import MissModel, TERMS, features  # noqa: E402
from analysis.pairs import D_DEFAULT, W_DEFAULT, missed  # noqa: E402
from analysis.stats import add_wilson, calibration, layover_needed  # noqa: E402
from scripts.build_pairs import COMPARE, WINDOW  # noqa: E402

CACHE = Path(os.environ.get("CONN_CACHE", Path.home() / "data-cache" / "connection-odds"))
TAB, RES = ROOT / "tables", ROOT / "results"
SEED = 39
MIN_PAIRS_AIRLINE = 1000   # an airline counts at a hub with at least this many pairs (spec 4.6)
MIN_CELL = 200             # smaller cells fall back (spec 6)
TEST = [(2026, m) for m in range(3, 9)]
TRAIN = [ym for ym in WINDOW if ym not in TEST]
N_TRAIN = int(os.environ.get("N_TRAIN", 3_000_000))
N_TEST = int(os.environ.get("N_TEST", 2_000_000))
LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def pairs_scan(months) -> pl.LazyFrame:
    files = [CACHE / "pairs" / f"{y}_{m:02d}.parquet" for y, m in months]
    return pl.scan_parquet([f for f in files if f.exists()]).with_columns(
        pl.col("hub", "mkt", "op_in", "op_out").cast(pl.Utf8))


def flights_scan(months) -> pl.LazyFrame:
    return pl.scan_parquet([CACHE / "parquet" / f"{y}_{m:02d}.parquet" for y, m in months])


def write(df: pl.DataFrame, name: str):
    df.write_csv(TAB / name, float_precision=5)


def lbin_expr():
    return (((pl.col("layover") - 30) // 5).clip(0, 29) * 5 + 30).alias("layover_bin")


# ---------------------------------------------------------------- EDA (flights)
def eda(hubs: list[str]) -> dict:
    f = flights_scan(WINDOW)
    dep = (f.filter(pl.col("origin").is_in(hubs))
           .group_by(hub="origin").agg(
               departures=pl.len(),
               cancel_rate=pl.col("cancelled").mean(),
               dep_delay_mean=pl.col("dep_delay").mean(),
               dep_delay_median=pl.col("dep_delay").median(),
               dep_late15=(pl.col("dep_delay") > 15).mean()).collect())
    arr = (f.filter(pl.col("dest").is_in(hubs))
           .group_by(hub="dest").agg(
               arrivals=pl.len(),
               arr_cancel_div_rate=((pl.col("cancelled") == 1) | (pl.col("diverted") == 1)).mean(),
               arr_delay_mean=pl.col("arr_delay").mean(),
               arr_late15=(pl.col("arr_delay") > 15).mean()).collect())
    pc = pl.read_csv(RES / "pair_counts.csv").filter(
        (pl.col("year") * 100 + pl.col("month")).is_in([y * 100 + m for y, m in WINDOW]))
    tail = pc.group_by("hub").agg(pl.col("candidates", "same_tail", "kept", "sampled").sum()).with_columns(
        same_tail_share=pl.col("same_tail") / pl.col("candidates"))
    hs = (pl.read_csv(TAB / "hubs.csv").select("rank", hub="origin")
          .join(dep, on="hub").join(arr, on="hub").join(tail, on="hub").sort("rank"))
    write(hs, "hub_summary.csv")

    hour = (f.filter(pl.col("origin").is_in(hubs))
            .group_by(hour=(pl.col("crs_dep") // 100).clip(0, 23))
            .agg(departures=pl.len(), dep_delay_mean=pl.col("dep_delay").mean(),
                 dep_late15=(pl.col("dep_delay") > 15).mean(), cancel_rate=pl.col("cancelled").mean())
            .sort("hour").collect())
    write(hour, "delay_by_hour.csv")
    month = (f.filter(pl.col("origin").is_in(hubs))
             .group_by(ym=pl.col("date").dt.strftime("%Y-%m"))
             .agg(departures=pl.len(), dep_delay_mean=pl.col("dep_delay").mean(),
                  dep_late15=(pl.col("dep_delay") > 15).mean(), cancel_rate=pl.col("cancelled").mean())
             .sort("ym").collect())
    write(month, "delay_by_month.csv")
    air = (f.group_by("mkt").agg(flights=pl.len(), cancel_rate=pl.col("cancelled").mean(),
                                 dep_delay_mean=pl.col("dep_delay").mean(),
                                 dep_late15=(pl.col("dep_delay") > 15).mean())
           .sort("flights", descending=True).collect())
    write(air, "airline_summary.csv")
    tot = f.select(flights=pl.len(), first=pl.col("date").min(), last=pl.col("date").max()).collect().row(0, named=True)
    peak = hour.filter(pl.col("departures") > 10000)
    return dict(
        flights_window=tot["flights"], first_date=str(tot["first"]), last_date=str(tot["last"]),
        hub_departures=int(hs["departures"].sum()),
        same_tail_share_all=float(tail["same_tail"].sum() / tail["candidates"].sum()),
        same_tail_max_hub=hs.sort("same_tail_share")[-1, "hub"],
        same_tail_max=float(hs["same_tail_share"].max()),
        candidates_window=int(tail["candidates"].sum()),
        sampled_window=int(tail["sampled"].sum()),
        delay_by_hour_first=peak.sort("dep_late15")[0].to_dicts()[0],
        delay_by_hour_max=peak.sort("dep_late15")[-1].to_dicts()[0],
        worst_month=month.sort("cancel_rate")[-1].to_dicts()[0],
    )


# ---------------------------------------------------------------- curves
def curves(p: pl.LazyFrame, keys: list[str], w=W_DEFAULT, extra=None) -> pl.DataFrame:
    by = keys + ["layover_bin"]
    df = (p.with_columns(lbin_expr(), m=missed(w, D_DEFAULT))
          .group_by(by).agg(n=pl.len(), k=pl.col("m").sum(),
                            k_cancel=(pl.col("status") != 0).sum(),
                            n_flown=(pl.col("status") == 0).sum(),
                            k_flown=((pl.col("status") == 0) & pl.col("m")).sum())
          .sort(by).collect())
    return add_wilson(df)


def needed_table(c: pl.DataFrame, keys: list[str], targets=(0.10, 0.05, 0.01), x="layover_bin") -> pl.DataFrame:
    rows = []
    for key, g in c.group_by(keys, maintain_order=True):
        g = g.filter(pl.col("n") >= MIN_CELL)
        r = dict(zip(keys, key))
        r["pairs"] = int(g["n"].sum())
        for t in targets:
            r[f"L{int(round(100 * (1 - t)))}"] = layover_needed(g, t, x=x)
        gf = g.filter(pl.col("n_flown") >= MIN_CELL).with_columns(rate=pl.col("k_flown") / pl.col("n_flown"))
        r["L95_if_both_fly"] = layover_needed(gf, 0.05, x=x)
        r["cancel_floor"] = float(g["k_cancel"].sum() / g["n"].sum()) if g.height else None
        rows.append(r)
    return pl.DataFrame(rows, infer_schema_length=None)


# ---------------------------------------------------------------- lookups and naive
LEVELS = [["hub", "mkt", "arr_hour", "month", "bucket"],
          ["hub", "mkt", "arr_hour", "bucket"],
          ["hub", "mkt", "bucket"],
          ["hub", "bucket"],
          ["bucket"]]


def naive_expr(w=W_DEFAULT, d=D_DEFAULT):
    """The shortcut: read only the inbound flight. Missed if it was cancelled or
    diverted, or landed later than layover - W - D past schedule."""
    return pl.col("status").is_in([1, 2]) | (pl.col("arr_delay") > (pl.col("layover") - w - d))


def backoff_predict(train: pl.LazyFrame, test: pl.DataFrame, outcome: pl.Expr) -> np.ndarray:
    """Cell average from the training months, backing off to coarser cells when a
    cell has fewer than MIN_CELL pairs."""
    t = train.with_columns(month=pl.col("date").dt.month(), y=outcome)
    out = test.with_columns(pred=pl.lit(None, dtype=pl.Float64))
    for lv in LEVELS:
        agg = (t.group_by(lv).agg(nn=pl.len(), kk=pl.col("y").sum())
               .filter(pl.col("nn") >= MIN_CELL).with_columns(r=pl.col("kk") / pl.col("nn"))
               .select(*lv, "r").collect())
        out = out.join(agg, on=lv, how="left").with_columns(pred=pl.coalesce("pred", "r")).drop("r")
    return out["pred"].to_numpy()


def sample(p: pl.LazyFrame, n: int, seed: int) -> pl.DataFrame:
    df = p.collect()
    if df.height > n:
        df = df.sample(n, seed=seed)
    return features(df.with_columns(month=pl.col("date").dt.month()))


# ---------------------------------------------------------------- main
def main():
    t0 = time.time()
    TAB.mkdir(exist_ok=True)
    hubs = pl.read_csv(TAB / "hubs.csv")["origin"].to_list()
    S: dict = {"W": W_DEFAULT, "D": D_DEFAULT, "hubs": hubs, "min_cell": MIN_CELL}

    allp = pairs_scan(WINDOW)
    ha = (allp.group_by("hub", "mkt").agg(n=pl.len()).collect()
          .filter(pl.col("n") >= MIN_PAIRS_AIRLINE).sort("hub", "n", descending=[False, True]))
    write(ha, "hub_airlines.csv")
    keep = ha.select("hub", "mkt")
    p = allp.join(keep.lazy(), on=["hub", "mkt"], how="semi").with_columns(month=pl.col("date").dt.month())
    S["hub_airlines"] = ha.height
    S["pairs"] = int(ha["n"].sum())
    log("pairs kept", S["pairs"], "hub-airlines", ha.height, f"{time.time()-t0:.0f}s")

    S["eda"] = eda(hubs)
    log("eda done", f"{time.time()-t0:.0f}s")

    st = p.group_by("status").agg(n=pl.len()).collect()
    S["status_share"] = {int(r["status"]): r["n"] / S["pairs"] for r in st.iter_rows(named=True)}

    # curves at the default W
    c_all = curves(p, [])
    c_hub = curves(p, ["hub"])
    c_ha = curves(p, ["hub", "mkt"])
    write(c_all, "curve_all.csv")
    write(c_hub, "curves_hub.csv")
    write(c_ha, "curves_hub_airline.csv")
    need_hub = needed_table(c_hub, ["hub"])
    need_ha = needed_table(c_ha, ["hub", "mkt"])
    write(need_hub, "layover_needed_hub.csv")
    write(need_ha, "layover_needed_hub_airline.csv")
    # hour-level, 15-minute buckets
    c_hh = (p.with_columns(layover_bin=(pl.col("bucket").cast(pl.Int32) * 15 + 30), m=missed())
            .group_by("hub", "mkt", "arr_hour", "layover_bin")
            .agg(n=pl.len(), k=pl.col("m").sum(), k_cancel=(pl.col("status") != 0).sum(),
                 n_flown=(pl.col("status") == 0).sum(),
                 k_flown=((pl.col("status") == 0) & pl.col("m")).sum())
            .sort("hub", "mkt", "arr_hour", "layover_bin").collect())
    c_hh = add_wilson(c_hh)
    need_hh = needed_table(c_hh, ["hub", "mkt", "arr_hour"])
    write(need_hh, "layover_needed_hour.csv")
    # pooled over airlines, by hub and hour, for the heatmap
    c_hhub = add_wilson(
        p.with_columns(layover_bin=(pl.col("bucket").cast(pl.Int32) * 15 + 30), m=missed())
        .group_by("hub", "arr_hour", "layover_bin")
        .agg(n=pl.len(), k=pl.col("m").sum(), k_cancel=(pl.col("status") != 0).sum(),
             n_flown=(pl.col("status") == 0).sum(), k_flown=((pl.col("status") == 0) & pl.col("m")).sum())
        .sort("hub", "arr_hour", "layover_bin").collect())
    need_hhub = needed_table(c_hhub, ["hub", "arr_hour"])
    write(need_hhub, "layover_needed_hub_hour.csv")
    log("curves done", f"{time.time()-t0:.0f}s")

    def at(c, lay, **kw):
        f = c.filter(pl.col("layover_bin") == lay)
        for k, v in kw.items():
            f = f.filter(pl.col(k) == v)
        return f.row(0, named=True) if f.height else None

    S["all"] = {str(L): at(c_all, L) for L in (30, 45, 60, 90, 120, 175)}
    S["need_all"] = needed_table(c_all.with_columns(g=pl.lit(1)), ["g"]).drop("g").to_dicts()[0]
    S["hub45"] = {h: at(c_hub, 45, hub=h) for h in hubs}
    S["need_hub"] = need_hub.to_dicts()

    # shortcut: naive against paired, per hub, at every 5-minute bin
    sc = (p.with_columns(lbin_expr(), m=missed(), nv=naive_expr(),
                         nv_delay=(pl.col("status") == 0) & (pl.col("arr_delay") > pl.col("layover") - 30),
                         pd_delay=(pl.col("status") == 0) & missed())
          .group_by("hub", "layover_bin")
          .agg(n=pl.len(), paired=pl.col("m").mean(), naive=pl.col("nv").mean(),
               dep_cancel=(pl.col("status") == 3).mean(),
               naive_delay=pl.col("nv_delay").mean(), paired_delay=pl.col("pd_delay").mean())
          .with_columns(gap=pl.col("naive") - pl.col("paired"))
          .sort("hub", "layover_bin").collect())
    write(sc, "shortcut_hub.csv")
    sc_all = (p.with_columns(lbin_expr(), m=missed(), nv=naive_expr(),
                             nv_delay=(pl.col("status") == 0) & (pl.col("arr_delay") > pl.col("layover") - 30),
                             pd_delay=(pl.col("status") == 0) & missed())
              .group_by("layover_bin")
              .agg(n=pl.len(), paired=pl.col("m").mean(), naive=pl.col("nv").mean(),
                   dep_cancel=(pl.col("status") == 3).mean(),
                   naive_delay=pl.col("nv_delay").mean(), paired_delay=pl.col("pd_delay").mean())
              .with_columns(gap=pl.col("naive") - pl.col("paired")).sort("layover_bin").collect())
    write(sc_all, "shortcut_all.csv")
    corr = (p.filter(pl.col("status") == 0)
            .with_columns(pl.col("arr_delay", "dep_delay").cast(pl.Float64).clip(-60, 300))
            .group_by("hub").agg(corr=pl.corr("arr_delay", "dep_delay"),
                                 corr_spearman=pl.corr("arr_delay", "dep_delay", method="spearman"),
                                 n=pl.len())
            .sort("corr").collect())
    corr_all = (p.filter(pl.col("status") == 0)
                .with_columns(pl.col("arr_delay", "dep_delay").cast(pl.Float64).clip(-60, 300))
                .select(pl.corr("arr_delay", "dep_delay"),
                        sp=pl.corr("arr_delay", "dep_delay", method="spearman")).collect().row(0))
    # conditional: when the inbound is 30+ minutes late, how often is the outbound late too
    cond = (p.filter((pl.col("status") == 0) & (pl.col("arr_delay") >= 30))
            .select(dep_late15=(pl.col("dep_delay") > 15).mean(),
                    dep_late30=(pl.col("dep_delay") >= 30).mean()).collect().row(0, named=True))
    base = (p.filter(pl.col("status") == 0)
            .select(dep_late15=(pl.col("dep_delay") > 15).mean(),
                    dep_late30=(pl.col("dep_delay") >= 30).mean()).collect().row(0, named=True))
    write(corr, "delay_correlation_hub.csv")
    S["shortcut"] = dict(
        all=sc_all.to_dicts(), corr_all=corr_all[0], corr_all_spearman=corr_all[1],
        corr_min=corr.row(0, named=True), corr_max=corr.row(-1, named=True),
        dep_late_given_arr_late30=cond, dep_late_base=base,
        hub45=sc.filter(pl.col("layover_bin") == 45).sort("gap").to_dicts(),
    )
    log("shortcut done", f"{time.time()-t0:.0f}s")

    # 2019 comparison
    if any((CACHE / "pairs" / f"{y}_{m:02d}.parquet").exists() for y, m in COMPARE):
        p19 = pairs_scan(COMPARE).join(keep.lazy(), on=["hub", "mkt"], how="semi")
        c19 = curves(p19, ["hub"])
        c19all = curves(p19, [])
        cmp = (c_hub.select("hub", "layover_bin", n="n", rate="rate")
               .join(c19.select("hub", "layover_bin", n_2019="n", rate_2019="rate"), on=["hub", "layover_bin"]))
        write(cmp, "compare_2019.csv")
        S["y2019"] = dict(all={str(L): at(c19all, L) for L in (30, 45, 60, 90)},
                          need_all=needed_table(c19all.with_columns(g=pl.lit(1)), ["g"]).drop("g").to_dicts()[0],
                          pairs=int(c19all["n"].sum()),
                          need_hub=needed_table(c19, ["hub"]).to_dicts())
    log("2019 done", f"{time.time()-t0:.0f}s")

    # ------------------------------------------------ evaluation: train 30 months, test 6
    train = pairs_scan(TRAIN).join(keep.lazy(), on=["hub", "mkt"], how="semi").with_columns(month=pl.col("date").dt.month())
    test_lf = pairs_scan(TEST).join(keep.lazy(), on=["hub", "mkt"], how="semi")
    te = sample(test_lf, N_TEST, SEED + 1)
    y = te.select(missed()).to_series().to_numpy().astype(float)
    preds = {"naive": backoff_predict(train, te, naive_expr()),
             "lookup": backoff_predict(train, te, missed())}
    log("lookups predicted", f"{time.time()-t0:.0f}s")
    tr = sample(train, N_TRAIN, SEED)
    ytr = tr.select(missed()).to_series().to_numpy().astype(float)
    mdl = MissModel().fit(tr, ytr)
    preds["model"] = mdl.predict(te)
    log("model fitted", f"{time.time()-t0:.0f}s")
    cal_rows, ev = [], {}
    for name, pr in preds.items():
        t, s = calibration(pr, y)
        cal_rows.append(t.with_columns(estimator=pl.lit(name)))
        ev[name] = s
        log(name, json.dumps({k: round(v, 5) for k, v in s.items()}))
    write(pl.concat(cal_rows).select("estimator", "decile", "n", "predicted", "observed"), "calibration.csv")
    best = min(ev, key=lambda k: (round(ev[k]["ece"], 4), ev[k]["brier"]))
    S["evaluation"] = dict(train=f"{TRAIN[0][0]}-{TRAIN[0][1]:02d} to {TRAIN[-1][0]}-{TRAIN[-1][1]:02d}",
                           test=f"{TEST[0][0]}-{TEST[0][1]:02d} to {TEST[-1][0]}-{TEST[-1][1]:02d}",
                           n_train_model=tr.height, n_test=te.height, scores=ev, best=best)
    # was the test period unusual? same calendar months in each year of the window
    same = (pairs_scan([(y, m) for y in (2024, 2025, 2026) for m in range(3, 9)])
            .join(keep.lazy(), on=["hub", "mkt"], how="semi")
            .group_by(year=pl.col("date").dt.year())
            .agg(miss=missed().mean(), cancel=(pl.col("status") != 0).mean()).sort("year").collect())
    S["evaluation"]["mar_aug_by_year"] = same.to_dicts()
    # calibration by hub for the shipped estimator
    byhub = (te.select("hub").with_columns(pred=pl.Series(preds[best]), y=pl.Series(y))
             .group_by("hub").agg(n=pl.len(), predicted=pl.col("pred").mean(), observed=pl.col("y").mean())
             .sort("hub"))
    write(byhub, "calibration_by_hub.csv")

    # drivers: refit without each factor on a smaller sample, compare test log loss
    small = tr.sample(min(600_000, tr.height), seed=SEED + 2)
    ys = small.select(missed()).to_series().to_numpy().astype(float)
    tes = te.sample(min(600_000, te.height), seed=SEED + 3)
    yts = tes.select(missed()).to_series().to_numpy().astype(float)
    groups = {"layover": ["lay", "lay_ha"], "hub and airline": ["ha", "lay_ha", "mo_hub", "hr_hub"],
              "arrival hour": ["hr", "hr_hub"], "month": ["mo", "mo_hub"], "weekday": ["dw"]}
    import analysis.model as am
    full_terms = list(am.TERMS)
    full = MissModel().fit(small, ys)
    _, sfull = calibration(full.predict(tes), yts)
    drv = []
    for g, drop in groups.items():
        am.TERMS[:] = [t for t in full_terms if t[0] not in drop]
        m2 = MissModel().fit(small, ys)
        _, s2 = calibration(m2.predict(tes), yts)
        drv.append(dict(factor=g, logloss_without=s2["logloss"], logloss_full=sfull["logloss"],
                        increase=s2["logloss"] - sfull["logloss"],
                        brier_increase=s2["brier"] - sfull["brier"]))
    am.TERMS[:] = full_terms
    drv = pl.DataFrame(drv).sort("increase", descending=True)
    write(drv, "drivers.csv")
    S["drivers"] = drv.to_dicts()
    log("drivers done", f"{time.time()-t0:.0f}s")

    (RES / "summary.json").write_text(json.dumps(S, indent=1, default=str))
    (RES / "analyze_log.txt").write_text("\n".join(LOG) + "\n")
    log("done", f"{time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
