"""Compare FortyGuard (data/raw_api/) with NOAA ASOS observations (data/noaa/).

Inputs
  data/raw_api/K???_YYYY-MM-DD.json        FortyGuard REST bodies (source of truth)
  data/noaa/K???_20250630_20250901_routine.csv   IEM ASOS routine METARs, UTC, as received
  data/noaa/K???_20250630_20250901_special.csv   IEM ASOS specials (counted, not matched)
  data/locations.csv                       station elevation for station pressure
  data/nws/advisory_days.csv               advisory vs non-advisory local days

Steps
  1. Match each FortyGuard hour (local America/New_York) to the nearest routine
     METAR within ±30 min that has both temperature and dewpoint. Record the
     offset (obs time − FortyGuard hour). Hours with no such obs stay unmatched.
  2. From NOAA, with MetPy and explicit units:
       relative humidity from T and Td
       station pressure from altimeter setting and station elevation
       wet-bulb temperature (station pressure, T, Td)
       NWS heat index (MetPy heat_index, mask_undefined=False)
       apparent temperature, two candidates:
         metpy    : metpy.calc.apparent_temperature (heat index / wind chill / T)
         steadman : AT = Ta + 0.33 e − 0.70 ws − 4.00 (BoM; Ta °C, e hPa, ws m/s at 10 m),
                    e = RH/100 · 6.105 · exp(17.27 Ta / (237.7 + Ta))
  3. Metrics (FortyGuard − NOAA): bias, MAE, RMSE, Pearson r, n, by station, by
     local hour, and by advisory vs non-advisory day.
     Baseline: leave-one-day-out NOAA climatology (for each station, local hour and
     NOAA variable, the mean of that hour over the other evaluation days), scored on
     the same hours as FortyGuard. mae_skill_vs_baseline = 1 − MAE_FG / MAE_baseline.
     Station-days flagged in the NOAA quality check (local day missing > 3 hours,
     or any hour 12-18, of routine obs with valid temperature) are excluded from
     the metrics; matched rows are still written to matched_hourly.csv.

Outputs
  results/matched_hourly.csv, results/accuracy_summary.csv, results/accuracy_by_hour.csv,
  results/bias_by_hour_<variable>.png

Usage: uv run scripts/eval_accuracy.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import metpy.calc as mpcalc  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from metpy.units import units  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "data" / "raw_api"
NOAA = ROOT / "data" / "noaa"
RESULTS = ROOT / "results"
TZ = "America/New_York"
TOL = pd.Timedelta(minutes=30)
STATIONS = ("KMIA", "KHST")

# variable -> (FortyGuard column, NOAA column, unit label)
VARIABLES = {
    "relative_humidity": ("fg_rh", "noaa_rh", "%"),
    "wet_bulb": ("fg_wb", "noaa_wb", "°C"),
    "apparent_temperature_vs_metpy": ("fg_at", "noaa_at_metpy", "°C"),
    "apparent_temperature_vs_steadman": ("fg_at", "noaa_at_steadman", "°C"),
}

# Palette: validated categorical slots 1-2 (light surface), text tokens.
COLORS = {"KMIA": "#2a78d6", "KHST": "#eb6834"}
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"


# ---------------------------------------------------------------- loading
def load_fortyguard():
    rows = []
    for p in sorted(API.glob("K???_*.json")):
        station = p.name[:4]
        res = json.loads(p.read_bytes())["data"]["result"]
        par = res["locations"][0]["parameters"]
        for i, ts in enumerate(res["metadata"]["timestamps"]):
            rows.append({
                "station": station,
                "fg_time": pd.Timestamp(ts),
                "fg_rh": par["relative_humidity_percent"][i],
                "fg_wb": par["wet_bulb_temperature_celsius"][i],
                "fg_at": par["apparent_temperature_celsius"][i],
            })
    df = pd.DataFrame(rows)
    for c in ("fg_rh", "fg_wb", "fg_at"):
        df[c] = pd.to_numeric(df[c], errors="coerce").where(lambda s: s > -999)
    df["fg_time"] = pd.to_datetime(df["fg_time"], utc=True)
    df["local_time"] = df["fg_time"].dt.tz_convert(TZ)
    df["local_date"] = df["local_time"].dt.strftime("%Y-%m-%d")
    df["local_hour"] = df["local_time"].dt.hour
    return df


def load_noaa(kind):
    frames = []
    for station in STATIONS:
        f = NOAA / f"{station}_20250630_20250901_{kind}.csv"
        d = pd.read_csv(f, na_values=["M"], keep_default_na=False)
        d["station"] = station
        d["obs_time"] = pd.to_datetime(d["valid"]).dt.tz_localize("UTC")
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- matching
def match(fg, routine):
    usable = routine.dropna(subset=["tmpf", "dwpf"]).sort_values("obs_time")
    fg = fg.sort_values("fg_time")
    m = pd.merge_asof(fg, usable, left_on="fg_time", right_on="obs_time", by="station",
                      direction="nearest", tolerance=TOL)
    m["offset_min"] = (m["obs_time"] - m["fg_time"]).dt.total_seconds() / 60
    m["matched"] = m["obs_time"].notna()
    return m.sort_values(["station", "fg_time"]).reset_index(drop=True)


# ---------------------------------------------------------------- NOAA physics
def add_noaa_physics(m, elevations):
    ok = m["matched"].to_numpy()
    T = m["tmpf"].to_numpy() * units.degF
    Td = m["dwpf"].to_numpy() * units.degF
    ws = m["sknt"].to_numpy() * units.knot
    alt = m["alti"].to_numpy() * units.inHg
    elev = m["station"].map(elevations).to_numpy() * units.m

    rh = mpcalc.relative_humidity_from_dewpoint(T, Td).to("percent")
    m["noaa_t"] = T.to("degC").m
    m["noaa_td"] = Td.to("degC").m
    m["noaa_rh"] = rh.m
    m["noaa_ws_ms"] = ws.to("m/s").m

    p = mpcalc.altimeter_to_station_pressure(alt, elev).to("hPa")
    m["noaa_p_station_hpa"] = p.m

    wb = np.full(len(m), np.nan)
    good = ok & np.isfinite(p.m) & np.isfinite(T.m) & np.isfinite(Td.m)
    wb[good] = mpcalc.wet_bulb_temperature(p[good], T[good], Td[good]).to("degC").m
    m["noaa_wb"] = wb

    m["noaa_hi"] = mpcalc.heat_index(T, rh, mask_undefined=False).to("degC").m
    at_m = np.full(len(m), np.nan)
    gw = ok & np.isfinite(ws.m)
    at_m[gw] = mpcalc.apparent_temperature(T[gw], rh[gw], ws[gw], mask_undefined=False).to("degC").m
    m["noaa_at_metpy"] = at_m

    ta = T.to("degC").m
    e_hpa = rh.m / 100 * 6.105 * np.exp(17.27 * ta / (237.7 + ta))  # BoM vapour pressure, hPa
    m["noaa_e_hpa"] = e_hpa
    m["noaa_at_steadman"] = ta + 0.33 * e_hpa - 0.70 * ws.to("m/s").m - 4.00
    return m


# ---------------------------------------------------------------- QA flags
def flagged_days(routine):
    """Station-days (Jul 1 - Aug 31) missing > 3 local hours or any hour 12-18."""
    valid = routine.dropna(subset=["tmpf"]).copy()
    lt = valid["obs_time"].dt.tz_convert(TZ)
    valid["d"], valid["h"] = lt.dt.strftime("%Y-%m-%d"), lt.dt.hour
    have = valid.groupby(["station", "d"])["h"].apply(set).to_dict()
    out = set()
    for station in STATIONS:
        for d in pd.date_range("2025-07-01", "2025-08-31").strftime("%Y-%m-%d"):
            missing = set(range(24)) - have.get((station, d), set())
            if len(missing) > 3 or missing & set(range(12, 19)):
                out.add((station, d))
    return out


# ---------------------------------------------------------------- metrics
def metrics(fgv, nv):
    ok = np.isfinite(fgv) & np.isfinite(nv)
    a, b = fgv[ok], nv[ok]
    n = int(ok.sum())
    if n == 0:
        return {"n": 0, "bias": np.nan, "mae": np.nan, "rmse": np.nan, "r": np.nan}
    d = a - b
    r = float(np.corrcoef(a, b)[0, 1]) if n > 2 and a.std() > 0 and b.std() > 0 else np.nan
    return {"n": n, "bias": d.mean(), "mae": np.abs(d).mean(), "rmse": np.sqrt((d ** 2).mean()), "r": r}


def add_climatology_baseline(ev):
    """Leave-one-day-out NOAA climatology: for each station, local hour and NOAA
    variable, the mean of that hour on all *other* evaluation days. One observation
    per station-hour-day, so leaving out the row's own value leaves out its day."""
    ev = ev.copy()
    for nc in {v[1] for v in VARIABLES.values()}:
        x = ev[nc].astype(float)
        g = ev.assign(_x=x, _ok=x.notna().astype(int), _xs=x.fillna(0)).groupby(["station", "local_hour"])
        total, count = g["_xs"].transform("sum"), g["_ok"].transform("sum")
        own, own_n = x.fillna(0), x.notna().astype(int)
        denom = count - own_n
        ev[f"clim_{nc}"] = ((total - own) / denom).where(denom > 0)
    return ev


