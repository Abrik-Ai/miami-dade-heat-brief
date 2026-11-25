# FortyGuard MCP — field notes

Notes from using the FortyGuard Temperature MCP as a new user, written as I go.
Each note: what I did, what I saw, and why it matters.

## Setup
- 2026-11-22: Connected the MCP to Claude Code with `claude mcp add --transport http` and an `Authorization: Bearer` header. All 9 tools appeared.
- The REST API uses an `api-key` header, but the MCP uses `Authorization: Bearer <key>`. The docs mention this, but it is easy to mix up when switching between the two.
- Claude Code found a `credit_balance` tool. The docs say the catalog has 9 tools and do not list it. Check whether it is undocumented.

## Cost
- `env_params` costs 2,900 credits per call on Premium (shown in `trace.cost_credits`). One call returns one point for one day, as 24 hourly values.
- Responses do not include the remaining balance. The balance is only visible in the dashboard.

## env_params findings
1. **heat_index_celsius depends on the reference temperature I send.**
   Recomputed with the NWS heat index formula from the constant reference temperature (33 °C) and the hourly relative humidity: all 24 values match within 0.1 °C.
   As a result, the "heat index" peaks at 07:00 (48.6 °C), when humidity is highest, not in the afternoon.
   The response contains no measured air temperature; the only `temperature` field is the input value.
2. **Controlled test confirms it.** Same point (Miami 25.7617, -80.1918), same day (2025-08-15), reference temperature 33 °C vs 28 °C: only `heat_index_celsius` changed. All other hourly fields were identical.
3. The summary block (`result.value.parameters`) is the first hour's value (`basis: first_hour_snapshot`, 00:00 local), although it looks like a daily summary.
4. Air-quality field names are inconsistent: most use `air_quality_*:idx`, but CO is `aqi_us_co`.
5. `heat_index_celsius` appears only in the hourly series, not in the summary block.
6. Timestamps are local time (America/New_York, UTC−4 in August), not UTC.
7. MCP calls that run past 120 s drop, and the credits are still charged (2 calls, 5,800 credits).
8. MCP latency is about 7.6 s per call on average (median 7.3 s, range 4.3–13.1 s).
## Questions for FortyGuard
- What is the reference temperature meant to represent, and how should a user choose it?
- Is there a way to get the hourly air temperature for a point?

## Project decisions that follow
- Risk rules use `wet_bulb_temperature_celsius` and `apparent_temperature_celsius`, not `heat_index_celsius`.
- Heat index is recomputed from NOAA hourly air temperature and humidity.
- Accuracy check: compare FortyGuard humidity, wet-bulb and apparent temperature with the same quantities computed from NOAA KMIA and KHST observations.
