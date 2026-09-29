# BUP Fuel Supply Simulator: Full Deterministic MVP Plan

**Document type:** Implementation plan only. No application is built by this document.  
**Prepared:** 29 September 2026.  
**User requirements:** Complete MVP; no AI or machine learning; no artificial implementation deadline; deterministic methods and optimization wherever justified.  
**User-selected UI stack:** shadcn/ui with Tailwind CSS, on React + TypeScript + Vite.  
**Primary reference:** `BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md`, supplied by the user, all 16 pages / 689 text lines reviewed.  
**Target simulator:** `asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, as specified in the guide.

**Validation status:** Source-document and official library-documentation review completed. Runtime contract probes, application tests, solver benchmarks, and simulator experiments described below are planned work, not completed results.

### Navigation

- [Product scope](#3-product-scope-and-definition-of-a-full-mvp)
- [Documentation and simulator contract checks](#4-phase-0-documentation-discovery-and-contract-validation)
- [Architecture and stack](#6-recommended-architecture-and-technology)
- [State and persistence](#7-state-collection-freshness-and-persistence)
- [Deterministic projections](#8-deterministic-demand-and-inventory-projection)
- [Optimization model](#9-optimization-specification)
- [Safe execution](#10-decision-loop-and-safe-shipment-execution)
- [Dashboard and workflows](#13-dashboard-and-operator-workflows)
- [Benchmark pipeline](#16-reproducible-scenario-and-benchmark-pipeline)
- [Implementation phases](#17-implementation-phases-and-completion-gates)
- [Definition of done](#22-final-definition-of-done)
- [Sources and handoff](#24-reference-index-and-copy-ready-implementation-sources)

## 1. Executive decision

Build a local **fuel operations and dispatch application** that connects to the official simulator, calculates future inventory using documented demand rules, solves a constrained replenishment problem, safely submits shipments, and explains its decisions through a dashboard and reproducible reports.

The complete operating pipeline is:

```text
Official simulator
  → REST observations + SSE notifications
  → validated, timestamped state snapshot
  → shipment reconciliation and freshness checks
  → deterministic demand and inventory projection
  → constrained shipment optimization
  → independent feasibility checks
  → durable dispatch intent
  → allocation submission / reconciliation
  → simulator executes shipment
  → outcome monitoring and benchmark evidence
```

The core contribution is **operations research plus reliable integration**. It requires neither a trained model nor an LLM.

Deliver a working application, not only an optimizer notebook or a dashboard. It must include automatic operation, manual review, shipment tracking, disruption handling, restart recovery, scenario testing, and honest performance comparisons.

### 1.1 What “optimal” will mean

There are three different claims:

1. **Feasible:** the proposed decisions satisfy the modeled constraints and pass execution checks.
2. **Model-optimal:** a solver proves optimality, within configured numerical tolerances, for a particular snapshot, demand trajectory, planning horizon, objective, and set of constraints.
3. **Best possible actual performance across the entire simulation:** not generally provable in advance because future injected events, API availability, and exact demand jitter are not fully known through the guide.

The MVP should achieve the first, support the second, and never misrepresent it as the third. Replanning repeatedly is useful, but it does not make a finite-horizon controller globally optimal over an unknown future.

If the solver stops early with a feasible incumbent, display **“Feasible; optimality not proven.”** If a fallback rule generates the plan, display **“Rule-based fallback.”** If conservative capacity rules restrict the feasible set, disclose that the optimality claim applies to that restricted model.

## 2. Authority, requirements, and unresolved scope

The supplied document explicitly says it is an **integration and interaction guide**. It does not supply the official participant brief, scoring weights, deliverables, mandatory technology, presentation length, or submission rules. Do not invent those requirements.

This plan uses four labels:

| Label | Meaning |
|---|---|
| Guide requirement | Explicitly documented simulator behavior or participant integration rule. |
| Proposed design | A recommended application choice, subject to implementation validation. |
| Validation required | Behavior that is ambiguous or absent in the guide. |
| Organizer clarification | Information that belongs in the missing official participant brief. |

### 2.1 Requirements to clarify when the participant brief is available

- Evaluation horizon and whether judging uses normal running speed, controlled stepping, or both.
- Actual score formula and weights, including any fairness, delivery-volume, or allocation-count penalties.
- Whether scheduled public events may be used proactively.
- Whether automated operation, predictive capabilities, or AI/ML are explicitly mandatory. Rule-based future projections provide predictive functionality, but an explicit ML requirement would need separate resolution.
- Required submission format, deployment constraints, demo length, and allowed dependencies.
- Whether organizers change seeds or image versions, and how they provide that configuration.

These unknowns do not prevent building the deterministic core. Keep evaluation assumptions configurable and label them in reports.

### 2.2 Non-negotiable guide rules

- Run outside the simulator and integrate over HTTP.
- Use the published simulator image; do not modify its source to improve results.
- Treat REST as authoritative. SSE only signals that a refresh is needed.
- Create shipments through `POST /v1/allocations`.
- Cancel only through the documented pending-allocation cancellation endpoint.
- Do not write directly to simulator storage.
- Use admin endpoints for controlled testing and diagnostics, not to bypass operational faults.
- Do not assume runtime scenario switching or a seed-setting API exists.

References: guide §§1–3, §5, §6, §7; especially lines 17, 75–97, 309–422.

## 3. Product scope and definition of a full MVP

### 3.1 Required capabilities

| Area | Complete MVP behavior |
|---|---|
| Connection | Connect to a configured simulator; distinguish liveness, operational availability, and freshness. |
| Inventory | Show all depot and station inventories for each fuel, with capacities and timestamps. |
| Network | Show all six real routes, availability, transit ticks, and per-shipment limits. |
| Projection | Calculate deterministic future demand, inventory paths, and predicted shortage times. |
| Planning | Optimize a finite horizon and produce immediately executable shipment proposals. |
| Execution | Submit safely, track responses, reconcile uncertain outcomes, and avoid duplicate intents. |
| Operations | Support observe, manual approval, and automatic modes. |
| Shipments | Show pending, in-transit, arrived, failed, and cancelled allocations. |
| Disruptions | Respond to all six documented domain event types. |
| Reliability | Handle all five documented API fault types and stream recovery. |
| Persistence | Preserve decisions, payloads, metrics, observations, and run identity across app restarts. |
| Testing | Repeat scenarios against the published simulator and compare policies. |
| Evidence | Export measured results, assumptions, plan explanations, and configuration. |
| Delivery | Provide reproducible local startup, documented configuration, and a demo procedure. |

### 3.2 Explicit exclusions

- LLMs, chatbots, agents making shipping decisions, model training, neural networks, reinforcement learning, or learned forecasting.
- Truck fleets, driver schedules, traffic APIs, geographic distances, and road-path routing: the simulator does not model these.
- Fuel prices, profits, emissions, procurement orders, monetary transport costs, or budgets: none are defined in the guide.
- New depots, stations, or routes; fuel transfers between stations or between depots.
- Redirecting or cancelling in-transit shipments.
- Cloud hosting, multi-tenant accounts, billing, Kubernetes, distributed queues, and microservices for the local MVP.
- A replacement simulator presented as the official one.

Test doubles are permitted for unit tests, but all compatibility and benchmark claims must come from the published image.

## 4. Phase 0: Documentation discovery and contract validation

This is the first implementation phase. Finish the relevant contract probes before relying on their semantics in the optimizer.

### 4.1 Documentation inventory

| Source | Use |
|---|---|
| Supplied guide §§4–5 | Entity schemas, public reads, allocation writes, validation, cancellation. |
| Supplied guide §6 | Stream protocol, reconnection, buffer overflow, actual event names. |
| Supplied guide §7 | Test controls, crisis types, fault types, audit. |
| Supplied guide §8 | Topology, starting stocks, demand profiles, hour factors, supply schedule pattern. |
| Supplied guide §§9–10 | Error envelopes and defensive-client checks; reconcile contradictions with §5. |
| Running image `/docs` and `/redoc` | Inspect actual request/response schemas and types. |
| Official dependency documentation in §24 | Verify solver, HTTP-client, and application lifecycle APIs. |

Archive the observed schemas and image digest with the eventual project. If the runtime exposes an OpenAPI JSON link through its documentation, save the exact linked document; do not assume an undocumented endpoint without checking.

### 4.2 Allowed public simulator API inventory

| Method and path | Purpose and important details |
|---|---|
| `GET /v1/health` | Fault-exempt liveness; includes simulation status and tick. Not proof other APIs work. |
| `GET /v1/instance` | Scenario, version, seed, simulation time, tick, tick size, running/paused status. |
| `GET /v1/regions` | Regional demand factors. |
| `GET /v1/depots` | All depots, inventories, capacities, status, dispatch capacity. |
| `GET /v1/depots/{entity_id}` | Refresh one affected depot. |
| `GET /v1/stations` | All stations, demand profile/multiplier, inventories, capacities, status. |
| `GET /v1/stations/{entity_id}` | Refresh one affected station. |
| `GET /v1/routes` | Connectivity, transit ticks, status, maximum quantity per allocation. |
| `GET /v1/supply-arrivals` | Existing supply schedule, sorted by planned tick. |
| `GET /v1/events` | Public scheduled, active, and resolved domain events; newest ID first. |
| `GET /v1/allocations` | Shipment ledger, newest ID first; no pagination/filter parameters documented. |
| `GET /v1/demand-history?station_id=...&limit=...` | Bounded observations; `limit` 1–2000, default 200. No cursor documented. |
| `GET /v1/metrics` | Cumulative served/unmet demand, service level, shipped liters, allocation failures. |
| `POST /v1/allocations` | Create one shipment with an idempotency key in the JSON body. |
| `POST /v1/allocations/{allocation_id}/cancel` | Cancel only pending shipments; refund depot inventory. |
| `GET /v1/stream` | SSE notifications; no replay on reconnect. |

Do not invent a batch-allocation endpoint, a route-edit API, history pagination, a scenario-switch API, or an allocation-update endpoint.

### 4.3 Allowed test and diagnostic API inventory

| Method and path | Use |
|---|---|
| `GET /admin` | Existing simulator diagnostic page. |
| `POST /admin/run` | Start background ticking. |
| `POST /admin/pause` | Pause background ticking. |
| `POST /admin/toggle` | Supported, but explicit run/pause is clearer for reproducible tests. |
| `POST /admin/step` | Advance exactly one tick; harness must pause first to avoid extra background ticks. |
| `POST /admin/reset` | Destructive simulator reset to baked scenario. |
| `POST /admin/events` | Inject a domain crisis. |
| `POST /admin/faults` | Inject a real-time API fault. |
| `POST /admin/faults/clear` | Clear active faults. |
| `GET /admin/audit?limit=...` | Audit; limit 1–1000, default 200. |
| `GET /admin/faults` | Last 50 fault rows. |
| `GET /admin/events` | Last 50 event rows. |

Admin knowledge must not leak into the operational planner. A testing service may know future events; the planner sees them only when the public interface exposes them under the chosen evaluation protocol.

### 4.4 Required black-box contract probes

For each probe: reset, pause, record initial state, perform the smallest relevant action, step deliberately, read public state, and use admin audit only to diagnose ordering. Save requests and observations as fixtures.

| ID | Question | Required evidence |
|---|---|---|
| C01 | Does inventory deduct at acceptance or departure? | Depot values before POST, after POST, after first step. |
| C02 | When exactly does a shipment depart and arrive? | Created/departure/arrival ticks for transit lengths 2, 3, and 4. |
| C03 | In what order do events, supplies, departures, arrivals, and demand execute? | Boundary-tick observations and audit entries. |
| C04 | Which allocations consume dispatch budget at a given tick? | Multiple requests across tick boundaries, pending/in-transit cases, cancellation and failure. |
| C05 | Are incoming shipments reserved against destination capacity at submission? | Two shipments to the same station/fuel before arrivals. |
| C06 | What happens if arriving stock exceeds station or depot capacity? | Whether excess is discarded, delayed, rejected, or treated another way. |
| C07 | What does depot `CONSTRAINED` change numerically? | Dispatch field and accepted requests before/during/after event. |
| C08 | Does disruption affect a shipment already in transit? | Disrupt separately before departure and after departure. |
| C09 | What happens to fuel and demand during station outage? | Inventory, demand, served/unmet, and deliveries through outage boundaries. |
| C10 | Does replay return 200 or 201? | Identical POST twice; same key with changed body; replay after cancellation. |
| C11 | What is demand timing and factor composition? | Hour boundaries, regional factors, multiplier effects, tick-size behavior. |
| C12 | How are overlapping events applied and resolved? | Overlapping spikes, disruptions, constraints, and outages; empty filter and combined filter semantics. |
| C13 | Which supply rows do delays/shortfalls mutate, and when? | Snapshot before event, at activation, after resolution; already-arrived rows included in inspection. |
| C14 | Does stream-disconnect fault interrupt existing streams or only block new connections? | Test both an existing connection and a new connection. |
| C15 | Does stale-data fault only flag responses? | Header/body observations; do not assume historical body replay. |
| C16 | How can external reset be recognized? | Notice, tick rollback, reused IDs, same scenario/seed, missing allocation keys. |
| C17 | What are precision and history-return ordering rules? | Fractional quantities, sorting behavior, partial windows. |
| C18 | How are failed shipments refunded and dispatch reservations released? | Failure-time depot inventory and subsequent request acceptance. |

### 4.5 Known documentation inconsistencies

- §5.4 says idempotent replay returns **201**, while §9 says **200**. Accept both with a valid allocation body.
- The guide calls allocation creation the only public write, but explicitly documents pending cancellation. Both are allowed in this plan.
- `CONSTRAINED` is explicitly shippable in §5.2. Do not treat it as closed because of the §9 troubleshooting wording.
- The `stale_data` fault is described as adding a header. Do not claim it necessarily returns an older snapshot.
- The exact demand-jitter distribution and reproduction algorithm are not supplied. A seed alone is insufficient to recreate them.

**Phase 0 exit gate:** a versioned semantics document separates confirmed behavior from remaining assumptions; no optimizer constraint depends silently on an unresolved behavior.

## 5. Domain model and world configuration

### 5.1 World inventory

Use IDs and current numeric values returned by REST. Keep the guide values below as reference fixtures and startup expectations, not replacements for live state.

| Depot | Dispatch liters/tick | Capacity D/P/O | Initial inventory D/P/O |
|---|---:|---|---|
| Gazipur | 12,000 | 90,000 / 70,000 / 45,000 | 60,000 / 45,000 / 26,000 |
| Patiya | 11,000 | 85,000 / 65,000 / 40,000 | 55,000 / 42,000 / 24,000 |

| Station | Profile | Capacity D/P/O | Initial inventory D/P/O |
|---|---|---|---|
| Mirpur | urban_high | 15,000 / 14,000 / 9,000 | 9,000 / 9,000 / 5,000 |
| Tongi | industrial | 18,000 / 9,000 / 6,000 | 11,000 / 6,000 / 3,500 |
| Karnaphuli | highway | 14,000 / 15,000 / 9,000 | 8,500 / 9,500 / 5,200 |
| Cox’s Bazar | regional | 12,000 / 12,000 / 7,000 | 7,500 / 7,500 / 4,200 |

`D/P/O` means DIESEL/PETROL/OCTANE. Quantities are liters. Dhaka's demand factor is 1.00; Chattogram's is 1.08.

### 5.2 Actual network

| Route ID | Transit ticks | Maximum liters per shipment |
|---|---:|---:|
| route-gazipur-mirpur | 2 | 7,000 |
| route-gazipur-tongi | 2 | 6,500 |
| route-patiya-karnaphuli | 2 | 7,000 |
| route-patiya-coxsbazar | 3 | 6,000 |
| route-gazipur-karnaphuli | 4 | 5,000 |
| route-patiya-mirpur | 4 | 5,000 |

**Critical constraint:** `max_shipment` applies to each allocation, not aggregate route throughput per tick. The guide explicitly permits splitting into multiple allocations. Depot dispatch capacity still limits total qualifying volume across routes and fuel types.

Tongi has only Gazipur as a supplier. Cox’s Bazar has only Patiya. Mirpur and Karnaphuli have two supply routes each. The planner should preserve scarce depot stock for dependent stations when that improves the selected objective.

### 5.3 Supply

The baked scenario contains 22 arrivals: four initial arrivals at ticks 12–20 and eighteen recurring arrivals described as spaced 64 ticks apart. Read actual rows from `/v1/supply-arrivals` for exact timing, destination, fuel, and quantity.

Do not generate an infinite recurring schedule from this description. After the final listed supply, project only existing stock unless additional arrivals are actually observed.

## 6. Recommended architecture and technology

### 6.1 Architecture

```text
Browser dashboard
       │ same-origin application API
       ▼
