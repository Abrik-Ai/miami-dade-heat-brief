"""Replay NWS MFL Heat Advisory days, July-August 2025, at KMIA and KHST.

Criterion (notes/thresholds.md): heat index >= 105 °F for at least 2 hours in the day.

Daily rules, each evaluated per station and local day (00-23 America/New_York):
  noaa_hi         NOAA-observed heat index (MetPy heat_index from the matched routine METAR)
  fg_implied_hi   MetPy heat_index from FortyGuard-implied air temperature + FortyGuard RH
  fg_apparent     FortyGuard apparent_temperature_celsius, against the same threshold

Duration variants:
  ge2h          at least 2 hours >= threshold in the day (not necessarily consecutive)  [primary]
  ge2h_consec   at least 2 consecutive hours >= threshold

Thresholds: 103, 105 (primary), 108 °F.

Truth: data/nws/advisory_days.csv (heat_product_in_effect), Jul 1 - Aug 31.

Day sets:
  common    station-days not flagged in the NOAA quality check (same days for all rules)  [primary]
  all_days  every day with data for that rule (FortyGuard: all 62 days per station;
            NOAA: days with at least one matched observation)

Outputs: results/replay_daily.csv, results/replay_contingency.csv

Usage: uv run scripts/replay_advisories.py   (after eval_accuracy.py and implied_temperature.py)
"""

import warnings
from pathlib import Path

import metpy.calc as mpcalc
import numpy as np
import pandas as pd
from metpy.units import units

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
THRESHOLDS_F = (103, 105, 108)
RULES = ("noaa_hi", "fg_implied_hi", "fg_apparent")
DURATIONS = ("ge2h", "ge2h_consec")
STATIONS = ("KMIA", "KHST")


def c_to_f(c):
    return np.asarray(c, float) * 9 / 5 + 32


def hourly_values():
    m = pd.read_csv(RESULTS / "matched_hourly.csv")
    imp = pd.read_csv(RESULTS / "implied_temperature_hourly.csv")
    key = ["station", "local_time"]
    df = m[key + ["local_date", "local_hour", "matched", "qa_flagged_day", "noaa_hi", "fg_at", "fg_rh"]].merge(
        imp[key + ["implied_t", "converged"]], on=key, how="left", validate="one_to_one")
    df["noaa_hi"] = np.where(df["matched"], c_to_f(df["noaa_hi"]), np.nan)
    hi = mpcalc.heat_index(df["implied_t"].to_numpy(float) * units.degC,
                           df["fg_rh"].to_numpy(float) * units.percent, mask_undefined=False)
    df["fg_implied_hi"] = np.where(df["converged"], hi.to("degF").m, np.nan)
    df["fg_apparent"] = c_to_f(df["fg_at"])
    return df


def max_run(hours):
    """Longest run of consecutive local hours."""
    best = run = 0
    prev = None
    for h in sorted(hours):
        run = run + 1 if prev is not None and h == prev + 1 else 1
        best = max(best, run)
        prev = h
    return best


def daily_table(df):
    rows = []
    for (station, day), g in df.groupby(["station", "local_date"]):
        row = {"station": station, "local_date": day, "qa_flagged_day": bool(g["qa_flagged_day"].any())}
        for rule in RULES:
            vals = g[["local_hour", rule]].dropna()
            row[f"{rule}_n_hours"] = len(vals)
            row[f"{rule}_max_f"] = vals[rule].max() if len(vals) else np.nan
            for thr in THRESHOLDS_F:
                above = vals.loc[vals[rule] >= thr, "local_hour"].tolist()
                row[f"{rule}_{thr}_hours_ge"] = len(above)
                row[f"{rule}_{thr}_max_consec"] = max_run(above)
                row[f"{rule}_{thr}_ge2h"] = len(above) >= 2 if len(vals) else np.nan
                row[f"{rule}_{thr}_ge2h_consec"] = max_run(above) >= 2 if len(vals) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def contingency(daily):
    rows = []
    for rule in RULES:
        for thr in THRESHOLDS_F:
            for dur in DURATIONS:
                col = f"{rule}_{thr}_{dur}"
                for day_set in ("common", "all_days"):
                    for station in (*STATIONS, "ALL"):
                        d = daily if station == "ALL" else daily[daily["station"] == station]
                        d = d[d[col].notna()]
                        if day_set == "common":
                            d = d[~d["qa_flagged_day"]]
                        pred, obs = d[col].astype(bool), d["nws_advisory"].astype(bool)
                        h, m_, fa = int((pred & obs).sum()), int((~pred & obs).sum()), int((pred & ~obs).sum())
                        cn = int((~pred & ~obs).sum())
                        tag = lambda s: [f"{a}:{b}" if station == "ALL" else b  # noqa: E731
                                         for a, b in zip(s["station"], s["local_date"])]
                        rows.append({
                            "rule": rule, "threshold_f": thr, "duration": dur, "day_set": day_set,
                            "station": station, "n_days": len(d), "hits": h, "misses": m_,
                            "false_alarms": fa, "correct_negatives": cn,
                            "hit_rate": h / (h + m_) if h + m_ else np.nan,
                            "false_alarm_ratio": fa / (h + fa) if h + fa else np.nan,
                            "csi": h / (h + m_ + fa) if h + m_ + fa else np.nan,
                            "miss_dates": " ".join(tag(d[~pred & obs])),
                            "false_alarm_dates": " ".join(tag(d[pred & ~obs])),
                        })
    return pd.DataFrame(rows)


