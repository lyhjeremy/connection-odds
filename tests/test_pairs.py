import datetime as dt
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.pairs import (ARR_CANCELLED, ARR_DIVERTED, DEP_CANCELLED, FLOWN,  # noqa: E402
                            add_times, build_pairs, missed)

D0 = dt.date(2026, 8, 10)


def fl(origin, dest, crs_dep, crs_arr, elapsed, dep_delay=0, arr_delay=0, tail="N1",
       mkt="DL", op="DL", date=D0, cancelled=0, diverted=0):
    return dict(date=date, mkt=mkt, op=op, tail=tail, origin=origin, dest=dest,
                crs_dep=crs_dep, crs_arr=crs_arr, crs_elapsed=elapsed,
                dep_delay=None if cancelled else dep_delay,
                arr_delay=None if (cancelled or diverted) else arr_delay,
                cancelled=cancelled, diverted=diverted)


SCHEMA = dict(date=pl.Date, mkt=pl.Utf8, op=pl.Utf8, tail=pl.Utf8, origin=pl.Utf8, dest=pl.Utf8,
              crs_dep=pl.Int16, crs_arr=pl.Int16, crs_elapsed=pl.Int16, dep_delay=pl.Int16,
              arr_delay=pl.Int16, cancelled=pl.Int8, diverted=pl.Int8)


def frame(rows):
    return add_times(pl.DataFrame(rows, schema=SCHEMA))


def pairs(arr_rows, dep_rows, sample=False):
    return build_pairs(frame(arr_rows), frame(dep_rows), seed=1, sample=sample)


def test_basic_pair_and_layover():
    p, c = pairs([fl("BOS", "ATL", 1000, 1300, 180, tail="A")],
                 [fl("ATL", "LAX", 1400, 1530, 270, tail="B")])
    assert p.height == 1
    assert p["layover"][0] == 60
    assert p["slack"][0] == 60
    assert p["status"][0] == FLOWN
    assert c == {"candidates": 1, "same_tail": 0, "kept": 1}


def test_same_tail_dropped():
    p, c = pairs([fl("BOS", "ATL", 1000, 1300, 180, tail="N100")],
                 [fl("ATL", "LAX", 1400, 1530, 270, tail="N100"),
                  fl("ATL", "SEA", 1410, 1600, 290, tail="N200")])
    assert p.height == 1
    assert c["same_tail"] == 1 and c["candidates"] == 2
    assert p["op_out"][0] == "DL"


def test_missing_tail_is_not_same_tail():
    p, c = pairs([fl("BOS", "ATL", 1000, 1300, 180, tail=None)],
                 [fl("ATL", "LAX", 1400, 1530, 270, tail=None)])
    assert p.height == 1 and c["same_tail"] == 0


def test_window_bounds_and_return_to_origin():
    p, _ = pairs([fl("BOS", "ATL", 1000, 1300, 180, tail="A")],
                 [fl("ATL", "LAX", 1329, 1500, 270, tail="B"),   # 29 min: too short
                  fl("ATL", "LAX", 1330, 1500, 270, tail="C"),   # 30: in
                  fl("ATL", "LAX", 1600, 1800, 270, tail="D"),   # 180: in
                  fl("ATL", "LAX", 1601, 1800, 270, tail="E"),   # 181: out
                  fl("ATL", "BOS", 1400, 1630, 150, tail="F")])  # back to origin: out
    assert sorted(p["layover"].to_list()) == [30, 180]


def test_other_airline_not_paired():
    p, _ = pairs([fl("BOS", "ATL", 1000, 1300, 180, tail="A")],
                 [fl("ATL", "LAX", 1400, 1530, 270, tail="B", mkt="UA", op="UA")])
    assert p.height == 0


def test_regional_operator_paired_under_marketing_carrier():
    p, _ = pairs([fl("CHA", "ATL", 1000, 1100, 60, tail="A", op="9E")],
                 [fl("ATL", "LAX", 1200, 1330, 270, tail="B", op="DL")])
    assert p.height == 1
    assert p["op_in"][0] == "9E" and not p["same_op"][0]


