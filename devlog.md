# DEVLOG — BUP Fuel Supply Simulator MVP

The single project log (owner decision 2026-09-29: **one Markdown file only** — progress, simulator semantics, decisions, results all live here). Read this first, then update it before you stop.

## How to use this file

1. Read **Current status** and **Next up**.
2. Do the work.
3. Append a dated entry to **Log** (newest on top): what changed, files touched, how it was verified, open issues.
4. Update **Current status**, **Milestones**, **Simulator semantics**, **Next up**, and **Decisions** if they changed.

Record only what was actually done and verified — no planned work written as finished, no invented results.

## Source documents

| File | Role |
|---|---|
| `BUP_Fuel_Supply_Deterministic_MVP_Full_Plan2.md` | Implementation plan (Revision 3 + phase-boundary correction). No-AI/ML boundary in §1.2, milestones in §17, definition of done in §22, deferred AI/ML work in §25. |
| `BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md` | Authoritative simulator API contract. Wins over the plan on any conflict. |
| `Problem_Statement_BUP_CSE_Fest_2026.pdf` | **Official problem statement and requirements** (11 pages; received 2026-09-29, after implementation had started). Defines deliverables (§19) and evaluation weights (§23). |

## Project constraints

- **This phase: complete everything that needs no AI/ML. Anything needing AI/ML is deferred to the next phase (plan §25).**

  | Where AI/ML would usually go | What this phase uses instead |
  |---|---|
  | Demand forecasting | Published demand-profile formula (plan §8.2) × hour factor × region factor × multiplier, plus a hand-set stress multiplier |
  | Decision policy (RL, learned policy) | Receding-horizon linear (mixed-integer only if needed) optimization with SciPy/HiGHS (plan §9) |
  | "Continuously improve" | Re-solving every decision cycle, plus offline sensitivity sweeps that a person tunes by hand |
  | Explanations (LLM) | Text templates filled from binding constraints (plan §13.4) |
  | Use of history | Validation and residual reporting only (plan §8.1) |
