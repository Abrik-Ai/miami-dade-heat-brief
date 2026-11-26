# PLAN

## Goal
An n8n agent that uses the FortyGuard Temperature MCP to produce a daily heat-risk brief for
Miami-Dade. Fixed rules decide the risk level, the LLM explains it, and code checks every number
before a brief is sent. The data is validated against NOAA stations, and the agent is replayed
on summer 2025 against the heat advisories the NWS actually issued.

## Current step
Steps 1–7 (data validation and replay) are done; results are in `notes/results-summary.md`.
Next: interpret the results and decide the risk rules.

## Done
1. **FortyGuard reference-temperature test.** Only `heat_index_celsius` depends on the reference
   temperature, and it matches the NWS formula within 0.1 °C. FortyGuard returns no air temperature.
2. **Stations.** KMIA and KHST coordinates from IEM FL_ASOS. Hourly coverage Jun–Sep 2025:
   0.34 % / 6.80 % missing.
3. **NWS products.** Zones FLZ074 and FLZ173; only Heat Advisories in Jun–Sep 2025; 11 advisory
   days per station, the same dates at both.
4. **FortyGuard Jul–Aug 2025 replay data.** 124 MCP calls; 2 lost but charged. Re-fetched by
   activity_id over REST (free) into `data/raw_api/`, now the source of truth; 0 differences
   from the retyped copies.
5. **REST.** Recovered the 2 lost days with POST `/v1/env_params`; a repeat request is
   byte-identical apart from activity_id. All 124 station-days present.
6. **Accuracy vs NOAA.** RH, wet-bulb and apparent temperature by station, hour and advisory
   day. Steadman/BoM fits FortyGuard's apparent temperature better by MAE/RMSE, MetPy better by r.
7. **Baseline, implied T, threshold, replay.** Leave-one-day-out climatology baseline; implied air
   temperature from FortyGuard wet-bulb + RH (all converged); NWS MFL criterion documented
   (`notes/thresholds.md`); advisory replay at 103/105/108 °F.

## Next
- [ ] Interpret steps 6–7 (`notes/results-summary.md`). Decide whether the brief's risk rules
      use wet-bulb, apparent temperature, implied heat index, or a combination, and which
      threshold.
- [ ] Decide whether to keep the 105 °F / 2 h NWS criterion as the replay target, given that
      NOAA observations alone reach it on no 2025 advisory day.
- [ ] README: fill "Why Miami-Dade" (the decision the brief supports, with thresholds and
      sources) and "Results".
- [ ] Build the n8n workflow: schedule → AI agent + FortyGuard MCP → rules → LLM brief →
      validator → Telegram.
- [ ] Number validator: every number in a brief must trace back to a FortyGuard or NOAA value.
- [ ] Replay the agent's risk levels against NWS advisories (hit rate, FAR, CSI).
- [ ] Open questions for FortyGuard (`notes/mcp-field-notes.md`): the meaning of the reference
      temperature, a source of hourly air temperature, and the apparent temperature definition.
- [ ] Tidy up: `README.md.save` (editor autosave, not committed) can be deleted.

## Log
- 2026-11-22: Steps 1–3. Reference-temperature test, station metadata, NWS zones and products.
- 2026-11-23/24: Step 4. 124 MCP calls (359,600 credits, 2 lost); REST re-fetch of 122 (free),
  0 differences.
- 2026-11-25: Step 5, REST recovery of 2 days and repeatability check (8,700 credits; balance
  625,900). Steps 6–7, accuracy, baseline, implied T, thresholds, replay.