def metric_row(sub, fc, nc):
    fg = metrics(sub[fc].to_numpy(float), sub[nc].to_numpy(float))
    # baseline scored on the same hours FortyGuard is scored on
    both = sub[sub[fc].notna() & sub[nc].notna()]
    base = metrics(both[f"clim_{nc}"].to_numpy(float), both[nc].to_numpy(float))
    return {**fg, "baseline_n": base["n"], "baseline_bias": base["bias"], "baseline_mae": base["mae"],
            "baseline_rmse": base["rmse"], "baseline_r": base["r"],
            "mae_skill_vs_baseline": 1 - fg["mae"] / base["mae"] if base["mae"] else np.nan}


def summarise(ev):
    rows = []
    for station in (*STATIONS, "ALL"):
        s = ev if station == "ALL" else ev[ev["station"] == station]
        for day_type, sub in (("all", s), ("advisory", s[s["advisory"]]), ("non_advisory", s[~s["advisory"]])):
            for var, (fc, nc, unit) in VARIABLES.items():
                rows.append({"station": station, "day_type": day_type, "variable": var, "unit": unit,
                             **metric_row(sub, fc, nc)})
    return pd.DataFrame(rows)


def by_hour(ev):
    rows = []
    for station in (*STATIONS, "ALL"):
        s = ev if station == "ALL" else ev[ev["station"] == station]
        for h in range(24):
            sub = s[s["local_hour"] == h]
            for var, (fc, nc, unit) in VARIABLES.items():
                rows.append({"station": station, "local_hour": h, "variable": var, "unit": unit,
                             **metric_row(sub, fc, nc)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- plots
def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axhline(0, color=TEXT2, linewidth=1)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlim(-0.5, 23.8)
    ax.set_xlabel("Local hour (America/New_York)", color=TEXT2, fontsize=9)


def plot_panel(ax, hr, var, unit, title):
    style(ax)
    for station in STATIONS:
        d = hr[(hr["station"] == station) & (hr["variable"] == var)].sort_values("local_hour")
        ax.plot(d["local_hour"], d["bias"], color=COLORS[station], linewidth=2, marker="o",
                markersize=5, markeredgecolor=SURFACE, markeredgewidth=1, label=station)
        last = d.dropna(subset=["bias"]).iloc[-1]
        ax.annotate(station, (last["local_hour"], last["bias"]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT)
    ax.set_ylabel(f"Bias, FortyGuard − NOAA ({unit})", color=TEXT2, fontsize=9)
    ax.set_title(title, color=TEXT, fontsize=10, loc="left")


def make_plots(hr):
    plt.rcParams["font.family"] = "DejaVu Sans"
    single = {"relative_humidity": "Relative humidity", "wet_bulb": "Wet-bulb temperature"}
    for var, title in single.items():
        fig, ax = plt.subplots(figsize=(8, 4.2), facecolor=SURFACE)
        plot_panel(ax, hr, var, VARIABLES[var][2], f"{title}: mean bias by local hour, Jul–Aug 2025")
        ax.legend(frameon=False, fontsize=9, labelcolor=TEXT, ncol=2,
                  loc="lower right", bbox_to_anchor=(1.0, 1.0), borderaxespad=0.2)
        fig.tight_layout()
        fig.savefig(RESULTS / f"bias_by_hour_{var}.png", dpi=150, facecolor=SURFACE)
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), facecolor=SURFACE, sharey=True)
    for ax, (var, label) in zip(axes, (("apparent_temperature_vs_metpy", "vs MetPy apparent_temperature"),
                                       ("apparent_temperature_vs_steadman", "vs Steadman/BoM AT"))):
        plot_panel(ax, hr, var, "°C", f"Apparent temperature {label}")
    axes[1].set_ylabel("")
    axes[0].legend(frameon=False, fontsize=9, labelcolor=TEXT, loc="upper left")
    fig.suptitle("Apparent temperature: mean bias by local hour, Jul–Aug 2025", color=TEXT, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(RESULTS / "bias_by_hour_apparent_temperature.png", dpi=150, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    RESULTS.mkdir(exist_ok=True)
    fg = load_fortyguard()
    routine, special = load_noaa("routine"), load_noaa("special")
    locs = pd.read_csv(ROOT / "data" / "locations.csv").set_index("id")["elevation_m"].to_dict()

    print("NOAA rows (routine / special):",
          {s: (int((routine.station == s).sum()), int((special.station == s).sum())) for s in STATIONS})
    print("routine rows without temperature or dewpoint (not matchable):",
          {s: int(routine[routine.station == s][["tmpf", "dwpf"]].isna().any(axis=1).sum()) for s in STATIONS})

    m = match(fg, routine)
    m = add_noaa_physics(m, locs)

    adv = pd.read_csv(ROOT / "data" / "nws" / "advisory_days.csv")
    adv_map = {(r.station, r.local_date): bool(r.heat_product_in_effect) for r in adv.itertuples()}
    m["advisory"] = [adv_map.get((s, d), False) for s, d in zip(m["station"], m["local_date"])]
    flags = flagged_days(routine)
    m["qa_flagged_day"] = [(s, d) in flags for s, d in zip(m["station"], m["local_date"])]

    cols = ["station", "local_time", "fg_time", "local_date", "local_hour", "matched", "obs_time",
            "offset_min", "advisory", "qa_flagged_day", "fg_rh", "fg_wb", "fg_at", "tmpf", "dwpf", "relh",
            "sknt", "alti", "noaa_t", "noaa_td", "noaa_rh", "noaa_ws_ms", "noaa_p_station_hpa", "noaa_wb",
            "noaa_hi", "noaa_e_hpa", "noaa_at_metpy", "noaa_at_steadman"]
    m[cols].to_csv(RESULTS / "matched_hourly.csv", index=False)

    print("\nmatching (±30 min, nearest routine METAR with T and Td):")
    for s in STATIONS:
        x = m[m.station == s]
        off = x.loc[x.matched, "offset_min"]
        print(f"  {s}: FortyGuard hours {len(x)}, matched {int(x.matched.sum())}, unmatched {int((~x.matched).sum())}; "
              f"offset min median {off.median():+.0f}, range {off.min():+.0f}..{off.max():+.0f}, "
              f"values {dict(off.value_counts().sort_index().astype(int))}")
    print("  sanity: |MetPy RH − IEM relh| max", f"{np.nanmax(np.abs(m.noaa_rh - m.relh)):.2f} %")

    ev = add_climatology_baseline(m[m.matched & ~m.qa_flagged_day])
    print("\nQA exclusion: flagged station-days", sorted(flags))
    for s in STATIONS:
        x = m[(m.station == s) & m.matched]
        print(f"  {s}: matched hours excluded as flagged-day {int(x.qa_flagged_day.sum())}, "
              f"kept {int((~x.qa_flagged_day).sum())}")

    summ = summarise(ev)
    hr = by_hour(ev)
    summ.to_csv(RESULTS / "accuracy_summary.csv", index=False, float_format="%.4f")
    hr.to_csv(RESULTS / "accuracy_by_hour.csv", index=False, float_format="%.4f")
    make_plots(hr)

    pd.set_option("display.width", 160)
    print("\naccuracy (FortyGuard − NOAA), all days:")
    print(summ[summ.day_type == "all"].drop(columns="day_type").to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nFortyGuard vs leave-one-day-out NOAA climatology baseline (same hours), all days:")
    print(summ[summ.day_type == "all"][["station", "variable", "n", "mae", "baseline_mae", "rmse", "baseline_rmse",
                                        "mae_skill_vs_baseline"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nadvisory vs non-advisory:")
    print(summ[summ.day_type != "all"].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    at = summ[(summ.day_type == "all") & summ.variable.str.startswith("apparent")]
    print("\napparent temperature candidate fit (all days):")
    print(at[["station", "variable", "bias", "mae", "rmse", "r", "n"]].to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
