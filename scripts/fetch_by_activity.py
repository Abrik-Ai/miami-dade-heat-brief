"""Re-fetch FortyGuard env_params results by activity_id and save the raw bytes.

For each successful call in logs/mcp_calls.jsonl, GET
    https://api.fortyguard.com/v1/status/{activity_id}
with the `api-key` header (FORTYGUARD_API_KEY from .env) and write the
response body exactly as received to data/raw_api/{station}_{date}.json.
Non-200 bodies go to data/raw_api/_errors/ instead, so they never look like data.

Every request is logged to logs/rest_calls.jsonl with a UTC timestamp taken
just before the request and latency measured by this script.

Usage:
    uv run scripts/fetch_by_activity.py --limit 1        # test on one activity
    uv run scripts/fetch_by_activity.py                  # all, skipping files already saved
    uv run scripts/fetch_by_activity.py --only KMIA_2025-07-01
    uv run scripts/fetch_by_activity.py --force          # re-download even if saved
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CALL_LOG = ROOT / "logs" / "mcp_calls.jsonl"
REST_LOG = ROOT / "logs" / "rest_calls.jsonl"
OUT_DIR = ROOT / "data" / "raw_api"
ERR_DIR = OUT_DIR / "_errors"
URL = "https://api.fortyguard.com/v1/status/{activity_id}"


def logged_activities():
    """(station, date, activity_id) for each successful MCP call, last entry wins."""
    seen = {}
    for line in CALL_LOG.read_text().splitlines():
        e = json.loads(line)
        if e.get("status") == "ok" and e.get("activity_id"):
            seen[(e["station"], e["date"])] = e["activity_id"]
    return [(s, d, a) for (s, d), a in sorted(seen.items())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="fetch at most N activities")
    ap.add_argument("--only", help="fetch a single STATION_DATE, e.g. KMIA_2025-07-01")
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--sleep", type=float, default=0.5, help="seconds between requests")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.environ.get("FORTYGUARD_API_KEY")
    if not key:
        sys.exit("FORTYGUARD_API_KEY is not set in .env")

    todo = logged_activities()
    if args.only:
        todo = [t for t in todo if f"{t[0]}_{t[1]}" == args.only]
    if not args.force:
        todo = [t for t in todo if not (OUT_DIR / f"{t[0]}_{t[1]}.json").exists()]
    if args.limit is not None:
        todo = todo[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REST_LOG.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"api-key": key, "User-Agent": "heat-brief-fetch/0.1"})

    n_ok = n_bad = 0
    for i, (station, day, activity_id) in enumerate(todo):
        if i:
            time.sleep(args.sleep)
        stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        t0 = time.perf_counter()
        error = None
        try:
            resp = session.get(URL.format(activity_id=activity_id), timeout=120)
            status, body = resp.status_code, resp.content
            ctype = resp.headers.get("content-type")
        except requests.RequestException as ex:
            status, body, ctype, error = None, b"", None, f"{type(ex).__name__}: {ex}"
        latency_ms = round((time.perf_counter() - t0) * 1000)

        name = f"{station}_{day}.json"
        if status == 200:
            path = OUT_DIR / name
            n_ok += 1
        else:
            ERR_DIR.mkdir(parents=True, exist_ok=True)
            path = ERR_DIR / f"{station}_{day}.{status}.body"
            n_bad += 1
        path.write_bytes(body)  # exactly as received, no decoding or re-serialising

        entry = {
            "time": stamp, "station": station, "date": day, "activity_id": activity_id,
            "http_status": status, "latency_ms": latency_ms, "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(), "content_type": ctype,
            "saved_to": str(path.relative_to(ROOT)), "error": error,
        }
        with REST_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(json.dumps({k: entry[k] for k in ("station", "date", "http_status", "latency_ms", "bytes")}))

    print(f"done: {n_ok} saved, {n_bad} non-200/errors, {len(todo)} attempted")


if __name__ == "__main__":
    main()
