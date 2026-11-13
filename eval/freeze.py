"""Write eval/itineraries.jsonl from eval/gold_source.py, after checking the hand-written
expectations are internally consistent (layover = departure minus arrival, hour and month match
the arrival, coverage matches the model). Run once, commit, then run the eval.

    python eval/freeze.py
"""
import json
import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from agent import model  # noqa: E402
from gold_source import I  # noqa: E402

BASELINE_N, BASELINE_SEED = 20, 39
F = "%Y-%m-%d %H:%M"


def main():
    rows, bad = [], []
    for iid, text, legs, conns in I:
        L = [dict(airline=a, flight=f, origin=o, destination=d, depart=dep, arrive=arr) for a, f, o, d, dep, arr in (legs or [])]
        C = []
        for hub, ai, ao, hr, mo, lay, cov in conns:
            C.append(dict(hub=hub, airline_in=ai, airline_out=ao, arrival_hour=hr, month=mo, layover_min=lay, covered=cov))
        # consistency: every connection matches some consecutive pair of legs
        pairs = list(zip(L, L[1:]))
        found = []
        for x, y in pairs:
            gap = (datetime.strptime(y["depart"], F) - datetime.strptime(x["arrive"], F)).total_seconds() / 60
            if gap <= 24 * 60:
                t = datetime.strptime(x["arrive"], F)
                cov = x["destination"] == y["origin"] and x["airline"] == y["airline"] and \
                    model.coverage(x["destination"], x["airline"], gap, 20) is None
                found.append(dict(hub=x["destination"], airline_in=x["airline"], airline_out=y["airline"],
                                  arrival_hour=t.hour, month=t.month, layover_min=int(gap), covered=cov))
        if found != C:
            bad.append((iid, found, C))
        rows.append(dict(id=iid, text=text, expected=dict(is_itinerary=legs is not None, legs=L, connections=C)))
    if bad:
        for b in bad:
            print("MISMATCH", b)
        sys.exit(1)
    eligible = [r["id"] for r in rows if r["expected"]["connections"]]
    base = sorted(random.Random(BASELINE_SEED).sample(eligible, BASELINE_N))
    for r in rows:
        r["in_baseline"] = r["id"] in base
    (ROOT / "eval" / "itineraries.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    n_conn = sum(len(r["expected"]["connections"]) for r in rows)
    n_cov = sum(c["covered"] for r in rows for c in r["expected"]["connections"])
    print(f"{len(rows)} itineraries, {sum(len(r['expected']['legs']) for r in rows)} legs, {n_conn} connections, {n_cov} covered; baseline {base}")


if __name__ == "__main__":
    main()
