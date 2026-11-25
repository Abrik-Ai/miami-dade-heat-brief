"""FortyGuard-implied air temperature, from FortyGuard wet-bulb and relative humidity.

FortyGuard returns no air temperature (its heat index uses the caller's 33 °C), but it
returns wet-bulb (Tw) and relative humidity (RH). For each FortyGuard hour, solve for
the air temperature T such that

    metpy.calc.wet_bulb_temperature(p, T, Td(T, RH_FG)) == Tw_FG

where Td(T, RH) = metpy.calc.dewpoint_from_relative_humidity(T, RH) and p is the NOAA
station pressure of the matched METAR (altimeter setting -> station pressure, from
results/matched_hourly.csv). Unmatched hours use the station's median station pressure
(flagged pressure_source = "station_median").

Solver: scipy.optimize.brentq on the bracket [Tw, Tw + 25] °C (air temperature can't be
below wet-bulb), xtol 1e-4 °C. An hour is flagged not converged if RH or Tw is missing,
the bracket has no sign change, or the solver raises.

Sensitivity: the same solve with RH_FG + 5 and RH_FG − 5 percentage points (RH capped at
100 %), reporting the change in implied T.

Outputs
  results/implied_temperature_hourly.csv
  results/implied_temperature_summary.csv   (bias/MAE/RMSE/r vs NOAA T, by station; RH ±5 sensitivity)
  results/implied_temperature_by_hour.csv

Usage: uv run scripts/implied_temperature.py   (run scripts/eval_accuracy.py first)
"""

import warnings
from pathlib import Path

import metpy.calc as mpcalc
import numpy as np
import pandas as pd
from metpy.units import units
from scipy.optimize import brentq

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
BRACKET_C = 25.0
XTOL = 1e-4


def wet_bulb_c(p_hpa, t_c, rh_pct):
    p = p_hpa * units.hPa
    t = t_c * units.degC
    td = mpcalc.dewpoint_from_relative_humidity(t, min(rh_pct, 100.0) * units.percent)
    return mpcalc.wet_bulb_temperature(p, t, td).to("degC").m


def solve_t(p_hpa, tw_c, rh_pct):
    """Return (T °C, converged, note)."""
    if not (np.isfinite(p_hpa) and np.isfinite(tw_c) and np.isfinite(rh_pct)) or rh_pct <= 0:
        return np.nan, False, "missing input"
    f = lambda t: wet_bulb_c(p_hpa, t, rh_pct) - tw_c  # noqa: E731
    lo, hi = tw_c, tw_c + BRACKET_C
    try:
        flo, fhi = f(lo), f(hi)
        if np.sign(flo) == np.sign(fhi):
            # at RH ~100 % T == Tw is the root itself
            if abs(flo) < 1e-3:
                return lo, True, "root at lower bound"
            return np.nan, False, f"no sign change (f(lo)={flo:.3f}, f(hi)={fhi:.3f})"
        t = brentq(f, lo, hi, xtol=XTOL)
        return t, True, ""
    except Exception as ex:  # noqa: BLE001
        return np.nan, False, f"{type(ex).__name__}: {ex}"


