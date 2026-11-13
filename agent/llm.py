"""One `claude -p` call: no tools, no MCP servers, no settings files, no saved session.

Cost and latency are what the Claude CLI reports (`total_cost_usd`, `duration_ms`), which is an
API-equivalent figure, not a bill: the runs here used a Claude subscription.
"""
from __future__ import annotations

import json
import subprocess
import time


def call(prompt: str, system: str, model: str, schema: dict | None = None, timeout: int = 180) -> dict:
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--model", model, "--system-prompt", system,
           "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
    if schema is not None:
        cmd += ["--json-schema", json.dumps(schema)]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - t0
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": (proc.stderr or proc.stdout)[:500], "wall_s": round(wall, 2), "model": model}
    usage = out.get("usage", {})
    return {
        "ok": not out.get("is_error", False),
        "text": out.get("result", ""),
        "structured": out.get("structured_output"),
        "cost_usd": out.get("total_cost_usd"),
        "duration_ms": out.get("duration_ms"),
        "wall_s": round(wall, 2),
        "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "model": next(iter(out.get("modelUsage", {})), model),
    }
