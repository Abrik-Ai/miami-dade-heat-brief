"""Build NWS heat-product tables from raw IEM VTEC responses in data/nws/raw/.

Inputs (already downloaded):
  data/nws/zones.csv
  data/nws/raw/iem_vtec_byugc_<zone>_*.json   (IEM /json/vtec_events_byugc.php)
  data/nws/raw/iem_vtec_event_MFL_2025_*.json (IEM /json/vtec_event.php, per-event detail)
Outputs:
  data/nws/heat_products.csv
  data/nws/advisory_days.csv
"""

import csv
import glob
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
NWS = ROOT / "data" / "nws"
RAW = NWS / "raw"
LOCAL = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
HEAT = {("HT", "Y"), ("EH", "W"), ("EH", "A"), ("XH", "W"), ("XH", "A")}
START, END = date(2025, 6, 1), date(2025, 9, 30)


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def event_detail(phen, sig, etn):
    f = RAW / f"iem_vtec_event_MFL_2025_{phen}_{sig}_{etn}.json"
    return json.loads(f.read_text()) if f.exists() else None


def main():
    zones = list(csv.DictReader((NWS / "zones.csv").open()))
    zone_station = {z["zone"]: z["station"] for z in zones}

    rows = []
    for z, station in zone_station.items():
        (path,) = glob.glob(str(RAW / f"iem_vtec_byugc_{z}_*.json"))
        for e in json.loads(Path(path).read_text())["events"]:
            if (e["phenomena"], e["significance"]) not in HEAT:
                continue
            issue, expire = parse(e["issue"]), parse(e["expire"])
            note = ""
            in_effect = expire > issue
            det = event_detail(e["phenomena"], e["significance"], e["eventid"])
            if det:
                u = next((u for u in det["ugcs"] if u["ugc"] == z), None)
                if u and u["status"] == "CAN" and not in_effect:
                    note = (f"cancelled {u['utc_updated']} before onset; originally "
                            f"{u['utc_issue']} to {u['utc_init_expire']}")
            if not in_effect and not note:
                note = "expire before issue"
            rows.append({
                "zone": z, "station": station,
                "phenomena": e["phenomena"], "significance": e["significance"],
                "product_name": e["name"],
                "issue_utc": issue.astimezone(UTC).isoformat(),
                "expire_utc": expire.astimezone(UTC).isoformat(),
                "issue_local": issue.astimezone(LOCAL).isoformat(),
                "expire_local": expire.astimezone(LOCAL).isoformat(),
                "event_id": e["eventid"], "wfo": e["wfo"],
                "first_product_id": e["product_id"],
                "in_effect": in_effect, "note": note,
            })
    rows.sort(key=lambda r: (r["station"], r["issue_utc"], r["event_id"]))
    with (NWS / "heat_products.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    out = []
    for station in sorted(set(zone_station.values())):
        d = START
        while d <= END:
            day0 = datetime(d.year, d.month, d.day, tzinfo=LOCAL)
            day1 = day0 + timedelta(days=1)
            hits = [r for r in rows if r["station"] == station and r["in_effect"]
                    and parse(r["issue_utc"]) < day1 and parse(r["expire_utc"]) > day0]
            hours = sum(
                (min(parse(r["expire_utc"]), day1) - max(parse(r["issue_utc"]), day0)).total_seconds()
                for r in hits) / 3600
            out.append({
                "station": station, "local_date": d.isoformat(),
                "heat_product_in_effect": bool(hits),
                "products": ";".join(f"{r['phenomena']}.{r['significance']}.{r['event_id']:04d}" for r in hits),
                "product_names": ";".join(sorted({r["product_name"] for r in hits})),
                "hours_in_effect": round(hours, 2),
            })
            d += timedelta(days=1)
    with (NWS / "advisory_days.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {len(rows)} product rows, {len(out)} station-day rows")


if __name__ == "__main__":
    main()
