"""Recompute heat_index_celsius in data/raw_api/ from 33 °C and relative_humidity_percent.

Uses the NWS/WPC heat index algorithm from scripts/compare_ref.py (Rothfusz
regression with the NWS adjustments, simple Steadman formula below 80 °F).
The reference temperature is fixed at 33 °C, as used for every call; the
script also checks that each file's location.temperature is 33.

Usage: uv run scripts/check_heat_index.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_ref import nws_heat_index_c  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "data" / "raw_api"
REF_T = 33.0


def main():
    rows = []  # (file, hour, rh, reported, computed, diff)
    wrong_t = []
    for p in sorted(API.glob("K???_*.json")):
        loc = json.loads(p.read_bytes())["data"]["result"]["locations"][0]
        if loc["temperature"] != REF_T:
            wrong_t.append((p.name, loc["temperature"]))
        par = loc["parameters"]
        for h, (rh, hi) in enumerate(zip(par["relative_humidity_percent"], par["heat_index_celsius"])):
            calc = nws_heat_index_c(REF_T, rh)
            rows.append((p.name, h, rh, hi, calc, hi - calc))

    absd = sorted(abs(r[5]) for r in rows)
    worst = max(rows, key=lambda r: abs(r[5]))
    print(f"files: {len({r[0] for r in rows})}, hourly values: {len(rows)}")
    print(f"files whose reference temperature is not 33: {wrong_t or 'none'}")
    print(f"max |reported - NWS|: {abs(worst[5]):.3f} °C  "
          f"({worst[0]} hour {worst[1]:02d}, RH {worst[2]}, reported {worst[3]}, NWS {worst[4]:.2f})")
    print(f"mean |diff| {sum(absd) / len(absd):.3f} °C, median {absd[len(absd) // 2]:.3f} °C")
    for tol in (0.05, 0.1, 0.15, 0.5):
        print(f"  values within {tol} °C: {sum(d <= tol for d in absd)} of {len(absd)}")
    print("10 largest differences:")
    for r in sorted(rows, key=lambda r: -abs(r[5]))[:10]:
        print(f"  {r[0]}  hour {r[1]:02d}  RH {r[2]:5.1f}  reported {r[3]:5.1f}  NWS {r[4]:6.2f}  diff {r[5]:+.3f}")


if __name__ == "__main__":
    main()
