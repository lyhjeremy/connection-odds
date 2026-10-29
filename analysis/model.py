"""Logistic model of a missed connection.

The design is a sum of lookups so the browser can evaluate it without a library:

    logit p = b0 + ha[hub|airline] + lay[bin] + hr[hour] + mo[month] + dw[weekday]
                 + lay_ha[bin, hub|airline] + mo_hub[month, hub] + hr_hub[hour, hub]

lay bins are 5 minutes wide (30-34, 35-39, ... 175-180). Fitted with L2-penalized
logistic regression on a seeded sample of pairs.
"""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy import sparse
from sklearn.linear_model import LogisticRegression

TERMS = [
    ("ha", ["ha"]),
    ("lay", ["lbin"]),
    ("hr", ["arr_hour"]),
    ("mo", ["month"]),
    ("dw", ["dow"]),
    ("lay_ha", ["lbin", "ha"]),
    ("mo_hub", ["month", "hub"]),
    ("hr_hub", ["arr_hour", "hub"]),
]


def features(p: pl.DataFrame | pl.LazyFrame):
    return p.with_columns(
        ha=pl.col("hub").cast(pl.Utf8) + "|" + pl.col("mkt").cast(pl.Utf8),
        lbin=((pl.col("layover").cast(pl.Int32) - 30) // 5).clip(0, 29).cast(pl.Int32),
        month=pl.col("date").dt.month().cast(pl.Int32),
    )


def _keys(df: pl.DataFrame, cols: list[str]) -> pl.Series:
    if len(cols) == 1:
        return df[cols[0]].cast(pl.Utf8)
    return df.select(pl.concat_str([pl.col(c).cast(pl.Utf8) for c in cols], separator=":")).to_series()


class MissModel:
    def __init__(self, C: float = 1.0):
        self.C = C
        self.index: dict[tuple[str, str], int] = {}

    def _matrix(self, df: pl.DataFrame, fit: bool):
        rows, cols = [], []
        n = df.height
        idx = np.arange(n)
        for name, cs in TERMS:
            keys = _keys(df, cs)
            if fit:
                for k in keys.unique(maintain_order=True).to_list():
                    self.index.setdefault((name, k), len(self.index))
            lut = {k: j for (t, k), j in self.index.items() if t == name}
            j = keys.replace_strict(lut, default=None, return_dtype=pl.Int64).to_numpy()
            ok = ~np.isnan(j.astype(float))
            rows.append(idx[ok])
            cols.append(j[ok].astype(np.int64))
        rows, cols = np.concatenate(rows), np.concatenate(cols)
        data = np.ones(len(rows), dtype=np.float32)
        return sparse.csr_matrix((data, (rows, cols)), shape=(n, len(self.index)))

    def fit(self, df: pl.DataFrame, y: np.ndarray):
        X = self._matrix(df, fit=True)
        self.lr = LogisticRegression(C=self.C, max_iter=400, solver="lbfgs")
        self.lr.fit(X, y)
        return self

    def predict(self, df: pl.DataFrame) -> np.ndarray:
        return self.lr.predict_proba(self._matrix(df, fit=False))[:, 1]

    def export(self, digits: int = 3) -> dict:
        """Coefficients grouped by term, keyed the way the browser looks them up."""
        out: dict = {"b0": round(float(self.lr.intercept_[0]), digits)}
        coef = self.lr.coef_[0]
        for (name, k), j in self.index.items():
            v = round(float(coef[j]), digits)
            if v != 0:
                out.setdefault(name, {})[k] = v
        return out