Application backend — one process, one operational writer
 ├─ read-only dashboard/query API
 ├─ operating-mode and manual-action API
 ├─ simulator REST client + separate SSE connection
 ├─ state collector + reconciliation coordinator
 ├─ pure deterministic projection engine
 ├─ optimization worker + safe heuristic fallback
 ├─ independent execution validator + durable outbox
 └─ SQLite decision/history store
       │
       ▼
Official simulator container

Scenario/benchmark command
 ├─ exclusive ownership of test simulator controls
 ├─ admin client for reset, step, events, faults
 └─ public client/policy pipeline for evaluated operations
```

The browser never holds the operational simulator client. All manual and automatic writes pass through the same coordinator and validation path.

### 6.2 Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python + FastAPI + Pydantic | Typed contracts, HTTP endpoints, straightforward numerical integration. |
| Simulator client | HTTPX async client | Reusable connections, explicit timeouts, async reads and streaming. |
| Optimization | SciPy interfaces to HiGHS | Linear programming first where valid; mixed-integer programming for exact piecewise rules. |
| Persistence | SQLite with migrations | Sufficient for one local participant application and durable intents. |
| Frontend | React + TypeScript + Vite | Interactive operational views without a separate server-rendering requirement. |
| UI components and styling | shadcn/ui + Tailwind CSS | User-selected component foundation, with a shared operations-dashboard theme. |
| Charts/network | SVG and a small chart library if needed | Six routes do not require a geographic mapping platform. |
| Backend tests | pytest | Pure-model, integration, and benchmark assertions. |
| UI verification | Playwright | Critical operator flows, error states, keyboard and mobile checks. |
| Packaging | Docker Compose | Official simulator plus application; one documented startup path. |

Pin mutually compatible stable dependency versions and lockfiles during implementation. This plan does not prescribe an untested version combination. Do not install ML frameworks.

Keep one backend worker for the MVP. Run CPU-bound optimization outside the async request loop, with a bounded executor and solve deadline. Do not start an independent controller in each web worker.

### 6.3 Proposed repository layout

All paths below describe future files, not existing implementation:

```text
fuel-operations/
  README.md
  compose.yaml
  .env.example
  backend/
    pyproject.toml
    app/
      main.py
      config.py
      api/                 # application routes, not simulator routes
      simulator/           # contracts, REST, SSE, normalized errors
      domain/              # entities, snapshot types, units
      projection/          # demand rules, timelines, event application
      planning/            # model builder, solver, baseline, fallback
      execution/           # coordinator, validation, outbox, reconciliation
      storage/             # schema, migrations, repositories
      reporting/           # metrics, explanations, exports
    tests/
      unit/
      contracts/
      integration/
      optimization/
  frontend/
    package.json
    components.json        # shadcn/ui configuration
    src/
      pages/
      components/
        ui/                # shadcn/ui primitives
        operations/        # domain-specific compositions
      api/
      types/
      styles/
    tests/
  scenarios/               # versioned test recipes, not simulator replacements
  benchmarks/              # runner and report specification
  docs/
    simulator-contract.md
    architecture.md
    optimization-model.md
    operations.md
    demo.md
  reports/                 # generated, timestamped benchmark outputs