- Stack: Python 3.12 + HTTPX + SciPy (+ FastAPI later); React + TS + Vite + shadcn/ui + Tailwind (Milestone 4).
- Simulator image `asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, unchanged, HTTP only.
- One operational writer. Never label a heuristic "optimal". Never show fake data as live.

## How to run

```bash
docker compose up -d                      # simulator on http://localhost:18000 (SIM_PORT to change)
.venv/Scripts/python.exe -m fuelops.probes c01 c06   # contract probes (reset the simulator!)
.venv/Scripts/python.exe -m fuelops.harness threshold none --ticks 672   # stepped benchmark → reports/
```

Python venv: `.venv` (created from `%LOCALAPPDATA%\Programs\Python\Python312`). Deps: `requirements.txt`.

## Current status

- Date: 2026-09-29. Plan Revision 4 executed within the 24-hour cut (D2). **Milestones M3–M9 done**; the AI/ML phase (plan §25) is deferred by owner decision.
- Run: `cp .env.example .env && docker compose up -d --build` → app http://localhost:8100, Grafana :3000, Prometheus :9090 (README).
- Verified: 11 automated tests pass; full stack builds and runs healthy **from a clean clone** (separate compose project); CI workflow pushed (repo is private — check the Actions tab for the first run result).
- Decision quality: LP within 3 L of the perfect-hindsight bound over 7 simulated days (stepped); live, lp-buffer serves 100% over 4.2 days and through a ×2.2 spike combined with a primary-route disruption (0 FAILED shipments).
- Load: realistic profile 128 req/s, 0 errors, dashboard p95 275 ms; capacity limit ~260 req/s (single backend process by design).
- Known limits: C11 (demand timing at hour boundaries) not probed; live results are single runs, not distributions; confidence and risk use a normal approximation of observed noise (documented, not a trained model).

## Milestones (plan Revision 4, R4.6)

| # | Milestone | Status |
|---|---|---|
| 0 | Supply adequacy (C00) + contract probes | Done |
| 1 | Working slice: threshold policy, executor, stepped harness | Done |
| 2 | LP planner + hindsight bound | Done (stepped); live needs safety buffer (D4) |
| M3 | Decision-support core: detectors, stockout risk, recommendation cards, what-if, approval queue, audit | Done |
| M4 | Resilience behaviours (PS §11 mappings) | Done (all four mappings demonstrated; 6 resilience tests) |
| M5 | Operator web app (5 views + lab) | Done (verified in browser against live simulator) |
| M6 | Observability: Prometheus, Grafana, logs, health | Done (Prometheus scraping, Grafana dashboard provisioned, /api/health, health view) |
| M7 | DevOps: Dockerfile, full compose, CI | Done (clean-clone deploy verified locally; CI result in GitHub Actions) |
| M8 | Load testing (k6) | Done (3 runs, see results) |
| M9 | Architecture diagram, README, demo script, final check | Done |
| Next | Learned forecast, LLM explanations, tuning (plan §25) | Deferred |

## Simulator semantics (verified by probes)

"View tick v" = the `tick` returned by `/v1/instance` while paused. `POST /admin/step` processes tick v and moves to v+1.

| Probe | Finding |
|---|---|
| C00 | 22 arrivals, **216,000 L total, all by tick 212** (4 initial at 12–20; then 3 cycles × 6 at 64/128/192, 4 ticks apart). Start stock 338,000 L. World ≈ 554,000 L ≈ 5.9 days of demand (~93k L/day). Dhaka-side fuel ≈ 6.7 days, Chattogram-side ≈ 5.3 days → cross-region shipping matters. Per depot/fuel supply: Gazipur D 54k / P 44k / O 21k; Patiya D 46k / P 24k / O 27k. |
| C01 | Depot inventory is deducted **at POST acceptance** (PENDING). |
| C02 | POST at view tick v → departs in tick v (`departure_tick = v`), `expected_arrival_tick = v + transit`, and arrives on time. Arrived stock is first visible at view tick v+transit+1. Transit 2/3/4 all behave the same. |
| C03 | Within a tick: allocation departures; arrivals and supply arrivals; demand; then `simulation.tick`. Supply arrival `supply-001` at tick 12 as planned. |
| C04 | Dispatch capacity counts only allocations **created in the current tick**. Gazipur (12,000/tick) at tick 0: 5,000 + 5,000 OK, +2,001 rejected, +2,000 accepted (= 12,000 exactly). Next tick the full budget is available again even with shipments in transit. |
| C05/C06 | Server checks destination headroom against **current inventory only** — in-transit is NOT reserved. On arrival, stock is added, **clipped to capacity (excess silently lost)**, then demand is served. Probe: 9,000 + 2×6,000 into 15,000 tank → 5,825 L lost. **Our executor must reserve headroom for in-transit arrivals.** |
| C10 | Replay same key+body → **201** with the same allocation (no duplicate). Changed body → 409 `IDEMPOTENCY_KEY_MISMATCH`. Replay after cancel → 201 returning the CANCELLED allocation (no new shipment). |
| C15 | `stale_data` only adds `X-Simulator-Stale: true`; bodies are current (tick matches `/v1/health`, inventory keeps moving). Safe to keep using the data. |
| C07 | `depot_constraint` → status `CONSTRAINED` but **no numeric effect**: `dispatch_capacity_per_tick` stays 12,000 and the full 12,000/tick is still accepted. |
| C08 | Events become ACTIVE at the **start** of their `start_tick` processing, before departures; active window = [start, end). A PENDING allocation whose route is disrupted in its creation tick → `FAILED` / `ROUTE_UNAVAILABLE`, `allocation_failures` +1. IN_TRANSIT shipments are unaffected (arrive normally). POST to a DISRUPTED route → 409 `ROUTE_DISRUPTED` (free). |
| C18 | **A FAILED allocation is NOT refunded** — depot stock stays deducted (Gazipur petrol 44,000 before and after failure). Fuel is lost. Executor must not POST on a route with a disruption starting this tick. |
| C09 | `station_outage`: station → `OUTAGE`; **all demand during outage is unmet** (served 0) and inventory is frozen; shipments arriving during outage are still added; POST → 409 `STATION_CLOSED`. |
| C12 | Overlapping spikes compose multiplicatively (1.5 × 2.0 = 3.0) and divide back on resolve; `/v1/stations.demand_multiplier` always shows the product. |
| C13 | At activation, `shipment_delay` shifts **every not-yet-arrived row** of the filtered depot(s)/fuel(s) by `delay_ticks` (status DELAYED); `supply_shortfall` multiplies **every future row** by `factor` (whole remaining schedule, one-shot, not restored). |
| C14 | `stream_disconnect` blocks only **new** `/v1/stream` connections (503); an already-open stream keeps delivering events. |
| C16 | Reset: `/v1/instance` keeps `id` 1, same scenario/seed; `tick` → 0, `sim_time` → start, `/v1/allocations` empty. **No `simulator.notice` reached an already-open SSE subscriber.** Detect reset by tick going backwards or our allocation ids vanishing. |
| C17 | Fractional quantities accepted (1,234.567 L). `/v1/demand-history` is newest-first (id desc); `limit` takes the newest rows. |

## Decisions

- 2026-09-29 — Owner answered D1–D4 (plan R4.3); < 24 h to judging → 24-hour cut order.

- 2026-09-29 — Simulator host port **18000** (`SIM_PORT`), bound to 127.0.0.1. Reason: Windows/Hyper-V reserves TCP 7983–8082 on this PC, so 8000 cannot bind. Image unchanged.
- 2026-09-29 — Plan revised to Revision 3 per design review (LP not MILP, degraded dispatch instead of hold, working-slice milestones, hindsight bound).
- 2026-09-29 — **Owner correction:** do every part that needs no AI/ML now; AI/ML parts go to the next phase. Reverted the review's residual-percentile safety buffers (history-driven) to hand-set stress multiplier; history = validation and residual reporting only. Plan §1.2 table and §25 added.
- 2026-09-29 — Executor reserves station headroom for our own in-transit shipments (C05/C06: server does not, and overflow is lost).
- 2026-09-29 — Only `devlog.md` is maintained as project documentation; no separate docs/*.md files.

## Open questions / blockers

- Participant brief received (PS). **Judging is not a simulator score** (PS §23 weights: product 20, intelligence 20, architecture 15, DevOps 15, resilience 10, observability 10, demo 10).
- Owner decisions (2026-09-29): **D1** stockout risk/confidence from observed demand noise + rule-based detection now, ML later; **D2** < 24 h remain; **D3** README (setup) + devlog; **D4** LP + hand-set buffer, threshold fallback.
- C11 (demand timing/factor composition) left for the AI/ML phase with the residual report (projection is a frozen component).

## Results (stepped, baseline scenario, seed 12345, no events, default 15-min tick)

| Policy | Sim days | Service level | Unmet (L) | Shipped (L) | Fuel lost (L) | Rejected POSTs | Run |
|---|---:|---:|---:|---:|---:|---|---|
| none | 1 | 0.8792 | 11,245 | 0 | 0 | 0 | aaef4993 |
| threshold 30/70 | 1 | 1.0000 | 0 | 79,203 | 0 | 0 | e012e5c2 |
| none | 7 | 0.1319 | 565,414 | 0 | 73,000 | 0 | db53820b |
| threshold 30/70 | 7 | 0.8502 | 97,568 | 468,000 | 0 | 0 | 88be0c76 (rerun b0ff15b6: identical) |
| LP per-tick (`lp-tick`) | 7 | 0.8504 | 97,423 | 467,991 | 9 | 0 | dac33beb |
| **LP batched (`lp`, H=96, replan 8)** | 7 | **0.8504** | **97,417** | 467,997 | 3 | 0 | b982151b |
| *hindsight bound* | 7 | *0.8504* | *97,414* | — | — | — | benchmark only |

Hindsight bound at shorter horizons: **100% service (0 L unmet) is achievable through 5.0 days.** Threshold holds 100% through day 4, then 0.9915 (3,907 L unmet) by tick 472 (≈4.9 d). So policies only differ in roughly days 4.5–6; beyond ~6 days the world is out of fuel and every loss-free policy converges to the bound.

C19: demand identical across `none` and `threshold` runs (8,064 rows, max diff 0.000000 L) → hindsight bound valid. Reruns are byte-identical in metrics.

LP solve time: 84 solves, p50 0.17 s, max 0.39 s, all optimal. **Issue:** LP sends 5,424 small POSTs (~86 L avg) vs 111 for threshold → 396 s wall per 7 d vs 93 s, and would be fragile under latency faults. Fix in executor (request consolidation) — Milestone 3.

"Fuel lost" = start stock + arrived supply − served − (depot + station + in-transit stock) at the end; with no shipping the depots overflow at supply arrivals. 7 days exceeds the ~5.9-day fuel ceiling (C00), so some unmet demand is unavoidable there; the hindsight bound (Milestone 2) will show how much.

### Live fault runs (normal speed 8 ticks/s, threshold policy, 400 ticks ≈ 4.2 days, fault injected at 10 s for 15 s)

| Fault | Service | Unmet (L) | FAILED | Incidents logged |
|---|---:|---:|---:|---|
| none | 1.0000 | 0 | 0 | — |
| latency 500 ms | 1.0000 | 0 | 0 | — |
| unavailable | 0.9336 | 25,393 | 0 | degraded → recovered |
| error_rate 0.25 | 1.0000 | 0 | 0 | 3× degraded → recovered |
| stale_data | 1.0000 | 0 | 0 | 61 stale flags (data used, C15) |
| stream_disconnect | 1.0000 | 0 | 0 | — (REST polling unaffected) |

`unavailable` blocks every `/v1` call including POSTs for ~120 ticks, so the loss is only preventable by holding more stock beforehand. Live runs are wall-clock based and not byte-identical; single runs, not distributions yet.

### Load testing (PS §17) — k6 against the containerized backend, simulator running live in auto mode

Workload: `ops/k6/load.js`. Scenario "dashboard" = what an operator's browser polls (status + overview + allocations per iteration), ramping 0 → 10 → 50 → 100 virtual users over 100 s. Scenario "decisions" = GET recommendations (risk, impact, alternatives) + health at a constant arrival rate. Command:
`MSYS_NO_PATHCONV=1 docker run --rm --network hackathaon_bup_final_default -v "$(pwd -W)/ops/k6:/scripts" -e BASE=http://fuelops:8100 [-e PROFILE=realistic] grafana/k6 run --summary-export /scripts/summary.json /scripts/load.js`

