"""Run the frozen itineraries through the checker and the bare-model baseline. Resumable.

    python eval/run_eval.py agent       # 30 itineraries: extract (sonnet) + answer (haiku)
    python eval/run_eval.py baseline    # the 20-itinerary baseline subset, sonnet with no tools

Raw records go to eval/runs/agent.jsonl and eval/runs/baseline.jsonl. Scoring is eval/score.py.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import llm, pipeline  # noqa: E402

RUNS = ROOT / "eval" / "runs"
BASELINE_MODEL = "sonnet"
BASELINE_SYSTEM = """You check US flight itineraries for missed-connection risk. The person pastes an itinerary. In at most 4 sentences, give for each connection the airport, the layover in minutes and your estimate of the chance of missing it.

Also fill connections with one entry per connection: airport (three-letter code), layover_min, and miss_probability_pct (your estimate, 0 to 100, or null if you would not give one)."""
BASELINE_SCHEMA = {"type": "object", "additionalProperties": False,
                   "properties": {"answer": {"type": "string"},
                                  "connections": {"type": "array", "items": {
                                      "type": "object", "additionalProperties": False,
                                      "properties": {"airport": {"type": "string"}, "layover_min": {"type": ["number", "null"]},
                                                     "miss_probability_pct": {"type": ["number", "null"]}},
                                      "required": ["airport", "layover_min", "miss_probability_pct"]}}},
                   "required": ["answer", "connections"]}


def main(which):
    RUNS.mkdir(exist_ok=True)
    rows = [json.loads(line) for line in (ROOT / "eval" / "itineraries.jsonl").read_text().splitlines()]
    path = RUNS / f"{which}.jsonl"
    have = {json.loads(l)["id"] for l in path.read_text().splitlines()} if path.exists() else set()
    for q in rows:
        if q["id"] in have or (which == "baseline" and not q["in_baseline"]):
            continue
        t0 = time.perf_counter()
        if which == "agent":
            rec = pipeline.check_itinerary(q["text"])
        else:
            r = llm.call(q["text"], BASELINE_SYSTEM, BASELINE_MODEL, BASELINE_SCHEMA)
            rec = dict(raw=r, **(r.get("structured") or {}))
        rec["id"] = q["id"]
        rec["run_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        print(q["id"], round(time.perf_counter() - t0, 1), "s", rec.get("status", ""), (rec.get("answer") or "")[:110], flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
