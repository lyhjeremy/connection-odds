"""Find every number in a piece of prose and check each one against the numbers a tool returned.

A number counts as sourced when some allowed value rounds to it at the precision the prose shows:
"$9.0M" is sourced by 9,044,391, "85%" by 84.8, "57" only by 57. Allowed values come from the
tool output (every numeric leaf, plus 100 minus each percentage for "80/20" style splits), the
resolved plan and the question itself.
"""
from __future__ import annotations

import re

CLOCK_RE = re.compile(r"(?<![\d:.])(\d{1,2}):(\d{2})(?!\d)(?:\s?([ap])(?:\.?m\.?)?(?![a-z]))?", re.I)


def find_clocks(text: str) -> list[dict]:
    """Clock times such as 2:15 pm or 14:15, as minutes after midnight (both readings when no am/pm)."""
    out = []
    for m in CLOCK_RE.finditer(text):
        h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if h > 23 or mi > 59:
            continue
        if ap:
            vals = [(h % 12 + (12 if ap == "p" else 0)) * 60 + mi]
        else:
            vals = [h * 60 + mi] + ([(h + 12) * 60 + mi] if h < 12 else [])
        out.append({"text": m.group(0).strip(), "minutes": vals, "span": m.span()})
    return out


def strip_clocks(text: str) -> str:
    return CLOCK_RE.sub(" ", text)

NUM_RE = re.compile(
    r"(?<![\w.])(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s?(?P<suf>k|K|M|m|million|mil|thousand|B|billion)\b)?(?P<pct>\s?%| percent)?")
_MULT = {"k": 1e3, "K": 1e3, "thousand": 1e3, "M": 1e6, "m": 1e6, "million": 1e6, "mil": 1e6, "B": 1e9, "billion": 1e9}


def find_numbers(text: str) -> list[dict]:
    """Each number with its value in plain units and the rounding tolerance its written form implies.
    Clock times are left out here and checked separately (find_clocks)."""
    text = strip_clocks(text)
    out = []
    for m in NUM_RE.finditer(text):
        raw = m.group("num")
        digits = raw.replace(",", "")
        val = float(digits)
        dec = len(digits.split(".")[1]) if "." in digits else 0
        mult = _MULT.get(m.group("suf") or "", 1.0)
        if m.group("suf") == "m" and not m.group("cur"):
            mult = 1.0  # "5 m" is more likely minutes or meters than millions
        unit = 10 ** (-dec) * mult
        out.append({"text": m.group(0).strip(), "value": val * mult, "tol": unit / 2 + 1e-9,
                    "pct": bool(m.group("pct")), "money": bool(m.group("cur")) or mult > 1,
                    "start": m.start()})
    return out


def leaves(obj) -> list[float]:
    vals = []
    if isinstance(obj, bool):
        return vals
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", obj):  # a leg timestamp: its date parts
            return [float(obj[:4]), float(obj[5:7]), float(obj[8:10])]
        return [n["value"] for n in find_numbers(obj)]
    if isinstance(obj, dict):
        for v in obj.values():
            vals += leaves(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            vals += leaves(v)
    return vals


def allowed_values(*sources) -> list[float]:
    vals = []
    for s in sources:
        vals += leaves(s)
    extra = [100 - v for v in vals if 0 <= v <= 100]
    return sorted(set(vals + extra))


def check(text: str, allowed: list[float], allowed_clocks: list[int] = ()) -> dict:
    """Split the numbers and clock times in `text` into sourced and unsourced."""
    nums = find_numbers(text)
    clocks = find_clocks(text)
    unsourced = [n["text"] for n in nums if not any(abs(n["value"] - a) <= n["tol"] for a in allowed)]
    unsourced += [c["text"] for c in clocks if not set(c["minutes"]) & set(allowed_clocks)]
    found = [n["text"] for n in nums] + [c["text"] for c in clocks]
    return {"numbers": found, "n": len(found), "unsourced": unsourced, "n_unsourced": len(unsourced)}


def mentions(text: str, value: float, tol: float = 0.0) -> bool:
    """True when the prose states `value` at its own rounding (or within an explicit tolerance)."""
    return any(abs(n["value"] - value) <= max(n["tol"], tol) for n in find_numbers(text))


def clock_values(*sources) -> list[int]:
    """Minutes after midnight of every clock time and leg timestamp in the sources."""
    vals = []

    def walk(o):
        if isinstance(o, str):
            m = re.fullmatch(r"\d{4}-\d{2}-\d{2} (\d{2}):(\d{2})", o)
            if m:
                vals.append(int(m.group(1)) * 60 + int(m.group(2)))
            else:
                for c in find_clocks(o):
                    vals.extend(c["minutes"])
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
    for s in sources:
        walk(s)
    return sorted(set(vals))