| Run | Profile | Throughput | Errors | Dashboard p50 / p95 / p99 | Decision path p50 / p95 / p99 | Backend CPU / memory (peak) |
|---|---|---:|---:|---|---|---|
| 1 | stress (no think time, 20 decision req/s) | 121 req/s | 0 / 12,125 | 1.44 s / 2.72 s / 2.84 s | 1.16 s / 2.56 s / 2.80 s | 118% / 101 MB |
| 2 | stress, after per-tick JSON cache | **260 req/s** | 3 / 25,965 (0.01%) | 419 ms / 1.54 s / 1.85 s | 460 ms / 1.61 s / 1.91 s | 142% / 110 MB |
| 3 | **realistic** (each dashboard polls once a second, 5 decision req/s) | 128 req/s | **0 / 12,933** | **32 ms / 275 ms / 432 ms** | **8 ms / 181 ms / 347 ms** | 113% / 132 MB |

Findings: the limit is CPU in the single backend process (one process by design: one operational writer). Run 1 recomputed demand projections and re-encoded the growing shipment ledger on every request; caching serialized JSON once per tick and capping the ledger at 200 rows doubled throughput. Capacity ≈ 260 req/s ≈ 65 dashboards polling 4 endpoints each second; at realistic load p95 stays under 300 ms. API load never reaches the simulator (metrics and health are cached). Raw summaries and `docker stats` samples: `ops/k6/summary_*.json`, `ops/k6/stats_run*.csv`.