def metrics(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if not len(a):
        return {"n": 0, "bias": np.nan, "mae": np.nan, "rmse": np.nan, "r": np.nan}
    d = a - b
    return {"n": int(len(a)), "bias": d.mean(), "mae": np.abs(d).mean(), "rmse": np.sqrt((d ** 2).mean()),
            "r": float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else np.nan}


def main():
    m = pd.read_csv(RESULTS / "matched_hourly.csv")
    med_p = m.groupby("station")["noaa_p_station_hpa"].median().to_dict()
    p = m["noaa_p_station_hpa"].copy()
    m["pressure_source"] = np.where(p.notna(), "matched_metar", "station_median")
    m["p_used_hpa"] = p.fillna(m["station"].map(med_p))

    for label, delta in (("", 0.0), ("_rh_plus5", 5.0), ("_rh_minus5", -5.0)):
        out = [solve_t(pp, tw, rh + delta)
               for pp, tw, rh in zip(m["p_used_hpa"], m["fg_wb"], m["fg_rh"])]
        m[f"implied_t{label}"] = [o[0] for o in out]
        m[f"converged{label}"] = [o[1] for o in out]
        m[f"solver_note{label}"] = [o[2] for o in out]
        print(f"solved{label or ' (FortyGuard RH)'}: converged {sum(o[1] for o in out)} / {len(out)}")

    # check: implied T reproduces FortyGuard wet-bulb
    ok = m["converged"]
    resid = [wet_bulb_c(pp, t, rh) - tw for pp, t, rh, tw in
             zip(m.loc[ok, "p_used_hpa"], m.loc[ok, "implied_t"], m.loc[ok, "fg_rh"], m.loc[ok, "fg_wb"])]
    print(f"check |Tw(implied T) − Tw_FG| max {np.max(np.abs(resid)):.5f} °C")

    m["d_implied_t_rh_plus5"] = m["implied_t_rh_plus5"] - m["implied_t"]
    m["d_implied_t_rh_minus5"] = m["implied_t_rh_minus5"] - m["implied_t"]

    cols = ["station", "local_time", "local_date", "local_hour", "matched", "qa_flagged_day", "advisory",
            "fg_wb", "fg_rh", "pressure_source", "p_used_hpa", "implied_t", "converged", "solver_note",
            "implied_t_rh_plus5", "converged_rh_plus5", "implied_t_rh_minus5", "converged_rh_minus5",
            "d_implied_t_rh_plus5", "d_implied_t_rh_minus5", "noaa_t"]
    m[cols].to_csv(RESULTS / "implied_temperature_hourly.csv", index=False, float_format="%.4f")

    not_conv = m[~m["converged"]]
    print(f"\nnot converged (FortyGuard RH): {len(not_conv)}")
    for r in not_conv.itertuples():
        print(f"  {r.station} {r.local_time}  Tw={r.fg_wb} RH={r.fg_rh}  {r.solver_note}")

    # comparison with NOAA measured T: same evaluation set as eval_accuracy (matched, not QA-flagged)
    ev = m[m["matched"] & ~m["qa_flagged_day"]]
    rows, hrows = [], []
    for station in ("KMIA", "KHST", "ALL"):
        s = ev if station == "ALL" else ev[ev["station"] == station]
        rows.append({"station": station, "comparison": "implied_t_vs_noaa_t", "unit": "°C",
                     **metrics(s["implied_t"].to_numpy(float), s["noaa_t"].to_numpy(float))})
        for lab in ("rh_plus5", "rh_minus5"):
            rows.append({"station": station, "comparison": f"implied_t_{lab}_vs_noaa_t", "unit": "°C",
                         **metrics(s[f"implied_t_{lab}"].to_numpy(float), s["noaa_t"].to_numpy(float))})
        for lab in ("rh_plus5", "rh_minus5"):
            d = s[f"d_implied_t_{lab}"].dropna()
            rows.append({"station": station, "comparison": f"sensitivity_{lab}_change_in_implied_t", "unit": "°C",
                         "n": int(len(d)), "bias": d.mean(), "mae": d.abs().mean(),
                         "rmse": np.sqrt((d ** 2).mean()), "r": np.nan,
                         "min": d.min(), "max": d.max()})
        for h in range(24):
            sh = s[s["local_hour"] == h]
            hrows.append({"station": station, "local_hour": h,
                          **metrics(sh["implied_t"].to_numpy(float), sh["noaa_t"].to_numpy(float)),
                          "sens_rh_plus5_mean": sh["d_implied_t_rh_plus5"].mean(),
                          "sens_rh_minus5_mean": sh["d_implied_t_rh_minus5"].mean()})
    summ, hr = pd.DataFrame(rows), pd.DataFrame(hrows)
    summ.to_csv(RESULTS / "implied_temperature_summary.csv", index=False, float_format="%.4f")
    hr.to_csv(RESULTS / "implied_temperature_by_hour.csv", index=False, float_format="%.4f")

    pd.set_option("display.width", 160)
    print(f"\nevaluation hours (matched, not QA-flagged): {len(ev)}; not converged among them: {int((~ev['converged']).sum())}")
    print(summ.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nbias by local hour (implied T − NOAA T, °C):")
    piv = hr.pivot(index="local_hour", columns="station", values="bias")[["KMIA", "KHST", "ALL"]]
    print(piv.to_string(float_format=lambda v: f"{v:+.2f}"))


if __name__ == "__main__":
    main()
