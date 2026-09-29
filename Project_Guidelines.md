# Fuel Operations — Fuel Supply Intelligence & Resilience Platform

A working operator application for the **BUP CSE Fest 2026 fuel supply challenge**. Fuel Operations observes the official simulator, estimates shortages, optimizes replenishment, explains recommendations, and records operator decisions while exposing health and performance information.

**Documentation baseline:** repository commit [0b2dd5c](https://github.com/rafidahad/bup_Final/commit/0b2dd5c2660cd9ec86081c7eeaf65bda27582f0a), reviewed on 29 September 2026. This README follows all **26 sections** of the [official problem statement](Problem_Statement_BUP_CSE_Fest_2026.pdf). “Implemented” describes code present in this snapshot; recorded results are historical evidence, not new measurements from this documentation review.

> **Current intelligence:** formula-based demand estimation, statistical diagnostics, stockout projection, a SciPy/HiGHS linear optimizer, and a threshold fallback. **Chronos forecasting and Grok incident summaries are approved plans, not implemented features in this snapshot.** No model training or API key is needed to run the current application.

## Quick start

Prerequisite: Docker with Docker Compose v2 and access to this repository.

~~~bash
git clone https://github.com/rafidahad/bup_Final.git
cd bup_Final
~~~

Create the configuration file:

~~~bash
# Linux / macOS
cp .env.example .env
~~~

~~~powershell
# Windows PowerShell
Copy-Item .env.example .env
~~~

For a slower demonstration, set **SIMULATION_SPEED=1** in .env. Then start the stack:

~~~bash
docker compose up -d --build
docker compose ps
~~~

| Service | Local address |
|---|---|
| Operator application | [localhost:8100](http://localhost:8100) |
| Backend API documentation | [localhost:8100/docs](http://localhost:8100/docs) |
| Component health | [localhost:8100/api/health](http://localhost:8100/api/health) |
| Prometheus metrics | [localhost:8100/metrics](http://localhost:8100/metrics) |
| Grafana | [localhost:3000](http://localhost:3000) |
| Prometheus | [localhost:9090](http://localhost:9090) |
| Official simulator API documentation | [localhost:18000/docs](http://localhost:18000/docs) |

The simulator starts **paused**. Open the application and click **Start** in the top bar. Keep **I approve** selected to review recommendations before sending fuel. Inspect the **Home**, **Actions**, **History**, and **System** pages.

~~~bash
docker compose logs -f fuelops
docker compose down
~~~

The normal stop command preserves the application's named SQLite volume. Simulator state has a separate lifecycle; preserving application history does not preserve the simulated world.

**Reading guide:** [architecture and source layout](#5-what-your-team-must-build) · [intelligence and AI roadmap](#7-intelligence-requirement) · [deployment](#12-devops-requirement) · [load-test evidence](#17-load-testing) · [demo](#22-suggested-demonstration-story) · [known limitations](#24-constraints-and-guardrails)

## 1. Executive Summary

The challenge is to build an operational fuel-supply application that remains useful during shortages, disruptions, and failures. A dashboard alone is insufficient: operators must be able to understand the network, anticipate problems, evaluate recommendations, act, and observe the outcome.

Fuel Operations implements this cycle:

**Observe → Detect → Predict → Optimize → Explain → Review → Allocate → Monitor**

Its current product combines a React interface, a FastAPI backend, the organizer's simulator, SQLite audit storage, and Prometheus/Grafana monitoring. It operates entirely inside the simulated environment.

## 2. Primary Engineering Challenge

The engineering problem is to connect intelligence to a reliable operational workflow.

| Challenge | Current implementation | Remaining work |
|---|---|---|
| Understand a changing fuel network | Validated snapshots of stations, depots, routes, events, supply, and allocations | Stronger stale-response detection |
| Anticipate shortages | Demand estimates, projected inventory, stockout timing, heuristic risk | Evaluate pretrained forecasts against the formula |
| Recommend feasible actions | Receding-horizon LP, capacity checks, threshold fallback | Complete pending outage/timing correctness fixes |
| Explain and review decisions | Before/after projections, signals, route alternatives, operator approval | Versioned proposals and stronger approval validation |
| Continue through failures | Retries, cached state, circuit breaking, fallback, alerts | Durable allocation-intent reconciliation after restart |
| Demonstrate engineering quality | Tests, Compose, CI smoke deployment, metrics, k6 artifacts | Rerun evidence on the intended VPS and after AI integration |

Implementation should be judged by service outcomes, decision quality, recoverability, and measured performance—not by the number of models used.

## 3. Scenario

The official simulator represents a Bangladesh fuel network containing regions, depots, stations, transport routes, scheduled supply, demand, events, and allocation records.

The application handles **DIESEL, PETROL, and OCTANE**. Each station needs replenishment before its available inventory is exhausted, subject to:

- Fuel actually available at the source depot.
- Depot dispatch capacity and route shipment limits.
- Route availability and transit time.
- Station capacity and fuel already on the way.
- Demand changes, outages, and disruptions.
- The finite amount of fuel in the simulated world.

An allocation accepted by the API is not the same as a completed delivery. Its pending, in-transit, delivered, cancelled, or failed state must be tracked separately.

## 4. Organizer-Provided Fuel Supply Simulator

The stack uses the organizer's image unchanged:

~~~text
asifmahmoud414/bup-fuel-supply-simulator:1.0.0
~~~

The simulator is the authoritative source of operational state. Application integration uses its public REST interfaces; test controls are used only for simulation setup and fault demonstrations.

| Integration responsibility | Source |
|---|---|
| HTTP client, retries, response handling | [fuelops/sim.py](fuelops/sim.py) |
| Snapshot assembly and allocation execution | [fuelops/execute.py](fuelops/execute.py) |
| Operational polling and recovery | [fuelops/controller.py](fuelops/controller.py) |
| Contract experiments | [fuelops/probes.py](fuelops/probes.py) |
| Reproducible crisis recipes | [fuelops/scenarios.py](fuelops/scenarios.py) |
| Simulator integration reference | [Integration guide](BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md) |

Important observed semantics, documented in the [development log](devlog.md):

- Accepted allocations reserve stock; acceptance does not prove arrival.
- Pending cancellation and idempotent retries have specific simulator semantics.
- Arrival capacity clipping can waste fuel, so incoming stock must count toward headroom.
- Outages affect service and inventory behavior and require explicit handling.
- Tick boundaries affect arrival and demand timing.
- A simulator reset creates a new operational context.

These findings apply to the pinned simulator image. The application currently polls REST; an SSE consumer is not implemented.

## 5. What Your Team Must Build

The delivered system is an application with an operational backend, persistent audit data, an intelligence layer, deployment configuration, and observable behavior.

### Current architecture

This diagram shows **implemented components only**. React is built into the backend image and served by FastAPI; it is not a separate production container.

~~~mermaid
flowchart TB
    OP["Operator"]
    UI["React application<br/>Home · Actions · History · System"]
    OP --> UI

    subgraph STACK["Docker Compose stack"]
        SIM["Official simulator container<br/>Network state, events, allocations"]
        subgraph APP["fuelops container — FastAPI, one operational writer"]
            API["REST API and static web assets"]
            CTRL["Controller<br/>Polling, validation, run tracking, recovery"]
            INTEL["Demand formula and diagnostics<br/>Stockout projection and confidence"]
            LP["Receding-horizon LP<br/>Threshold fallback"]
            CARDS["Recommendation cards<br/>Impact, constraints, alternatives"]
            EXEC["Approval and execution<br/>Fresh snapshot, clipping, idempotency"]
            STORE["SQLite audit store"]
            MON["Health, metrics and incidents"]
            CTRL --> INTEL --> LP --> CARDS
            CTRL --> MON
            LP --> MON
            EXEC --> MON
            API --> CARDS
            API --> EXEC
            CARDS -->|"Approved or eligible automatic action"| EXEC
            EXEC --> STORE
            CTRL --> STORE
        end
        PROM["Prometheus<br/>5-second scrape"]
        GRAF["Grafana<br/>Provisioned dashboard"]
        VOL[("fuelops-data volume")]
        CTRL -->|"Read public REST state"| SIM
        EXEC -->|"Create or cancel simulated allocations"| SIM
        STORE --> VOL
        MON --> PROM --> GRAF
    end
    UI -->|"/api requests"| API
    API -->|"Serves production web build"| UI
~~~

The operational path remains inside the backend. Prometheus and Grafana observe it; they do not authorize or dispatch fuel.

### Current project structure

~~~text
bup_Final/
├── README.md
├── Problem_Statement_BUP_CSE_Fest_2026.pdf
├── BUP_Fuel_Supply_Deterministic_MVP_Full_Plan2.md
├── BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md
├── devlog.md
├── .env.example
├── Dockerfile
├── compose.yaml
├── requirements.txt
├── .github/
│   └── workflows/ci.yml
├── fuelops/
│   ├── api.py             # HTTP endpoints and production web serving
│   ├── controller.py      # Live observation/decision cycle and recovery
│   ├── sim.py             # Official simulator HTTP client
│   ├── execute.py         # Snapshots, allocation limits and execution
│   ├── intel.py           # Diagnostics, observed noise and confidence
│   ├── projection.py      # Inventory and stockout projections
│   ├── lp.py              # Linear programming formulation
│   ├── policies.py        # LP variants and threshold fallback
│   ├── decisions.py       # Recommendation explanations and alternatives
│   ├── store.py           # SQLite decision and incident persistence
│   ├── metrics.py         # Prometheus instrumentation
│   ├── scenarios.py       # Baseline and crisis recipes
│   ├── probes.py          # Simulator contract checks
│   ├── harness.py         # Stepped policy comparison
│   ├── hindsight.py       # Offline perfect-hindsight comparison
│   └── livetest.py        # Live fault experiments
├── tests/
│   ├── test_lp.py
│   └── test_resilience.py
├── ops/
│   ├── prometheus.yml
│   ├── grafana/
│   │   ├── dashboards/fuelops.json
│   │   └── provisioning/
│   │       ├── dashboards/fuelops.yml
│   │       └── datasources/prometheus.yml
│   └── k6/
│       ├── load.js
│       ├── summary_run1.json
│       ├── summary_run2.json
│       ├── summary_realistic.json
│       └── stats_run*.csv
└── web/
    ├── package.json
    ├── package-lock.json
    ├── vite.config.ts
    ├── public/
    └── src/
        ├── App.tsx
        ├── main.tsx
        ├── index.css
        ├── components/
        │   ├── NetworkMap.tsx
        │   └── ui/
        ├── lib/
        │   ├── api.ts
        │   ├── text.ts
        │   └── utils.ts
        └── views/
            ├── Home.tsx
            ├── Actions.tsx
            ├── History.tsx
            ├── System.tsx
            └── parts.tsx
~~~

Generated databases, experiment reports, dependencies, and web build output are not source directories in this tree.

### Technology choices

| Layer | Technology |
|---|---|
| Operator interface | React, TypeScript, Vite, Tailwind CSS, UI components |
| API and controller | Python, FastAPI, Uvicorn, HTTPX |
| Optimization | SciPy/HiGHS and NumPy |
| Audit persistence | SQLite |
| Packaging | Multi-stage Docker image and Docker Compose |
| Monitoring | Prometheus and Grafana |
| Validation | pytest, frontend type-check/build, k6, simulator probes |
| Continuous integration | GitHub Actions |

Python dependencies are pinned in [requirements.txt](requirements.txt); frontend resolution is captured in [web/package-lock.json](web/package-lock.json).

## 6. Application Requirement

The current interface has **four pages**.

| Page | Operator purpose |
|---|---|
| **Home** | Review network status, station fuel, incoming allocations, projected need, and the network map |
| **Actions** | Inspect recommendations, reasons, constraints, alternatives, and before/after impact; send or skip actions |
| **History** | Inspect decision records and simulator shipment status |
| **System** | Inspect component health and incidents, change settings, and access simulation test tools |

Top-bar operating modes map to backend modes:

| Interface label | Backend value | Behavior |
|---|---|---|
| View only | observe | Observe and inspect without automatic dispatch |
| I approve | manual | Operator reviews recommendations before sending |
| Automatic | auto | Confidence/review gates govern automated sending; uncertain recommendations require review |

Use **I approve** for the main judge demonstration. Automatic mode is an explicit simulator experiment feature.

### Backend interface

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /api/status | Run, mode, policy, tick, and degraded state |
| GET | /api/overview | Network and supply overview |
| GET | /api/recommendations | Current recommendation cards |
| GET | /api/alerts | Active operational alerts |
| GET | /api/allocations | Simulator allocation records |
| GET | /api/decisions | Persistent decision history |
| GET | /api/incidents | Current process's incident feed |
| GET | /api/plans | Planning information |
| GET | /api/health | Component status and recent request statistics |
| GET | /metrics | Prometheus exposition |
| POST | /api/recommendations/{card_id}/approve | Approve a recommendation |
| POST | /api/recommendations/{card_id}/reject | Reject a recommendation |
| POST | /api/allocations/{allocation_id}/cancel | Request cancellation |
| PUT | /api/operating-mode | Change operating mode |
| PUT | /api/policy | Select planning policy |
| PUT | /api/intelligence | Toggle intelligence |
| POST | /api/lab/events | Inject a simulated crisis |
| POST | /api/lab/faults | Inject a supported test fault |
| POST | /api/lab/faults/clear | Clear injected faults |
| POST | /api/lab/control | Start, pause, step, or reset the simulator |

See [api.py](fuelops/api.py) and the running [/docs](http://localhost:8100/docs) for request schemas. Authentication coverage has a known gap described in Section 18.

## 7. Intelligence Requirement

The brief permits AI, ML, optimization, detection, or meaningful decision support. The current optimizer and operational decision-support pipeline satisfy this category without requiring a trained neural model.

### Implemented pipeline

1. **Observe:** collect and validate simulator state.
2. **Estimate demand:** combine the nominal demand profile, time effects, regional factors, and active demand multiplier.
3. **Detect:** identify operational risks, disruptions, abnormal conditions, and observed demand variation.
4. **Project:** estimate future inventory, unmet demand, and time to stockout.
5. **Optimize:** calculate replenishment under resource and transport constraints.
6. **Explain:** generate a card with reasons, impact, uncertainty, limits, and alternatives.
7. **Review and execute:** refresh state, enforce execution limits, and submit simulated allocations.
8. **Record:** retain decisions, incidents, and operational metrics.

### Current planning policies

| Policy | Role | Parameters at the default 15-minute tick |
|---|---|---|
| **lp-buffer** | Default optimizer with safety stock | 192-tick / **48-hour horizon**, 32-tick / **8-hour buffer**, 48-tick / **12-hour dispatch batch window** |
| lp | LP comparison without the added buffer | 96-tick / 24-hour horizon |
| threshold | Simple baseline and fallback | Reorder below 30% of capacity; target 70%, counting incoming fuel |
| none / lp-tick | Backend experiment variants | No replenishment / unbatched LP execution |

LP normally replans every eight ticks and is invalidated when relevant world state changes. Actual dispatch is further clipped against fresh stock, capacity, and incoming-fuel constraints. The buffer is a policy choice, not a learned parameter.

The objective prioritizes reducing unmet demand, with additional penalties for undesirable inventory/transport behavior. Solver optimality applies to the encoded formulation; it does not establish that every real simulator behavior is represented perfectly.

**Interpretation limits:** current risk and confidence values are heuristic estimates. The stockout risk calculation is not a calibrated probability of any shortage across the entire horizon. The metric named fuelops_prediction_mape is an observed residual diagnostic; it must not be presented as a held-out Chronos accuracy result.

### Planned pretrained AI extension — not yet implemented

The [approved Revision 5 plan](BUP_Fuel_Supply_Deterministic_MVP_Full_Plan2.md) adds pretrained forecasting and incident summarization without training on synthetic data.

~~~mermaid
flowchart LR
    SIM["Simulator observations"] --> HIST["Backend history and evidence"]
    HIST --> FC["Background forecast client"]
    FC --> CH["Planned forecaster container<br/>Chronos-2-Small on CPU"]
    WEIGHTS[("Pinned pretrained weights<br/>Persistent model volume")] --> CH
    CH --> VALID["Validate forecast bundle<br/>Coverage, age, run, quantiles"]
    VALID --> SHADOW["Shadow comparison against formula"]
    SHADOW --> UI["Planned forecast chart and source label"]
    SHADOW -. "Only after promotion and full horizon alignment" .-> LP["Existing LP planner"]
    FORM["Current formula forecast"] --> LP
    HIST --> JOB["Planned background summary worker"]
    JOB --> GROK["Grok API"]
    GROK --> CHECK["Schema and evidence validation"]
    CHECK --> SUMMARY["Stored incident summary"]
    JOB --> TEMPLATE["Factual template fallback"]
    TEMPLATE --> SUMMARY
    SUMMARY --> UI
    LP --> REVIEW["Operator review and existing executor"]
~~~

The external LLM has **no direct simulator action path**. It explains bounded incident evidence; the optimizer and operator workflow remain responsible for allocation decisions.

| Phase | Planned implementation | Acceptance condition |
|---|---|---|
| **P0 — correctness first** | Fix demand-map validation, outage semantics and demand timing; version proposals; protect approval/cancellation; journal and reconcile allocation intents | Focused correctness tests, changed proposals rejected, restart behavior demonstrated |
| **P1 — history** | Full plan: durable, deduplicated observations and multiplier history; approved time-limited scope: in-memory history with startup synchronization | History is correctly scoped to the simulator run; missing context is explicit |
| **P2 — forecast service** | Add a separate forecaster container; load autogluon/chronos-2-small once from pinned saved weights; internal POST /forecast and GET /health | Offline startup after download, measured CPU latency, invalid bundles rejected |
| **P3 — shadow evaluation** | Compare Chronos with the formula on held-out simulator observations | Persist errors, quantile coverage, and the promotion decision |
| **P4 — optional LP integration** | Use a complete, validated q50 forecast in LP, projection, and cards | Promote only after evaluation; retain formula and threshold fallbacks |
| **P5 — Grok summaries** | Background evidence-based API calls, validated structured output, stored summaries, bounded retries, template fallback | Valid/invalid response, timeout, rate-limit, and missing-key cases tested |
| **P6 — interface** | Forecast chart on Home, summary display on System, explicit model/source/health labels | Operators can distinguish measured, predicted, and template content |
| **P7 — evidence** | Forecast/API metrics, mocked tests, load rerun, demo and README update | Results captured with AI enabled and disabled |

The approved time-limited scope prioritizes **P0, P2, P3, P5, minimal P6/P7**, reduces P1, and **skips P4**. Thus, the first AI release should keep the existing formula operational while Chronos runs in shadow mode.

**Integration alignment required:** the older AI plan specifies a 96-tick forecast horizon, while the latest lp-buffer policy now needs 192 ticks. Before enabling P4, supply the full planner horizon or explicitly redesign and validate that boundary. Missing demand entries must never silently become zero.

Chronos requires a one-time model download and local inference resources, not a hosted inference API key. Grok requires a backend-held **XAI_API_KEY** when enabled. These services, variables, model files, and summary storage are not yet wired into the current application.

The proposed **2-core / 8-GB VPS** needs benchmarking with the complete stack and model loaded. No CPU latency, peak-memory, or concurrent-load guarantee is established by this README.

## 8. Reinforcement Learning

Reinforcement learning is optional in the brief and is **not implemented** here.

The project uses a constrained optimizer and a simple threshold comparator. Any later RL policy should be evaluated against these baselines on the same scenarios, with equal information access and the same execution constraints. It must not rely on hidden future demand during live operation.

## 9. Decision Support

A recommendation is more than a quantity to dispatch. Current cards expose:

- The affected station and fuel.
- Current stock and incoming fuel.
- Reasons and triggering signals.
- Projected stockout timing, risk, and unmet demand before the proposed action.
- Estimated impact after the action.
- Candidate routes, travel time, allocation volume, and binding constraints.
- Alternatives and reasons they may be unusable.
- Confidence and whether human review is required.

The current recommendation what-if view covers a 12-hour window; this is distinct from the default LP's 48-hour planning horizon.

Approval obtains a fresh snapshot and applies execution checks. However, immutable proposal versions and approval-time evidence hashes are still planned. Do not describe existing approval as a complete stale-proposal guarantee.

## 10. Crisis and Event Handling

The experiment suite covers the following simulator event families:

| Crisis | Operational effect to demonstrate |
|---|---|
| Demand spike | Increased consumption changes shortage projections and recommendations |
| Route closure | Unavailable paths require another usable route or an explicit constraint |
| Depot constraint | Reduced operational options should be visible in decisions |
| Shipment delay | Later incoming supply changes availability assumptions |
| Supply shortfall | Less future fuel increases scarcity |
| Station outage | Station service interruption changes feasible replenishment and demand treatment |
| Combined crisis | Multiple simultaneous constraints expose planner tradeoffs |

[scenarios.py](fuelops/scenarios.py) includes baseline and named scenarios, including regional spikes, isolated destinations, and overlapping events.

The current **System → Test tools** event interface exposes demand spike, route closure, station outage, supply shortfall, and shipment delay. Depot-constraint experiments are available through the backend/scenario tools, not that current selector.

The controller reacts to relevant observed changes and invalidates the current plan. Anticipating all future scheduled events inside the LP is still a known gap.

## 11. Application Resilience

| Failure | Current behavior | Boundary |
|---|---|---|
| Simulator request failure | Bounded retries, failure tracking, cached state and degraded operation | Cached information must not be presented as fresh |
| Repeated simulator failure | Circuit breaker reduces repeated calls; subsequent attempts allow recovery | Not a distributed failover system |
| Invalid snapshot | Reject data and raise an incident/alert | Coverage depends on implemented validation |
| LP failure | Threshold policy supplies a simpler fallback | Requires usable operational state |
| Intelligence switched off | Rule-based behavior remains available | Does not represent a separate ML-service failure today |
| Low confidence | Recommendation waits for human review | Confidence is heuristic |
| Ambiguous allocation submission | Reuse idempotency identity and inspect allocation records | Full crash-safe startup reconciliation is pending |
| Simulator tick rollback | Start a new run context | Not a durable restoration of the previous controller session |

The executor records intents to a report journal, but that is not yet a complete transactional outbox. Decision/incident persistence and external allocation reconciliation are different concerns.

The UI fault selector currently exposes **unavailable**, **latency**, and **error rate**. Additional stale-data and stream-disconnect experiments exist in backend tooling. Because the application uses REST polling, a stream-disconnect test does not prove recovery of an implemented SSE consumer.

When Chronos and Grok are added, demonstrate forecaster failure → formula fallback, and summarizer failure → factual template, without blocking operator requests.

## 12. DevOps Requirement

[Dockerfile](Dockerfile), [compose.yaml](compose.yaml), and [CI](.github/workflows/ci.yml) implement a reproducible delivery path:

**Source → Python tests → frontend build → container package → Compose deployment → health check → simulator step → running application**

The production image builds the frontend with Node 22 and runs the backend on Python 3.12 as a non-root user. The deployment contains four current services: simulator-api, fuelops, prometheus, and grafana.

CI runs on pull requests and pushes to main. It tests and smoke-deploys the stack on a GitHub Actions runner. **It does not deploy automatically to the user's VPS.** Workflow presence also does not prove that the latest remote Actions run passed.

### Runtime configuration

| Variable | Default | Purpose |
|---|---|---|
| SIMULATION_SPEED | 8 | Simulator ticks per real second; use 1 for a slower demo |
| TICK_MINUTES | 15 | Simulated minutes per tick |
| SIMULATOR_START_MODE | paused | Initial simulation state |
| SIM_PORT | 18000 | Host simulator port |
| APP_PORT | 8100 | Host application port |
| FUELOPS_POLICY | lp-buffer | Selected planning policy |
| FUELOPS_MODE | manual | observe, manual, or auto |
| FUELOPS_OPERATOR_TOKEN | empty | Optional token for currently protected controls |
| PROMETHEUS_PORT | 9090 | Host monitoring port |
| GRAFANA_PORT | 3000 | Host dashboard port |
| GRAFANA_ADMIN_PASSWORD | change-me | Change before shared use |
| FUELOPS_VERSION | dev | Compose application image tag |

See [.env.example](.env.example) for the supplied configuration. Direct backend development also supports SIM_URL, FUELOPS_DB, and FUELOPS_WEB; Compose sets container-specific values.

### VPS access and persistence

All exposed Compose ports bind to **127.0.0.1**. On a VPS, access the application using SSH forwarding, for example:

~~~bash
ssh -L 8100:127.0.0.1:8100 -L 3000:127.0.0.1:3000 user@your-vps
~~~

Then open localhost:8100 and localhost:3000 on your own machine. Public exposure needs an intentional TLS/authentication deployment and completion of the authorization gaps in Section 18.

The fuelops-data volume persists SQLite at /app/data. Simulator state, experiment report files, and monitoring time-series history are not all persisted by that one volume. Back up the actual database volume before deployment changes requiring retention.

### Local development

Prerequisites: Python 3.12, Node.js 22, and the simulator.

~~~bash
docker compose up -d simulator-api
python -m venv .venv
~~~

Activate the virtual environment using the command for your shell:

~~~powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
~~~

~~~bash
# Linux / macOS
source .venv/bin/activate
~~~

Then:

~~~bash
python -m pip install -r requirements.txt
python -m pytest -q tests
python -m uvicorn fuelops.api:app --port 8100
~~~

In another terminal:

~~~bash
cd web
npm ci
npm run dev
~~~

Open the URL printed by Vite. Its /api requests proxy to the local backend on port 8100. Do not run the Compose backend and local backend against the same port or run multiple active controllers against one test world.

## 13. Advanced DevOps Opportunities

The brief treats advanced infrastructure as an opportunity, not a prerequisite for a useful application.

Implemented foundations include a multi-stage image, a non-root runtime, Compose health checks, provisioned dashboards, and CI smoke deployment.

Possible next steps are versioned image publication, controlled VPS deployment, backup/restore verification, rollback procedures, and resource limits based on measurements. Kubernetes, distributed tracing, and a multi-node architecture are not present and are not necessary to claim the current functionality.

## 14. Observability Requirement

Prometheus scrapes the backend every five seconds. Grafana loads a provisioned dashboard from [ops/grafana](ops/grafana).

| Observable | Representative metric |
|---|---|
| Request volume and status | fuelops_http_requests_total |
| Request duration | fuelops_http_request_seconds |
| Snapshot duration and simulator errors | fuelops_sim_snapshot_seconds, fuelops_sim_errors_total |
| Simulation progress | fuelops_sim_tick |
| Degraded mode and breaker | fuelops_degraded, fuelops_circuit_open |
| Decision activity | fuelops_decision_cycles_total, fuelops_decisions_total |
| Fallback activation | fuelops_fallback_activations_total |
| Alerts and pending recommendations | fuelops_active_alerts, fuelops_open_recommendations |
| Prediction diagnostic and confidence | fuelops_prediction_mape, fuelops_recommendation_confidence |
| LP solve time | fuelops_solve_seconds |
| Accepted allocation volume | fuelops_shipped_liters_total |

Accepted allocation volume must not be interpreted as confirmed delivered liters. Simulator shipment status supplies delivery outcomes.

The default Prometheus process collectors expose backend process resource information where supported; saved Docker resource captures complement application metrics. This does not provide complete VPS-wide resource monitoring.

Current structured incidents and audit decisions support investigation. Chronos latency/age/coverage and Grok request/error/token metrics remain planned.

## 15. Health and Status

[/api/health](http://localhost:8100/api/health) reports the backend API, database, simulator, prediction service, and decision engine, together with recent request latency and error statistics.

The existing **prediction_service** health component refers to the in-process prediction logic. It is not evidence that a Chronos container is running.

The Docker application health check uses /api/status for availability. An HTTP 200 response or a healthy container alone does not prove that every dependency or decision path is operational; use component health, freshness, degraded status, and metrics together.

The System page presents this information to operators. Record screenshots or response samples during both normal operation and a controlled failure for the final demonstration.

## 16. Data

| Data | Origin | Current use/storage |
|---|---|---|
| Network, inventory, routes, supply, events | Official simulator | Validated operational snapshots and planning inputs |
| Demand observations | Simulator demand-history interface | In-memory noise/history calculations |
| Allocations | Simulator | Incoming-fuel accounting and shipment tracking |
| Operator decisions | Application | Persistent SQLite decisions table |
| Incidents | Application | SQLite incidents table plus an in-memory feed |
| Experiment demand/outcomes | Harness and simulator | Generated reports for offline evaluation |
| Load results | k6 and resource capture | Committed summaries and CSV artifacts |

The current /api/incidents feed comes from process memory even though incidents are also written to SQLite. It should not be described as a complete restored incident timeline after restart.

No custom model training dataset is required for the current pipeline. Future Chronos work uses pretrained weights and observed simulator history for inference/evaluation. Future Grok summaries receive bounded operational evidence, not unrestricted database access.

Offline hindsight evaluation may use realized future demand to estimate an upper bound. That information must never enter live decisions.

## 17. Load Testing

The committed [k6 workload](ops/k6/load.js) exercises real operator read paths:

- Dashboard requests: status, overview, and allocations.
- Decision requests: recommendations and health.
- Dashboard concurrency ramps up to 100 virtual users.
- The realistic profile adds a one-second dashboard think time and uses five decision-path iterations per second.
- The stress profile removes dashboard think time and uses twenty decision-path iterations per second.
- Each decision iteration makes two requests; iterations per second are not requests per second.

The project's thresholds are request failures below 1% and p95 below 500 ms for the dashboard and decision paths. These are project targets, not numerical requirements supplied by the brief.

With k6 installed and the application running:

~~~bash
k6 run -e BASE=http://localhost:8100 -e PROFILE=realistic --summary-export ops/k6/summary_new_realistic.json ops/k6/load.js
~~~

For the stress profile:

~~~bash
k6 run -e BASE=http://localhost:8100 -e PROFILE=stress --summary-export ops/k6/summary_new_stress.json ops/k6/load.js
~~~

### Recorded results

The following values are rounded from committed JSON artifacts. They describe historical runs; they were **not rerun for this README**, do not validate the latest 192-tick policy under load, and are not measurements of the proposed VPS.

| Artifact | Requests/s | Failed requests | Dashboard mean / p50 / p95 / p99 (ms) | Decision p95 (ms) |
|---|---:|---:|---|---:|
| [Run 1](ops/k6/summary_run1.json) | 121.1 | 0 | 1484 / 1445 / 2724 / 2842 | 2568 |
| [Run 2](ops/k6/summary_run2.json) | 259.6 | 3, approximately 0.012% | 574 / 419 / 1550 / 1852 | 1612 |
| [Realistic](ops/k6/summary_realistic.json) | 128.5 | 0 | 70 / 32 / 275 / 432 | 181 |

The realistic run's recorded p95 values meet the stated latency targets. Both earlier stress runs exceed them. Dropped iterations were also recorded in the stress runs, so throughput must be interpreted together with unmet load.

The custom decision latency measures the recommendations request, not the combined recommendations-plus-health iteration. Its full distribution remains in the JSON files; container resource captures are in ops/k6/stats_run*.csv. For the next benchmark, record commit, hardware, active policy, simulation speed, model state, concurrency, throughput, errors, dropped iterations, latency percentiles, CPU, and peak RAM together.

## 18. Security and Engineering Hygiene

Current controls include loopback port binding, a non-root application container, environment-based configuration, optional operator-token checks for selected controls, and simulator-only action execution.

**Known authorization gap:** mode, policy, intelligence, and lab controls use the optional operator-token dependency, but approve, reject, and cancellation endpoints do not yet apply the same dependency. Setting FUELOPS_OPERATOR_TOKEN therefore does **not** protect every mutation. Completing that coverage is a P0 item before shared/public deployment.

Additional boundaries:

- Keep API keys and tokens in backend configuration, never frontend VITE variables or Git.
- Change the example Grafana administrator password. Anonymous Viewer access is enabled in the supplied configuration.
- Isolate simulator administration and test controls from public access.
- Validate model output and evidence references before presenting future AI summaries.
- Add proposal version/expiry checks and durable action reconciliation.
- Treat operational text and model output as data; neither should authorize simulator actions.

A repository containing configuration examples is not proof that historical commits have been scanned for secrets.

## 19. Required Deliverables

This mapping follows the eleven deliverables in the brief.

| Required deliverable | Repository evidence | Status at this snapshot |
|---|---|---|
| 1. Working application | React views and FastAPI backend | Implemented; deployment/demo must be shown |
| 2. Source, setup, dependencies, deployment instructions | This README, requirements, package lock, Dockerfile, Compose | Present |
| 3. Simulator integration | sim.py, execute.py, controller.py, integration guide | Implemented |
| 4. Intelligence component | LP, formula projections, diagnostics, fallback | Implemented; neural AI extension planned |
| 5. Operator interface | Home, Actions, History, System | Implemented |
| 6. Architecture diagram | Current and planned diagrams in this README | Documented separately |
| 7. Deployment evidence | Compose and CI smoke workflow | Reproducible setup present; actual VPS evidence still needed |
| 8. Observability evidence | Metrics, Grafana provisioning, resource artifacts | Present; capture current demo evidence |
| 9. Resilience evidence | Tests, livetest, incident handling, devlog | Partial; complete pending recovery/safety checks |
| 10. Load workload and results | ops/k6 script, summaries, resource CSVs | Historical results present; updated deployment rerun needed |
| 11. Final demonstration | Section 22 walkthrough | Prepared sequence; live demonstration still required |

“Present” means repository evidence exists. It does not substitute for successfully running the demonstration or independently verifying all historical claims.

## 20. Recommended Deliverables

The repository also provides:

- Automated optimizer/resilience tests in [tests](tests).
- A CI workflow with a frontend build and full-stack smoke check.
- Persistent decision audit records.
- Reproducible scenario and policy evaluation tools.
- Development notes and recorded experiments in [devlog.md](devlog.md).
- Baseline and perfect-hindsight comparison tooling.
- Explicit fallback policies.

Still useful to complete: release/image provenance, tested rollback and backup restoration, durable history/reconciliation, saved AI evaluation records, and model/prompt version manifests.

### Reproducible evaluation

These tools reset or control the simulator. Use a dedicated test world and stop the live application controller before running them.

~~~bash
docker compose stop fuelops
docker compose up -d simulator-api
~~~

From an activated Python environment with dependencies installed:

~~~bash
python -m fuelops.probes c01 c06
python -m fuelops.harness threshold lp-buffer --ticks 480
python -m fuelops.harness threshold lp-buffer --ticks 480 --recipe s04_primary_route_down
python -m fuelops.hindsight reports/<run>_demand.json
python -m fuelops.livetest none unavailable --policy lp-buffer
~~~

Replace the hindsight placeholder with a generated demand file. Restart the application afterward:

~~~bash
docker compose up -d fuelops
~~~

The current test suite contains eleven tests covering LP fixtures and selected resilience behavior. The development log records passing tests, but this documentation update does not claim a fresh execution.

The latest recorded horizon/buffer experiment reports aggregate five-day unmet demand across seventeen recipes decreasing from **65,589 L** with the earlier 96-tick/16-tick configuration to **23,783 L** with the new 192-tick/32-tick configuration. These are devlog results with a single run per cell and surprise-event scenarios; they are not a statistical guarantee or a Chronos result.

## 21. Optional Advanced Work

Optional extensions include pretrained forecasting, evidence-grounded incident summaries, more complete future-event modeling, richer scenario replay, stronger deployment automation, and broader failure testing.

RL, distributed tracing, orchestration clusters, and extensive custom training are optional. Prioritize correctness, operator usefulness, and measured improvement before adding them.

The approved Chronos/Grok roadmap in Section 7 is the relevant next AI integration path. No LightGBM training pipeline is present or required for that path.

## 22. Suggested Demonstration Story

Use a fresh simulated world, slow simulation speed, and **I approve** mode. This sequence follows the brief while using the current four-page interface:

1. Start the stack and show healthy components on **System**.
2. Click **Start** and show normal network operation on **Home**.
3. Explain current stock, incoming fuel, and projected shortage timing.
4. Open **System → Test tools** and inject a demand spike.
5. Show the resulting alert and revised projection.
6. Open **Actions** and inspect the replenishment recommendation.
7. Explain its signals, constraints, alternatives, and before/after impact.
8. Approve a simulated allocation.
9. Show the decision in **History** and follow the shipment state.
10. Inject a route disruption and show changed feasible actions.
11. Inject a simulator availability fault and inspect degraded status, incidents, and monitoring.
12. Clear the fault and demonstrate recovery.
13. Show the threshold fallback or intelligence-off behavior.
14. Finish with the recorded load results and the current limitations.

For today's implementation, describe step 5 as a **formula-based projection**. After the planned AI work is implemented and tested, add the Chronos forecast band, Grok incident summary, and an explicit forecaster-stop → formula-fallback demonstration.

Judge-facing explanation:

> “Our application reads the fuel network from the simulator, estimates future demand, and uses an optimizer to recommend feasible deliveries. Operators can inspect why each delivery is suggested and approve it. The system records decisions, monitors health, and falls back to simpler rules when needed. Pretrained forecasting and AI incident summaries are a planned extension, clearly separated from the current working system.”

## 23. Evaluation Criteria

| Official criterion | Weight | Evidence to emphasize |
|---|---:|---|
| Product and application quality | 20% | Useful four-page operator workflow and inspectable actions |
| Intelligence and decision quality | 20% | Constrained planning, baseline comparison, projection quality and honest uncertainty |
| System architecture and integration | 15% | Simulator/API/UI/data boundaries and accurate architecture |
| DevOps and deployment | 15% | Reproducible Compose deployment and CI smoke path |
| Resilience and failure handling | 10% | Controlled failures, degraded behavior, fallback and recovery |
| Observability and performance | 10% | Component health, metrics, Grafana and reproducible k6 evidence |
| Demonstration and explanation | 10% | Clear end-to-end story with visible outcomes |

Do not substitute an impressive model name for operational evidence.

## 24. Constraints and Guardrails

All allocations, cancellations, crises, and test faults apply only to the official simulated environment. The project does not control real fuel infrastructure, purchase fuel, or dispatch physical vehicles.

Keep the simulator image unchanged, use documented integration surfaces, and separate test administration from operator decisions. Prefer human review for consequential actions.

### Known implementation gaps

| Area | Current limitation / required follow-up |
|---|---|
| Pretrained AI | Chronos and Grok are planned; no forecaster service or LLM summary worker exists yet |
| Demand overrides | Validate complete demand maps before future LP integration; missing values must not become zero demand |
| Station outages | Complete the planned projection and LP semantics fixes |
| Tick semantics | Finish the explicit demand/arrival timing validation probe |
| Proposal approval | Add version/hash/expiry checks and reject changed proposals |
| Authorization | Apply operator-token checks consistently to approval, rejection, and cancellation |
| Restart recovery | Complete durable intent journaling and startup reconciliation |
| Staleness | Strengthen freshness handling, including shared-client stale-response bookkeeping |
| Future events | LP does not fully incorporate scheduled future events |
| Persistence | Durable demand history and full incident-feed restoration are not implemented |
| Risk reporting | Heuristic confidence/risk must not be advertised as calibrated probabilities |
| Deployment evidence | Benchmark the full stack on the intended VPS, including AI if enabled |

The world contains finite fuel. Shortages after available supply is exhausted are not automatically evidence of a planner bug; assess them against a feasible baseline or carefully qualified hindsight bound.

Examples and illustrative performance numbers in the problem statement are not results achieved by this project.

## 25. Success Criteria

A successful submission should demonstrate that:

- An evaluator can start the application using the documented setup.
- The application reads live simulator state and presents a useful operator workflow.
- Recommendations respect modeled constraints and explain their expected benefit.
- Approved actions create traceable simulator allocations.
- Crises change alerts and recommendations in an understandable way.
- Failures become visible, trigger appropriate fallback/degraded behavior, and recover.
- Tests and load evidence are reproducible and tied to a known configuration.
- Implemented features, planned work, and known limitations are clearly distinguished.

For the next AI release, additionally require valid saved forecasts, an explicit shadow-evaluation decision, safe formula/template fallbacks, and a new resource/load measurement. Training a custom model is not a prerequisite.

## 26. Final Challenge Statement

Fuel Operations addresses the challenge as an integrated operational system: it observes the simulated fuel network, predicts shortages using the current demand model, optimizes replenishment, explains and records decisions, and exposes failures and performance.

The next milestone is to complete the identified safety/correctness work and add pretrained forecasting and Grok summaries behind explicit validation and fallback boundaries. The objective remains a useful, understandable, and dependable operator application.

---

**Project references:** [Official brief](Problem_Statement_BUP_CSE_Fest_2026.pdf) · [Implementation and AI plan](BUP_Fuel_Supply_Deterministic_MVP_Full_Plan2.md) · [Simulator integration guide](BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md) · [Development log and experiment evidence](devlog.md)
