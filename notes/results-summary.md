# Results summary, steps 1–7

Written 2026-11-25. Numbers only; interpretation comes later. All results can be reproduced
from the committed scripts and data (see "Reproduce" at the end).

Stations: KMIA (Miami Intl Airport, 25.788, −80.3169, 4 m) and KHST (Homestead AFB,
25.4884, −80.3837, 2 m), from the IEM FL_ASOS station metadata (`data/locations.csv`).
FortyGuard period: 2025-07-01 to 2025-08-31, both stations, 124 station-days.

---

## 1. FortyGuard reference-temperature test (step 1)

Same point (Miami downtown, 25.7617, −80.1918) and day (2025-08-15), reference temperature
33 °C vs 28 °C (`scripts/compare_ref.py`).

- Only `heat_index_celsius` changed (max |diff| 16.4 °C). All other 14 hourly fields and the
  non-hourly fields were identical.
- The change matches the NWS heat index formula: residuals ≤ 0.10 °C (base 0.09, new 0.10,
  delta 0.10).
- Conclusion carried forward: FortyGuard's heat index is computed from the caller's reference
  temperature and FortyGuard RH. It is not an observation, and FortyGuard returns no air temperature.

## 2. NOAA station coverage (step 2)

IEM ASOS routine hourly reports, 2025-06-01 to 2025-09-30 (2,928 local hours):

| Station | Rows | Missing hours |
|---|---|---|
| KMIA | 2,918 | 10 (0.34 %) |
| KHST | 2,729 | 199 (6.80 %) |

## 3. NWS heat products (step 3)

- Zones (NWS points API): KMIA is in FLZ074 Metropolitan Miami Dade, KHST is in FLZ173 Coastal
  Miami Dade County (WFO MFL). Both zones carry `effectiveDate` 2026-04-16 in the API. IEM's
  by-point search returned the same 2025 events.
- IEM VTEC, 2025-06-01 to 2025-09-30: **only Heat Advisories (HT.Y)**. There were no EH.W, EH.A,
  XH.W or XH.A for either zone.
- 12 HT.Y events. #11 was issued 2025-08-27 06:59Z and cancelled at 07:02Z, before onset, then
  replaced by #12. It has `in_effect=False` and is excluded from advisory days.
- **11 advisory days per station**, the same dates at both: 07-18, 07-21, 07-31, 08-01 to 08-06,
  08-20, 08-27. All products cover part of the day (mostly 11:00–19:00 local, 6–9.4 h).
- Cross-check: the NWS MFL Summer 2025 Summary reports "Miami-Dade: 11" Heat Advisory days.
- Files: `data/nws/zones.csv`, `data/nws/heat_products.csv`, `data/nws/advisory_days.csv`,
  raw responses in `data/nws/raw/`.

## 4. FortyGuard data collection and integrity (steps 4–5)

### NOAA quality flags, Jul–Aug (used as exclusions later)
Station-days with more than 3 missing local hours, or any missing hour from 12:00 to 18:00:
- KMIA: 2025-07-16 (1 day)
- KHST: 07-01, 07-02, 07-19, 07-24, 07-28, 08-06, 08-19, 08-27, 08-28, 08-29, 08-30, 08-31
  (12 days; 08-30 and 08-31 have no NOAA data at all)

### MCP collection (124 calls)
- 124 `env_params` calls made over MCP (reference temperature 33 °C, single day): 122 succeeded,
  **2 failed**: KHST 2025-07-09 and KHST 2025-08-17. Both ran over 120 s, the MCP transport
  dropped and the response was lost. **Both were still charged.**
- Credits: 359,600 (124 × 2,900, premium plan). Mean latency 7,556 ms (median 7,329, range
  4,320–13,109).

### Source of truth: REST bytes (`data/raw_api/`)
- The MCP responses could only be saved by Claude retyping them (`data/raw/`, not in git), so
  they are not the source of truth.
