"""Python port of the lookup tool's model evaluation (modelP in assets/app.js).

Reads assets/tool.json, the same file the browser loads, and sums the same coefficients:

    logit p = b0 + ha[hub|airline] + lay[bin] + hr[hour] + mo[month] + dw[weekday]
                 + lay_ha[bin, hub|airline] + mo_hub[month, hub] + hr_hub[hour, hub]

then averages the probability over the seven weekdays, as the browser does.
scripts/check_model_port.py runs both on the same inputs and requires identical output.
Standard library only.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_LAYOVER, MAX_LAYOVER = 30, 180


@lru_cache(maxsize=1)
def tool() -> dict:
    d = json.loads((ROOT / "assets" / "tool.json").read_text())
    d["_ha_idx"] = {k: i for i, k in enumerate(d["ha_order"])}
    d["_hubs"] = {h["code"]: h for h in d["hubs"]}
    return d


@lru_cache(maxsize=1)
def airports() -> dict:
    return json.loads((ROOT / "assets" / "airports.json").read_text())["airports"]


def model_p(W: int, hub: str, air: str, hour: int, month: int, layover: float) -> float:
    """Line-for-line with modelP in assets/app.js."""
    D = tool()
    m = D["model"][str(W)]
    i = D["_ha_idx"].get(hub + "|" + air)
    b = max(0, min(29, math.floor((layover - 30) / 5)))
    base = (m["b0"] + (m["ha"][i] if i is not None else 0) + m["lay"][b] + m["hr"][hour] + m["mo"][month - 1]
            + (m["lay_ha"][i][b] if i is not None else 0) + (m["mo_hub"][hub][month - 1] if hub in m["mo_hub"] else 0)
            + (m["hr_hub"][hub][hour] if hub in m["hr_hub"] else 0))
    s = 0.0
    for d in range(7):
        s += 1 / (1 + math.exp(-(base + m["dw"][d])))
    return s / 7


def coverage(hub: str, air: str, layover: float, W: int) -> str | None:
    """None when the model covers this connection, else the reason it does not."""
    D = tool()
    if hub not in D["_hubs"]:
        return f"{hub} is not one of the {len(D['hubs'])} hubs in the model"
    if hub + "|" + air not in D["_ha_idx"]:
        return f"{air} has too few connections at {hub} in the data to be modeled"
    if not (MIN_LAYOVER <= layover <= MAX_LAYOVER):
        return f"a {layover:g}-minute layover is outside the model's {MIN_LAYOVER} to {MAX_LAYOVER} minute range"
    if W not in D["W_values"]:
        return f"walk time must be one of {D['W_values']} minutes"
    return None


def connection_risk(hub: str, airline: str, arrival_hour: int, month: int, layover_min: float,
                    walk_min: int | None = None) -> dict:
    """Miss probability for one same-airline connection, as the lookup tool shows it."""
    D = tool()
    W = D["W_default"] if walk_min is None else walk_min
    hub, airline = hub.upper(), airline.upper()
    out = {"tool": "connection_risk", "hub": hub, "airline": airline, "arrival_hour": arrival_hour, "month": month,
           "layover_min": layover_min, "walk_min": W, "door_closes_min": D["D"]}
    if not (0 <= arrival_hour <= 23) or not (1 <= month <= 12):
        out.update(covered=False, reason="arrival hour must be 0 to 23 and month 1 to 12")
        return out
    why = coverage(hub, airline, layover_min, W)
    if why:
        out.update(covered=False, reason=why)
        return out
    p = model_p(W, hub, airline, arrival_hour, month, layover_min)
    out.update(covered=True, miss_probability_pct=round(100 * p, 1), make_probability_pct=round(100 - 100 * p, 1),
               hub_name=D["_hubs"][hub]["name"], airline_name=D["airlines"].get(airline, airline))
    return out