def test_cancellations_and_diversions():
    arr = [fl("BOS", "ATL", 1000, 1300, 180, tail="A", cancelled=1),
           fl("MIA", "ATL", 1000, 1200, 120, tail="B", diverted=1),
           fl("ORD", "ATL", 1000, 1300, 120, tail="C")]
    dep = [fl("ATL", "LAX", 1400, 1530, 270, tail="D", cancelled=1),
           fl("ATL", "SEA", 1415, 1630, 300, tail="E")]
    p, _ = pairs(arr, dep)
    st = {(r["slack"], r["status"]) for r in p.iter_rows(named=True)}
    by_status = p.group_by("status").len().sort("status")
    counts = dict(zip(by_status["status"], by_status["len"]))
    # BOS arrival cancelled: two pairs, both status 1
    assert counts[ARR_CANCELLED] == 2
    # MIA diverted: pairs with both departures (gaps 120 and 135)
    assert counts[ARR_DIVERTED] == 2
    # ORD on time: LAX departure cancelled, SEA flown
    assert counts[DEP_CANCELLED] == 1 and counts[FLOWN] == 1
    assert (75, FLOWN) in st
    m = p.with_columns(m=missed()).filter(pl.col("status") != FLOWN)["m"]
    assert m.all()


def test_overnight_arrival_crosses_midnight():
    # Departs 21:30 Pacific, block 300 min, lands 05:30 Eastern next day.
    arr = [fl("LAX", "ATL", 2130, 530, 300, tail="A", arr_delay=25)]
    dep = [fl("ATL", "BOS", 630, 845, 135, tail="B", date=D0 + dt.timedelta(days=1), dep_delay=-2)]
    p, _ = pairs(arr, dep)
    assert p.height == 1
    assert p["layover"][0] == 60
    assert p["slack"][0] == 60 - 25 - 2
    assert p["date"][0] == D0 + dt.timedelta(days=1)


def test_connection_across_midnight():
    # Arrives 23:40, leaves 00:25 the next day: a 45-minute connection on two dates.
    arr = [fl("MCO", "ATL", 2210, 2340, 90, tail="A", arr_delay=10)]
    dep = [fl("ATL", "SEA", 25, 300, 335, tail="B", date=D0 + dt.timedelta(days=1), dep_delay=0)]
    p, _ = pairs(arr, dep)
    assert p.height == 1
    assert p["layover"][0] == 45
    assert p["slack"][0] == 35
    assert p["arr_hour"][0] == 23
    assert not p.with_columns(m=missed())["m"][0]  # slack 35 >= W + D = 30


def test_missed_rule():
    df = pl.DataFrame({"status": [0, 0, 0, 3], "slack": [29, 30, 45, None]},
                      schema={"status": pl.Int8, "slack": pl.Int16})
    assert df.with_columns(m=missed(20, 10))["m"].to_list() == [True, False, False, True]
    assert df.with_columns(m=missed(5, 10))["m"].to_list() == [False, False, False, True]


def test_delay_can_push_departure_past_midnight():
    arr = [fl("MCO", "ATL", 2000, 2130, 90, tail="A", arr_delay=0)]
    dep = [fl("ATL", "SEA", 2230, 2359, 300, tail="B", dep_delay=95)]  # leaves 00:05
    p, _ = pairs(arr, dep)
    assert p["slack"][0] == 60 + 95


def test_sampling_one_per_bucket_and_reproducible():
    arr = [fl("BOS", "ATL", 1000, 1300, 180, tail="A")]
    dep = [fl("ATL", "LAX", 1330 + i, 1600, 270, tail=f"T{i}") for i in range(0, 15, 3)] + \
          [fl("ATL", "LAX", 1400 + i, 1600, 270, tail=f"U{i}") for i in range(0, 15, 3)]
    p1, c = build_pairs(frame(arr), frame(dep), seed=7)
    p2, _ = build_pairs(frame(arr), frame(dep), seed=7)
    assert c["kept"] == 10
    assert p1.height == 2 and sorted(p1["bucket"].to_list()) == [0, 2]
    assert p1.equals(p2)
