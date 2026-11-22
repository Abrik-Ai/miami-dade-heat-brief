"""Compare two FortyGuard env_params responses that differ only in reference temperature.

Usage:
    uv run scripts/compare_ref.py [BASE_JSON] [NEW_JSON]

For each hourly field: identical/changed, max |diff|, and whether the change
is consistent with the NWS heat index formula (Rothfusz regression with the
NWS adjustments and the simple Steadman formula below 80 °F), evaluated with
each file's reference temperature and its own hourly relative humidity.
"""

import json
import math
import sys
from pathlib import Path

DEFAULT_BASE = Path("data/raw/miami_2025-08-15.json")
DEFAULT_NEW = Path("data/raw/miami_2025-08-15_ref28.json")

# Reported values are rounded to 0.1 °C; allow rounding on both sides plus
# small slack for the provider rounding RH or converting units differently.
HI_TOL_C = 0.15


def nws_heat_index_f(t_f: float, rh: float) -> float:
    """NWS/WPC heat index algorithm, °F in, °F out."""
    simple = 0.5 * (t_f + 61.0 + (t_f - 68.0) * 1.2 + rh * 0.094)
    if (simple + t_f) / 2.0 < 80.0:
        return simple
    hi = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t_f**2
        - 0.05481717 * rh**2
        + 0.00122874 * t_f**2 * rh
        + 0.00085282 * t_f * rh**2
        - 0.00000199 * t_f**2 * rh**2
    )
    if rh < 13 and 80 <= t_f <= 112:
        hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t_f - 95.0)) / 17)
    elif rh > 85 and 80 <= t_f <= 87:
        hi += ((rh - 85) / 10) * ((87 - t_f) / 5)
    return hi


def nws_heat_index_c(t_c: float, rh: float) -> float:
    return (nws_heat_index_f(t_c * 9 / 5 + 32, rh) - 32) * 5 / 9


def load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def location(resp: dict) -> dict:
    return resp["result"]["value"]["raw"]["locations"][0]


def fmt(x) -> str:
    return "None" if x is None else f"{x:.2f}"


def main() -> None:
    base_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BASE
    new_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_NEW
    base, new = load(base_path), load(new_path)
    lb, ln = location(base), location(new)
    tb, tn = lb["temperature"], ln["temperature"]

    print(f"base: {base_path}  (reference temperature {tb} °C)")
    print(f"new:  {new_path}  (reference temperature {tn} °C)")

    ts_b = base["result"]["value"]["raw"]["metadata"]["timestamps"]
    ts_n = new["result"]["value"]["raw"]["metadata"]["timestamps"]
    print(f"timestamps identical: {ts_b == ts_n}  ({len(ts_b)} hours)")
    print()

    pb, pn = lb["parameters"], ln["parameters"]
    rh_b, rh_n = pb["relative_humidity_percent"], pn["relative_humidity_percent"]
    hi_rows = []

    header = f"{'field':<32} {'status':<10} {'max|diff|':>10}  NWS-HI consistency"
    print(header)
    print("-" * len(header + " " * 30))
    for field in sorted(set(pb) | set(pn)):
        a, b = pb.get(field), pn.get(field)
        if a is None or b is None:
            print(f"{field:<32} {'MISSING':<10} {'':>10}  only in {'new' if a is None else 'base'}")
            continue
        diffs = [y - x for x, y in zip(a, b)]
        maxabs = max(abs(d) for d in diffs)
        status = "identical" if a == b else "changed"

        if field == "heat_index_celsius":
            resid_b, resid_n, resid_d = [], [], []
            for h in range(len(a)):
                pred_b = nws_heat_index_c(tb, rh_b[h])
                pred_n = nws_heat_index_c(tn, rh_n[h])
                resid_b.append(a[h] - pred_b)
                resid_n.append(b[h] - pred_n)
                resid_d.append((b[h] - a[h]) - (pred_n - pred_b))
                hi_rows.append((h, rh_b[h], rh_n[h], a[h], pred_b, b[h], pred_n))
            worst = max(max(map(abs, resid_b)), max(map(abs, resid_n)), max(map(abs, resid_d)))
            ok = worst <= HI_TOL_C
            verdict = (
                f"{'CONSISTENT' if ok else 'INCONSISTENT'} "
                f"(max |resid| base {max(map(abs, resid_b)):.2f}, new {max(map(abs, resid_n)):.2f}, "
                f"delta {max(map(abs, resid_d)):.2f}; tol {HI_TOL_C})"
            )
        else:
            verdict = (
                "n/a: not an NWS HI output; formula predicts no change -> "
                + ("consistent" if a == b else "NOT consistent")
            )
        print(f"{field:<32} {status:<10} {maxabs:>10.3f}  {verdict}")

    print()
    print("heat_index_celsius hour by hour (NWS = recomputed from ref temp + that file's RH)")
    print(f"{'hr':>2} {'RH_b':>6} {'RH_n':>6} {'HI_b':>6} {'NWS_b':>6} {'HI_n':>6} {'NWS_n':>6} {'dHI':>6} {'dNWS':>6}")
    for h, rb, rn, hb, nb, hn, nn in hi_rows:
        print(f"{h:>2} {rb:>6.1f} {rn:>6.1f} {hb:>6.1f} {nb:>6.2f} {hn:>6.1f} {nn:>6.2f} {hn - hb:>6.1f} {nn - nb:>6.2f}")

    print()
    print("non-hourly fields")
    for key in sorted(set(lb) | set(ln)):
        if key == "parameters":
            continue
        print(f"  location.{key:<20} {'identical' if lb.get(key) == ln.get(key) else 'changed'}: {lb.get(key)!r:.60} -> {ln.get(key)!r:.60}")
    sb, sn = base["result"]["value"]["parameters"], new["result"]["value"]["parameters"]
    for key in sorted(set(sb) | set(sn)):
        print(f"  summary.{key:<21} {'identical' if sb.get(key) == sn.get(key) else 'changed'}: {sb.get(key)} -> {sn.get(key)}")


if __name__ == "__main__":
    main()