```

## 7. State collection, freshness, and persistence

### 7.1 Snapshot contract

Each planning snapshot contains:

- Application run ID and simulator scenario/version/seed.
- Start and end observed ticks, simulation time, and tick size.
- Depot, station, route, region, supply, event, and allocation data.
- Per-response receive time, stale header, error, and content hash.
- Snapshot quality: `CONSISTENT`, `BOUNDED_SKEW`, `STALE`, `INCOMPLETE`, or `RESET_UNCERTAIN`.
- Existing pending/in-transit commitments and unresolved local intents.

Collect independent REST resources concurrently, with a bounded connection pool. Read `/v1/instance` before and after collection to estimate tick skew. This is a consistency heuristic, not an atomic-snapshot guarantee.

In paused tests, require the same tick before and after. In live mode, bounded skew may be unavoidable. Record it, validate relevant resources again before dispatch, and stop rather than combining severely inconsistent observations.

Do not create an endless retry loop seeking an impossible same-tick snapshot under injected latency.

### 7.2 Notifications and polling

Actual SSE names:

- `simulation.tick`
- `allocation.status_changed`
- `inventory.updated` — documented payload concerns depots, not station-demand updates.
- `simulator.notice`

Consume the stream promptly. Mark affected resources dirty and coalesce bursts into bounded REST refreshes; do not solve independently for every event. Retain the obligation to refresh after changes even when several notifications share one refresh.

Poll periodically as a recovery path. A stream that is still connected may have stopped delivering useful events after a queue overflow. Compare stream progress with REST tick progress.

On reconnect, perform a full refresh and ledger reconciliation. Do not send `Last-Event-ID` expecting replay.

### 7.3 Historical data capture

Persist demand rows by `(run_id, observation_id)` and enforce uniqueness of station/fuel/tick where consistent with confirmed schemas. Query each station with an explicit limit and locally retain needed history.

At defaults:

- 96 ticks per simulated day.
- 12 demand rows per tick globally.
- A global 2,000-row response spans about 166.7 ticks.
- A station-specific 2,000-row response spans about 666.7 ticks if it returns all three fuels.

These are row-count capacities, not guarantees of recoverability. If an outage exceeds the accessible window and no pagination exists, mark a history gap. Preserve global metrics as authoritative but do not invent complete per-station metrics.

### 7.4 Minimum persistent records

| Record | Essential fields |
|---|---|
| Run | UUID, simulator identity, image/version if known, start/end, policy/configuration hash, reset reason. |
| Snapshot | Run, tick range, timestamps, quality, payload reference/hash. |
| Observation | Run, simulator row ID, station, fuel, tick, demand/served/unmet. |
| Plan | Run, snapshot, model version, horizon, assumptions, solver status, objective values, solve duration. |
| Planned action | Route, endpoints, fuel, quantity, intended submission tick, reason and validation result. |
| Dispatch intent | Unique immutable key, exact body, request state, attempt count, simulator allocation ID. |
| Allocation mirror | Run + allocation ID, status, quantities, all lifecycle ticks, failure reason. |
| Metrics sample | Run, observed tick, raw simulator metrics and sample time. |
| Incident | Type, first/last seen, recovery, related resources, missing-history ranges. |
| Benchmark result | Scenario hash, policy, horizon, clock protocol, final metrics, completeness flags. |

Store decision inputs and immutable request bodies before sending. Separate historical storage from authoritative live state. The local database must never silently override fresh REST information.

### 7.5 Reset and restart

- On application restart, automatic sending starts disabled until current simulator state and unresolved intents are reconciled.
- On a known simulator reset, close the old run, create a new application run UUID, clear operational reservations, and retain historical reports.
- Never replay an old run's outbox into a reset simulator.
- Simulator IDs can be reused after reset. Key local records by run plus simulator ID.
- Scenario/seed equality is not a unique run identity. Tick rollback and reset notices help but may be missed during downtime.
- If reset cannot be distinguished safely from continuity, require an explicit run-boundary decision before enabling automatic dispatch. Document this limitation rather than inventing a reliable server run UUID.

## 8. Deterministic demand and inventory projection

### 8.1 No-ML boundary

Use fixed documented demand profiles, observed multipliers, known event schedules, arithmetic, and configurable safety assumptions. No fitted coefficients, trained prediction model, or learned policy is required.

History supports validation, residual reporting, and benchmarking. For this MVP, do not silently introduce adaptive training under a different name.

### 8.2 Nominal demand

After validating factor composition and clock semantics, calculate:

```text
nominal demand(station, fuel, tick)
  = profile_daily_liters
  × tick_minutes / 1440
  × hour_factor(profile, simulated_hour)
  × region_demand_factor
  × effective_station_multiplier(tick)
```

Use the simulator's time convention confirmed by C11. Do not convert to the developer's local timezone automatically.

| Profile | Diesel/day | Petrol/day | Octane/day | Guide noise parameter |
|---|---:|---:|---:|---:|
| urban_high | 8,500 | 10,500 | 5,600 | 0.10 |
| industrial | 14,000 | 4,500 | 2,200 | 0.08 |
| highway | 10,500 | 11,000 | 6,200 | 0.12 |
| regional | 7,200 | 7,600 | 3,600 | 0.10 |

| Profile | Busy period and factor | Otherwise |
|---|---|---|
| industrial | 06:00–17:59, 1.55 | 0.45 |
| highway | Hours 06–09 and 16–20, 1.35 | 0.75 |
| urban_high | Hours 07–09 and 16–20, 1.45 | 0.70 |
| regional | 07:00–20:59, 1.25 | 0.65 |

Verify inclusive hourly boundaries. If a configured tick crosses an hour boundary, reproduce the simulator's sampled or integrated behavior; do not assume either.

The guide's noise values do not establish a probability distribution or hard upper bound. Do not label `nominal × (1 + noise)` a guaranteed maximum without evidence.

### 8.3 Safety envelope

Provide explicit, deterministic policy parameters:

- Demand stress multiplier above nominal.
- Additional delivery-delay allowance in ticks.
- Target coverage buffer expressed in simulated minutes/hours.
- Optional extra coverage for stations with only one route.

Version these values and run sensitivity comparisons. They are engineering assumptions, not measured probabilities or guaranteed service levels. Convert durations using actual tick size.

Use either a documented stressed demand trajectory or separate named nominal/stress scenarios. Do not mix several unrelated buffers invisibly.

### 8.4 Events and double-counting prevention

- Current station multipliers already reflect active demand spikes. Do not multiply them again for the same active event.
- Start projections from the current observed state. Apply only future transitions whose semantics are confirmed.
- Delay/shortfall events may already have changed supply rows. Track event application state to avoid applying changes twice.
- Route and outage end times can guide projections only if publicly visible and their boundary semantics are verified.
- If overlapping events do not behave as simple independent multipliers or reference-counted closures, implement observed semantics or mark future projections uncertain.
- Run surprise-event experiments by injecting at the intended tick. Do not preload hidden future events into the planner.

### 8.5 Inventory trajectory

For each station/fuel, project tick by tick using verified ordering:

1. Apply the relevant status/event transitions.
2. Add existing arrivals at their actual expected times.
3. Add candidate new shipment arrivals at their projected times.
4. Apply verified capacity/overflow behavior.
5. Serve demand according to simulator behavior.
6. Record remaining stock and unmet demand.

The actual order must follow C03; the list above is a conceptual template, not an asserted simulator execution order.

For pending shipments with null arrival times, use verified departure timing to estimate arrival and mark it estimated. For in-transit shipments, use their returned expected-arrival field.

Calculate:

- First predicted shortage tick and simulated duration until shortage.
- Minimum inventory before the next incoming shipment.
- Nominal and stressed coverage.
- Unmet liters over the horizon.
- Route redundancy and next feasible delivery time.
- Depot stock trajectory and next resupply.

Do not add all incoming shipments to current usable stock: late deliveries cannot cover earlier demand.

## 9. Optimization specification

### 9.1 Planning policy

Use receding-horizon optimization:

1. Obtain a usable snapshot.
2. Reconcile existing commitments.
3. Build deterministic future demand, supply, and event timelines.
4. Solve for future submissions and resulting stock trajectories.
5. Execute only actions selected for the current decision epoch.
6. Observe actual results and solve again.

Start evaluation with a 96-tick horizon at the default tick size, and compare 48, 96, and 192 ticks. These are experiments, not established optimal settings. Expose horizon in simulated hours so non-default tick sizes remain meaningful.

The horizon should cover relevant lead times and demand peaks. Use a terminal-coverage objective or extended tail to reduce end-of-horizon shortsightedness. Near the end of a fixed evaluation, distinguish real post-evaluation service needs from arbitrary terminal stock rewards.

### 9.2 Variables and indices

Indices: depot `d`, station `s`, fuel `f`, route `r`, planning offset `k`, and allocation slot `j` where individual requests must be modeled.

Suggested variables:

| Variable | Meaning |
|---|---|
| `x[r,f,k,j] ≥ 0` | Liters submitted on route r in allocation slot j at offset k. |
| `z[r,f,k,j] ∈ {0,1}` | Optional slot-used flag, needed for shipment-count minimization. |
| `D[d,f,k] ≥ 0` | Depot inventory at a precisely defined phase of tick k. |
| `I[s,f,k] ≥ 0` | Station inventory at a precisely defined phase of tick k. |
| `y[s,f,k] ≥ 0` | Demand actually served in the model. |
| `u[s,f,k] ≥ 0` | Unmet demand, with `y + u = demand`. |
| `b[s,f,k] ∈ {0,1}` | Shortage branch selector where exact automatic consumption requires it. |
| `w[d or s,f,k] ≥ 0` | Overflow only if the simulator actually discards excess stock. |

Existing pending and in-transit shipments are commitments, not free decision variables. Cancellation is a separate validated action; do not silently remove pending commitments to make a plan feasible.

Use tight finite bounds from capacities, supplies, demand, and dispatch budgets. Never use arbitrary giant constants when a physical bound is available.

### 9.3 Conservation and timing

The model builder must express inventory at each relevant within-tick phase so an arrival cannot serve demand before it physically arrives.

Conceptually:

```text
depot next stock
  = depot current stock
  + realized scheduled supply
  + verified refunds
  - newly reserved/dispatched stock according to simulator semantics
  - verified overflow

station next stock
  = station current stock
  + realized shipment arrivals
  - automatically served demand
  - verified overflow
