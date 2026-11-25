"""Append one logs/mcp_calls.jsonl line per saved env_params response.

Usage: uv run scripts/log_mcp_calls.py data/raw/KMIA_2025-07-01.json [...]
       uv run scripts/log_mcp_calls.py --fail STATION DATE "error text"

`time` is when the entry was logged (just after the call returned), UTC.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "logs" / "mcp_calls.jsonl"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(args):
    lines = []
    if args[0] == "--fail":
        station, date, err = args[1], args[2], args[3]
        lines.append({"time": now(), "station": station, "date": date, "status": "error",
                      "latency_ms": None, "cost_credits": None, "activity_id": None, "error": err})
    else:
        for p in map(Path, args):
            station, date = re.match(r"(K[A-Z]{3})_(\d{4}-\d{2}-\d{2})\.json$", p.name).groups()
            d = json.loads(p.read_text())
            tr = d.get("trace", {})
            n = len(d["result"]["value"]["raw"]["metadata"]["timestamps"]) if d.get("ok") else None
            lines.append({"time": now(), "station": station, "date": date,
                          "status": tr.get("status", "ok" if d.get("ok") else "error"),
                          "latency_ms": tr.get("latency_ms"), "cost_credits": tr.get("cost_credits"),
                          "activity_id": d.get("result", {}).get("activity_id"), "n_hours": n})
    with LOG.open("a") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
            print(json.dumps(line))


if __name__ == "__main__":
    main(sys.argv[1:])