### Resilience demonstrations (PS §11) — against the running compose stack

| PS §11 mapping | How it was triggered | Observed behaviour |
|---|---|---|
| ML model unavailable → fallback allocation policy | Lab switch `PUT /api/intelligence {enabled:false}` | Health: prediction service **down**, decision engine **degraded**, source "threshold (fallback: intelligence disabled)"; `fuelops_fallback_activations_total{reason="intelligence_disabled"}` = 1; allocation continues on rules. Test: `test_intelligence_off_falls_back_to_rule_policy_and_keeps_operating`. |
| Invalid simulator response → reject input + raise alert | Fake simulator returning negative inventory (the official image must not be modified) | Snapshot rejected, never becomes state, incident `invalid_response`, no shipment decided. Tests: `test_invalid_response_is_rejected_and_raises_an_alert`, `test_validate_rejects_unknown_allocation_status`. |
| Prediction confidence too low → human review | Fresh run (48 history rows) + lab demand spike ×2.5 at Mirpur, auto mode | Immediate replan (incident at tick 17); Mirpur cards carry allocations (e.g. 11,819 L petrol, risk 100% → 0%) but confidence **0.47 < 0.5** → "Needs your review"; **0 automatic shipments to Mirpur** after the spike. Test: `test_low_confidence_during_crisis_requires_review`. |
| Backend dependency unavailable → retry / cached state / degraded | (a) simulator fault `unavailable` 10 s while running; (b) `docker compose stop simulator-api` 10 s | (a) degraded within 2 s, cached snapshot (tick 35) served, circuit breaker limited reads to 9 attempts, recovered ~1 s after expiry (tick 113). (b) health: simulator **down**, backend healthy, `/api/overview` still HTTP 200 from cache; all components healthy again after restart. |