```

Do not subtract existing pending stock twice if REST already reflects reservation. C01 and C18 determine these accounting rules.

### 9.4 Exact automatic consumption: avoid a subtle false optimum

The simulator serves available fuel automatically. An optimizer must not gain fictitious flexibility by withholding service today to preserve inventory for tomorrow.

For an open station with available pre-demand stock `A` and demand `q`, encode `y = min(A, q)`. One mixed-integer formulation is:

```text
0 ≤ y ≤ A
y ≤ q
y ≥ A - M × b
y ≥ q - M × (1 - b)
b ∈ {0, 1}
```

Use a valid tight `M` for the particular station/fuel/tick. This selects `y=A` when supply is limiting and `y=q` otherwise. Outage service and inventory effects must follow C09.

A pure LP relaxation can be faster, but `y ≤ A` and `y ≤ q` alone do not force the correct consumption semantics when fairness or terminal-stock objectives are present. Use an LP operationally only after proving that its formulation reproduces the relevant behavior, or label it an approximation and validate proposals independently. An LP relaxation is also useful as an objective bound for tests.

Similarly, if the simulator clips excess inventory, any overflow variable must reproduce mandatory clipping. It must not allow the optimizer to discard usable stock voluntarily to create headroom.

### 9.5 Required constraints

| Constraint | Implementation requirement |
|---|---|
| Valid connectivity | Only observed routes connecting the requested depot and station. |
| Valid statuses | Station open; route available at required times; depot OPEN or CONSTRAINED as allowed. |
| Fuel conservation | No invented fuel and no substitution between fuel types. |
| Source availability | Reserve/dispatch only fuel available at the relevant phase. |
| Depot capacity | Respect observed capacities and confirmed arrival overflow semantics. |
| Dispatch budget | Sum all fuel/route quantities in the exact accounting window established by C04. |
| Per-allocation route limit | Each `x[r,f,k,j] ≤ route.max_shipment`; do not impose this on aggregate route flow. |
| Destination submission check | Each immediate request must satisfy current API headroom validation. |
| Destination arrival capacity | Existing and new incoming shipments must be considered at arrival times. |
| Lead times | Include verified acceptance-to-departure delay and route transit time. |
| Existing commitments | Preserve in-transit shipments and account for pending shipments. |
| Known future closures | Disallow actions whose verified submission/departure behavior would fail. |
| Finite supply | Use only observed future arrivals, with known delay/shortfall effects. |
| Execution window | Current actions must still be relevant when they are submitted. |

Allocation slots need an explicitly justified bound. The guide defines no minimum positive shipment volume. For practical dispatch, choose a documented quantity precision and stable consolidation/splitting policy; do not claim a slot-limited model covers every mathematically possible API request sequence without proving that bound sufficient.

An aggregate-flow model may split a planned quantity into valid requests after solving. That split is acceptable only if its ordered execution passes source, dispatch, current headroom, and future-arrival checks. Otherwise repair/re-solve; do not assume splitting preserves feasibility automatically.

### 9.6 Conservative safety restrictions

It can be sensible to reserve station headroom against all locally committed arrivals even if the server validates only current stock plus one request. This avoids overbooking but can exclude otherwise feasible time-separated deliveries.

Track such rules in the plan metadata as **application safety restrictions**. A model solved with them is optimal only within those restrictions. Prefer time-indexed arrival checks over unnecessarily reserving all future fuel against present headroom.

### 9.7 Objective hierarchy

Until official scoring is supplied, use a configurable lexicographic objective:

1. Minimize total unmet liters over the horizon.
2. Among plans within a small declared tolerance of the best primary value, improve the worst station/fuel service ratio where demand is positive.
3. Improve terminal coverage within feasible supply and capacity.
4. Reduce unnecessary allocated volume and transit exposure, then shipment count if supported.
5. Apply stable ordering/tie-breaking for reproducible plans.

Do not invent monetary costs. Transit exposure may use `liters × transit_ticks` as an explicitly labeled proxy, not currency, distance, emissions, or actual transport expense.

Solve objective stages sequentially with constraints preserving earlier objective values. Avoid giant arbitrary weights that accidentally sacrifice service for cosmetic preferences.

Display the objectives and tolerances. If official judging weights differ, create a separate policy profile and rerun comparisons rather than claiming the old hierarchy matches the official score.

### 9.8 Solver policy

- Begin with correctness on small cases, then benchmark the full time-indexed formulation.
- Use sparse constraints, stable variable order, pinned solver versions, and recorded options.
- Set a solve deadline derived from measured operational timing; unlimited project time does not imply unlimited decision latency.
- Check solver status before using result arrays.
- Independently check finite numbers, bounds, conservation, constraints, and current-action feasibility.
- Record objective values, solve duration, and MIP gap/dual bound when exposed.
- Reject incomplete or invalid solutions and use a fresh-state fallback.
- Preserve feasibility after numerical rounding; never round upward across a capacity constraint.
- Avoid a minimum shipment size hidden in code. If operationally useful, configure it and acknowledge it restricts the model.

### 9.9 Baseline and fallback policies

Implement these explicit policies:

| Policy | Purpose |
|---|---|
| No replenishment | Sanity baseline showing when starting inventory becomes insufficient. |
| Threshold replenishment | Simple valid comparator using current stock thresholds and feasible routes. |
| Earliest-shortage rule | Stronger deterministic comparator, also reused as the solver fallback. |
| Deterministic optimizer | Main policy using time-indexed demand, supply, and commitments. |

For an initial reproducible threshold baseline, use a declared reorder threshold of 30% and order-up-to target of 70% of station/fuel capacity. Count confirmed incoming commitments when calculating the refill amount; keep current API headroom and future receiving feasibility checks. Choose the fastest feasible route, then stable route ID for ties. These percentages are baseline configuration choices, not simulator rules; also report a reasonable threshold sensitivity sweep so the comparison is not against an intentionally weak setting.

The threshold policy and optimizer must share the same reliable integration/execution layer. Otherwise a benchmark may measure different retry implementations rather than better decisions.

Fallback when optimization fails but state is usable:

1. Rank station/fuel pairs by earliest shortage relative to feasible delivery time.
2. Prefer actions preventing immediate unmet demand; account for route dependency.
3. Compute a limited replenishment target from the same deterministic demand rules.
4. Select a feasible route and quantity using current source, dispatch, and destination checks.
5. Submit through the same outbox, then recompute remaining capacity.

If state is stale, incomplete, or reset-uncertain, fallback does **not** mean guessing. Hold new allocations and reconcile.

## 10. Decision loop and safe shipment execution

### 10.1 Operational pseudocode

```text
on startup:
    load configuration and unresolved intents
    establish run continuity
    refresh public state and reconcile ledger
    keep automatic sending disabled until reconciliation succeeds
    start stream consumer and polling scheduler

on state-change notification or polling deadline:
    coalesce work into one coordinator cycle
    collect a versioned snapshot
    detect reset, stale responses, missing resources, and ambiguous writes
    reconcile existing allocations and reservations
    if snapshot cannot support safe decisions:
        publish degraded state; do not create new dispatch intents
    else:
        build deterministic projections
        generate and independently validate a plan
        publish plan and reasons
        if automatic mode is enabled:
            execute current actions serially with freshness checks
    persist outcomes and schedule the next necessary refresh
```

### 10.2 Operating modes

- **Observe:** reads, projections, and plans only; no shipment writes.
- **Manual:** operator can approve a still-valid plan or create a validated manual allocation.
- **Automatic:** coordinator submits validated immediate actions.

Turning automatic mode off stops new intents. It does not recall in-transit shipments or erase requests whose outcomes are unknown. Explain that distinction in the interface.

### 10.3 Durable outbox lifecycle

```text
PROPOSED → VALIDATED → READY → SENDING
                              ├─ CONFIRMED
                              ├─ DEFINITIVELY_REJECTED
                              └─ UNKNOWN_OUTCOME → RECONCILING
                                                   ├─ CONFIRMED
                                                   ├─ exact replay if still appropriate
                                                   └─ HELD_FOR_REVIEW
