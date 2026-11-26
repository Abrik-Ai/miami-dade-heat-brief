"""Compare every hourly value in data/raw_api/ (source of truth) with data/raw/ (hand copies).

data/raw_api/*.json : FortyGuard REST /v1/status bodies, hourly data under data.result
data/raw/*.json     : MCP env_params responses, hourly data under result.value.raw

Checks per station-day: file present in both, activity_id, timestamps, the set of
hourly fields, and every one of the 24 values in every field. Also compares the
non-hourly location fields (lat, lon, elevation, temperature, solar_irradiance).
Values are compared exactly (so 1 and 1.0 are equal, 24.6 and 24.5 are not).

Usage: uv run scripts/compare_raw.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "data" / "raw_api"
RAW = ROOT / "data" / "raw"
NAME = re.compile(r"^(K[A-Z]{3})_(\d{4}-\d{2}-\d{2})\.json$")


def files(d):
    return {p.name: p for p in d.glob("K???_*.json") if NAME.match(p.name)}


def main():
    api, raw = files(API), files(RAW)
    diffs = []  # (file, field, hour, raw_value, api_value)
    notes = []

    for name in sorted(set(api) - set(raw)):
        notes.append(f"{name}: in raw_api only")
    for name in sorted(set(raw) - set(api)):
        notes.append(f"{name}: in raw only")

    n_values = 0
    common = sorted(set(api) & set(raw))
    for name in common:
        a = json.loads(api[name].read_bytes())
        r = json.loads(raw[name].read_bytes())
        ares, rres = a["data"]["result"], r["result"]["value"]["raw"]

        if a["data"]["activity_id"] != r["result"]["activity_id"]:
            notes.append(f"{name}: activity_id differs ({r['result']['activity_id']} vs {a['data']['activity_id']})")
        if ares["metadata"]["timestamps"] != rres["metadata"]["timestamps"]:
            notes.append(f"{name}: timestamps differ")

        aloc, rloc = ares["locations"][0], rres["locations"][0]
        for key in ("lat", "lon", "elevation", "temperature", "solar_irradiance"):
            if aloc.get(key) != rloc.get(key):
                notes.append(f"{name}: location.{key} differs ({rloc.get(key)!r} vs {aloc.get(key)!r})")

        ap, rp = aloc["parameters"], rloc["parameters"]
        for k in sorted(set(ap) ^ set(rp)):
            notes.append(f"{name}: field {k} only in {'raw_api' if k in ap else 'raw'}")
        for k in sorted(set(ap) & set(rp)):
            if len(ap[k]) != len(rp[k]):
                notes.append(f"{name}: {k} length {len(rp[k])} (raw) vs {len(ap[k])} (raw_api)")
            for h, (rv, av) in enumerate(zip(rp[k], ap[k])):
                n_values += 1
                if rv != av:
                    diffs.append((name, k, h, rv, av))

    print(f"files: raw_api {len(api)}, raw {len(raw)}, compared {len(common)}")
    print(f"hourly values compared: {n_values}")
    print(f"hourly value differences: {len(diffs)}")
    for name, k, h, rv, av in diffs:
        print(f"  {name}  {k}  hour {h:02d}  raw={rv!r}  raw_api={av!r}")
    print(f"other differences: {len(notes)}")
    for n in notes:
        print(f"  {n}")


if __name__ == "__main__":
    main()