- All 122 were re-fetched by activity_id with `GET /v1/status/{activity_id}` and saved
  byte for byte (`scripts/fetch_by_activity.py`). **Free:** balance unchanged at 634,600.
  122 × HTTP 200, mean latency 696 ms.
- `scripts/compare_raw.py`: **43,920 hourly values, 0 differences** between REST and the retyped
  copies. Activity IDs, timestamps, field sets, coordinates, elevation, reference temperature
  and solar irradiance also identical.
- `scripts/check_heat_index.py`: FortyGuard `heat_index_celsius` vs NWS formula from 33 °C and
  FortyGuard RH, 2,928 values: **max |diff| 0.099 °C**, mean 0.033, all within 0.1 °C.

### Lost days recovered over REST (step 5)
`scripts/fetch_env_rest.py` (POST `/v1/env_params`, then poll `/v1/status`):

| Station-day | Time | Credits |
|---|---|---|
| KHST 2025-07-09 | 8.6 s, 1 poll | 2,900 |
| KHST 2025-08-17 | 8.8 s, 1 poll | 2,900 |
| KMIA 2025-08-03 (repeatability check) | 8.4 s, 1 poll | 2,900 |

`data/raw_api/` now holds all **124 station-days**, each 15 fields × 24 h, with no nulls.

### Repeatability (step 5)
KMIA 2025-08-03 requested twice: once started via MCP, once via REST, both saved from REST
(`scripts/compare_api_bodies.py`).
- Byte-identical once `data.activity_id` is masked (both 3,492 bytes).
- Structure, JSON types, key order and the 20 non-hourly values are identical except activity_id.
  All 360 hourly values are identical.

### Credits overall
Balance 994,200 before the 124 MCP calls → **625,900** after step 5. Spent: 359,600 (MCP,
including 5,800 on the two lost calls) + 8,700 (REST). Step 1 also used 2,900 before that.

## 5. Accuracy: FortyGuard vs NOAA (step 6)

Matching: each FortyGuard local hour is matched to the nearest routine METAR within ±30 min
that has both T and Td.

| | KMIA | KHST |
|---|---|---|
| FortyGuard hours | 1,488 | 1,488 |
| Matched | 1,487 | 1,406 |
| Unmatched | 1 | 82 |
| Offset (obs − hour) | median −7 min (−7/−6) | median −5 min (−30 to 0) |
| Excluded (QA-flagged days) | 23 | 215 |
| **Evaluated** | **1,464** | **1,191** |

Accuracy (FortyGuard − NOAA), all evaluated days, with the leave-one-day-out NOAA climatology
baseline (step 7A) scored on the same hours. Skill = 1 − MAE_FG / MAE_baseline.

| Station | Variable | n | Bias | MAE | RMSE | r | Baseline MAE | Baseline RMSE | Skill |
|---|---|---|---|---|---|---|---|---|---|
| KMIA | RH (%) | 1,464 | +4.97 | 7.82 | 9.61 | 0.792 | 5.91 | 7.70 | −0.32 |
| KMIA | Wet-bulb (°C) | 1,464 | −0.21 | 0.72 | 0.93 | 0.529 | 0.71 | 0.90 | −0.02 |
| KMIA | AT vs MetPy (°C) | 1,460 | +0.36 | 2.07 | 2.88 | 0.734 | 2.69 | 3.48 | +0.23 |
| KMIA | AT vs Steadman (°C) | 1,460 | +0.42 | 1.90 | 2.46 | 0.618 | 1.56 | 2.05 | −0.22 |
| KHST | RH (%) | 1,191 | +4.20 | 6.96 | 8.63 | 0.833 | 5.13 | 6.68 | −0.36 |
| KHST | Wet-bulb (°C) | 1,191 | −0.15 | 0.71 | 0.96 | 0.514 | 0.69 | 0.91 | −0.03 |
| KHST | AT vs MetPy (°C) | 1,191 | +0.86 | 2.43 | 3.20 | 0.751 | 2.71 | 3.43 | +0.10 |
| KHST | AT vs Steadman (°C) | 1,191 | +0.14 | 1.82 | 2.42 | 0.627 | 1.56 | 2.09 | −0.17 |
| Both | RH (%) | 2,655 | +4.62 | 7.43 | 9.18 | 0.810 | 5.56 | 7.26 | −0.34 |
| Both | Wet-bulb (°C) | 2,655 | −0.18 | 0.72 | 0.95 | 0.524 | 0.70 | 0.91 | −0.02 |
| Both | AT vs MetPy (°C) | 2,651 | +0.58 | 2.23 | 3.03 | 0.742 | 2.70 | 3.46 | +0.17 |
| Both | AT vs Steadman (°C) | 2,651 | +0.30 | 1.86 | 2.44 | 0.622 | 1.56 | 2.07 | −0.20 |