Bugs found by these demos and fixed: (1) a spike did not trigger a replan until the 8-tick cadence → cards had no allocation; now any change in events, multipliers, route/station/depot status or supply forces an immediate re-solve (plan §9.1). (2) During an injected outage the executor retried every shipment of a batch (~0.75 s each) and the controller froze without flagging degraded; now the batch stops at the first write failure and the controller goes degraded. (3) Fallback wording claimed "all cards need review" while the fallback policy (correctly, per PS §11) keeps allocating; wording fixed.

## Demo script (PS §22 story, about 8 minutes)

Setup: `.env` with `SIMULATION_SPEED=1`, `FUELOPS_MODE=auto`, an operator token; `docker compose up -d --build`; open the app, Grafana, and this list. Lab → Reset, then Run.

| # | PS §22 step | Do / show |
|---|---|---|
| 1 | Normal operations | Overview: tank wall filling, routes with fuel moving, demand served 100%. |
| 2 | Operator dashboard | Walk the views; System health all green, p95 latency, prediction error. |
| 3 | Demand starts increasing | Incidents and lab → Crisis event: demand spike, Karnaphuli, ×2.0, 60 ticks → Start. |
| 4 | System detects risk | Recommendations → "Detected now": anomalous demand (z-score) and the spike signal; incident "Replanned". |
| 5 | Intelligence predicts shortage | Card: "runs out in about N h", stockout risk %, observed demand noise and sample size. |
| 6 | Allocation recommendation generated | Card: liters, depot, route, arrival time, binding constraint. |
| 7 | Operator inspects recommendation | Open "Constraints and alternatives"; confidence below 50% → "Needs your review" (PS §11). |
| 8 | Allocation is simulated | Risk bars "Now" vs "If sent"; unmet liters before → after. Approve and send. |
| 9 | Crisis event occurs | Lab: route disruption on Patiya → Karnaphuli (or combined crisis: add a supply shortfall). |
| 10 | System adapts | Route drawn dashed "disrupted"; replan; recommendation switches to Gazipur → Karnaphuli; no FAILED shipments (disruption guard). |
| 11 | Failure injected | Lab → Software failure: unavailable, 15 s (or stop the simulator container, or switch intelligence off). |
| 12 | Monitoring detects failure | Amber banner "Simulator unreachable, showing data from N s ago"; System health: simulator degraded; Grafana: degraded = 1, read failures. |
| 13 | Fallback / recovery activates | Cached state stays visible; circuit breaker; with intelligence off the rule policy keeps allocating. |
| 14 | Operations continue | Incident "Recovered"; banner clears; decisions continue; Decisions view shows the full audit trail. |

Evidence to have open: Results and Load testing sections of this log, the hindsight comparison (LP within 3 L of the best possible over 7 days), CI run, Grafana dashboard.

## Next up

- Execute the 24-hour cut (plan R4.3): M3 → M5 → M7 → M6 → M4 → M8 → M9.

## Log

### 2026-09-29 — Operator UI simplified for end users (owner feedback: "too complex")
- 5 views → 4: **Home** (one-line status, problems in plain sentences, stations with OK/Low/Critical and "runs out in 3.2 hours", "+2,000 L arriving in 30 min", depots, roads as a list), **Actions** (cards phrased as instructions "Send 3,488 L octane to Mirpur", Why, If sent, Send / Skip, Send all; technical detail under "More details"), **History** (decisions and shipments as sentences), **System** (health in plain words, readable event timeline, Settings with friendly planner names, demo tools collapsed under "Test tools").
- Top bar: simulation time with Start/Pause, and "Sending fuel: View only / I approve / Automatic". Planner moved to Settings; `lp-tick` and `none` hidden.
- No internal jargon on screen (ticks, lp, z-scores, raw event parameters, route ids); body text 16 px, darker secondary text.
- Backend: overview now includes per-fuel stockout time, risk, and next arrival (same projection as recommendations); single simulator steps no longer flood the incident log.
- Verified in the browser (text and screenshots) against the live stack; build passes.

