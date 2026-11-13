"""Score eval/runs/*.jsonl against eval/itineraries.jsonl. No model calls.

    python eval/score.py

Writes eval/results.json, eval/error_analysis.json, eval/traces.json (replayed on the write-up)
and eval/labeling_sheet.csv.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import model, numcheck  # noqa: E402

LEG_F = ["airline", "flight", "origin", "destination", "depart", "arrive"]
CON_F = ["hub", "layover_min", "arrival_hour", "month", "covered"]


def load(name):
    p = ROOT / "eval" / "runs" / f"{name}.jsonl"
    return {r["id"]: r for r in map(json.loads, p.read_text().splitlines())} if p.exists() else {}


def pctl(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def gold_risk(c):
    return model.connection_risk(c["hub"], c["airline_in"], c["arrival_hour"], c["month"], c["layover_min"]) if c["covered"] else None


def main():
    qs = [json.loads(line) for line in (ROOT / "eval" / "itineraries.jsonl").read_text().splitlines()]
    ag, bl = load("agent"), load("baseline")
    rows, errs = [], []
    leg_tot = leg_ok = con_tot = con_ok = 0
    risk_n = risk_same = 0
    risk_diffs = []
    per = {f: [0, 0] for f in LEG_F + CON_F}
    for q in qs:
        e, a = q["expected"], ag[q["id"]]
        row = dict(id=q["id"], is_itin_ok=(a["status"] != "not_itinerary") == e["is_itinerary"],
                   first_status=a["first_status"], status=a["status"],
                   repaired=any(s["step"] == "repair" for s in a["steps"]), leg_errors=[], con_errors=[], risk=[])
        for i, el in enumerate(e["legs"]):
            al = a["legs"][i] if i < len(a["legs"]) else {}
            for f in LEG_F:
                ok = al.get(f) == el[f]
                leg_tot += 1
                leg_ok += ok
                per[f][0] += 1
                per[f][1] += ok
                if not ok:
                    row["leg_errors"].append(dict(leg=i + 1, field=f, expected=el[f], got=al.get(f)))
        if len(a["legs"]) > len(e["legs"]):
            row["leg_errors"].append(dict(leg=None, field="extra legs", expected=len(e["legs"]), got=len(a["legs"])))
        acalls = {c["connection"]: c for c in a["calls"]}
        for i, ec in enumerate(e["connections"]):
            ac = a["connections"][i] if i < len(a["connections"]) else None
            call = acalls.get(i + 1)
            got = None if ac is None else dict(ac, covered=bool(call and call["covered"]))
            for f in CON_F:
                ok = got is not None and got.get(f) == ec[f]
                con_tot += 1
                con_ok += ok
                per[f][0] += 1
                per[f][1] += ok
                if not ok:
                    row["con_errors"].append(dict(connection=i + 1, field=f, expected=ec[f], got=None if got is None else got.get(f)))
            g = gold_risk(ec)
            if g:
                risk_n += 1
                p = call["miss_probability_pct"] if call and call.get("covered") else None
                same = p == g["miss_probability_pct"]
                risk_same += same
                if p is not None:
                    risk_diffs.append(abs(p - g["miss_probability_pct"]))
                row["risk"].append(dict(connection=i + 1, hub=ec["hub"], direct=g["miss_probability_pct"], agent=p, same=same,
                                        stated=p is not None and numcheck.mentions(a["answer"], p)))
        if len(a["connections"]) > len(e["connections"]):
            row["con_errors"].append(dict(connection=None, field="extra connections", expected=len(e["connections"]), got=len(a["connections"])))
        row["e2e_ok"] = (row["is_itin_ok"] and not row["con_errors"] and all(r["same"] and r["stated"] for r in row["risk"]))
        if a.get("check"):
            row["draft_numbers"], row["draft_unsourced"] = a["check"]["n"], a["check"]["unsourced"]
        row["answer_source"] = a["answer_source"]
        rows.append(row)
        if row["leg_errors"] or row["con_errors"] or not row["e2e_ok"] or row.get("draft_unsourced") or row["repaired"]:
            errs.append(dict(id=q["id"], text=q["text"], leg_errors=row["leg_errors"], con_errors=row["con_errors"],
                             risk=row["risk"], status=a["status"], first_status=a["first_status"], errors=a["errors"],
                             first_errors=next((s["errors"] for s in a["steps"] if s["step"] == "resolve"), []),
                             draft=a.get("draft"), draft_unsourced=row.get("draft_unsourced"), answer=a["answer"]))

    drafts = [r for r in rows if "draft_numbers" in r]
    brows = []
    for q in qs:
        if q["id"] not in bl:
            continue
        b, e, a = bl[q["id"]], q["expected"], ag[q["id"]]
        golds = [gold_risk(c) for c in e["connections"]]
        allowed = numcheck.allowed_values(e["legs"], e["connections"], [g for g in golds if g], q["text"])
        clocks = numcheck.clock_values(e["legs"], q["text"])
        c = numcheck.check(b.get("answer") or "", allowed, clocks)
        bc = b.get("connections") or []
        lay_ok, risk_err, risk_given = 0, [], 0
        for i, ec in enumerate(e["connections"]):
            x = bc[i] if i < len(bc) else {}
            lay_ok += x.get("layover_min") == ec["layover_min"]
            g = golds[i]
            if g and x.get("miss_probability_pct") is not None:
                risk_given += 1
                risk_err.append(abs(x["miss_probability_pct"] - g["miss_probability_pct"]))
        brows.append(dict(id=q["id"], connections=len(e["connections"]), layover_ok=lay_ok, risk_given=risk_given,
                          covered=sum(1 for g in golds if g), risk_abs_err=risk_err, numbers=c["n"], unsourced=c["unsourced"],
                          agent_draft_numbers=a["check"]["n"] if a.get("check") else 0,
                          agent_draft_unsourced=len(a["check"]["unsourced"]) if a.get("check") else 0,
                          answer=b.get("answer"), baseline_connections=bc,
                          gold=[dict(hub=ec["hub"], layover_min=ec["layover_min"], model=g and g["miss_probability_pct"])
                                for ec, g in zip(e["connections"], golds)],
                          cost_usd=b["raw"].get("cost_usd"), duration_ms=b["raw"].get("duration_ms")))
    agent_sub = [r for r in rows if r["id"] in bl]

    def step_vals(name, key):
        return [s[key] for r in ag.values() for s in r["steps"] if s["step"] == name and s.get(key) is not None]

    costs = [r["cost_usd"] for r in ag.values()]
    walls = [r["wall_s"] for r in ag.values()]
    berr = [x for b in brows for x in b["risk_abs_err"]]
    res = dict(
        n_itineraries=len(qs), n_legs=sum(len(q["expected"]["legs"]) for q in qs),
        n_connections=sum(len(q["expected"]["connections"]) for q in qs), n_covered=risk_n,
        synthetic="All 30 itineraries were written by the coding agent; none is a real booking.",
        models=dict(extract="sonnet", answer="haiku", baseline="sonnet"),
        model_ids=sorted({s.get("model") for r in ag.values() for s in r["steps"] if s.get("model")}),
        run_dates=sorted({r["run_at"][:10] for r in ag.values()}),
        claude_calls=dict(agent=sum(1 for r in ag.values() for s in r["steps"] if s["step"] in ("extract", "repair", "answer")),
                          baseline=len(bl)),
        is_itinerary_accuracy=sum(r["is_itin_ok"] for r in rows) / len(rows),
        leg_fields=dict(n=leg_tot, correct=leg_ok), connection_fields=dict(n=con_tot, correct=con_ok),
        per_field={f: dict(n=v[0], correct=v[1]) for f, v in per.items()},
        itineraries_parsed_exactly=sum(not r["leg_errors"] and not r["con_errors"] and r["is_itin_ok"] for r in rows),
        validation=dict(first_pass_invalid=sum(r["first_status"] == "invalid" for r in rows), repaired=sum(r["repaired"] for r in rows),
                        still_invalid=sum(r["status"] == "invalid" for r in rows)),
        risk_agreement=dict(n=risk_n, identical=risk_same, max_abs_diff_when_scored=max(risk_diffs) if risk_diffs else None,
                            note="agent's miss probability vs a direct connection_risk call on the expected connection"),
        end_to_end=dict(n=len(rows), correct=sum(r["e2e_ok"] for r in rows)),
        unsourced=dict(agent_draft=dict(numbers=sum(r["draft_numbers"] for r in drafts), unsourced=sum(len(r["draft_unsourced"]) for r in drafts),
                                        answers_with_any=sum(bool(r["draft_unsourced"]) for r in drafts), answers=len(drafts)),
                       fallback_to_template=sum(r["answer_source"] == "template" for r in drafts),
                       baseline=dict(numbers=sum(b["numbers"] for b in brows), unsourced=sum(len(b["unsourced"]) for b in brows),
                                     answers_with_any=sum(bool(b["unsourced"]) for b in brows), answers=len(brows)),
                       agent_draft_same_subset=dict(numbers=sum(b["agent_draft_numbers"] for b in brows),
                                                    unsourced=sum(b["agent_draft_unsourced"] for b in brows))),
        baseline_vs_model=dict(connections=sum(b["connections"] for b in brows), layover_right=sum(b["layover_ok"] for b in brows),
                               covered=sum(b["covered"] for b in brows), risk_given=sum(b["risk_given"] for b in brows),
                               risk_abs_err_median=statistics.median(berr) if berr else None,
                               risk_abs_err_max=max(berr) if berr else None,
                               risk_within_2pts=sum(x <= 2 for x in berr),
                               agent_subset_layover_right=sum(1 for r in agent_sub for c in range(len(next(q for q in qs if q["id"] == r["id"])["expected"]["connections"]))
                                                               if not any(e["connection"] == c + 1 and e["field"] == "layover_min" for e in r["con_errors"])),
                               agent_subset_risk_identical=sum(x["same"] for r in agent_sub for x in r["risk"]),
                               agent_subset_e2e=sum(r["e2e_ok"] for r in agent_sub)),
        cost=dict(agent_per_itinerary_usd_mean=statistics.mean(costs), agent_total_usd=sum(costs),
                  extract_usd_median=statistics.median(step_vals("extract", "cost_usd")),
                  answer_usd_median=statistics.median(step_vals("answer", "cost_usd")),
                  baseline_per_itinerary_usd_mean=statistics.mean(b["cost_usd"] for b in brows),
                  baseline_total_usd=sum(b["cost_usd"] for b in brows)),
        latency=dict(agent_wall_s_median=statistics.median(walls), agent_wall_s_p95=pctl(walls, 0.95),
                     extract_ms_median=statistics.median(step_vals("extract", "duration_ms")),
                     answer_ms_median=statistics.median(step_vals("answer", "duration_ms")),
                     model_ms_median=statistics.median(step_vals("model", "ms")),
                     baseline_ms_median=statistics.median(b["duration_ms"] for b in brows),
                     baseline_ms_p95=pctl([b["duration_ms"] for b in brows], 0.95),
                     machine="Apple M4 for the model and parser; LLM latencies as reported by the Claude CLI"),
        cost_note="API-equivalent cost reported by the Claude CLI (total_cost_usd); the runs used a subscription",
    )
    (ROOT / "eval" / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (ROOT / "eval" / "error_analysis.json").write_text(json.dumps(dict(agent=errs, baseline=brows, rows=rows), indent=1) + "\n")
    traces = []
    for q in qs:
        a, r = ag[q["id"]], next(x for x in rows if x["id"] == q["id"])
        traces.append(dict(id=q["id"], text=q["text"], status=a["status"], first_status=a["first_status"],
                           extraction=a["extraction"], legs=a["legs"], connections=a["connections"], errors=a["errors"],
                           assumptions=a["assumptions"], calls=a["calls"], draft=a["draft"],
                           unsourced=(a["check"] or {}).get("unsourced"), answer=a["answer"], answer_source=a["answer_source"],
                           steps=[dict(step=s["step"], model=s.get("model"), ms=s.get("duration_ms", s.get("ms")),
                                       cost_usd=s.get("cost_usd"), errors=s.get("errors")) for s in a["steps"]],
                           cost_usd=a["cost_usd"], wall_s=a["wall_s"], e2e_ok=r["e2e_ok"],
                           leg_errors=r["leg_errors"], con_errors=r["con_errors"], risk=r["risk"]))
    (ROOT / "eval" / "traces.json").write_text(json.dumps(dict(run_dates=res["run_dates"], traces=traces), indent=1) + "\n")
    with (ROOT / "eval" / "labeling_sheet.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "itinerary_text", "expected_connections", "agent_connections", "agent_answer",
                    "expected_parse_right (y/n)", "answer_faithful_to_model (y/n)", "notes"])
        for q in qs:
            a = ag[q["id"]]
            w.writerow([q["id"], q["text"], json.dumps(q["expected"]["connections"]), json.dumps(a["connections"]), a["answer"], "", "", ""])
    print(json.dumps({k: v for k, v in res.items() if k != "per_field"}, indent=1))


if __name__ == "__main__":
    main()