```

Persist the immutable body and its idempotency key before the HTTP call. Use a run-scoped unique key under 150 characters, such as `runUUID:decisionSequence:actionSequence`.

The key belongs in the JSON body, not an HTTP idempotency header.

### 10.4 Submission contract

Copy the exact field pattern from guide §5.1:

```json
{
  "idempotency_key": "run-example:12:1",
  "source_depot_id": "depot-gazipur",
  "destination_station_id": "station-mirpur",
  "route_id": "route-gazipur-mirpur",
  "fuel_type": "DIESEL",
  "quantity": 3000
}
```

This is a schema example, not a recommended live shipment.

### 10.5 Uncertain outcomes and retries

- A timeout or connection loss may occur after the server accepted the allocation.
- First search a fresh allocation ledger for the immutable key.
- If found, attach the existing allocation and reconcile; do not submit a replacement.
- If not found and the exact original action remains safe and timely, retry the exact body with the same key.
- An exact replay can create a new shipment if the first attempt never reached the server. Therefore do not replay an obsolete decision blindly after a long outage.
- If safe resolution is impossible, hold the intent and avoid conflicting new allocations until resolved or explicitly reviewed.
- Never change quantity while retaining the old key.
- Cancellation does not make a key reusable.
- A mismatch error is a bug or explicit changed intent, not a reason to automatically generate a new key and resend.

There is no transactional bulk submit. Earlier allocations remain accepted if a later request fails. Refresh/replan remaining actions rather than pretending the whole plan was atomic.

### 10.6 Cancellation

Offer cancellation only for an allocation currently observed as pending. Immediately revalidate and call the documented endpoint. If it has departed, reconcile the returned conflict and keep it in projected arrivals.

After a cancel timeout, read allocation state before retrying. Account for refunds only after confirmation through authoritative state.

Automatic cancellation should be limited to clearly invalidated pending actions and must be tested for cancellation/replacement churn. Do not build it into the initial optimizer as a free rollback mechanism.

### 10.7 Error normalization

Handle all documented envelopes:

```text
{"detail": {"code": "...", "message": "..."}}
{"error":  {"code": "...", "message": "..."}}
{"detail": [ ... validation errors ... ]}
```

Preserve unexpected non-JSON error bodies safely in diagnostic records without crashing the controller.

| Error family | Response |
|---|---|
| 200/201 with valid allocation | Confirm and reconcile. |
| 404 unknown entity | Refresh configuration/state; stop the invalid action. |
| 409 route/status/capacity/inventory | Refresh affected state; invalidate the old decision and replan. |
| 409 idempotency mismatch | Quarantine intent and surface an implementation/integrity error. |
| 409 cannot cancel | Refresh allocation lifecycle; do not assume refund. |
| 422 invalid request | Fix client/model validation; do not retry unchanged. |
| 503 injected fault | Bounded retry/backoff and degraded mode; preserve write ambiguity rules. |
| Timeout/network error | Reconcile uncertain writes; bounded retry for reads. |

## 11. Crisis handling playbook

Read crisis state from public endpoints during operational runs. The scenario harness uses the admin endpoint only to create the test condition.

| Event | Deterministic response | Important limit |
|---|---|---|
| `demand_spike` | Refresh station multiplier; rebuild demand and shortage timelines; prioritize additional deliveries that improve service. | Do not double-apply already reflected multipliers. |
| `route_disruption` | Remove unavailable routes; inspect pending actions; use actual alternative routes where available; pre-position only when public advance notice exists. | Tongi and Cox’s Bazar have no alternate route in the documented network. |
| `station_outage` | Stop new submissions to closed station; model verified inventory/arrival behavior; prepare feasible replenishment for reopening. | Do not remove outage-related unmet demand from official metrics. |
| `depot_constraint` | Read current dispatch capacity and observed acceptance behavior; redistribute across available depots when beneficial. | `CONSTRAINED` remains shippable; no arbitrary capacity reduction. |
| `shipment_delay` | Refresh the depot supply schedule; postpone use of delayed stock; allocate available stock across competing stations. | This modifies depot supply arrivals, not necessarily participant shipment transit times. |
| `supply_shortfall` | Refresh supply quantities; optimize scarce fuel and expose unavoidable shortage risk. | One-shot quantity change does not automatically reverse when the event resolves. |

Empty filter lists apply broadly. In the test-lab UI, show the affected entities and require an explicit “all entities” selection rather than interpreting an accidentally empty selection as a targeted test.

Exact documented event parameter shapes:

| Event | `parameters` fields | Guide default |
|---|---|---|
| `demand_spike` | `multiplier`, `station_ids[]`, `region_ids[]` | multiplier 1.5 |
| `route_disruption` | `route_ids[]` | Empty filters apply to all routes. |
| `station_outage` | `station_ids[]` | Empty filters apply to all stations. |
| `depot_constraint` | `depot_ids[]` | Empty filters apply to all depots. |
| `shipment_delay` | `delay_ticks`, `depot_ids[]`, `fuel_types[]` | delay 2 ticks |
| `supply_shortfall` | `factor`, `depot_ids[]`, `fuel_types[]` | factor 0.5 |

The request wrapper is `type`, `start_tick` (integer ≥ 0), `duration_ticks` (positive integer), and optional `parameters` (object). End tick equals start plus duration. An example schema, copied from guide §7.7, is:

```json
{
  "type": "demand_spike",
  "start_tick": 8,
  "duration_ticks": 12,
  "parameters": {
    "region_ids": ["region-dhaka"],
    "multiplier": 1.8
  }
}
```

This demonstrates the request format; scenario timing should be selected and documented for each test.

Cancellation/replacement proposals must account for whether the original is still pending and whether any refund has actually occurred. If all feasible routes are unavailable, report the limitation; do not draw or use an imaginary route.

## 12. Fault handling and performance policy

### 12.1 Fault response

| Fault | Required response | Recovery gate |
|---|---|---|
| `latency` | Bound request concurrency, coalesce refreshes, measure plan age in ticks, avoid overlapping cycles. | Fresh enough snapshot and revalidated actions. |
| `unavailable` | Preserve local last-known display with age; pause new dispatch; retry public reads with bounded backoff. | Full state and outbox reconciliation. |
| `error_rate` | Retry transient reads; handle uncertain writes with same immutable key and ledger reconciliation. | Successful authoritative refresh; unresolved writes accounted for. |
| `stale_data` | Mark flagged data untrusted; invalidate operational cache; hold new allocations by default. | Unflagged refresh of every resource needed for the next action. |
| `stream_disconnect` | Reconnect with bounded backoff; keep REST polling active. | Stream recovered or operational polling verified; full resync after reconnect. |

Keep last-known values visible for diagnosis, but label them with age and degraded status. Holding new dispatch on stale data is an explicit safety policy, not a claim that it maximizes service under every failure.

Fault requests contain `type`, integer `duration_seconds` from 1 through 3600, and optional `parameters`. They start at the current wall time. `latency` accepts `delay_ms` (default 500); `error_rate` accepts `rate` (default 0.25); no parameters are documented for the other three types. Example:

```json
{
  "type": "latency",
  "duration_seconds": 5,
  "parameters": {"delay_ms": 500}
}
```

Clear active test faults with `POST /admin/faults/clear`. The operational controller must recover from natural expiration as well; clearing is a harness action, not an operational availability workaround.

### 12.2 Two clocks

With default settings:

```text
1 tick = 15 simulated minutes
1 tick ≈ 125 real milliseconds while running at 8 ticks/second
1 simulated day = 96 ticks ≈ 12 real seconds
500 ms API delay ≈ 4 ticks ≈ 1 simulated hour
60 real seconds of unavailability ≈ 5 simulated days
```

These are nominal conversions; actual measured tick progress is authoritative. Domain events use ticks. Faults use real seconds. Record both clocks in every resilience result.

### 12.3 Initial configurable performance targets

These are engineering targets to measure, not claims of achieved performance:

- One coordinator cycle in flight; no unbounded event or solve queue.
- At normal speed without faults, aim for at most one tick of observation-to-action age for urgent actions; measure whether hardware and model size permit this.
- Record p50/p95/p99 snapshot, solve, and submission latency separately.
- Choose a solver time budget below the remaining action-validity window, then benchmark. Do not prescribe a universal millisecond limit without measurement.
- Refresh display at a human-readable rate independent of decision frequency.
- Lower-priority histories and reports must not block the operational snapshot.
- On extended latency, skip outdated plans and replan rather than building a growing backlog.

If the full model cannot meet the real-time budget, shorten the horizon, simplify verified equivalent constraints, solve only on meaningful changes with a watchdog, or use the safe heuristic. Report the resulting policy and performance openly.

Do not silently slow or pause the simulator during a claimed normal-speed benchmark. A slow-motion demonstration is valid only when labeled as such.

### 12.4 Retry and stream timing

Configure connection, read, write, and pool timeouts separately. Reuse the operational HTTP client; give the stream its own long-lived connection lifecycle.

Do not impose a normal short request read timeout on an SSE stream whose documented keepalive interval is 15 seconds. A single quiet interval while paused is not a fault.

Use bounded retry/backoff appropriate to observed tick progression. If jitter is used to avoid synchronized reconnects, record its policy and use reproducible settings in deterministic tests. Allocation decisions remain independent of retry randomness.

## 13. Dashboard and operator workflows

### 13.1 Product design

Design a compact operations workspace, not a marketing landing page. The first screen should show network health, shortage risk, and operational controls.

Proposed visual direction: cool white surfaces, deep marine-blue structure, teal for normal fuel flow, amber for warnings, and red for failures. Use clear proportional typography and tabular numerals for quantities. The network diagram is the distinctive visual element; avoid decorative charts with no operational purpose.

All data must carry units. Never confuse real seconds, simulation ticks, and simulated hours.

Use **shadcn/ui + Tailwind CSS** as the required frontend component foundation, per the user's selection. Follow the [official Vite setup](https://ui.shadcn.com/docs/installation/vite) when implementation begins: configure Tailwind, matching TypeScript/Vite import aliases, and `components.json`; add only components the actual workflows need.

Compose the interface from shadcn/ui primitives rather than independently rebuilding equivalent controls:

| Dashboard need | Planned shadcn/ui component |
|---|---|
| Main navigation and grouped views | Sidebar and Tabs |
| Shipment, inventory, and benchmark rows | Table; add sorting/filtering composition where required |
| Allocation and event input | Field, Input, Select, Button, and explicit validation messages |
| Plan review and shipment details | Dialog or Sheet |
| Destructive simulator reset | Alert Dialog |
| Lifecycle and freshness indicators | Badge and Alert, with meaningful text |
| Three operating modes | Radio Group or Select; do not represent three states with one boolean switch |
| Loading and explanatory help | Skeleton and Tooltip |

Keep custom network SVG and domain charts inside this component system. Define shared theme tokens for surfaces, text, status colors, spacing, and focus states. Keep simulator/planning logic outside UI primitives. Verify keyboard focus, dialog behavior, contrast, and responsive tables after customization; using a component library does not replace accessibility checks.

### 13.2 Views

| View | Required contents and actions |
|---|---|
| Overview | Simulation clock, mode, data freshness, service level, unmet liters, six-route network, ranked shortage list. |
| Station detail | Fuel tanks, capacities, nominal/stressed inventory projection, observed demand, next arrivals, outage state, source options. |
| Depot detail | Current available stock, capacity, dispatch usage from confirmed semantics, future supplies, dependent stations. |
| Plans | Snapshot time, horizon, assumptions, solver result, immediate proposals, future tentative actions, approve/recalculate controls. |
| Shipments | Filter by lifecycle, station, depot, fuel; inspect request/arrival times; cancel pending shipments. |
| Incidents | Public event timeline, connectivity/staleness incidents, response and recovery log. |
| Test lab | Explicit simulator pause/run/step/reset, event/fault forms, benchmark controls; disabled when another run owns controls. |
| Reports | Baseline comparisons, per-station service, test metadata, completeness warnings, CSV/JSON export. |

These may be tabs or routes. Do not duplicate operational state across independent frontend stores.

### 13.3 Essential user journeys

1. **Start safely:** connect → view snapshot quality → inspect proposed plan → enable automatic mode.
2. **Understand a shipment:** select allocation → see demand risk, route choice, quantity bounds, solver/policy, and actual outcome.
3. **Review manually:** generate plan → review current actions → approve → revalidate snapshot → submit → show partial or complete results.
4. **Create a manual allocation:** choose station/fuel → show valid depots/routes → enter quantity → validate → persist intent → submit.
5. **Respond to crisis:** see event → inspect affected station/route → view changed risk → see replanned allocation or explicit infeasibility.
6. **Recover from outage:** see stale last-known values → controller holds writes → public reads recover → intents reconcile → automatic mode resumes only under configured policy.
7. **Run a benchmark:** select recipe and policies → review that the simulator will reset → run sequentially → inspect measured results → export.

Manual action errors must be understandable: “Only 1,400 L of receiving capacity remains” is better than exposing a raw traceback. Preserve raw simulator codes in expandable diagnostics.

### 13.4 Explainability without AI

Generate explanations from recorded calculations and binding constraints, using templates such as:

> Send {quantity} L of {fuel} from {depot} to {station}. Under the {assumption_profile} demand projection, stock falls below the buffer at tick {risk_tick}. This route is available and arrives at tick {arrival_tick}. The quantity is limited by {limiting_constraint}.

An explanation must distinguish:

- Observed current facts.
- Projected future outcomes.
- Policy preferences and safety margins.
- Solver-proven results versus heuristic actions.

Do not claim causal shortage prevention from one run alone. Measured “liters saved” needs a controlled comparison.

### 13.5 Accessibility and UI acceptance

- Keyboard-accessible actions, visible focus, labels, and meaningful table headers.
- Warnings use text/icons as well as color.
- Charts provide a readable table or textual summary.
- Destructive reset is visibly separated from ordinary controls and asks for in-product confirmation.
- Prevent double-click duplicate submission and show pending action state.
- Clear loading, empty, unavailable, stale, partial-success, and recovered states.
- Usable on a laptop and mobile width, without hidden critical controls.
- No fake live numbers, random chart series, or prefilled benchmark wins.

## 14. Application API proposal

These are **new application-owned endpoints**, not claimed simulator endpoints. Prefix them with `/api` to keep the distinction clear. Final schemas should be typed and documented during implementation.

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Application readiness, simulator connectivity, mode, run, freshness, controller state. |
| `GET /api/overview` | Current read model for network, metrics, risk, and incidents. |
| `GET /api/stations/{id}` | Observed and projected station details. |
| `GET /api/depots/{id}` | Observed depot and supply timeline. |
| `GET /api/allocations` | Local mirrored ledger with application-owned filters/pagination. |
| `GET /api/plans` | Plan history. |
| `GET /api/plans/{id}` | Inputs, status, proposals, assumptions, explanation. |
| `POST /api/plans/recalculate` | Request a new plan; coalesced through the coordinator. |
| `POST /api/plans/{id}/execute` | Revalidate and execute the immediate portion of a manual plan. |
| `POST /api/manual-allocations` | Validate and dispatch an operator-authored request. |
| `POST /api/allocations/{id}/cancel` | Safe pending cancellation through the coordinator. |
| `PUT /api/operating-mode` | Set observe/manual/automatic mode. |
| `GET /api/incidents` | Operational incident history. |
| `POST /api/lab/control` | Explicit run/pause/step/reset operation when lab is enabled. |
| `POST /api/lab/events` | Validated event injection for self-tests. |
| `POST /api/lab/faults` | Validated fault injection for self-tests. |
| `POST /api/lab/faults/clear` | Clear test faults. |
| `POST /api/benchmarks` | Start one exclusive benchmark job. |
| `GET /api/benchmarks/{id}` | Progress, results, and failures. |
| `GET /api/reports/{id}/export?format=csv` | Download report; support JSON separately. |

Use dashboard polling initially; an application-owned event stream is optional if it materially improves UX. Do not confuse it with simulator SSE.

For execute requests, include the expected plan/snapshot identity. Return a meaningful conflict when the plan is expired, replaced, or already executed. A second execute click must return existing action state, not create a second set of intents.

## 15. Metrics and evidence

### 15.1 Authoritative simulator metrics

| Metric | Interpretation |
|---|---|
| `served_demand_liters` | Total served since simulator reset. |
| `unmet_demand_liters` | Total unmet since reset. |
| `service_level` | Served divided by served plus unmet. Verify zero-demand convention. |
| `allocation_liters` | Only in-transit and arrived quantities count. Not all created quantities. |
| `allocation_failures` | Count of allocations marked FAILED, documented for departure-time route disruption. |

Keep these raw values. Do not replace official unmet demand with an adjusted figure that excludes outages or shortages the application considers unavoidable.

### 15.2 Application-derived metrics

- Per-station/fuel service level and unmet liters, with history completeness flags.
- Number and duration of stockout intervals, under a declared definition such as positive demand with positive unmet volume.
- Validated intent count, confirmed shipment count, rejections by code, retries, uncertain outcomes, and reconciliation duration.
- Duplicate logical shipment incidents; desired invariant is zero for the tested retry/restart scenarios.
- Snapshot age/skew, observation-to-submission ticks, solve time, missed decision windows, and fallback use.
- Stream disconnects, stale intervals, outage recovery time, and incomplete-history periods.
- Request count and transit-exposure proxy, labeled as application metrics.

### 15.3 Comparison calculations

```text
unmet reduction %
  = (baseline_unmet - candidate_unmet) / baseline_unmet × 100