Apparent-temperature definition (FortyGuard doesn't document it): **Steadman/BoM fits better by
MAE and RMSE** at both stations and overall. **MetPy fits better by correlation** (0.742 vs 0.622),
and also by MAE/RMSE on advisory days only (1.73 / 2.32 vs 1.80 / 2.36).

Advisory vs non-advisory days, both stations (bias / MAE / RMSE / r):

| Variable | Advisory (n = 479) | Non-advisory (n = 2,176) |
|---|---|---|
| RH (%) | +4.12 / 8.63 / 10.37 / 0.846 | +4.73 / 7.17 / 8.90 / 0.800 |
| Wet-bulb (°C) | −0.13 / 0.61 / 0.78 / 0.573 | −0.19 / 0.74 / 0.98 / 0.506 |
| AT vs MetPy (°C) | +0.06 / 1.73 / 2.32 / 0.799 | +0.70 / 2.34 / 3.16 / 0.724 |
| AT vs Steadman (°C) | +0.50 / 1.80 / 2.36 / 0.672 | +0.25 / 1.88 / 2.46 / 0.598 |

Bias by local hour (`results/bias_by_hour_*.png`, `results/accuracy_by_hour.csv`):
- RH: about +7 to +10 % overnight; about −1.5 % (KMIA) and −3.5 % (KHST) at 13–14 h.
- Wet-bulb: −0.84 °C (KMIA, 07 h) to +0.43 °C (KMIA, 13 h).
- AT vs Steadman: about −1.8 °C near 07 h to about +3.9 °C (KMIA, 14 h).
- AT vs MetPy: −1.0 °C (10 h, 17 h) to +2.6 °C (KHST, 07 h).

## 6. FortyGuard-implied air temperature (step 7B)

For each hour, T is solved so that MetPy `wet_bulb_temperature(p, T, Td(T, RH_FG))` equals
FortyGuard wet-bulb (`scripts/implied_temperature.py`). Solver: brentq on [Tw, Tw + 25 °C],
xtol 1e-4. p is the NOAA station pressure of the matched METAR (station median if unmatched).

- Converged: **2,976 / 2,976** (also in both ±5 RH cases). Reproduces FortyGuard wet-bulb to
  within 0.00002 °C.

| Implied T − NOAA T | n | Bias | MAE | RMSE | r |
|---|---|---|---|---|---|
| KMIA | 1,464 | −0.94 | 1.56 | 1.94 | 0.823 |
| KHST | 1,191 | −0.74 | 1.39 | 1.81 | 0.837 |
| Both | 2,655 | −0.85 | 1.48 | 1.89 | 0.829 |

- Bias by hour (both): −1.5 to −1.8 °C at 00–08 h, −0.21 at 11 h, +0.80 / +0.81 at 13–14 h,
  −0.77 at 19 h, −1.50 at 23 h.
- RH sensitivity (±5 percentage points): RH+5 changes implied T by −0.78 °C on average (range
  −1.52 to 0.00); RH−5 by +0.85 °C (+0.61 to +1.72). Bias vs NOAA becomes −1.63 °C (RH+5) and
  +0.005 °C (RH−5). In the +5 case, 238 evaluated hours have RH > 95 % and were capped at 100 %.

## 7. Advisory replay, July–August 2025 (step 7D)

Rules, per station and local day (00–23): (1) NOAA-observed heat index (MetPy), (2) heat index
from FortyGuard-implied T + FortyGuard RH, (3) FortyGuard apparent temperature against the same
threshold. An advisory day is the threshold reached in **at least 2 hours** of the day (primary),
or **at least 2 consecutive hours** (variant). Truth: `data/nws/advisory_days.csv`.

Primary day set ("common"): station-days not QA-flagged, the same for all rules. That is 61 days
for KMIA (11 advisory) and 50 for KHST (9 advisory; the advisory days 08-06 and 08-27 are flagged).

### 105 °F, ≥ 2 h (primary)

| Rule | Station | H | M | FA | CN | Hit rate | FAR | CSI |
|---|---|---|---|---|---|---|---|---|
| NOAA observed HI | KMIA | 0 | 11 | 0 | 50 | 0.00 | – | 0.00 |
| NOAA observed HI | KHST | 0 | 9 | 0 | 41 | 0.00 | – | 0.00 |
| FG implied HI | KMIA | 2 | 9 | 2 | 48 | 0.18 | 0.50 | 0.15 |
| FG implied HI | KHST | 0 | 9 | 0 | 41 | 0.00 | – | 0.00 |
| FG apparent temp | KMIA | 2 | 9 | 2 | 48 | 0.18 | 0.50 | 0.15 |
| FG apparent temp | KHST | 0 | 9 | 1 | 40 | 0.00 | 1.00 | 0.00 |

The consecutive-hours variant is identical at 105 °F.

Misses and false alarms at 105 °F, ≥ 2 h:
- NOAA, KMIA misses: all 11 (07-18, 07-21, 07-31, 08-01 to 08-06, 08-20, 08-27). KHST misses:
  07-18, 07-21, 07-31, 08-01 to 08-05, 08-20.
- FG implied, KMIA: misses 07-18, 07-21, 07-31, 08-01, 08-02, 08-04, 08-06, 08-20, 08-27; FA
  08-17, 08-19. KHST: misses 07-18, 07-21, 07-31, 08-01 to 08-05, 08-20.
- FG apparent, KMIA: misses 07-18, 07-21, 07-31, 08-01 to 08-04, 08-06, 08-20; FA 08-17, 08-19.
  KHST: misses 07-18, 07-21, 07-31, 08-01 to 08-05, 08-20; FA 08-22.
- NOAA heat index ≥ 105 °F occurred in only 6 hours (KMIA) and 5 hours (KHST), never twice on
  one day. Max 107.6 °F (KMIA), 106.4 °F (KHST).

### Threshold sensitivity (H/M/FA/CN, CSI; ≥ 2 h, common days)

| Rule | Station | 103 °F | 105 °F | 108 °F |
|---|---|---|---|---|
| NOAA observed | KMIA | 6/5/9/41, 0.30 | 0/11/0/50, 0.00 | 0/11/0/50, 0.00 |
| NOAA observed | KHST | 2/7/4/37, 0.15 | 0/9/0/41, 0.00 | 0/9/0/41, 0.00 |
| FG implied | KMIA | 8/3/10/40, 0.38 | 2/9/2/48, 0.15 | 0/11/1/49, 0.00 |
| FG implied | KHST | 4/5/2/39, 0.36 | 0/9/0/41, 0.00 | 0/9/0/41, 0.00 |
| FG apparent | KMIA | 7/4/10/40, 0.33 | 2/9/2/48, 0.15 | 0/11/0/50, 0.00 |
| FG apparent | KHST | 3/6/3/38, 0.25 | 0/9/1/40, 0.00 | 0/9/0/41, 0.00 |

The consecutive variant differs only for NOAA KMIA at 103 °F: 5/6/9/41, CSI 0.25.
`all_days` (flagged days included): NOAA 0 hits at both stations; FortyGuard gains 1–2 KHST false
alarms. All combinations are in `results/replay_contingency.csv`.

## 8. Thresholds and sources (step 7C, `notes/thresholds.md`)

- Used: **heat index ≥ 105 °F (40.6 °C) for at least 2 hours**, the NWS MFL pilot criterion for
  the Miami-Dade zones (FLZ073/074/173/174). User decision, 2026-11-25.
- Official source (2024): https://www.weather.gov/mfl/HeatCriteriaChangeBroward2024 — "Heat
  Advisory : Heat Index of 105F or higher for at least 2 hours". Described there as a test, to
  be evaluated "during and after the 2024 heat season".
- 2025 confirmation: WLRN, 2025-06-27 (news, not NWS): "A heat advisory is issued when the heat
  index values will be greater than 105 degrees for two hours." The Miami-Dade County 2025 Heat
  Season Summary PDF (user-provided URL) returned **HTTP 404** and could not be quoted.
- **The 2025 rule text was not found on an NWS page.** weather.gov/mfl/HeatCriteriaChange is 404;
  the 2025 NWS products and summaries don't state the criterion.

## 9. Method choices

- FortyGuard reference temperature fixed at 33 °C for every call; it only affects
  `heat_index_celsius`, which is not used as an observation.
- Source of truth for FortyGuard: `data/raw_api/` (REST bytes). `data/raw/` holds retyped MCP
  copies for comparison only (not in git).
- NOAA: IEM ASOS routine METARs only for matching (specials downloaded, not matched), UTC
  download, converted to America/New_York.
- Station pressure from altimeter setting + station elevation (MetPy
  `altimeter_to_station_pressure`), because IEM provides no station pressure. Used for wet-bulb
  and the implied-T solve.
- NOAA RH from T and Td (MetPy); heat index MetPy `heat_index(mask_undefined=False)`.
- Apparent temperature candidates: MetPy `apparent_temperature`; Steadman/BoM
  AT = Ta + 0.33 e − 0.70 ws − 4.00 with e = RH/100 · 6.105 · exp(17.27 Ta/(237.7 + Ta)), ws =
  ASOS 10 m wind in m/s.
- QA exclusion: every hour on the 13 NOAA-flagged station-days is excluded from the accuracy
  metrics and the "common" replay set (an interpretation of "NOAA-flagged hours").
- Baseline: leave-one-day-out mean of NOAA values at the same station and local hour, over the
  evaluation days only (Jul–Aug 2025).
- Replay: whole local day 00–23; NOAA heat index from matched hourly METARs; RH ±5 means
  percentage points, capped at 100 %.

## 10. Caveats

- NWS advisories are issued from forecasts; the replay uses observations (NOAA) and FortyGuard
  values for the same day.
- Advisories are per zone; each station is one point in its zone.
- Two of KHST's 11 advisory days (08-06, 08-27) fall on QA-flagged days and are excluded from the
  primary replay set.
- The baseline is in-sample climatology from the same two months, not an independent forecast.
- FortyGuard provides no air temperature; implied T inherits errors in FortyGuard RH and
  wet-bulb (sensitivity above).
- MetPy `heat_index` differs from the NWS formula by up to 2.2 °F, but only at 77–79 °F air
  temperature (HI ≈ 79–81 °F), well away from 103–108 °F.
- One IEM observation (KMIA 2025-07-07 10:53 UTC) has `relh` 96.7 % inconsistent with its own
  T/Td (80/77 °F); MetPy's RH from T/Td is used.
- The NWS API shows both zones with `effectiveDate` 2026-04-16; the 2025 events were found under
  the same zone codes.
- `logs/` (MCP and REST call logs with credits, latency and activity IDs) is excluded by
  `.gitignore` and exists only locally.

## Reproduce

```bash
uv run scripts/eval_accuracy.py         # matching, NOAA physics, accuracy + baseline, PNGs
uv run scripts/implied_temperature.py   # ~2 min
uv run scripts/replay_advisories.py
uv run scripts/compare_raw.py           # needs data/raw/ (local only)
uv run scripts/check_heat_index.py
uv run scripts/compare_api_bodies.py data/raw_api/KMIA_2025-08-03.json data/raw_api/_rest_check/KMIA_2025-08-03.json
```