def main():
    df = hourly_values()
    daily = daily_table(df)
    adv = pd.read_csv(ROOT / "data" / "nws" / "advisory_days.csv")
    daily = daily.merge(adv[["station", "local_date", "heat_product_in_effect"]], on=["station", "local_date"],
                        how="left", validate="one_to_one").rename(columns={"heat_product_in_effect": "nws_advisory"})
    assert daily["nws_advisory"].notna().all()
    daily.to_csv(RESULTS / "replay_daily.csv", index=False, float_format="%.2f")
    ct = contingency(daily)
    ct.to_csv(RESULTS / "replay_contingency.csv", index=False, float_format="%.4f")

    print("NWS advisory days (Jul-Aug):", {s: int(daily[(daily.station == s)].nws_advisory.sum()) for s in STATIONS})
    print("QA-flagged days excluded from 'common':",
          {s: int(daily[(daily.station == s)].qa_flagged_day.sum()) for s in STATIONS},
          "of which NWS advisory days:",
          sorted(f"{r.station}:{r.local_date}" for r in daily[daily.qa_flagged_day & daily.nws_advisory].itertuples()))

    pd.set_option("display.width", 200, "display.max_colwidth", 120)
    f = lambda v: f"{v:.3f}"  # noqa: E731
    base = ["rule", "station", "n_days", "hits", "misses", "false_alarms", "correct_negatives",
            "hit_rate", "false_alarm_ratio", "csi"]
    for dur in DURATIONS:
        sel = ct[(ct.threshold_f == 105) & (ct.duration == dur) & (ct.day_set == "common")]
        print(f"\n=== 105 °F, {dur}, common days ===")
        print(sel[base].to_string(index=False, float_format=f))
        for r in sel[sel.station != "ALL"].itertuples():
            print(f"  {r.rule:14s} {r.station}  misses: {r.miss_dates or '-'}")
            print(f"  {'':14s} {r.station}  false alarms: {r.false_alarm_dates or '-'}")

    print("\n=== sensitivity: threshold x duration, common days, per station (H/M/FA/CN, CSI) ===")
    for rule in RULES:
        for station in STATIONS:
            parts = []
            for thr in THRESHOLDS_F:
                for dur in DURATIONS:
                    r = ct[(ct.rule == rule) & (ct.station == station) & (ct.threshold_f == thr)
                           & (ct.duration == dur) & (ct.day_set == "common")].iloc[0]
                    parts.append(f"{thr}{'c' if dur.endswith('consec') else ' '} {r.hits}/{r.misses}/{r.false_alarms}/"
                                 f"{r.correct_negatives} {r.csi:.2f}")
            print(f"  {rule:14s} {station}  " + " | ".join(parts))

    print("\n=== 105 °F, ge2h, all_days ===")
    sel = ct[(ct.threshold_f == 105) & (ct.duration == "ge2h") & (ct.day_set == "all_days")]
    print(sel[base].to_string(index=False, float_format=f))

    print("\nmax daily value on NWS advisory days (°F, common + flagged):")
    a = daily[daily.nws_advisory]
    print(a[["station", "local_date", "qa_flagged_day", "noaa_hi_max_f", "noaa_hi_105_hours_ge",
             "fg_implied_hi_max_f", "fg_implied_hi_105_hours_ge", "fg_apparent_max_f",
             "fg_apparent_105_hours_ge"]].to_string(index=False, float_format=lambda v: f"{v:.1f}"))


if __name__ == "__main__":
    main()
