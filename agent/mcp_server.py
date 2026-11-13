"""MCP server: the lookup tool's model as tools over stdio, for Claude Desktop or Claude Code.

    python agent/mcp_server.py      # needs the `mcp` package
    claude mcp add connection-odds -- python /path/to/connection-odds/agent/mcp_server.py

connection_risk is the same function the itinerary checker calls (agent/model.py, the Python port
of modelP in assets/app.js), so a client gets the number the browser tool shows. parse_legs runs
the deterministic itinerary checks on legs a client has already extracted.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from agent import itinerary, model, pipeline  # noqa: E402

server = MCPServer(
    name="connection-odds",
    log_level="WARNING",
    instructions=("Missed-connection model for same-airline US domestic connections at the 30 busiest US hubs, "
                  "fitted on BTS on-time data from September 2023 to August 2026. Quote the probabilities these "
                  "tools return rather than estimating your own."),
)


@server.tool(description=("Chance of missing a same-airline connection. hub: three-letter code of the connecting "
                          "airport (one of the 30 busiest US hubs); airline: two-letter marketing carrier code such as "
                          "DL, UA, AA or WN; arrival_hour: scheduled local arrival hour at the hub, 0 to 23; month: 1 "
                          "to 12; layover_min: scheduled minutes from arrival to departure, 30 to 180; walk_min: gate "
                          "to gate minutes, 10 to 30 in steps of 5 (default 20)."))
def connection_risk(hub: str, airline: str, arrival_hour: int, month: int, layover_min: float,
                    walk_min: int = 20) -> dict:
    return model.connection_risk(hub, airline, arrival_hour, month, layover_min, walk_min)


@server.tool(description=("Validate flight legs and score every connection. legs: list of objects with airline, "
                          "flight_number, origin, destination (IATA codes), depart_date, depart_time, arrive_date, "
                          "arrive_time, the date and time strings as printed on the itinerary. Layovers are computed "
                          "in code from the local times at the connecting airport."))
def parse_legs(legs: list[dict]) -> dict:
    res = itinerary.resolve({"is_itinerary": True, "legs": legs})
    return dict(res, model_results=pipeline.risk_calls(res) if res["status"] == "ok" else [])


if __name__ == "__main__":
    server.run("stdio")
