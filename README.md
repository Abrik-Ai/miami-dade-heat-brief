# Miami-Dade Heat Brief

An n8n agent that uses the FortyGuard Temperature MCP to produce a daily heat-risk brief for Miami-Dade.
Fixed rules decide the risk level, the LLM explains it, and code checks every number before a brief is sent.
The data is checked against NOAA weather stations, and the agent is replayed on summer 2025 against the heat advisories the National Weather Service actually issued.

> Status: in progress. Sections marked TODO are not built yet.

## Why Miami-Dade
Miami-Dade has long, humid heat seasons, and humidity is what makes heat dangerous for outdoor workers.
TODO: name the one decision the brief supports (e.g. work/rest scheduling for outdoor crews) and cite the official thresholds used.

## What I found about the data
Before building anything, I checked what FortyGuard's `env_params` tool returns.

- One call returns one point for one day, as 24 hourly values (local time, America/New_York). It costs 2,900 credits.
- **`heat_index_celsius` depends on the reference temperature the user sends.** Recomputing it with the NWS heat index formula from the constant reference temperature (33 °C) and the hourly humidity reproduces all 24 values within 0.1 °C. It therefore peaks at 07:00, when humidity is highest, instead of in the afternoon.
- **Controlled test:** same point and day, reference temperature 33 °C vs 28 °C. Only `heat_index_celsius` changed; every other hourly field was identical.
- The response contains no measured air temperature.

**Decision:** the risk rules use wet-bulb temperature and apparent temperature. Heat index is recomputed from real NOAA air temperature and humidity.

Full notes: [notes/mcp-field-notes.md](notes/mcp-field-notes.md)

## Ground truth
| Station | Name | Lat, Lon | Missing hours, Jun–Sep 2025 |
|---|---|---|---|
| KMIA | Miami International Airport | 25.788, -80.3169 | 0.34% |
| KHST | Homestead AFB | 25.4884, -80.3837 | 6.80% |

Source: Iowa Environmental Mesonet ASOS network metadata (FL_ASOS).
FortyGuard is queried at these exact coordinates so both sources describe the same place.
Limitation: airports are open and windy, so they do not show the hottest streets; some difference from a hyperlocal model is expected.

## Results
TODO
- Accuracy: FortyGuard vs NOAA (humidity, wet-bulb, apparent temperature), error and bias per hour
- Replay: agent risk levels vs NWS heat advisories, summer 2025 (hit rate, false-alarm rate, CSI)
- Validator: briefs checked, numbers caught

## How it works
TODO: diagram and n8n workflow screenshot (schedule → AI Agent + FortyGuard MCP → rules → LLM brief → validator → Telegram)

## Run it yourself
```bash
git clone https://github.com/Abrik-Ai/miami-dade-heat-brief
cd miami-dade-heat-brief
uv sync
cp .env.example .env   # add your FORTYGUARD_API_KEY
```
TODO: n8n setup, tests, replay

## Repository layout
- `data/locations.csv` — station coordinates with sources
- `data/raw/` — raw FortyGuard responses (not committed)
- `data/raw_api/` — FortyGuard REST response bodies, the source of truth for analysis (not committed)
- `results/` — aggregate metrics and charts. Per-hour and per-day files with FortyGuard values (`matched_hourly.csv`, `implied_temperature_hourly.csv`, `replay_daily.csv`) are not committed. Regenerate them locally with a FortyGuard API key in `.env`: fetch with `scripts/fetch_env_rest.py`, then run `scripts/eval_accuracy.py`, `scripts/implied_temperature.py` and `scripts/replay_advisories.py`.
- `data/noaa/`, `data/nws/` — station observations and advisory archive
- `notes/mcp-field-notes.md` — findings from using the MCP as a new user
- `PLAN.md` — goal, current step, log

## Acknowledgements
Data from the FortyGuard Temperature API and MCP, NOAA ASOS stations via the Iowa Environmental Mesonet, and the National Weather Service.