### 2026-09-29 — Final verification and two execution fixes
- Clean clone → `docker compose -p verify up -d --build` on alternate ports: all 5 components healthy, simulator steps, metrics exposed, web app and Grafana HTTP 200; torn down.
- Crisis replay (Karnaphuli spike ×2.2 + Patiya→Karnaphuli disrupted) exposed octane starvation: a batch exceeded the 12,000 L/tick depot dispatch budget and the unsent remainder was dropped. Fix: executor returns liters sent per route/fuel, the controller carries remainders to the next tick, and auto mode executes the most urgent cards first. Replay: all three fuels rerouted via Gazipur (octane 3,654 L), 0 FAILED, 100% served.
- Route map labels moved to 30% along each line (crossing 4-tick routes overlapped); verified by measuring label boxes (no overlaps).
- README (setup, configuration, Mermaid architecture diagram) and demo script (PS §22) written.

### 2026-09-29 — M3 decision support (+ most of M4)
- `intel.py`: NoiseModel (relative demand noise per profile from observed history, residual computed once per row, 3-day window), `project()` (time to stockout, 12 h stockout risk via normal approximation, what-if arrivals), `confidence()` (0.5 from guide prior → 1.0 with 3 days of history; ×0.5 degraded, ×0.8 active crisis), 4 rule-based detectors (anomalous demand z>4, abnormal inventory vs ≥8-tick reference, dispatch bottleneck ≥90%, public disruptions).
- `decisions.py`: recommendation cards (PS §9): why, signals, allocations with limits/binding constraint, before/after risk and stockout hours, alternatives, confidence, review flag (<0.5 → human review, PS §11).
- `store.py`: SQLite decision + incident audit. `metrics.py`: Prometheus metrics (app, integration, intelligence).
- `controller.py` rewritten: validation (invalid response → reject + incident), circuit breaker (5 failures → 2 s open), cached state, intelligence kill switch → threshold fallback, auto mode executes only confident cards, approvals revalidate on a fresh snapshot, metrics cached for API.
- `lp.py`: hand-set safety buffer (D4), soft penalty c_buf = ε/2 — **first attempt (0.5/H) failed a new unit test: the LP withheld service**; fixed after correcting the argument (withheld liters still serve later demand, so the buffer weight must be below ε). 5/5 tests pass.
- `api.py`: recommendations/approve/reject, decisions, alerts, health (PS §15 components + p95 + error rate), `/metrics`, lab event/fault/control (operator token), path-traversal-safe SPA serving.
- Measured: **lp-buffer live, no fault, 400 ticks: service 1.0000, 0 L unmet** (unbuffered LP was 0.977). Smoke test: Karnaphuli spike detected at z≈12–15; card "Diesel runs out in ~7.8 h … risk 100% → 0% with 3,621 L" approved and executed.
- Found and fixed: startup confidence 0 blocked auto mode (Karnaphuli diesel fell to 236 L); abnormal-inventory false positives from live read skew (16 in one run); slow cycles from recomputing residuals.

### 2026-09-29 — Official problem statement received; plan Revision 4
- Read `Problem_Statement_BUP_CSE_Fest_2026.pdf` (11 pages) in full and added it to the repo.
- Key change: evaluation is product/intelligence/architecture/DevOps/resilience/observability/demo, not simulator service level. Load testing, observability, CI/CD, architecture diagram, and an operator web app are required deliverables.
- Plan Revision 4 added: facts (R4.1), gap analysis (R4.2), owner decisions D1–D4 (R4.3), recommendation card (R4.4), architecture + 5 views (R4.5), milestones M3–M9 (R4.6), deliverable checklist (R4.7), PS §22 demo mapping (R4.8). Superseded sections marked.
- Execution paused until the owner confirms.

