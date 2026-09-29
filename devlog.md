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

- Date: 2026-09-29
- **Scope rule (owner, 2026-09-29): execute only components that will not get AI/ML later** (plan §17 scope table). Projection, safety margins, decision policy tuning, crisis planning logic, and explanations are frozen and resumed in the AI/ML phase.
- Milestones 0 and 1 done. Milestone 2 core done (LP policy, hindsight bound, C19); policy tuning frozen by the scope rule. Next: Milestone 3 non-AI/ML parts.
- Code: `fuelops/sim.py` (client), `fuelops/probes.py`, `fuelops/execute.py` (snapshot + safe executor), `fuelops/policies.py` (none, threshold, lp), `fuelops/projection.py` (demand formula), `fuelops/lp.py` (LP), `fuelops/hindsight.py` (upper bound + C19), `fuelops/harness.py` (stepped benchmark), `tests/test_lp.py` (4 fixtures, passing), `compose.yaml`.
- Best measured score so far: **LP, 7 simulated days: service level 0.8504, 97,423 L unmet — within 9 L of the perfect-hindsight bound (97,414 L)** (run `dac33beb`).

## Milestones (plan §17)

| # | Milestone | Status |
|---|---|---|
| 0 | Supply adequacy (C00) + blocking probes C01–C04, C06, C10, C15 | Done |
| 1 | Working slice: threshold policy, auto, stepped harness, score | Done |
| 2 | LP planner + hindsight bound | Core done; tuning frozen (AI/ML target) |
| 3 | Events + fault handling (non-AI/ML parts only) | Next |
| 4 | Dashboard: Overview, Shipments, Plans | Not started |
| 5 | Hardening and delivery | Not started |
| — | Next phase: AI/ML extensions (plan §25) | Deferred — not this phase |

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

## Decisions

- 2026-09-29 — Simulator host port **18000** (`SIM_PORT`), bound to 127.0.0.1. Reason: Windows/Hyper-V reserves TCP 7983–8082 on this PC, so 8000 cannot bind. Image unchanged.
- 2026-09-29 — Plan revised to Revision 3 per design review (LP not MILP, degraded dispatch instead of hold, working-slice milestones, hindsight bound).
- 2026-09-29 — **Owner correction:** do every part that needs no AI/ML now; AI/ML parts go to the next phase. Reverted the review's residual-percentile safety buffers (history-driven) to hand-set stress multiplier; history = validation and residual reporting only. Plan §1.2 table and §25 added.
- 2026-09-29 — Executor reserves station headroom for our own in-transit shipments (C05/C06: server does not, and overflow is lost).
- 2026-09-29 — Only `devlog.md` is maintained as project documentation; no separate docs/*.md files.

## Open questions / blockers

- Participant brief (evaluation horizon, scoring) not available. With only ~5.9 days of fuel, run length decides how much unmet demand is unavoidable.
- Remaining probes (C07–C09, C11–C14, C16–C19) scheduled for Milestones 2–3.

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

## Next up (non-AI/ML only)

1. Remaining probes C07–C09, C12–C14, C16–C18.
2. Fault handling: degraded mode (plan §12.1), retries/backoff, SSE consumer with polling fallback, event-triggered replan; F01–F05 scenarios.
3. Milestone 4 dashboard; Milestone 5 persistence/outbox/packaging.

## Log

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
