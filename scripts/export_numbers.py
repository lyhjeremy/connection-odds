"""Write every number the site, write-up and README quote into site/numbers.json.

Copy never types a result by hand; templates use {{name}} and build_site.py fills them.
"""
import json
import pathlib

import polars as pl

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES, TAB = ROOT / "results", ROOT / "tables"
NAMES = {"lookup": "the cell-average lookup", "model": "the logistic model", "naive": "the inbound-only shortcut"}
FACTOR = {"layover": "the layover itself", "hub and airline": "the hub and airline",
          "arrival hour": "the hour of arrival", "month": "the month", "weekday": "the day of the week"}


def pct(x, d=0):
    return f"{100 * x:.{d}f}"


def pts(x, d=1):
    return f"{100 * x:.{d}f}"


def mins(v):
    return "over 180" if v is None else f"{int(v)}"


def tmins(v):
    return "&gt;180" if v is None else f"{int(v)}"


def fmt_date(s):
    import datetime as dt
    d = dt.date.fromisoformat(s)
    return f"{d.day} {d.strftime('%B %Y')}"


def build():
    s = json.loads((RES / "summary.json").read_text())
    hubs = pl.read_csv(TAB / "hubs.csv")
    names = {h["code"]: h["name"] for h in json.loads((ROOT / "assets/tool.json").read_text())["hubs"]}
    need_hub = {r["hub"]: r for r in s["need_hub"]}
    hub45 = {h: r for h, r in s["hub45"].items() if r}
    n = {}
    top = hubs[0, "origin"]
    n["topHub"], n["topHubName"] = top, names[top]
    n["topHub45"] = pct(hub45[top]["rate"])
    n["topHub45lo"], n["topHub45hi"] = pct(hub45[top]["lo"], 1), pct(hub45[top]["hi"], 1)
    n["topHub95"] = mins(need_hub[top]["L95"])
    n["topHub90"] = mins(need_hub[top]["L90"])
    n["topHub95flown"] = mins(need_hub[top]["L95_if_both_fly"])
    n["topHubFloor"] = pct(need_hub[top]["cancel_floor"], 1)
    rates = sorted(((r["rate"], h) for h, r in hub45.items()))
    n["best45"], n["best45hub"], n["best45name"] = pct(rates[0][0]), rates[0][1], names[rates[0][1]]
    n["worst45"], n["worst45hub"], n["worst45name"] = pct(rates[-1][0]), rates[-1][1], names[rates[-1][1]]
    a = s["all"]
    for L in ("30", "45", "60", "90", "120"):
        n[f"all{L}"] = pct(a[L]["rate"])
    n["all175"] = pct(a["175"]["rate"], 1)
    na = s["need_all"]
    n["allL90"], n["allL95"], n["allL99"] = mins(na["L90"]), mins(na["L95"]), mins(na["L99"])
    n["allL95flown"] = mins(na["L95_if_both_fly"])
    n["all45OneIn"] = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}.get(round(1 / a["45"]["rate"]), str(round(1 / a["45"]["rate"])))
    n["allL99Sentence"] = ("no layover up to 180 minutes reached 99%" if na["L99"] is None
                           else f"99% needed {na['L99']} minutes")
    n["minCell"] = s["min_cell"]
    n["minGap"] = 30
    n["allFloor"] = pct(na["cancel_floor"], 1)
    reach95 = [h for h in need_hub if need_hub[h]["L95"] is not None]
    n["hubsReach95"] = len(reach95)
    n["hubsTotal"] = len(need_hub)
    flown = sorted((need_hub[h]["L95_if_both_fly"], h) for h in need_hub if need_hub[h]["L95_if_both_fly"] is not None)
    n["flown95min"], n["flown95minHub"] = flown[0][0], flown[0][1]
    n["flown95max"], n["flown95maxHub"] = flown[-1][0], flown[-1][1]
    floors = sorted((need_hub[h]["cancel_floor"], h) for h in need_hub)
    n["floorMin"], n["floorMinHub"] = pct(floors[0][0], 1), floors[0][1]
    n["floorMax"], n["floorMaxHub"] = pct(floors[-1][0], 1), floors[-1][1]

    # shortcut
    sc = {r["layover_bin"]: r for r in s["shortcut"]["all"]}
    r45 = sc[45]
    n["sc45paired"], n["sc45naive"] = pct(r45["paired"], 1), pct(r45["naive"], 1)
    n["sc45gap"] = pts(r45["naive"] - r45["paired"])
    n["sc45delayGap"] = pts(r45["naive_delay"] - r45["paired_delay"])
    n["sc45depCancel"] = pts(r45["dep_cancel"])
    n["sc45naiveDelay"], n["sc45pairedDelay"] = pct(r45["naive_delay"], 1), pct(r45["paired_delay"], 1)
    cross = [b for b in sorted(sc) if sc[b]["naive"] - sc[b]["paired"] < 0]
    n["scCross"] = cross[0] if cross else "none"
    r120 = sc[120]
    n["sc120gap"] = pts(r120["paired"] - r120["naive"])
    n["sc120paired"], n["sc120naive"] = pct(r120["paired"], 1), pct(r120["naive"], 1)
    n["corrAll"] = f"{s['shortcut']['corr_all']:.2f}"
    n["corrMin"], n["corrMinHub"] = f"{s['shortcut']['corr_min']['corr']:.2f}", s["shortcut"]["corr_min"]["hub"]
    n["corrMax"], n["corrMaxHub"] = f"{s['shortcut']['corr_max']['corr']:.2f}", s["shortcut"]["corr_max"]["hub"]
    n["depLateGiven"] = pct(s["shortcut"]["dep_late_given_arr_late30"]["dep_late15"])
    n["depLateBase"] = pct(s["shortcut"]["dep_late_base"]["dep_late15"])
    h45 = s["shortcut"]["hub45"]
    n["scHubGapMax"], n["scHubGapMaxHub"] = pts(h45[-1]["gap"]), h45[-1]["hub"]
    n["scHubGapMin"], n["scHubGapMinHub"] = pts(h45[0]["gap"]), h45[0]["hub"]

    # evaluation
    ev = s["evaluation"]
    sc_ = ev["scores"]
    for k in ("naive", "lookup", "model"):
        n[f"{k}Brier"] = f"{sc_[k]['brier']:.4f}"
        n[f"{k}Ece"] = pts(sc_[k]["ece"], 2)
        n[f"{k}Pred"] = pct(sc_[k]["predicted"], 1)
        n[f"{k}Skill"] = pct(sc_[k]["brier_skill"], 1)
        n[f"{k}LogLoss"] = f"{sc_[k]['logloss']:.4f}"
    n["evalObserved"] = pct(sc_["model"]["observed"], 1)
    n["evalN"] = f"{ev['n_test']:,}"
    n["evalTrainN"] = f"{ev['n_train_model']:,}"
    n["shipped"] = NAMES[ev["best"]]
    n["shippedKey"] = ev["best"]
    my = {r["year"]: r for r in ev["mar_aug_by_year"]}
    n["marAug2024"], n["marAug2025"], n["marAug2026"] = (pct(my[y]["miss"], 1) for y in (2024, 2025, 2026))
    n["marAugCancel2026"] = pct(my[2026]["cancel"], 1)
    n["marAugCancelPrior"] = pct((my[2024]["cancel"] + my[2025]["cancel"]) / 2, 1)
    cal = pl.read_csv(TAB / "calibration.csv").filter(pl.col("decile") == 10)
    top = {r["estimator"]: r for r in cal.iter_rows(named=True)}
    n["naiveTopPred"], n["naiveTopObs"] = pct(top["naive"]["predicted"]), pct(top["naive"]["observed"])
    drv = s["drivers"]
    n["driver1"], n["driver2"], n["driver3"] = (FACTOR[d["factor"]] for d in drv[:3])
    n["driverLast"] = FACTOR[drv[-1]["factor"]]
    n["Driver1"] = n["driver1"][0].upper() + n["driver1"][1:]
    last = drv[-1]
    n["driverLastSentence"] = (
        f"Dropping {FACTOR[last['factor']]} made the test score slightly better, so it adds nothing out of sample."
        if last["increase"] < 0 else
        f"{FACTOR[last['factor']][0].upper() + FACTOR[last['factor']][1:]} added the least.")
    small = [FACTOR[d["factor"]] for d in drv if abs(d["increase"]) < 0.001]
    n["driverSmall"] = " and ".join(small) if small else "none"
    n["driver1inc"] = f"{drv[0]['increase']:.4f}"

    # data and pairs
    e = s["eda"]
    n["flights"] = f"{e['flights_window']:,}"
    n["flightsM"] = f"{e['flights_window'] / 1e6:.1f}"
    n["firstDate"], n["lastDate"] = fmt_date(e["first_date"]), fmt_date(e["last_date"])
    n["candidatesB"] = f"{e['candidates_window'] / 1e9:.2f}"
    n["candidatesM"] = f"{e['candidates_window'] / 1e6:,.0f}"
    n["pairsM"] = f"{s['pairs'] / 1e6:.1f}"
    n["pairs"] = f"{s['pairs']:,}"
    n["hubAirlines"] = s["hub_airlines"]
    n["sameTail"] = pct(e["same_tail_share_all"], 1)
    n["sameTailMaxHub"], n["sameTailMax"] = e["same_tail_max_hub"], pct(e["same_tail_max"], 1)
    hr = e["delay_by_hour_max"]
    n["hourWorst"], n["hourWorstLate"] = hr["hour"], pct(hr["dep_late15"])
    h = int(hr["hour"])
    n["hourWorstLabel"] = f"{(h - 1) % 12 + 1} {'am' if h < 12 else 'pm'}"
    n["hourFirst"], n["hourFirstLate"] = e["delay_by_hour_first"]["hour"], pct(e["delay_by_hour_first"]["dep_late15"])
    wm = e["worst_month"]
    import datetime as dt
    n["worstMonth"] = dt.date.fromisoformat(wm["ym"] + "-01").strftime("%B %Y")
    n["worstMonthCancel"] = pct(wm["cancel_rate"], 1)
    st = s["status_share"]
    n["shareArrCancel"] = pct(st.get("1", 0) + st.get("2", 0), 1)
    n["shareDepCancel"] = pct(st.get("3", 0), 1)

    # 2019
    if "y2019" in s:
        y = s["y2019"]
        n["y2019_45"], n["y2019_60"] = pct(y["all"]["45"]["rate"]), pct(y["all"]["60"]["rate"])
        n["y2019L95"] = mins(y["need_all"]["L95"])
        n["y2019L95Sentence"] = ("so 95% was not reached within 180 minutes" if y["need_all"]["L95"] is None
                                 else f"and 95% took {y['need_all']['L95']} minutes")
        n["y2019L95flown"] = mins(y["need_all"]["L95_if_both_fly"])
        n["y2019Floor"] = pct(y["need_all"]["cancel_floor"], 1)
        n["y2019pairsM"] = f"{y['pairs'] / 1e6:.1f}"
    n["toolKB"] = f"{s['tool_json_bytes'] / 1024:,.0f}"
    n["toolGzKB"] = f"{s['tool_json_gzip_bytes'] / 1024:,.0f}"
    n["toolCells"] = f"{s['tool_cells']:,}"
    n["toolCellsShare"] = pct(s["tool_cells_pairs_share"])
    # hub table, generated
    corr = {r["hub"]: r["corr"] for r in pl.read_csv(TAB / "delay_correlation_hub.csv").iter_rows(named=True)}
    gap = {r["hub"]: r["gap"] for r in s["shortcut"]["hub45"]}
    hs = {r["hub"]: r for r in pl.read_csv(TAB / "hub_summary.csv").iter_rows(named=True)}
    rows = []
    for h in hubs["origin"]:
        nh = need_hub[h]
        rows.append(
            f'<tr><td>{h}</td><td>{names[h]}</td><td class="num">{nh["pairs"] / 1e6:.1f}</td>'
            f'<td class="num">{pct(hub45[h]["rate"])}%</td><td class="num">{tmins(nh["L90"])}</td>'
            f'<td class="num">{tmins(nh["L95"])}</td><td class="num">{tmins(nh["L95_if_both_fly"])}</td>'
            f'<td class="num">{pct(nh["cancel_floor"], 1)}%</td><td class="num">{pct(hs[h]["same_tail_share"], 1)}%</td>'
            f'<td class="num">{corr[h]:.2f}</td><td class="num">{100 * gap[h]:+.1f}</td></tr>')
    n["TABLE_HUBS"] = "\n".join(rows)
    hh = pl.read_csv(TAB / "layover_needed_hub_hour.csv").filter(pl.col("pairs") >= 2000)
    for hr in (8, 19):
        v = hh.filter(pl.col("arr_hour") == hr)["L95_if_both_fly"].drop_nulls()
        n[f"flownMedian{hr}"] = int(v.median())
    n["hourMorningLate"] = pct(pl.read_csv(TAB / "delay_by_hour.csv").filter(pl.col("hour") == 8)["dep_late15"][0])
    d19 = {r["hub"]: r for r in s["y2019"]["need_hub"]} if "y2019" in s else {}
    if d19:
        c = pl.read_csv(TAB / "compare_2019.csv").filter(pl.col("layover_bin") == 45)
        diff = c.with_columns(d=pl.col("rate") - pl.col("rate_2019")).sort("d")
        n["y2019worseNowCount"] = int((diff["d"] > 0).sum())
        n["y2019worseHub"], n["y2019worseD"] = diff[-1, "hub"], pts(diff[-1, "d"])
        n["y2019betterHub"], n["y2019betterD"] = diff[0, "hub"], pts(-diff[0, "d"])
    (ROOT / "site").mkdir(exist_ok=True)
    (ROOT / "site/numbers.json").write_text(json.dumps(n, indent=1))
    return n


if __name__ == "__main__":
    for k, v in build().items():
        print(f"{k:>18}  {v}")