```

If baseline unmet is zero, report absolute differences and “percentage reduction not defined”; do not divide by zero or claim an artificial percentage improvement.

For service improvement, distinguish **percentage points** from relative percentages. Compare equivalent run horizons and information access. Do not infer total customer counts from liters.

### 15.4 Result record

Each report must contain:

- Policy/configuration hash, application revision, solver version/options.
- Simulator image tag and digest when available, scenario/version/seed.
- Tick size, simulation speed, start/end ticks, and wall-clock duration.
- Event recipe, event visibility protocol, and fault schedule.
- State/observation completeness and known measurement gaps.
- Raw simulator metrics and derived metrics with definitions.
- Optimal/feasible/fallback counts and solver timing.
- Limitations and failures, including scenarios where the optimizer does not improve on the baseline.

## 16. Reproducible scenario and benchmark pipeline

### 16.1 Execution protocol

For each scenario and policy, sequentially on the same isolated test instance:

1. Acquire exclusive ownership; reject conflicting UI controls.
2. Export/preserve the previous run before resetting.
3. Reset the simulator, then explicitly pause and verify state.
4. Start a new local run and empty operational outbox for that run.
5. Configure the event schedule using the chosen announcement protocol.
6. For stepped tests, collect state, allow one complete policy decision epoch, submit immediate actions, then step once.
7. Continue for the declared horizon, capture demand history frequently, and record metric checkpoints.
8. Stop new allocations at the defined evaluation boundary and record in-transit/pending tail separately if relevant.
9. Export results and validate observation completeness.
10. Repeat for the next policy with identical initial conditions and action opportunities.

The application cannot switch baked scenarios or set a new seed through an invented API. Use organizer-provided image/configuration mechanisms only if actually available.

### 16.2 Announced versus surprise crises

- **Announced:** event is scheduled in advance and is visible through `/v1/events`; planners may use that public information if allowed by the evaluation protocol.
- **Surprise:** the harness injects at the chosen boundary; the planner does not receive the future recipe in advance.

Label these results separately. Advance warning is a different information condition, not necessarily a better algorithm.

### 16.3 Minimum scenario suite

| ID | Scenario | Required assertion or evidence |
|---|---|---|
| S01 | Baseline without events, long enough to require replenishment | Valid shipments and meaningful comparison after initial stock is consumed. |
| S02 | Single-station demand spike | Multiplier applied once; plan adjusts to increased nominal demand. |
| S03 | Regional spike spanning a busy period | Joint dispatch allocation across stations and fuels. |
| S04 | Primary route disrupted for Mirpur or Karnaphuli | Uses only actual alternate connectivity; respects longer lead time. |
| S05 | Tongi sole route disrupted | Announced case may pre-position; surprise case reports unavoidable isolation. |
| S06 | Cox’s Bazar sole route disrupted | Same test with its distinct transit/capacity profile. |
| S07 | Depot constraint | Uses observed capacity semantics; does not assume depot is closed. |
| S08 | Depot supply delay | Does not allocate stock before availability; updates future schedule. |
| S09 | Supply shortfall | Prioritizes under scarcity and preserves conservation. |
| S10 | Station outage and reopening | No new invalid submissions; verified demand/arrival behavior; recovery measured. |
| S11 | Overlapping crises | Correctly follows actual event interactions. |
| S12 | Beyond final listed supply | Shows finite-stock limits; never invents new resupply. |
| F01 | Latency | Bounded queue, no concurrent writers, measured plan age. |
| F02 | API unavailability | No blind new allocations; reconciliation after recovery. |
| F03 | Probabilistic errors | Safe retries without duplicate logical shipments. |
| F04 | Stale-data header | Blocks new automatic dispatch by default and explains why. |
| F05 | Stream connection failure | Polling continues, reconnect resynchronizes state. |
| R01 | Response lost after accepted allocation | Exactly one simulator allocation for the immutable intent. |
| R02 | App restart with unknown request outcome | Reconciles before resuming automatic sends. |
| R03 | Simulator reset while controller exists | Old run actions cannot leak into new run. |
| R04 | Partial plan execution followed by rejection | Retains confirmed actions, replans remainder. |
| R05 | Cancellation racing with departure | No assumed refund or duplicate replacement. |
| R06 | Solver timeout/invalid output | Feasible fallback or explicit hold; no unsafe payload. |
| R07 | Stream silently stops delivering useful events | REST watchdog detects progress mismatch and resyncs. |
| R08 | History window exceeded | Reports data gap; does not fabricate per-station totals. |

Exact event quantities and tick positions are scenario parameters chosen after baseline behavior is observed. Do not hard-code a hand-picked easy demonstration as the only benchmark.

### 16.4 Live fault testing

Run the same policy at documented normal speed in addition to stepped tests. Faults are wall-clock based and `error_rate` is probabilistic; repeat live trials and show distributions/ranges rather than claiming byte-identical outcomes.

A transport test double or local test proxy may reproduce “server accepted, response lost” precisely. Label that a client fault test and separately verify successful integration with the real simulator. Do not count proxy-generated outcomes as official simulation benchmarks.

### 16.5 Optimization correctness tests

- Hand-solvable tiny cases with one depot, one station, one fuel.
- Two stations competing for one limited dispatch budget.
- A station with no alternate supplier competing with a station that has one.
- Two arrivals at different times, proving late stock cannot serve earlier demand.
- An API headroom constraint binding at request time even when arrival-time space would exist.
- Multiple same-route allocations demonstrating per-request, not aggregate-route, limits.
- Counterexample preventing voluntary withholding of service by the model.
- Supply overflow and station outage cases matching confirmed semantics.
- Lexicographic priority test: secondary convenience cannot worsen primary service beyond tolerance.
- Numerical rounding and request-splitting feasibility.
- Solver objective compared with exhaustive enumeration on small quantized fixtures; label quantization and compare within the same model.
- Independent trajectory replay of every proposed plan before accepting solver feasibility claims.

Use deliberately small fixtures to test modeling errors. Do not reproduce the optimizer matrix construction verbatim in tests and call that independent verification.

## 17. Implementation phases and completion gates

There is no imposed schedule. Execute in dependency order and advance only when the phase's evidence is complete. Phase 0 is specified in §4.

### Phase 1 — Reproducible project foundation

**Implement:** repository structure, locked dependencies, typed configuration, application health endpoint, database migrations, Compose startup using the guide's simulator service pattern. Bind local services appropriately and keep the simulator image unchanged.

**Read/copy:** guide §1 lines 50–73 for Compose/startup; official FastAPI lifecycle reference in §24 for resource ownership.

**Verify:** clean startup from documented instructions; configuration errors explained; state persists across app restarts; simulator health and application health remain distinct.

**Guards:** no UI fake data presented as live; no ML dependency; no multiple auto-started controllers.

**Deliverables:** reproducible skeleton and setup documentation. No optimization claim yet.

### Phase 2 — Typed simulator client and state mirror

**Implement:** all public read contracts, allocation/cancellation clients, normalized error envelopes, resource freshness metadata, snapshot collection, SSE consumer and polling recovery.

**Read/copy:** guide §§4–6; public JSON examples lines 109–303; SSE protocol lines 390–422; HTTPX references in §24.

**Verify:** all documented resources load; stale flags propagate; stream reconnect performs resync; paused snapshots are consistent; bounded-skew running snapshots are labeled.

**Guards:** no invented filtering/pagination; no treating SSE as state; no audit event names used as SSE subscriptions.

**Deliverables:** integration tests and a trustworthy read-only state API.

### Phase 3 — Durable execution and reconciliation

**Implement:** run identity, serialized writer, immutable outbox, key generation, partial-plan handling, cancellation, restart/reset reconciliation, and mode controls.

**Read/copy:** guide §5.1 payload lines 320–329, §5.2 validation, §5.4 idempotency, §5.5 cancellation; this plan §10.

**Verify:** identical retry creates one allocation; changed body is rejected; lost-response recovery works; old-run intents cannot replay after reset; concurrent manual/auto actions cannot overspend shared resources.

**Guards:** no new key for an uncertain retry; no assumed cancellation refund; no batch atomicity assumption.

**Deliverables:** safe end-to-end manual allocation and lifecycle tracking.

### Phase 4 — Baseline and benchmark harness

**Implement:** no-action and threshold policies, exclusive test ownership, reset/pause/step loop, observation capture, CSV/JSON reports, versioned scenario recipes.

**Read/copy:** guide §7.5–7.13; event/fault request examples; metrics §4.12; this plan §16.

**Verify:** identical stepped runs reproduce documented domain outcomes; baseline sends valid requests; horizon reaches replenishment-dependent behavior; benchmark settings and missing data are recorded.

**Guards:** no admin fault bypass by evaluated policy; no preloaded surprise-event knowledge; no fabricated benchmark numbers.

**Deliverables:** a usable baseline report before optimizer work begins.

### Phase 5 — Deterministic projection engine

**Implement:** documented demand factors, simulated-clock handling, event transitions, fixed safety parameters, time-indexed stock/supply/arrival projections, shortage calculations, model discrepancy reports.

**Read/copy:** guide §8.5–8.6 tables and station/region fields; verified C01–C13 fixtures; this plan §8.

**Verify:** hour boundaries, non-default tick size, event overlap, no double-counting, incoming arrival timing, outage behavior, and conservation.

**Guards:** no learned demand model; no treating noise parameter as a proven bound; no exact jitter prediction from seed alone.

**Deliverables:** deterministic projection API and clear assumption profiles.

### Phase 6 — Optimization model

**Implement:** time-indexed constraints, exact required piecewise behavior, objective hierarchy, solver status reporting, stable variable ordering, independent feasibility validator, splitting/rounding policy, and fallback.

**Read/copy:** official SciPy API signatures in §24, guide §5.2 and §8, and this plan §9. Use verified simulator semantics rather than inferring missing behavior from examples.

**Verify:** hand-solvable fixtures, no fictitious withheld demand, known optimal cases, constraint residuals, timeout behavior, stable repeated plans under pinned settings, and full-network benchmark comparison.

**Guards:** no route aggregate cap mistaken for per-allocation cap; no fake monetary objective; no “optimal” label for a heuristic or incomplete solve.

**Deliverables:** versioned model specification plus executable planning component with correctness evidence.

### Phase 7 — Automatic operating loop

**Implement:** coalesced event-driven planning, polling backstop, plan expiration, fresh-state validation, shared manual/automatic coordinator, bounded solve execution, degraded/hold/recovery state transitions.

**Read/copy:** guide §§6 and 10; this plan §§7, 10, and 12.

**Verify:** no overlapping writers; no unlimited queue growth; good behavior at default speed; old plans rejected after changed state; no writes based on unusable snapshots.

**Guards:** automatic mode must not pause the simulator to conceal performance issues; no CPU-bound solves blocking networking.

**Deliverables:** autonomous end-to-end runs with measured decision latency.

### Phase 8 — Complete operator dashboard

**Implement:** all views and journeys in §13 using React + TypeScript + Vite, shadcn/ui, and Tailwind CSS, backed by the application API; network diagram, risk table, projections, shipment lifecycle, plan review, incidents, and report export. Initialize the shared theme and required shadcn/ui primitives before composing domain screens.

**Read/copy:** typed application schemas from prior phases; guide field names for data mapping; design requirements in §13.

**Verify:** live data throughout; approve/cancel/recalculate flows; stale/loading/error/partial-success states; accessibility and laptop/mobile checks; no duplicate submissions on repeated clicks.

**Guards:** no fictitious routes or metrics; no raw solver implementation jargon in ordinary operator actions; future tentative actions clearly distinguished from submitted shipments.

**Deliverables:** complete manual and automatic user workflows.

### Phase 9 — Crisis and resilience suite

**Implement:** all documented event/fault types in the lab, targeted scenario recipes, retry/restart/reset tests, overlap tests, and normal-speed performance experiments.

**Read/copy:** guide §7.8 event parameter table, §7.9–7.10 fault fields; this plan §§11–12 and §16.

**Verify:** execute all S/F/R scenarios; capture failures and recovery evidence; history gaps correctly flagged; tests remain isolated from ordinary operation.

**Guards:** distinguish wall time from ticks; empty filters must not accidentally affect the whole world; no hidden lab state passed to planner.

**Deliverables:** fault-resilience report and resolved critical integration defects.

### Phase 10 — Optimization evaluation and refinement

**Implement:** horizon/safety-profile comparisons, fairness reporting, solver performance tuning, and evidence-backed policy defaults.

**Read/copy:** official solver method/options documentation; baseline reports and independent replay results; this plan §§9 and 15–16.

**Verify:** compare policies on identical scenarios and action opportunities; retain negative results; distinguish nominal model performance from actual service; confirm no primary-objective regressions caused by secondary weights.

**Guards:** no tuning only to one demo scenario; no claims of guaranteed zero stockouts; no switch to a different runtime speed in only the favored policy.

**Deliverables:** defensible default policy, sensitivity report, and documented limits.

### Phase 11 — Packaging, documentation, and demonstration

**Implement:** clean local startup, configuration examples, backup/export procedure, operational runbook, known limitations, architecture/model docs, and a short repeatable demo script.

**Read/copy:** guide startup pattern and tested commands; actual measured reports, not hypothetical improvements.

**Verify:** clean environment setup, no network-dependent fonts/assets required for core use, persisted run recovery, exported report readability, and rehearsed crisis demo.

**Guards:** no unsupported promises about judging criteria; no optional cloud deployment required to run a local simulator app.

**Deliverables:** full MVP release candidate and submission-ready evidence package subject to official participant brief.

### Phase 12 — Final verification and release gate

**Implement:** fix any remaining release blockers; freeze the reviewed contract/model/configuration versions and benchmark package.

**Read:** all guide hard rules, recorded contract probes, final application behavior, and official participant brief if provided.

**Verify:** complete the definition-of-done checklist in §22; run required contract, optimization, integration, resilience, and critical UI checks; confirm fresh reports match the released application revision.

**Anti-pattern audit:** search for unauthorized simulator database access, ML dependencies, invented API paths, random dashboard metrics, undocumented hard-coded capacity reductions, multiple controller startup sites, and new idempotency keys inside blind retry loops. Review findings rather than relying on keyword search alone.

**Deliverables:** release notes with measured results, unresolved limitations, and exact startup/demo instructions.

## 18. Configuration specification

Separate simulator configuration from application policy configuration.

| Configuration | Meaning / initial policy |
|---|---|
| Simulator base URL | Backend connection target; container and host URLs differ. |
| Tick size | Read from instance; simulator environment controls actual value. |
| Simulation speed | Test metadata / simulator setup; do not infer solely from wall-clock assumption. |
| Start mode | Observe/manual by default until run reconciliation completes. |
| Horizon hours | Starting experiment 24 hours; compare 12 and 48 hours. |
| Demand profile version | Versioned fixed tables and verified factor semantics. |
| Demand stress multiplier | Explicit configurable assumption; baseline nominal = 1.0. |
| Delay allowance | Fixed extra planning ticks after verified physical lead time. |
| Coverage target | Simulated duration, not an unlabelled liters constant. |
| Single-route reserve preference | Visible policy option evaluated in benchmarks. |
| Snapshot skew/age budget | Conservative dispatch gate calibrated against measured speed. |
| Solve deadline | Measured operational budget, with fallback. |
| Solver tolerances | Recorded feasibility/optimality settings. |
| Quantity precision | Declared rounding policy and minimum effective quantity if any. |
| Request timeouts/backoff | Separate ordinary requests and SSE. |
| History collection limit | Explicit legal limit; choose station-specific collection when needed. |
| Retention | Preserve run metrics/intents; rotate verbose snapshots/logs by policy. |
| Lab enabled | Local-only controls; visibly separated from operational mode. |

Reject invalid configurations early: negative buffers, unsupported policy names, nonpositive horizon, illegal history limits, or impossible numerical tolerances. Record effective configuration with every run.

## 19. Security, local operation, and maintenance

Keep this proportional to a single-tenant local hackathon application:

- Bind published ports to loopback by default where practical; the guide does not specify simulator authentication.
- Do not expose admin reset/fault controls publicly.
- Keep browser mutations same-origin and apply an appropriate origin/CSRF guard for local state-changing endpoints.
- Validate all user-entered quantities, IDs, durations, and event parameters on the backend.
- Route all UI mutations through the coordinator; do not allow a UI shortcut to bypass execution validation.
- Keep simulator base URL in trusted configuration rather than an unrestricted arbitrary URL-fetch endpoint.
- Store SQLite in a named persistent volume or documented local data directory; back up/export before reset-driven benchmark sessions.
- Preserve run logs outside the simulator, since simulator reset deletes its tables and audit history.
- On shutdown, stop generating intents, persist unresolved requests, and reconcile on restart.
- Keep one controller owner and one test-harness owner; locks must fail visibly if conflicting work is requested.

No authentication platform is needed for a loopback-only MVP. If later deployed to a shared network, access control and deployment security become a separate required workstream.

## 20. Demo and presentation plan

The demonstration should prove an operating system and its evidence. Adapt length to the official participant brief when available.

1. Show the official simulator connection, clock, current inventory, and service metrics.
2. Show a deterministic projection and explain one potential shortage using visible inputs.
3. Show the plan's solver status, assumptions, and immediate actions.
4. Enable automatic execution and follow a shipment from pending to arrival.
5. Introduce a declared crisis and show the system react through actual available routes.
6. Demonstrate a fault or lost-response recovery without duplicate logical shipments.
7. Open a saved controlled comparison against the threshold policy.
8. State where the policy is model-optimal, where it is conservative, and where unknown future conditions limit guarantees.

Use one understandable crisis sequence in the live demo. Keep the broader scenario evidence available in reports. Do not attempt to prove every fault type live during a short presentation.

Suggested evidence package:

- Screenshot or live view of network and shortage risk.
- One decision record with its input snapshot and constraint explanation.
- Benchmark comparison table and per-station service chart.
- Reliability case showing a single allocation after uncertain response/retry.
- One-page assumptions and limitations summary.

## 21. Risk register

| Risk | Consequence | Mitigation / closure evidence |
|---|---|---|
| Missing participant brief | MVP might miss official deliverables or objective weights. | Obtain brief; map every explicit requirement before submission. |
| Incorrect tick ordering | Optimizer uses stock too early or misses departures. | C02/C03 probes and independent trajectory tests. |
| Demand model mismatch | Model-optimal plan performs poorly in actual runs. | Compare nominal projection with actual demand; expose discrepancy; fixed stress profiles. |
| Pure LP with voluntary service | False optimum that simulator cannot execute. | Exact consumption constraints or proven equivalence. |
| Too much optimization latency | Plan expires before dispatch. | Measure full cycle, bound solve time, simplify horizon, safe fallback. |
| Inconsistent REST snapshots | Overspending or rejected actions. | Timestamp/skew tracking, resource revalidation, serialized execution. |
| Ambiguous POST outcome | Duplicate or obsolete shipment. | Durable immutable intent, ledger reconciliation, same-key replay only when appropriate. |
| Hidden reset | Old intents replay into a new world. | Run isolation, continuity checks, hold on ambiguity. |
| Sole-route isolation | Unavoidable local shortage. | Public-notice pre-positioning where possible; report physical limitation honestly. |
| Finite total supply | Service eventually falls regardless of controller. | Fixed benchmark horizon and supply feasibility analysis. |
| Lost history during outage | Misleading station-level reports. | Frequent persistence, explicit gap detection and completeness flags. |
| Overfitting scenario recipes | Attractive demo but fragile general performance. | Hold-out recipes, varied event times and severities, report failures. |
| Incorrect “optimal” marketing | Claims exceed evidence. | Record exact model, objective, tolerance, solve status, and information assumptions. |

## 22. Final definition of done

### Integration and safety

- [ ] Official image runs unchanged through documented setup.
- [ ] Every used simulator API exists and matches verified request/response contracts.
- [ ] Current source and destination data are validated before submissions.
- [ ] One operational writer handles manual and automatic requests.
- [ ] Retry and restart tests show no duplicate logical shipment for the same intent.
- [ ] Pending-only cancellation and departure races are handled correctly.
- [ ] Reset boundaries isolate old histories and unresolved requests.
- [ ] All documented error envelopes are handled without crashing.
- [ ] Stream reconnection and silent-loss polling fallback work.
- [ ] Stale/incomplete/reset-uncertain state cannot silently trigger new dispatch.

### Deterministic planning

- [ ] No AI/ML/LLM dependency participates in decisions or explanations.
- [ ] Demand equations, hour factors, event effects, and safety parameters are documented.
- [ ] Source reservation and shipment timing follow contract probes.
- [ ] Future arrivals are time-indexed and not counted as immediately usable stock.
- [ ] Per-shipment limits are not mistaken for aggregate route limits.
- [ ] Model respects automatic service and actual overflow behavior.
- [ ] Solver output is independently checked before execution.
- [ ] “Optimal,” “feasible,” and “fallback” labels match actual evidence.
- [ ] No claim of global optimality or guaranteed zero shortages is made without proof.

### Product and evidence

- [ ] Observe, manual, and automatic workflows function end to end.
- [ ] Dashboard uses the user-selected shadcn/ui + Tailwind CSS foundation with consistent theme tokens and verified keyboard interactions.
- [ ] All displayed values have correct units and freshness indicators.
- [ ] All six domain events and five fault types are covered by tests.
- [ ] Stepped benchmarks and default-speed runs are both recorded.
- [ ] Baseline and optimizer use comparable information and action opportunities.
- [ ] Reports contain authoritative metrics, per-station detail where complete, and missing-data flags.
- [ ] Setup, operations, model, and demo documentation match the released version.
- [ ] A clean local startup and a complete demonstration have been rehearsed.
- [ ] Official participant-brief requirements are reconciled before submission, or their absence remains explicitly stated.

Completion is defined by these gates, not by an arbitrary number of implementation hours.

## 23. Requirement traceability

| Guide requirement or fact | Plan coverage | Primary verification |
|---|---|---|
| External app, published simulator (§2) | §§2, 6, 17 | Clean Compose run; unchanged image. |
| REST authoritative (§2, §6) | §§7, 10, 12 | Reconnect, snapshot, and stale-data tests. |
| Allocation creation contract (§5.1) | §§4, 10 | Typed request contract test. |
| Capacity/status validation (§5.2) | §§4, 9, 10 | Boundary cases and independent feasibility checks. |
| Idempotency (§5.4) | §§7, 10 | Lost-response/restart tests. |
| Pending cancellation (§5.5) | §§10, 13 | Cancellation race test. |
| No SSE replay; queue 200 (§6) | §§7, 12 | Disconnect and silent-loss tests. |
| Six crises (§7.8) | §§8, 11, 16 | S02–S11 and contract probes. |
| Five faults (§7.10) | §§12, 16 | F01–F05 and live trials. |
| Admin bypasses faults (§2, §7) | §§4, 6, 16 | Planner cannot access admin-only state. |
| Fixed topology (§8.1–8.4) | §§5, 9, 13 | Valid route matrix and sole-route cases. |
| Demand profiles/time factors (§8.5–8.6) | §8 | Hour/timezone/tick-size projection tests. |
| Finite 22-arrival schedule (§8.7) | §§5, 9, 16 | No-supply-tail scenario. |
| Demand history limits (§4.11) | §§7, 15 | Window overflow and gap-reporting test. |
| Official metrics (§4.12) | §15 | Raw metric preservation and formula checks. |
| Missing judging/deliverable brief (scope) | §§2, 20, 22 | Organizer clarification and final mapping. |

## 24. Reference index and copy-ready implementation sources

### 24.1 Supplied source

Primary local source: `/home/bakau/BUP_Hakathon/BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md`.

| Location in supplied Markdown | What to read/copy during implementation |
|---|---|
| Line 17 | Scope limitation: integration guide, not full participant brief. |
| Lines 52–62 | Official simulator Compose service. |
| Lines 75–97 | Hard rules and quick reference. |
| Lines 109–303 | Public response examples and metrics. |
| Lines 320–338 | Allocation payload and constraints. |
| Lines 340–354 | Server validation order. |
| Lines 358–388 | Success object, idempotency, cancellation. |
| Lines 390–422 | SSE framing, names, buffer, reconnect, fault interaction. |
| Lines 446–458 | Step and reset behavior. |
| Lines 467–498 | Event request and parameter shapes. |
| Lines 507–531 | Fault request and effects. |
| Lines 543–563 | Audit example and admin listing behavior. |
| Lines 571–630 | World configuration and finite supply pattern. |
| Lines 634–656 | Status-code table; reconcile replay inconsistency with §5.4. |
| Lines 662–687 | Defensive integration checklist. |

Line references are for the supplied file as reviewed; section numbers remain the more stable references if formatting changes.

### 24.2 Verified official dependency documentation

These sources support proposed technology/API choices; they are not hackathon rules. Recheck against pinned versions during implementation.

- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite): official setup for the user-selected UI stack, including Tailwind CSS, import aliases, initialization, and adding components. Apply this during the frontend implementation phase; no installation is performed as part of this plan update.

- [SciPy `linprog`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html): linear objectives, equality/inequality constraints, bounds, HiGHS methods, result status. Documented call shape: `linprog(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None, bounds=(0, None), method='highs', ..., options=None, ..., integrality=None)`. Consult method-specific options; do not assume unsupported HiGHS callbacks or `x0` warm starts.
- [SciPy `milp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html): mixed-integer model interface with objective, integrality, bounds, constraints, and options. Use `Bounds` and `LinearConstraint` as documented. Check status and available solution/gap fields before interpreting output; use supported time and gap controls for the pinned version.
- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/): manage HTTP clients, storage connections, and controller startup/shutdown through the application lifespan mechanism. Ensure one owner of the controller.
- [HTTPX async support](https://www.python-httpx.org/async/): reuse an `AsyncClient` and use its streaming interface for long-lived responses. Avoid creating a new client inside every hot-loop request.
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/): configure connect, read, write, and pool timeouts separately, with a distinct policy for the SSE connection.

### 24.3 Implementation handoff instructions

When implementation is later authorized, execute one phase at a time. At the start of each phase:

1. Read that phase's listed source sections and previously verified contract fixtures.
2. Identify its dependencies and unresolved assumptions.
3. Implement only the stated deliverables and necessary supporting code.
4. Run its verification checklist and document actual outcomes.
5. Update the contract/model document if observations differ from the guide.
6. Advance only when the completion gate passes or a clearly documented limitation has an accepted conservative treatment.

The first concrete implementation milestone is a safe manual shipment lifecycle against the official image. The final milestone is a complete, tested deterministic operations application with measured benchmark evidence. No application construction is authorized by this planning document itself.
