"""Fetch FortyGuard Environmental Parameters over REST for one station-day.

POST https://api.fortyguard.com/v1/env_params  (api-key header, FORTYGUARD_API_KEY in .env)
body: latitude/longitude from data/locations.csv, temperature 33 °C,
      date_time {start_date, filter_type: 3 (single day)}; `analysis` omitted = all parameters.

If the POST response carries an activity_id and is not yet Completed, poll
GET /v1/status/{activity_id} until status is "Completed" (or failed), within an
overall 300 s budget. The final body is saved exactly as received. The POST
body is also kept (data/raw_api/_post/) so the first response is not lost.

Each HTTP request is logged to logs/rest_calls.jsonl (UTC time, status, latency).
This script cannot read the credit balance itself (no documented REST endpoint
for it), so the caller passes the balance read just before the run with
--credits-before, and records the balance read just after with --credits-after.

PAID: one POST costs 2,110 credits (Basic/Startup) or 2,900 (Premium).

Usage:
    uv run scripts/fetch_env_rest.py KHST 2025-07-09 --credits-before 634600
    uv run scripts/fetch_env_rest.py KMIA 2025-08-03 --out data/raw_api/_rest_check/KMIA_2025-08-03.json --credits-before N
    uv run scripts/fetch_env_rest.py --credits-after N --run-id <run_id printed by the run>
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.fortyguard.com/v1"
LOCATIONS = ROOT / "data" / "locations.csv"
REST_LOG = ROOT / "logs" / "rest_calls.jsonl"
OUT_DIR = ROOT / "data" / "raw_api"
POST_DIR = OUT_DIR / "_post"
REF_T = 33.0
BUDGET_S = 300
POLL_EVERY_S = 5


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(entry):
    REST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REST_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def station_coords(station):
    for row in csv.DictReader(LOCATIONS.open()):
        if row["id"] == station:
            return float(row["lat"]), float(row["lon"])
    sys.exit(f"{station} not found in {LOCATIONS}")


def timed(session, method, url, remaining, **kw):
    """Run one request; return (status, body_bytes, latency_ms, error)."""
    t0 = time.perf_counter()
    try:
        r = session.request(method, url, timeout=max(1.0, remaining), **kw)
        return r.status_code, r.content, round((time.perf_counter() - t0) * 1000), None
    except requests.RequestException as ex:
        return None, b"", round((time.perf_counter() - t0) * 1000), f"{type(ex).__name__}: {ex}"


def parse(body):
    try:
        return json.loads(body)
    except ValueError:
        return None


def status_of(doc):
    if not isinstance(doc, dict):
        return None, None
    data = doc.get("data") if isinstance(doc.get("data"), dict) else doc
    return data.get("activity_id"), data.get("status")


def fetch(station, day, out, credits_before, session):
    lat, lon = station_coords(station)
    run_id = uuid.uuid4().hex[:12]
    payload = {"latitude": lat, "longitude": lon, "temperature": REF_T,
               "date_time": {"start_date": day, "filter_type": 3}}
    start = time.monotonic()
    base = {"run_id": run_id, "station": station, "date": day}

    stamp = now()
    st, body, ms, err = timed(session, "POST", f"{BASE}/env_params",
                              BUDGET_S, json=payload)
    POST_DIR.mkdir(parents=True, exist_ok=True)
    post_path = POST_DIR / f"{station}_{day}.{run_id}.body"
    post_path.write_bytes(body)
    doc = parse(body)
    activity_id, status = status_of(doc)
    log({**base, "time": stamp, "kind": "post", "url": "/v1/env_params", "request": payload,
         "http_status": st, "latency_ms": ms, "bytes": len(body),
         "sha256": hashlib.sha256(body).hexdigest(), "activity_id": activity_id,
         "activity_status": status, "credits_before": credits_before,
         "saved_to": str(post_path.relative_to(ROOT)), "error": err})
    print(json.dumps({"run_id": run_id, "post_status": st, "activity_id": activity_id,
                      "activity_status": status, "latency_ms": ms}))

    final = body if status == "Completed" else None
    polls = 0
    while final is None and st == 200 and activity_id and status not in ("Failed", "Error"):
        remaining = BUDGET_S - (time.monotonic() - start)
        if remaining <= POLL_EVERY_S:
            break
        time.sleep(POLL_EVERY_S)
        remaining = BUDGET_S - (time.monotonic() - start)
        stamp = now()
        pst, pbody, pms, perr = timed(session, "GET", f"{BASE}/status/{activity_id}", remaining)
        polls += 1
        _, status = status_of(parse(pbody))
        log({**base, "time": stamp, "kind": "poll", "url": f"/v1/status/{activity_id}",
             "poll": polls, "http_status": pst, "latency_ms": pms, "bytes": len(pbody),
             "activity_id": activity_id, "activity_status": status, "error": perr})
        if pst == 200 and status == "Completed":
            final = pbody

    elapsed = round(time.monotonic() - start, 1)
    if final is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(final)  # exactly as received
        outcome = "completed"
    else:
        outcome = "timeout" if elapsed >= BUDGET_S - POLL_EVERY_S else "failed"
    log({**base, "time": now(), "kind": "result", "outcome": outcome, "activity_id": activity_id,
         "activity_status": status, "polls": polls, "elapsed_s": elapsed,
         "bytes": len(final) if final else None,
         "sha256": hashlib.sha256(final).hexdigest() if final else None,
         "saved_to": str(out.relative_to(ROOT)) if final else None,
         "credits_before": credits_before})
    print(json.dumps({"run_id": run_id, "outcome": outcome, "activity_id": activity_id,
                      "polls": polls, "elapsed_s": elapsed,
                      "saved_to": str(out.relative_to(ROOT)) if final else None}))
    return outcome


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("station", nargs="?")
    ap.add_argument("date", nargs="?")
    ap.add_argument("--out", type=Path, help="output path (default data/raw_api/{station}_{date}.json)")
    ap.add_argument("--credits-before", type=int, help="balance read just before this run")
    ap.add_argument("--credits-after", type=int, help="record the balance read after a run")
    ap.add_argument("--run-id", help="run the --credits-after value belongs to")
    args = ap.parse_args()

    if args.credits_after is not None:
        if not args.run_id:
            sys.exit("--credits-after needs --run-id")
        log({"run_id": args.run_id, "time": now(), "kind": "credits_after",
             "credits_after": args.credits_after})
        print(f"recorded credits_after={args.credits_after} for run {args.run_id}")
        return

    if not (args.station and args.date):
        ap.error("station and date are required")
    out = args.out if args.out else OUT_DIR / f"{args.station}_{args.date}.json"
    out = out if out.is_absolute() else ROOT / out
    if out.exists():
        sys.exit(f"{out.relative_to(ROOT)} already exists; refusing to overwrite")

    load_dotenv(ROOT / ".env")
    key = os.environ.get("FORTYGUARD_API_KEY")
    if not key:
        sys.exit("FORTYGUARD_API_KEY is not set in .env")
    session = requests.Session()
    session.headers.update({"api-key": key, "User-Agent": "heat-brief-fetch/0.1"})
    outcome = fetch(args.station, args.date, out, args.credits_before, session)
    sys.exit(0 if outcome == "completed" else 1)


if __name__ == "__main__":
    main()
