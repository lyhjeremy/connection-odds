"""Check agent/model.py against modelP in assets/app.js on 2,000 seeded random inputs.

    python scripts/check_model_port.py     # needs playwright and its Chromium

Pulls the modelP function text out of the shipped app.js, runs it in headless Chromium on the
same tool.json, and compares with the Python port. Writes results/model_port_check.json.
"""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import model  # noqa: E402

N = 2000


def main():
    D = model.tool()
    rnd = random.Random(39)
    cases = []
    for _ in range(N):
        hub, air = rnd.choice(D["ha_order"]).split("|")
        cases.append([rnd.choice(D["W_values"]), hub, air, rnd.randrange(24), rnd.randint(1, 12), rnd.randint(30, 180)])
    src = (ROOT / "assets" / "app.js").read_text()
    fn = re.search(r"function modelP\(.*?\n  }\n", src, re.S).group(0)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.set_content("<!DOCTYPE html><title>model port check</title>")
        js = pg.evaluate("""([fnSrc, tool, cases]) => {
            const D = tool, haIdx = {};
            D.ha_order.forEach((k, i) => haIdx[k] = i);
            const modelP = new Function('D', 'haIdx', fnSrc + '; return modelP;')(D, haIdx);
            return cases.map(c => modelP(...c));
        }""", [fn, {k: v for k, v in D.items() if not k.startswith("_")}, cases])
        b.close()
    py = [model.model_p(*c) for c in cases]
    diffs = [abs(a - b) for a, b in zip(py, js)]
    worst = max(diffs)
    out = dict(cases=N, seed=39, identical=sum(d == 0 for d in diffs), max_abs_difference=worst,
               same_at_one_decimal_pct=sum(round(100 * a, 1) == round(100 * b, 1) for a, b in zip(py, js)),
               sample=[dict(inputs=c, python=p, js=j) for c, p, j in list(zip(cases, py, js))[:5]])
    (ROOT / "results" / "model_port_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "sample"}))
    if worst > 1e-12:
        sys.exit(1)


if __name__ == "__main__":
    main()
