"""Build constructed connections (arrival, departure pairs) at a hub.

The BTS file holds flights, not itineraries. A candidate connection is an arrival
and a departure at the same hub, sold by the same marketing airline, with a
scheduled gap of 30 to 180 minutes, the departure going somewhere other than the
arrival's origin, and not flown by the same aircraft. See docs/decisions.md.

All clock times in BTS are local. Both legs of a connection are timed at the hub,
so the gap is computed in the hub's local time and no time-zone table is needed.
Scheduled times become "minutes since 1970-01-01, hub local"; actual times are the
scheduled time plus the reported delay in minutes, which BTS computes across
midnight already.
"""
from __future__ import annotations

import numpy as np
import polars as pl

MIN_GAP = 30
MAX_GAP = 180
BUCKET = 15
W_DEFAULT = 20   # gate to gate, minutes
D_DEFAULT = 10   # door closes this long before pushback

# status codes for a pair
FLOWN, ARR_CANCELLED, ARR_DIVERTED, DEP_CANCELLED = 0, 1, 2, 3


def hhmm_to_min(col: str) -> pl.Expr:
    """2400 and 0000 both mean midnight; 2400 is kept as 1440 so it sorts last."""
    c = pl.col(col).cast(pl.Int32)
    return (c // 100) * 60 + c % 100


def add_times(df: pl.DataFrame) -> pl.DataFrame:
    """Add scheduled and actual minute stamps (local time of the airport concerned).

    sched_dep: on FlightDate, at the origin.
    sched_arr: at the destination, on FlightDate or the day after (or before, for a
    westbound date-line hop). The day offset is the one that makes the arrival land
    nearest to departure plus scheduled block time; time-zone gaps inside the US are
    at most six hours, well under the twelve hours that would make this ambiguous.
    """
    day = pl.col("date").cast(pl.Int32) * 1440
    dep_m = hhmm_to_min("crs_dep")
    arr_m = hhmm_to_min("crs_arr")
    elapsed = pl.col("crs_elapsed").cast(pl.Int32).fill_null(0)
    k = ((dep_m + elapsed - arr_m) / 1440).round().cast(pl.Int32)
    return df.with_columns(
        sched_dep=day + dep_m,
        sched_arr=day + arr_m + k * 1440,
    ).with_columns(
        act_dep=pl.col("sched_dep") + pl.col("dep_delay").cast(pl.Int32),
        act_arr=pl.col("sched_arr") + pl.col("arr_delay").cast(pl.Int32),
    )


def build_pairs(arrs: pl.DataFrame, deps: pl.DataFrame, seed: int,
                sample: bool = True) -> tuple[pl.DataFrame, dict]:
    """Pair arrivals with departures at one hub.

    arrs: flights whose dest is the hub, deps: flights whose origin is the hub, both
    already passed through add_times. Returns the sampled pairs and a dict of counts
    (candidates before the same-tail drop, same-tail pairs, kept before sampling).
    """
    a = arrs.select(
        "mkt", "tail", "origin", "sched_arr", "act_arr", "cancelled", "diverted",
        "arr_delay", op_in="op",
    ).with_row_index("aid").with_columns(
        h0=(pl.col("sched_arr") + MIN_GAP) // 60,
        nh=(pl.col("sched_arr") + MAX_GAP) // 60 - (pl.col("sched_arr") + MIN_GAP) // 60 + 1,
    )
    d = deps.select(
        "mkt", "dest", "sched_dep", "act_dep", "dep_delay",
        dep_cancelled="cancelled", dep_tail="tail", op_out="op",
    ).with_row_index("did").with_columns(hk=pl.col("sched_dep") // 60)

    # Expand each arrival over the clock hours its connection window touches, then
    # equi-join on (airline, hour). This keeps the join small without a range join.
    a = a.with_columns(hk=pl.int_ranges(pl.col("h0"), pl.col("h0") + pl.col("nh"))).explode("hk")
    p = a.join(d, on=["mkt", "hk"], how="inner").with_columns(
        layover=(pl.col("sched_dep") - pl.col("sched_arr")).cast(pl.Int32)
    ).filter(
        pl.col("layover").is_between(MIN_GAP, MAX_GAP) & (pl.col("dest") != pl.col("origin"))
    )
    same_tail = (pl.col("tail") == pl.col("dep_tail")).fill_null(False)
    counts = {"candidates": p.height, "same_tail": int(p.select(same_tail.sum()).item())}
    p = p.filter(~same_tail)
    counts["kept"] = p.height

    p = p.with_columns(bucket=((pl.col("layover") - MIN_GAP) // BUCKET).clip(0, (MAX_GAP - MIN_GAP) // BUCKET - 1))
    if sample and p.height:
        p = p.sort("aid", "did")
        rng = np.random.default_rng(seed)
        p = p.with_columns(r=pl.Series(rng.random(p.height)))
        p = p.sort("aid", "bucket", "r").unique(["aid", "bucket"], keep="first", maintain_order=True).drop("r")
    p = p.with_columns(
        status=pl.when(pl.col("cancelled") == 1).then(ARR_CANCELLED)
        .when(pl.col("diverted") == 1).then(ARR_DIVERTED)
        .when(pl.col("dep_cancelled") == 1).then(DEP_CANCELLED)
        .otherwise(FLOWN).cast(pl.Int8),
        slack=(pl.col("act_dep") - pl.col("act_arr")),
    )
    # A flown pair with a missing actual time cannot be scored; there are very few.
    p = p.filter((pl.col("status") != FLOWN) | pl.col("slack").is_not_null())
    p = p.with_columns(
        arr_hour=((pl.col("sched_arr") % 1440) // 60).cast(pl.Int8),
        date=(pl.col("sched_arr") // 1440).cast(pl.Date),
        slack=pl.when(pl.col("status") == FLOWN).then(pl.col("slack")).cast(pl.Int16),
        arr_delay=pl.col("arr_delay").cast(pl.Int16),
        dep_delay=pl.col("dep_delay").cast(pl.Int16),
        layover=pl.col("layover").cast(pl.Int16),
        bucket=pl.col("bucket").cast(pl.Int8),
        same_op=(pl.col("op_in") == pl.col("op_out")),
    )
    p = p.with_columns(dow=pl.col("date").dt.weekday().cast(pl.Int8))
    return p.select("mkt", "date", "dow", "arr_hour", "layover", "bucket", "status",
                    "slack", "arr_delay", "dep_delay", "op_in", "op_out", "same_op"), counts


def missed(w: int = W_DEFAULT, d: int = D_DEFAULT) -> pl.Expr:
    """A pair is missed if any leg needed was cancelled or diverted, or if actual
    arrival + W is later than actual departure - D, that is slack < W + D."""
    return (pl.col("status") != FLOWN) | (pl.col("slack") < (w + d))
