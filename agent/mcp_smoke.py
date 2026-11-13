"""Start the MCP server over stdio, list its tools and call them. Writes eval/mcp_smoke.json.

    python -m agent.mcp_smoke
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
CALLS = [
    ("connection_risk", {"hub": "ATL", "airline": "DL", "arrival_hour": 10, "month": 4, "layover_min": 53}),
    ("parse_legs", {"legs": [
        {"airline": "DL", "flight_number": "DL 2318", "origin": "BOS", "destination": "ATL", "depart_date": "14APR",
         "depart_time": "0715", "arrive_date": None, "arrive_time": "1012"},
        {"airline": "DL", "flight_number": "DL 1544", "origin": "ATL", "destination": "MSY", "depart_date": "14APR",
         "depart_time": "1105", "arrive_date": None, "arrive_time": "1158"}]}),
    ("connection_risk", {"hub": "ABQ", "airline": "WN", "arrival_hour": 10, "month": 11, "layover_min": 45}),
]


async def main() -> dict:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "agent" / "mcp_server.py")], cwd=str(ROOT))
    t0 = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            listed = await session.list_tools()
            out = {"date": date.today().isoformat(), "server": init.server_info.name,
                   "startup_s": round(time.perf_counter() - t0, 2), "tools": [t.name for t in listed.tools], "calls": []}
            for name, args in CALLS:
                t1 = time.perf_counter()
                res = await session.call_tool(name, args)
                text = "".join(getattr(c, "text", "") for c in res.content)
                out["calls"].append({"tool": name, "args": args, "is_error": res.is_error,
                                     "seconds": round(time.perf_counter() - t1, 2),
                                     "result": json.loads(text) if text.startswith("{") else text})
    return out


if __name__ == "__main__":
    result = asyncio.run(main())
    (ROOT / "eval" / "mcp_smoke.json").write_text(json.dumps(result, indent=1) + "\n")
    for c in result["calls"]:
        print(c["tool"], "error" if c["is_error"] else "ok", c["seconds"], "s", json.dumps(c["result"])[:220])
