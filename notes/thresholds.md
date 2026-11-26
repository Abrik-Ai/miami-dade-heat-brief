# NWS Miami (MFL) Heat Advisory criteria used for the 2025 replay

## Criterion used (primary rule)

**Heat index ≥ 105 °F (40.6 °C) for at least 2 hours in the day**, Miami-Dade public
zones, including FLZ074 Metro Miami-Dade (KMIA) and FLZ173 Coastal Miami-Dade (KHST).
This is the NWS MFL pilot criterion. Decided by the user on 2026-11-25.

The 2025 rule text itself was **not found on an NWS page**. The criterion comes from the
official 2024 NWS MFL page. That the pilot was still in use in 2025 rests on the sources
below (one news article, one county document that could not be retrieved).

## 1. Official NWS MFL page (2024)

URL: https://www.weather.gov/mfl/HeatCriteriaChangeBroward2024
Title: "New Experimental Heat Advisory/Warning Criteria for Broward County"
Retrieved: 2026-11-25 (HTTP 200)

Exact wording:

> ...The National Weather Service Miami Forecast Office Will Test New Heat Advisory and Excessive Heat Warning Criteria for the 2024 Heat Season...
>
> Broward County will now have the same heat advisory/excessive heat warning criteria as Miami-Dade County (Table 1), which is as follows for each public zone in those counties:
>
> Heat Advisory : Heat Index of 105F or higher for at least 2 hours
>
> Excessive Heat Warning : Heat Index of 110F or higher for at least 2 hours

Table 1 lists FLZ073 Inland Miami-Dade, FLZ074 Metro Miami-Dade, FLZ173 Coastal Miami-Dade,
FLZ174 Far South Miami-Dade, and the Broward zones.

> The remaining WFO Miami public forecast zones below (Table 2) will continue with the existing heat advisory/excessive heat warning criteria ( Heat Advisory - Heat Index 108F or higher for at least 2 hours; Excessive Heat Warning - Heat Index 113F or higher for at least 2 hours)
>
> Evaluation of this experiment will take place during and after the 2024 heat season to determine if these changes will become official policy in future years for parts or all of the WFO Miami service area.

## 2. Confirmation that the pilot was in use in 2025

### WLRN (news, 2025-06-27)

URL: https://www.wlrn.org/2025-06-27/what-does-a-heat-advisory-and-excessive-heat-warning-really-mean-nws-heat-alerts-explained
Title: "What does a heat advisory and excessive heat warning really mean? NWS heat alerts explained"
By William Maxham (FPREN), published June 27, 2025 at 10:23 AM EDT. Retrieved 2026-11-25 (HTTP 200).

Exact wording:

> Heat alert criteria are slightly different in the Miami metro area. In Miami-Dade and Broward counties, the thresholds for heat alerts are a bit lower. A heat advisory is issued when the heat index values will be greater than 105 degrees for two hours. Excessive heat warnings are issued when heat index values over 110 degrees are expected.

(WLRN writes "greater than 105"; the NWS page writes "105F or higher". The replay uses ≥.)

### Miami-Dade County, 2025 Heat Season Summary

URL: https://www.miamidade.gov/environment/library/heat/2025-heat-season-summary.pdf
**Could not be retrieved:** HTTP 404 on 2026-11-25 (with and without a browser user agent),
so its wording could not be checked. A web-search snippet of it reads: "The County's
partnership with the National Weather Service (NWS) resulted in piloting a lowered heat
advisory and warning threshold in Miami-Dade County." The snippet gives no numbers.

## 3. Related official NWS documents (no criterion stated)

- NWS MFL Summer 2025 Summary, https://www.weather.gov/media/mfl/news/Summer2025Summary.pdf
  (retrieved 2026-11-25): "Heat advisories were issued for the following number of days per
  county this summer: Miami-Dade: 11 (40 at this time in 2024)". Also: "No Excessive Heat
  Warnings were issued." It refers to graphs of "hours with heat index values at or above
  105F" without calling 105F the criterion. The 11 days match data/nws/advisory_days.csv.
- NWS MFL Heat Advisory product, 2025-08-27 (WWUS72 KMFL 270704, via IEM,
  data/nws/raw/iem_vtec_event_MFL_2025_HT_Y_12.json): "Heat index values up to 108 expected."
- https://www.weather.gov/mfl/HeatCriteriaChange (original Miami-Dade pilot page): HTTP 404.
- https://www.weather.gov/mfl/heat: no thresholds.
- https://weather.gov/media/mfl/news/TempWildfireWeb_2025.pdf: mentions 105F only in a 2023 statistic.

## Replay rules derived from this (scripts/replay_advisories.py)

- Primary: a station-day counts as an advisory day if heat index ≥ threshold in at least
  2 hours of that local day (not necessarily consecutive).
- Variant: at least 2 consecutive hours.
- Sensitivity: thresholds 103, 105 and 108 °F.
