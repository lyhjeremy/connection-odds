"""Small statistics helpers shared by the analysis and the tool export."""
from __future__ import annotations

import numpy as np
import polars as pl

Z95 = 1.959964


def wilson(k, n, z: float = Z95):
    """Wilson score interval for k successes in n trials. Works on scalars or arrays."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = k / n
        den = 1 + z * z / n
        mid = (p + z * z / (2 * n)) / den
        half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return mid - half, mid + half


def add_wilson(df: pl.DataFrame, k: str = "k", n: str = "n") -> pl.DataFrame:
    lo, hi = wilson(df[k].to_numpy(), df[n].to_numpy())
    return df.with_columns(rate=pl.col(k) / pl.col(n), lo=pl.Series(lo), hi=pl.Series(hi))


def layover_needed(curve: pl.DataFrame, target: float, x: str = "layover", rate: str = "rate"):
    """Shortest layover at which the miss rate is at or below target and stays there for
    every longer layover in the curve. None if the curve never gets there."""
    c = curve.sort(x)
    xs, rs = c[x].to_list(), c[rate].to_list()
    best = None
    for xv, rv in zip(reversed(xs), reversed(rs)):
        if rv is None or rv > target:
            break
        best = xv
    return best


def calibration(pred: np.ndarray, y: np.ndarray, bins: int = 10) -> tuple[pl.DataFrame, dict]:
    """Decile calibration table, Brier score, expected calibration error (count weighted
    mean of |mean predicted - observed| over deciles of the prediction) and log loss."""
    pred = np.clip(np.asarray(pred, dtype=float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, dtype=float)
    order = np.argsort(pred, kind="stable")
    groups = np.array_split(order, bins)
    rows = []
    for i, g in enumerate(groups):
        rows.append(dict(decile=i + 1, n=len(g), predicted=float(pred[g].mean()), observed=float(y[g].mean())))
    t = pl.DataFrame(rows)
    ece = float((t["n"] * (t["predicted"] - t["observed"]).abs()).sum() / t["n"].sum())
    brier = float(np.mean((pred - y) ** 2))
    ll = float(-np.mean(y * np.log(pred) + (1 - y) * np.log(1 - pred)))
    base = float(np.mean((y.mean() - y) ** 2))
    return t, dict(brier=brier, ece=ece, logloss=ll, brier_climatology=base,
                   brier_skill=1 - brier / base, n=int(len(y)), observed=float(y.mean()),
                   predicted=float(pred.mean()))