### 2026-09-29 — Fault handling, live controller, API skeleton (before problem statement arrived)
- `sim.py`: GET retries with backoff on 503/transport errors. `execute.py`: parallel snapshot (8 reads in one round trip — latency fault costs one delay, not eight), events in snapshot, **route-disruption guard** (never POST on a route disrupted now/next tick; C08/C18: fuel would be lost).
- `scenarios.py`: 11 crisis recipes (S02–S11). Harness: `--recipe`, `--announced`, failed-allocation count. Verified: S04 LP run → 0 FAILED allocations.
- `controller.py`: live loop (observe/manual/auto), reset detection by tick rollback, degraded/recovered incidents, measured execution lag. `livetest.py`: live fault runs at normal speed.
- **Finding:** LP is near-optimal stepped but fragile live (just-in-time deliveries, no safety stock; 0.873 service at tick 400 live vs threshold 1.000). Modelling the measured execution lag in the LP (`earliest=`) → 0.977. Remaining gap needs safety buffers (§8.3). Live default policy = threshold for now.
- `api.py`: FastAPI `/api/*` skeleton (status, overview, allocations, plans, execute, cancel, mode, policy, incidents). Not yet run end-to-end.
- Frontend not started. Work paused: official problem statement received → full plan review before further execution.

### 2026-09-29 — Remaining contract probes
- Added and ran C07, C08 (+C18), C09, C12, C13, C14, C16, C17 in `fuelops/probes.py`. Findings in **Simulator semantics**.
- Execution-relevant: FAILED shipments lose their fuel (no refund); outages make all demand unmet; shortfall/delay events rewrite the whole remaining schedule; reset is silent on existing SSE streams.

### 2026-09-29 — Request consolidation
- `LPPolicy(batch=True)` (default `lp`): at each solve, sends the next 8 ticks of planned flow per route/fuel at once, executor reserves in-transit headroom. Model unchanged.
- Result: 7 d unmet 97,417 L (3 L above bound), POSTs cut from 5,424 to 762, wall 145 s vs 396 s.
- Fixed Windows cp1252 write of `fuelops/policies.py` (re-encoded UTF-8). Use `PYTHONUTF8=1` for scripts that write files.

### 2026-09-29 — Milestone 2 core: LP + hindsight bound; scope narrowed
- Added `fuelops/projection.py`, `fuelops/lp.py` (continuous LP, decreasing unmet weights, arrival clipping, depot overflow, per-tick dispatch budget), `LPPolicy` (re-solve every 8 ticks), `fuelops/hindsight.py`, `tests/test_lp.py`.
- Executor got `reserve_incoming=False` mode for the LP (LP models arrival clipping; executor enforces the server's per-request headroom rule).
- Harness now saves full demand history per run (`reports/<run>_<policy>_demand.json`).
- Verified: 4/4 LP fixtures pass; C19 identical demand; LP 7-day = 0.8504 service, 9 L from the bound.
- Owner directive: execute only components without future AI/ML integration; plan §17 scope table added. Policy tuning, projection refinement, crisis planning logic, explanations frozen.

### 2026-09-29 — Milestone 1: working slice + first score
- Added `fuelops/execute.py`: snapshot; executor that splits into `max_shipment` chunks, clips to depot stock, per-tick dispatch budget (C04), and station headroom **minus our in-transit** (C05/C06); writes key+body to `reports/<run>_intents.jsonl` before each POST; 503 → same-key retry; transport error → look up key in ledger before replay.
- Added `fuelops/policies.py` (none; threshold 30%/70%, in-transit-aware, fastest route) and `fuelops/harness.py` (reset → pause → decide → step; metrics every 8 ticks; conservation "fuel lost" check; JSON report).
- Verified: 1-day and 7-day stepped runs complete for both policies; 0 rejected POSTs; conservation balances (threshold lost 0 L). Results table above. ~12 s wall per simulated day.
- Plan corrected per owner: no-AI/ML phase boundary (§1.2), history for validation/residual reporting only, AI/ML deferred to §25.

### 2026-09-29 — Milestone 0: environment + contract probes
- Installed Python 3.12 (winget, user scope), created `.venv` (httpx, scipy, numpy, pytest, fastapi, uvicorn). Pulled simulator image.
- Added `compose.yaml` (port 18000), `fuelops/sim.py`, `fuelops/probes.py`.
- Ran C00, C01, C02, C03, C04, C06, C10, C15 against the live simulator; findings in **Simulator semantics**.
- C00 contradicted both the guide wording and the review's assumption: resupply ends at tick 212, not ~12 days. Plan §5.3/§5.4 updated with measured values.

### 2026-09-29 — Plan Revision 3
- Applied the 7-point design review to the plan (see plan header table).

### 2026-09-29 — devlog created
- Created `devlog.md`.
