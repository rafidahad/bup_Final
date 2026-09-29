# BUP Fuel Supply Simulator: Full Deterministic MVP Plan

**Document type:** Implementation plan only. No application is built by this document.  
**Prepared:** 29 September 2026.  
**User requirements:** Complete, in this phase, every part of the MVP that requires no AI or machine learning; parts that would require AI/ML are deferred to the next phase (§25). No artificial implementation deadline; deterministic methods and optimization wherever justified.  
**User-selected UI stack:** shadcn/ui with Tailwind CSS, on React + TypeScript + Vite.  
**Primary reference:** `BUP_Fuel_Supply_Simulator_Integration_and_Interaction_Guide.md`, supplied by the user, all 16 pages / 689 text lines reviewed.  
**Target simulator:** `asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, as specified in the guide.

**Validation status:** Source-document and official library-documentation review completed. Runtime contract probes, application tests, solver benchmarks, and simulator experiments described below are planned work, not completed results.

### Revision 3 — changes from design review

| # | Review finding | Where the plan changed |
|---|---|---|
| 1 | Total supply is probably below total demand; this decides the design. | New probe C00 and §5.4 supply-adequacy analysis; §9.7 objective reframed around "every liter consumed, none lost or stranded"; S12 promoted from edge case to main regime. |
| 2 | Holding all dispatch on `stale_data` empties station tanks within about one real minute. | §10.1, §12.1: degraded mode keeps dispatching conservatively from an estimated state; server-side POST validation is the safety net, and a 409 costs nothing. |
| 3 | MILP binaries are unnecessary. | §9.2–9.5, §9.7: plain LP with unmet-demand weights that fall over time and no terminal-stock reward; aggregate flow split into `max_shipment` chunks after solving. |
| 4 | Planning cadence is over-engineered. | §7.1, §9.1: replan every 8 ticks or on events; three snapshot states instead of five; no before/after skew reads; revalidate right before each POST. |
| 5 | The no-ML rule conflicts with guide page 2. | **Resolved by owner (29 Sep 2026):** this phase builds everything that needs no AI/ML; the guide's history-driven "predictive capabilities / continuously improve" requirement moves to the next phase (§1.2, §25). History is used for validation and residual reporting only; safety margins are hand-set (§8.3). `demand_multiplier` is read directly from `/v1/stations`. |
| 6 | No upper-bound benchmark. | §9.9, §15.3, §16: perfect-hindsight LP on recorded demand; report the share of the baseline-to-ideal gap closed. |
| 7 | Phase order delays the first scored run. | §17 rewritten as milestones built around a working slice: threshold policy first, then LP, faults, a trimmed dashboard, and hardening last. |

The probe list (§4.4) and execution-safety rules (§10.3–10.7) are unchanged apart from the additions noted above.

## Revision 4 — alignment with the official problem statement

The official problem statement (`Problem_Statement_BUP_CSE_Fest_2026.pdf`, BUP CSE Fest 2026 Hackathon Finals, 11 pages) arrived on 29 Sep 2026, after Revision 3 and after implementation had started. **Where Revision 4 conflicts with any earlier section, Revision 4 wins.** Statement sections are cited as "PS §n".

### R4.1 What the statement settles

- **Product:** a "Fuel Supply Intelligence & Resilience Platform" for an operations team. It must observe the network, identify emerging shortages, help decide constrained allocation, respond to disruptions, expose reasoning, stay usable during failures, and show measured performance under load (PS §1).
- **Engineering loop to demonstrate:** Observe → Detect → Predict → Decide → Simulate → Act → Monitor → Recover (PS §2). Judges must be able to interact with a working system.
- **Must include:** operator-facing application (web recommended; a notebook is not enough), backend, intelligence component, deployment, observability, resilience, and load testing (PS "Challenge at a Glance", §5–§6).
- **Intelligence:** at least one meaningful AI / ML / optimization / detection capability. Optimization and detection qualify on their own; RL is optional and, if used, must be compared against a rule-based approach (PS §7–§8).
- **Human review:** preserve human review for consequential simulated decisions (PS §24). Low prediction confidence must request human review (PS §11).
- **Surprises:** organizers may introduce domain and engineering events during development or judging, and the environment may change (PS §2, §26).
- **Judging is not a simulator score.** No service-level formula is used. Weights (PS §23):

| Criterion | Weight | Current status | Where Revision 4 puts the work |
|---|---:|---|---|
| Working product & user experience | 20% | API skeleton only; no UI | R4.6 M5 operator app |
| Intelligence & decision quality | 20% | LP within 3 L of hindsight bound (stepped); threshold fallback | M3 decision support: detection, prediction, recommendation cards, what-if impact |
| Architecture & integration | 15% | Client, probes, executor, controller | M3–M5; architecture diagram in M9 |
| DevOps & engineering quality | 15% | Simulator compose only; 4 unit tests | M7 containers, CI, tests |
| Resilience & incident response | 10% | Retries, disruption guard, reset detection, live fault runner | M4 resilience behaviours and demos |
| Observability & performance | 10% | None beyond logs | M6 metrics, dashboards, health; M8 load test |
| Demo & problem understanding | 10% | Strong measured understanding (probes, supply analysis) | M9 demo script following PS §22 |

Consequence: Revision 3's optimizer and benchmark evidence remain the core of "Intelligence & decision quality", but **most remaining effort moves to the operator application, decision support, DevOps, observability, resilience demonstration, and load testing.** The Revision 3 gate "a score exists" is replaced by "a demonstrable loop exists".

### R4.2 Gap analysis

| Statement requirement | Status now | Action |
|---|---|---|
| Operator web app with a meaningful subset of: inventory, depot/station status, regional demand, shortage alerts, projected shortage risk, incoming supply, disruptions, recommended allocations, expected impact, system alerts, decision history, service health (PS §6) | Missing | Five views (R4.5); all twelve items covered. |
| Inspectable recommendations: why at risk, signals, constraints, expected impact, confidence/uncertainty, alternatives (PS §9 card: projected stockout hours, inventory, expected demand, recommended liters and depot, risk before → after) | Missing | Recommendation card (R4.4) built from projection, LP/threshold output, and what-if simulation. |
| Detect: anomalous demand, abnormal inventory changes, bottlenecks, emerging regional disruptions (PS §7) | Missing | Rule-based detectors on residuals, inventory deltas, dispatch-budget saturation, and public events. |
| Predict: shortage prediction, stockout probability (PS §7, §9) | Deterministic time-to-stockout exists in projection | Add stockout risk % and confidence (R4.3 decision D1). |
| Simulate: "allocation is simulated" before acting (PS §2, §22 step 8) | Projection engine can do it | What-if: projected trajectory with and without the recommended allocation. |
| Crisis handling: shipment delay, demand spike, depot constraint, regional disruption, combined; detect → evaluate → respond → explain → monitor recovery (PS §10) | Recipes + disruption guard; LP reacts; no UI | Incident timeline per event with impact, response, and recovery status. |
| Resilience mappings: ML unavailable → fallback policy; invalid simulator response → reject + alert; low confidence → human review; dependency unavailable → retry / cached state / degraded (PS §11) | Retries, degraded flag, fallback exists | Response schema validation, circuit breaker, cached state in UI, intelligence kill switch for demo, confidence gate. |
| Deployment: `docker compose up`; Source → Build → Test → Package → Deploy → Health check; CI/CD strongly encouraged (PS §12) | Simulator only | Dockerfile(s), full compose with health checks, GitHub Actions. |
| Observability: app (rate, latency, errors, availability), system (CPU, memory), intelligence (prediction error, confidence, alert rate, decision frequency, fallback activations), logs (PS §14) | Missing | Prometheus `/metrics`, Grafana provisioned dashboard, structured JSON logs. |
| Health page: backend, database, simulator, prediction service, decision engine, p95 latency, error rate (PS §15) | Missing | `/api/health` + System health view. |
| Load test: one meaningful path; avg, p50, p95, p99, throughput, error rate, concurrency, resource usage (PS §17) | Missing | k6 (container) against dashboard backend and decision request paths; report in devlog. |
| Security hygiene: no hard-coded secrets, validate input, handle failures, document config, restrict sensitive actions (PS §18) | Partial | `.env` config, Pydantic validation, operator token for lab/mode/auto actions. |
| Deliverables 1–11 incl. architecture diagram, observability evidence, resilience demo, load-test evidence (PS §19) | 1, 3 partial | Tracked in R4.7. |
| Recommended: CI/CD, automated tests, decision audit history, scenario configuration, simulation replay, automated fallback, rollback (PS §20) | Tests, scenarios, replay (stepped harness), fallback partial | Audit history in SQLite; policy rollback = switch policy version from UI. |

### R4.3 Decisions that need the owner (asked before execution)

> **Answered 29 Sep 2026:** D1 = statistics now, ML later. D2 = **less than 24 hours** remain. D3 = README for setup + devlog. D4 = LP + hand-set buffer, threshold as fallback.
>
> **24-hour cut (execution order):** M3 decision support → M5 web app → M7 compose + CI → M6 metrics + health (Grafana only if time remains) → M4 remaining resilience mappings → M8 k6 load test → M9 README, diagram, demo script. Cut first if late: Grafana, lab polish, second load-test path, alternatives list on cards.

- **D1 — Predict/Detect scope.** The statement does not require ML, but "stockout risk 72% → 19%" (PS §9), "model confidence" (PS §14), and "confidence too low → human review" (PS §11) need a probability. **Proposal:** compute stockout risk and confidence now with statistics (the observed demand-noise distribution from `/v1/demand-history`, applied to the deterministic projection), and rule-based detectors. Learned forecasting and LLM explanations stay in the next phase (§25), added later as optional layers with fallbacks. This relaxes one earlier rule: history would feed displayed risk and confidence, not only residual reports. Optimizer decisions stay deterministic.
- **D2 — Time remaining** until submission and judging, which decides how much of M8–M9 and the next phase fits.
- **D3 — Documentation.** Deliverable PS §19.2 needs setup and deployment instructions. **Proposal:** `README.md` holds only setup/deploy instructions and the architecture diagram; `devlog.md` stays the single working log.
- **D4 — Live policy.** The LP is near-optimal stepped but fragile live without safety stock (devlog). **Proposal:** LP with a hand-set safety buffer as the recommender, threshold as the fallback and live default until the buffered LP is measured live.

### R4.4 Recommendation card (PS §9)

Every recommendation is a stored, inspectable object:

| Field | Source |
|---|---|
| Station, fuel, region | Snapshot |
| Why at risk: projected stockout time (hours), current inventory, expected demand over the horizon, incoming supply | Deterministic projection (§8) |
| Signals that influenced it | Active events, demand multiplier, detector hits, route status |
| Recommended allocation: liters, source depot, route, arrival tick | LP (or threshold fallback, labelled) |
| Constraints that bind | Depot stock, dispatch budget, route limit, destination headroom, route availability |
| Expected impact: stockout time and unmet liters with vs without; stockout risk before → after | What-if projection; risk per D1 |
| Confidence / uncertainty | Per D1; low confidence routes the card to human review |
| Alternatives | Other feasible routes/depots with their impact, or "wait" |
| Decision | Pending, approved (by operator), auto-approved (guardrails), rejected, expired; audit trail |

### R4.5 Architecture and operator application

```text
Official simulator (container, unchanged)
   │  REST
   ▼
Backend container — FastAPI, one operational writer
 ├─ Observe   collector: parallel snapshot, response validation, retries, circuit breaker, cached state
 ├─ Detect    detectors: demand anomaly, abnormal inventory change, dispatch bottleneck, regional disruption
 ├─ Predict   projection, time-to-stockout, stockout risk + confidence (D1)
 ├─ Decide    LP optimizer + threshold fallback → recommendation cards
 ├─ Simulate  what-if projection with / without each recommendation
 ├─ Act       approval queue (manual default), guarded auto mode, idempotent executor
 ├─ Monitor   /metrics (Prometheus), /api/health, JSON logs, decision audit (SQLite)
 └─ Recover   degraded mode, reset detection, intelligence kill switch → fallback
   │  /api/*  (web app served by the backend)
   ▼
Operator web app — React + TypeScript + Vite + shadcn/ui + Tailwind
Prometheus + Grafana (containers, provisioned)      k6 load tests (container)
GitHub Actions CI: tests → build → package → compose smoke test (health check)
```

The prediction service stays a module inside the backend with its own health status and a kill switch, rather than a separate container. That demonstrates "ML model unavailable → fallback" (PS §11) without extra infrastructure (PS §13 warns against complexity that does not improve the solution).

Operator application views (replaces §13.2):

| View | PS §6 items covered |
|---|---|
| Overview | Current inventory, depot and station status, regional demand, incoming supply, disruptions, network map |
| Alerts & recommendations | Shortage alerts, projected shortage risk, recommended allocations, expected impact, approve / reject |
| Decisions | Decision history and audit trail, outcomes of executed allocations |
| Incidents & lab | Crisis timeline (detect → respond → recover), system alerts; lab controls to inject events and faults for the demo (operator token) |
| System health | Service health per component, p95 latency, error rate, fallback state, links to Grafana |

### R4.6 Revised milestones (replaces §17 Milestones 3–5)

Milestones 0–2 are done (devlog). Remaining work, in priority order:

| # | Milestone | Main PS sections | Gate |
|---|---|---|---|
| M3 | Decision-support core: detectors, stockout projection and risk, recommendation cards with what-if impact, approval queue, SQLite decision audit, buffered LP (D4) | §6, §7, §9, §10, §24 | Recommendations visible via API for a crisis recipe, with impact and alternatives; approval executes through the existing executor |
| M4 | Resilience behaviours: response validation (reject + alert), circuit breaker and cached state, intelligence kill switch → fallback, low-confidence → review, degraded mode | §11 | Each PS §11 mapping demonstrated once and logged |
| M5 | Operator web app: five views, lab controls, clear loading/degraded/empty states | §6, §22 | The 14-step demo story (PS §22) runs end to end in the browser |
| M6 | Observability: Prometheus metrics, Grafana dashboard, JSON logs, `/api/health` + health view | §14, §15 | Metrics and a failure visible in Grafana and in the health view |
| M7 | DevOps: Dockerfile, full `docker compose up` (simulator, backend+web, Prometheus, Grafana) with health checks, `.env.example`, GitHub Actions CI | §12, §18 | Clean clone → one command → healthy system; CI green |
| M8 | Load testing: k6 scenarios on dashboard backend and decision request; report avg/p50/p95/p99, throughput, errors, concurrency, resource use | §17 | Report recorded in devlog with limits found |
| M9 | Delivery: architecture diagram, README setup, demo script, rehearsal, final verification against R4.7 | §19, §22 | All required deliverables checked |
| Next | Learned forecast, LLM incident explanations, parameter tuning on crisis recipes (§25) | §7, §21 | Only after M9, and only if it beats the deterministic baseline |

### R4.7 Required deliverables (PS §19) — definition of done

| # | Deliverable | Covered by |
|---|---|---|
| 1 | Working application | M3–M5 |
| 2 | Source repository with setup, dependencies, deployment instructions | M7, M9 (README per D3) |
| 3 | Simulator integration | Done (client, probes, executor, controller) |
| 4 | Intelligence component | LP optimizer (done) + detection and prediction (M3) |
| 5 | Operator interface | M5 |
| 6 | Architecture diagram: simulator → data/backend → intelligence → decision → application → monitoring | M9 (from R4.5) |
| 7 | Reproducible deployment | M7 |
| 8 | Observability evidence | M6 |
| 9 | Resilience demonstration | M4 + live fault runs (devlog) |
| 10 | Load-test evidence | M8 |
| 11 | Final demo | M9, following PS §22 |

### R4.8 Demo story (PS §22) mapped to features

| PS §22 step | Feature |
|---|---|
| 1 Normal operations | Controller running; Overview |
| 2 Operator dashboard | Overview + System health |
| 3 Demand starts increasing | Lab injects `demand_spike` |
| 4 System detects risk | Demand-anomaly detector + multiplier signal → alert |
| 5 Intelligence predicts shortage | Projected stockout time and risk % |
| 6 Allocation recommendation generated | Recommendation card (LP) |
| 7 Operator inspects recommendation | Card: why, constraints, impact, confidence, alternatives |
| 8 Allocation is simulated | What-if with/without |
| 9 Crisis event occurs | Lab injects route disruption or combined crisis |
| 10 System adapts | Disruption guard, alternative route, replan; incident timeline |
| 11 Application or dependency failure injected | Lab injects simulator fault, or intelligence kill switch, or simulator container stopped |
| 12 Monitoring detects failure | Health view + Grafana + alert |
| 13 Fallback / recovery activates | Degraded mode with cached state; threshold fallback |
| 14 Operations continue | Recovery incident; metrics back to normal |

## Revision 5 — AI/ML phase implementation plan (awaiting owner approval)

> **Correction (owner, 29 Sep 2026): the LLM provider is Groq (groq.com), not xAI Grok.** Summaries call Groq's OpenAI-compatible `POST https://api.groq.com/openai/v1/chat/completions` with `response_format` `json_schema` `strict: true` (verified on Groq docs: strict mode supports `openai/gpt-oss-120b`, `openai/gpt-oss-20b`; all fields required, `additionalProperties: false`). Default model `openai/gpt-oss-120b` (production, $0.15 / $0.60 per million tokens → ≈ $0.0006 per summary). Settings: `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`, `SUMMARIES_ENABLED`. Everywhere below that says Grok/xAI, read Groq.
>
> **Approved 29 Sep 2026 as written.** Time left < 12 h → cut: **P0, P2, P3, P5**, minimal P6 (forecast chart on Home, AI summaries on System, health rows) and minimal P7 (metrics, tests with fakes, README/demo update). **P4 skipped** (Chronos drives the LP only if promoted later). **P1 reduced**: history stays in memory with a 2,000-row sync per station at start. Owner provides `XAI_API_KEY` in `.env`; downloads approved.

Source: the owner-supplied "Full AI/ML Implementation Guideline" (Chronos-2-Small forecasts, existing LP, Grok incident summaries, human-reviewed proposals). This revision reviews that guideline against the current repository (commit `4ec7eaa`), Revision 4, and the earlier ML-layer review, and turns it into one executable plan. **Nothing in this revision is implemented yet.** The pasted guideline arrived truncated after its section 11 "Phase 2"; its later phases are reconstructed here from its sections 1–10.

### R5.1 Review of the guideline

**Verified externally (29 Sep 2026):**

| Claim | Result |
|---|---|
| `autogluon/chronos-2-small` exists, Apache-2.0, ~28M parameters, `chronos-forecasting` package, `BaseChronosPipeline.from_pretrained` + `predict_df`, quantile output | Confirmed on the model card (27.9M F32 parameters ≈ 112 MB of weights). Minimum context not documented. |
| `grok-4.7` exists | Confirmed; $2 input / $6 output per million tokens (< 200k context). |
| Structured output through the Responses API `text.format` with `json_schema`, `strict` | Confirmed; `grok-4.7` supported. |

**Verified against our code — every correctness gap the guideline names is real:**

| Gap | Where | Adopted fix |
|---|---|---|
| Missing demand-override key silently becomes 0 L | `lp.py` line 115 `demand.get(..., 0.0)` | LP rejects incomplete, non-finite or negative override maps |
| Projection sets demand to 0 during a station outage (simulator: demand unmet, stock frozen) | `intel.py` line 100 | Outage demand counts as unmet; stock frozen |
| LP can serve demand from stock during a known outage | `lp.py` station block | No service while the station is out (public event window) |
| Approve / reject / cancel are not operator-protected | `api.py` lines 264–286 | Same operator dependency as lab/mode actions |
| Card id `station:fuel` is reused, so approving an old screen can execute a newer plan | `decisions.py` line 70 | Immutable proposal id + version + plan hash; 409 on mismatch |
| Intent journal lives in `reports/`, which is not a durable volume | `controller.py` line 85, `compose.yaml` | Journal under `/app/data`; startup reconciliation by idempotency key |
| Every app start mints a new run id; outstanding intents are never reconciled | `controller.py` line 78 | Continue the run when the simulator tick shows continuity |
| Incident list is in memory only | `api.py` line 201 | Read incidents and summaries from SQLite |
| History = 200 rows per station every 8 ticks, memory only | `controller.py` line 181 | Persistent demand history (needed as Chronos context) |

**Out of date in the guideline:** repository path (`D:/Hackathon_final` → `D:/Hackathaon_BUP_Final`), checkpoint (`4b1603e` → `4ec7eaa`), view names (now Home, Actions, History, System), M9 and README (done).

**Changed from the guideline, with reasons:**

| Guideline | This plan | Why |
|---|---|---|
| Chronos worker as a separate process sharing SQLite job tables (WAL, leases) | **Separate `forecaster` container** with a small HTTP API (`POST /forecast`, `GET /health`); backend calls it from a background thread | Keeps torch (~1 GB installed) out of the main image and CI; no multi-process SQLite locking; the PS §11 demo "ML model unavailable → fallback" becomes `docker compose stop forecaster` |
| Durable Grok job table with leases | Background thread in the backend with a bounded queue; results, attempts and failures persisted in SQLite; unfinished jobs re-queued on start | One process only; same guarantees for this scale |
| Snapshot, simulator-run and per-read metadata tables | Deferred | Not needed for the AI features in < 24 h; current continuity checks remain |
| Optional SSE, joint-trajectory stockout probability, autotuning | Out of scope | Guideline itself marks them optional |

**Honest expectation.** The simulator's demand is the published formula times ~5% noise (measured projection error 5.0–5.5%). A zero-shot pretrained model will very likely **not** beat the formula on point accuracy. That is why Chronos starts in **shadow mode** and only drives the optimizer if it passes the promotion gate (R5.3 P3). Its lasting value is the forecast with an uncertainty band, which is the clearest evidence of "predictive capability" (PS §7, §14), plus measured prediction error. Reports will state which model won.

**Alignment with earlier decisions.** This is the AI/ML phase that Revision 4 D1 and plan §25 deferred, now approved by the owner. It matches the earlier ML-layer review: a prediction chart with a quantile band, an LLM that only explains, never decides, and a fallback for every AI part. It drops RL and parameter tuning. The LP, executor, validation and retries stay deterministic.

### R5.2 Architecture

```text
Official simulator ──REST──▶ Backend (FastAPI, one operational writer)
                               ├─ controller: snapshot, validation, detectors, LP, proposals, executor
                               ├─ history ingestion ─▶ SQLite (demand history, forecasts, proposals,
                               │                          incidents, summaries, intents, audit)
                               ├─ forecast client ──HTTP──▶ forecaster container (Chronos-2-Small, CPU,
                               │    (background thread)        weights in a named volume, loaded once)
                               ├─ summary worker ──HTTPS──▶ xAI Grok API (evidence packet only)
                               └─ /api, /metrics ──▶ web app, Prometheus → Grafana
```

AI components never write to the simulator. Forecasts feed the LP only in operational mode after promotion. Grok output is text for operators; quantities and approvals stay deterministic and human-reviewed.

### R5.3 Phases, gates and estimates

| # | Phase | Work | Gate | Est. |
|---|---|---|---|---|
| P0 | Correctness and safety (non-ML) | LP override validation; outage semantics in projection and LP; proposal id/version/hash with 409 on change; operator token on approve/reject/cancel; durable intent journal and startup reconciliation; C11 probe (demand tick timing) | Unit tests for each; approving a changed plan returns 409 | 3 h |
| P1 | Durable demand history | SQLite `demand_observations` (dedupe by run + source id), per-tick demand-multiplier log, ingestion continues with intelligence off, explicit gap markers, reset = new epoch | Restart keeps history; no duplicates; gaps visible | 1 h |
| P2 | Forecaster service | `forecaster/` container (python:3.12-slim, CPU torch, chronos-forecasting, pandas); `scripts/download_models.py` at a pinned revision into a volume + manifest; load once; `POST /forecast` → q10/q50/q90 per station/fuel/absolute tick; backend client with timeout and breaker; ForecastBundle validation (coverage, finite, non-negative, ordered quantiles, age, run, event hash) | Starts offline from saved weights; latency measured; malformed output rejected | 3 h |
| P3 | Shadow evaluation and promotion | Rolling-origin comparison Chronos vs formula per station/fuel: MAPE, pinball loss, q10–q90 coverage; spike handling by normalising history with the recorded multiplier and applying the known future multiplier once; **promotion rule:** operational only if Chronos MAPE ≤ formula MAPE and 10–90 coverage within 70–95% over at least one simulated day of held-out ticks | Evaluation stored and shown; promotion decision recorded either way | 2 h |
| P4 | `lp-chronos` planner (conditional) | Complete q50 demand map → existing LP; the same bundle drives projections and cards; card shows forecast source; fallbacks: forecaster down → formula, LP fails → threshold, kill switch → threshold | Policy selectable; falls back cleanly when the forecaster is stopped | 1.5 h |
| P5 | Grok incident summaries | Incident grouping (kind + entity + event) with version and evidence hash; bounded evidence packet; versioned prompt file; Pydantic schema; Responses API (`store: false`, 20 s timeout, 2 attempts, ≤ 6 calls/min, 1 concurrent); evidence-id and entity checks; factual template fallback; no key → template | Mocked-Grok tests (valid, bad references, 429, timeout, incomplete); one live call when a key is provided | 3 h |
| P6 | Operator UI (plain language kept) | Home: demand forecast chart per station (observed + q50 + q10–q90 band, source label); Actions: forecast source and "if demand is higher" line; System: AI incident summaries (badge, generated-at, template state); health rows "Forecasting (Chronos)" and "AI summaries (Grok)"; proposal version sent on approval | Verified in the browser; no jargon | 3 h |
| P7 | Observability, load and evidence | Metrics: forecast latency, age, fallbacks, error vs formula; Grok calls, errors, latency, tokens, estimated cost; Grafana panels; k6 rerun with AI active; README, diagram and demo script updated (PS §22 step 5 = Chronos band, step 11 = stop forecaster → formula fallback, Grok summary of the crisis); CI runs AI tests with fake forecaster and Grok (no torch in CI) | Evidence recorded in devlog; CI green | 2.5 h |

Total ≈ 19 h. **If time is short, cut in this order:** P4 (only matters if Chronos is promoted), the Actions forecast line in P6, the Grafana AI panels, then P1 gap handling. Never cut P0 safety fixes or the fallbacks.

### R5.4 Configuration (backend-only secrets)

`.env.example` gains: `FORECAST_ENABLED`, `FORECAST_MODE=shadow|operational`, `FORECAST_URL=http://forecaster:8200`, `FORECAST_MODEL_ID=autogluon/chronos-2-small`, `FORECAST_MODEL_REVISION`, `FORECAST_CONTEXT_TICKS=288`, `FORECAST_MIN_CONTEXT_TICKS=96`, `FORECAST_HORIZON_TICKS=96`, `FORECAST_REFRESH_TICKS=8`, `GROK_ENABLED`, `XAI_API_KEY` (placeholder), `GROK_MODEL=grok-4.7`, `GROK_BASE_URL=https://api.x.ai/v1`, `GROK_TIMEOUT_SECONDS=20`, `GROK_MAX_ATTEMPTS=2`, `GROK_MAX_CALLS_PER_MINUTE=6`. No `VITE_` variables carry secrets; `.env`, weights, databases and reports stay out of Git.

### R5.5 Downloads, cost and data leaving the machine

- Downloads (need owner permission): CPU PyTorch wheel (~180 MB), chronos-forecasting and pandas (~40 MB), Chronos-2-Small weights (~112 MB) from Hugging Face.
- Grok: about 2k input + 0.5k output tokens per summary ≈ $0.007 at grok-4.7 prices; a demo day with ~100 summaries ≈ $1. Only simulated incident evidence is sent to xAI; no keys, tokens or databases.

### R5.6 Risks

| Risk | Mitigation |
|---|---|
| Chronos worse than the formula | Shadow mode + promotion gate; formula stays operational; reported honestly |
| Chronos latency at 8 ticks/s | Background thread, bounded queue, max-age check, formula fallback; demo at `SIMULATION_SPEED=1` |
| Spike semantics misread by the model | Normalise by recorded multiplier; affected station falls back to the formula until validated |
| Grok hallucination | Strict schema, evidence-id and entity checks, template fallback, facts and numbers from our own fields only |
| No xAI key or network at judging | Template summaries; everything else offline |
| Image size and CI time | Torch only in the forecaster image; CI uses fakes |

### Navigation

- [Revision 4 — official problem statement alignment](#revision-4--alignment-with-the-official-problem-statement)
- [Revision 5 — AI/ML phase implementation plan](#revision-5--aiml-phase-implementation-plan-awaiting-owner-approval)
- [Product scope](#3-product-scope-and-definition-of-a-full-mvp)
- [Documentation and simulator contract checks](#4-phase-0-documentation-discovery-and-contract-validation)
- [Architecture and stack](#6-recommended-architecture-and-technology)
- [State and persistence](#7-state-collection-freshness-and-persistence)
- [Deterministic projections](#8-deterministic-demand-and-inventory-projection)
- [Optimization model](#9-optimization-specification)
- [Safe execution](#10-decision-loop-and-safe-shipment-execution)
- [Dashboard and workflows](#13-dashboard-and-operator-workflows)
- [Benchmark pipeline](#16-reproducible-scenario-and-benchmark-pipeline)
- [Implementation milestones](#17-implementation-milestones-and-completion-gates)
- [Definition of done](#22-final-definition-of-done)
- [Sources and handoff](#24-reference-index-and-copy-ready-implementation-sources)
- [Next phase: AI/ML extensions](#25-next-phase-ai-ml-extensions-deferred-not-in-this-phase)

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

### 1.2 Phase boundary: no AI/ML now, AI/ML next

> **Revision 4:** the problem statement makes Predict/Detect/Explain part of the required loop. Decision D1 (Revision 4, R4.3) proposes statistical stockout risk and rule-based detection now, with learned models and LLMs still in the next phase. Pending owner confirmation.

**This phase completes every part of the MVP that requires no AI or machine learning.** Anything that would require AI/ML is deferred to the next phase (§25), not dropped. The deterministic system must be complete and scored on its own before that phase starts.

| Where AI/ML would usually go | What this phase uses instead | Next phase (§25) |
|---|---|---|
| Demand forecasting | The published demand-profile formula (§8.2) × hour factor × region factor × multiplier, plus a hand-set stress multiplier (§8.3). | Forecasts learned from demand history. |
| Decision policy (RL, learned policy) | Receding-horizon linear optimization with SciPy/HiGHS (§9); mixed-integer only if a verified simulator rule needs integers. | Learned or RL policies benchmarked against the LP. |
| "Continuously improve" | Re-solving every decision cycle, plus offline sensitivity sweeps that a person tunes by hand (§16). | Automatic tuning of margins and parameters from observed outcomes. |
| Explanations (LLM) | Text templates filled from binding constraints (§13.4). | Optional LLM-written summaries, grounded in the same recorded data. |
| Use of history | Validation and residual reporting only (§8.1). | Training data for forecasting and tuning. |

## 2. Authority, requirements, and unresolved scope

The supplied document explicitly says it is an **integration and interaction guide**. It does not supply the official participant brief, scoring weights, deliverables, mandatory technology, presentation length, or submission rules. Do not invent those requirements.

> **Revision 4:** the official problem statement is now available (`Problem_Statement_BUP_CSE_Fest_2026.pdf`). It supplies the deliverables (PS §19) and evaluation weights (PS §23); see Revision 4. Evaluation horizon and scoring questions in §2.1 are answered there: judging is not based on a simulator score.

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
- The guide (page 2, line 29) asks participants to "use the historical and simulated data … to build predictive capabilities and continuously improve your decisions." This phase covers the rule-based part: formula projections and re-solving every cycle. Learning from history is deferred to the next phase (§25). Confirm with organizers whether this phase alone is acceptable for judging.
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

- In this phase: LLMs, chatbots, agents making shipping decisions, model training, neural networks, reinforcement learning, learned forecasting, and safety margins or parameters derived automatically from history. These are deferred to the next phase (§25), not dropped.
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

**Run C00 first; it takes about one minute and decides the design regime (§5.4).** Of the rest, only C01–C04, C06, C10, and C15 block the first working slice (Milestone 1, §17). The remaining probes can run alongside later milestones.

| ID | Question | Required evidence |
|---|---|---|
| C00 | Is total supply enough for total demand? | Sum `/v1/supply-arrivals` quantities by depot and fuel; add starting depot and station stock; divide by projected network demand per day; compare with the span of the supply schedule. |
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
| C19 | Is realized demand identical across runs under different policies? | Run no-replenishment and threshold policies from reset with the same event recipe; compare demand-history rows. Identical demand makes the hindsight bound (§9.9) valid. |

### 4.5 Known documentation inconsistencies

- §5.4 says idempotent replay returns **201**, while §9 says **200**. Accept both with a valid allocation body.
- The guide calls allocation creation the only public write, but explicitly documents pending cancellation. Both are allowed in this plan.
- `CONSTRAINED` is explicitly shippable in §5.2. Do not treat it as closed because of the §9 troubleshooting wording.
- The `stale_data` fault is described as adding a header. Do not claim it necessarily returns an older snapshot.
- The exact demand-jitter distribution and reproduction algorithm are not supplied. A seed alone is insufficient to recreate them.

**Milestone 0 exit gate:** the semantics section of `devlog.md` separates confirmed behavior from remaining assumptions; no optimizer constraint depends silently on an unresolved behavior.

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

The baked scenario contains 22 arrivals: four initial arrivals at ticks 12–20, then three cycles of six arrivals (one per depot/fuel, 4 ticks apart) starting at ticks 64, 128, and 192. The last arrives at tick 212 (C00, §5.4). Read actual rows from `/v1/supply-arrivals` for exact timing, destination, fuel, and quantity.

Do not generate an infinite recurring schedule from this description. After the final listed supply, project only existing stock unless additional arrivals are actually observed.

### 5.4 Supply adequacy — the regime decision

**C00 measured on 29 Sep 2026** against the live `baseline` scenario (seed 12345):

| Quantity | Measured / estimated | Basis |
|---|---:|---|
| Network demand | ≈ 93,000 L/day (estimate) | Profile daily liters × regional factor × mean hour factor (urban 0.95, highway 0.975, industrial and regional 1.0). |
| Starting stock, depots + stations | 338,000 L ≈ 3.6 days | Live `/v1/depots` + `/v1/stations`. |
| 22 supply arrivals | **216,000 L ≈ 2.3 days** | Live `/v1/supply-arrivals`: 4 initial arrivals (ticks 12–20), then 3 cycles of 6 arrivals (one per depot/fuel) starting at ticks 64, 128, 192. |
| Supply schedule span | **ticks 12–212 ≈ 2.2 days** | Last arrival `supply-306` at tick 212. The guide's "18 arrivals spaced 64 ticks apart" means 3 cycles 64 ticks apart, not 18 gaps of 64 ticks. |
| Total fuel in the world | ≈ 554,000 L ≈ 5.9 days | Diesel ≈ 6.1 days, petrol ≈ 5.5 days, octane ≈ 6.5 days. |
| By region | Dhaka ≈ 6.7 days, Chattogram ≈ 5.3 days | Gazipur-side fuel vs Dhaka demand; Patiya-side fuel vs Chattogram demand (demand ×1.08). |

So the world holds about 6 days of fuel, and all resupply is delivered within the first 2.2 days. Any run longer than about 6 simulated days (≈ 72 real seconds at default speed) ends in structural shortage, however good the controller. Chattogram runs short about 1.4 days before Dhaka unless fuel moves across regions. **Supply is the binding limit for any long run**, and the planner's job changes:

- From "avoid stockouts" to **"make every liter get consumed somewhere; lose none to overflow, and strand none in the wrong depot."**
- Cross-region routes (`route-gazipur-karnaphuli`, `route-patiya-mirpur`) become important for rebalancing between regions, not just as fallbacks.
- Depot overflow at supply arrival is a direct loss. Drain depots ahead of large arrivals.
- Unmet demand is unavoidable, so the score depends on how completely the available fuel is delivered.

Runs shorter than about 5 simulated days are limited by timing, dispatch capacity, and station tank size rather than total fuel. The same LP objective (§9.7) covers both regimes; only the reported expectations change. Every report states the run length in simulated days next to the 5.9-day fuel ceiling.

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
| Optimization | SciPy `linprog(method="highs")` | Plain LP (§9.4); no integer variables, so solves take milliseconds. |
| Persistence | SQLite | Sufficient for one local participant application and durable intents. Add a migration tool only when the schema changes after the first release. |
| Frontend | React + TypeScript + Vite | Interactive operational views without a separate server-rendering requirement. |
| UI components and styling | shadcn/ui + Tailwind CSS | User-selected component foundation, with a shared operations-dashboard theme. |
| Charts/network | SVG and a small chart library if needed | Six routes do not require a geographic mapping platform. |
| Backend tests | pytest | Pure-model, integration, and benchmark assertions. |
| UI verification | Playwright (Milestone 5) | Critical operator flows, error states, keyboard and mobile checks; deferred until after a score exists. |
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
  reports/                 # generated, timestamped benchmark outputs (CSV/JSON)
devlog.md                  # the single project log: progress, simulator semantics, decisions, results
```

Project documentation lives in one Markdown file, `devlog.md` (owner decision, 29 Sep 2026). Contract semantics, model notes, operations notes, and demo steps go there as sections, not as separate files. `README.md` holds only startup instructions.

## 7. State collection, freshness, and persistence

### 7.1 Snapshot contract

Each planning snapshot contains:

- Application run ID and simulator scenario/version/seed.
- Start and end observed ticks, simulation time, and tick size.
- Depot, station, route, region, supply, event, and allocation data.
- Per-response receive time, stale header, and error.
- Snapshot quality: `FRESH`, `DEGRADED` (stale-flagged, partial, or estimated from the last good snapshot), or `RESET_UNCERTAIN`.
- Existing pending/in-transit commitments and unresolved local intents.

Collect independent REST resources concurrently, with a bounded connection pool. No before/after `/v1/instance` skew reads are needed. Tanks hold 70–150 ticks of demand and lead times are 3–5 ticks, so a snapshot a few ticks inconsistent loses almost nothing in plan quality.

What matters is the action, not the snapshot. **Immediately before each POST, re-read the source depot and destination station** and clip the quantity to current source stock and destination headroom. The server validates every POST as well (§10.7), and a rejected request never becomes an allocation.

Only `RESET_UNCERTAIN` blocks dispatch. `DEGRADED` dispatches conservatively (§12.1).

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

Use fixed documented demand profiles, observed multipliers, known event schedules, arithmetic, and hand-set safety assumptions. No trained prediction model, fitted regression, neural network, or learned policy.

**Use of history in this phase: validation and residual reporting only.** Record `actual − nominal` per station/fuel and show it in reports and plan explanations so a person can judge the formula and tune margins by hand. History never feeds back into decisions automatically; that is the next phase (§25).

`demand_multiplier` is returned directly by `/v1/stations` and already includes active spikes. Read it; do not estimate it with a filter or state estimator.

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

### 8.3 Safety envelope (hand-set)

Provide explicit, deterministic policy parameters, set by a person:

- Demand stress multiplier above nominal (start 1.0; the guide's noise parameters, 0.08–0.12, suggest trying 1.1).
- Additional delivery-delay allowance in ticks.
- Target coverage buffer expressed in simulated hours.
- Optional extra coverage for single-route stations (Tongi, Cox's Bazar).

Version these values and choose them through offline sensitivity sweeps (§16) that a person reviews; the residual report (§8.1) informs that choice. They are engineering assumptions, not measured probabilities or guaranteed service levels. Convert durations using actual tick size.

Under supply scarcity (§5.4), buffers only decide **where** scarce fuel waits; they cannot create fuel. Keep them small.

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

**Cadence:** replan every 8 ticks (2 simulated hours at default), and immediately on a new public event, an allocation turning `FAILED`, a supply-row change, or a reset notice. Coalesce triggers so at most one cycle runs at a time. Tanks hold 70–150 ticks of demand against 3–5 ticks of lead time, so replanning more often gains almost nothing.

Start evaluation with a 96-tick horizon at the default tick size, and compare 48, 96, 192 ticks, and the full remaining supply schedule. The LP (§9.4) is cheap enough for all four. These are experiments, not established optimal settings. Expose horizon in simulated hours so non-default tick sizes remain meaningful.

The horizon should cover lead times, demand peaks, and at least the next supply arrival at each depot. **Do not reward stock held at the end of the horizon**; that reward is what breaks the LP's greedy-service property (§9.4). End-of-horizon myopia is handled by replanning and by a horizon long enough to see the next supply arrival.

### 9.2 Variables and indices

Indices: depot `d`, station `s`, fuel `f`, route `r`, planning offset `k`. No allocation-slot index: shipment count is not scored, so the model plans aggregate flow and splits it afterward (§9.5).

All variables are continuous:

| Variable | Meaning |
|---|---|
| `x[r,f,k] ≥ 0` | Total liters submitted on route r for fuel f at offset k. |
| `D[d,f,k] ≥ 0` | Depot inventory at a precisely defined phase of tick k. |
| `I[s,f,k] ≥ 0` | Station inventory at a precisely defined phase of tick k. |
| `y[s,f,k] ≥ 0` | Demand actually served in the model. |
| `u[s,f,k] ≥ 0` | Unmet demand, with `y + u = demand`. |
| `w[d or s,f,k] ≥ 0` | Overflow only if the simulator actually discards excess stock (C06). |

This removes roughly 1,150+ binaries per 96-tick horizon compared with the previous MILP.

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

### 9.4 Automatic consumption as a plain LP

The simulator serves available fuel automatically: `y = min(A, q)` for pre-demand stock `A` and demand `q`. An optimizer must not gain fictitious flexibility by withholding service today to keep inventory for tomorrow.

Get this for free, without binaries, through the objective weights:

```text
0 ≤ y ≤ A,   y ≤ q,   y + u = q

weight on u[s,f,k] = 1 + ε (H − k),   ε > 0, e.g. ε = 1 / (10H)
no reward for stock remaining at the end of the horizon
```

**Why the LP serves greedily.** Suppose a solution withholds δ liters at tick k while stock is available. Those δ liters can reduce unmet demand at some later tick k′ > k by at most δ, at weight `1 + ε(H − k′)`. That is strictly smaller than the `1 + ε(H − k)` saved by serving now. Serving at k is therefore never worse and usually strictly better, so every optimal solution has `y = min(A, q)`.

The argument holds only while nothing else in the objective pays for keeping stock. Specifically:

- No terminal-stock or coverage reward (§9.1).
- Any secondary terms (overflow, transit exposure) cost at most a small fraction of the smallest weight gap ε per liter, and neither rewards holding.
- Fairness is reported as a metric, not optimized inside this LP (§9.7).

The independent trajectory replay (§16.5) checks `y = min(A, q)` on every accepted plan anyway.

Outage service and inventory effects must follow C09. If the simulator clips excess inventory (C06), model overflow `w ≥ stock + inflow − capacity` with a small positive cost. Because discarding fuel never frees anything useful, the LP never discards voluntarily; the replay test checks this too.

### 9.5 Required constraints

| Constraint | Implementation requirement |
|---|---|
| Valid connectivity | Only observed routes connecting the requested depot and station. |
| Valid statuses | Station open; route available at required times; depot OPEN or CONSTRAINED as allowed. |
| Fuel conservation | No invented fuel and no substitution between fuel types. |
| Source availability | Reserve/dispatch only fuel available at the relevant phase. |
| Depot capacity | Respect observed capacities and confirmed arrival overflow semantics. |
| Dispatch budget | Sum all fuel/route quantities in the exact accounting window established by C04. |
| Per-allocation route limit | Applied after solving: split each `x[r,f,k]` into `ceil(x / max_shipment)` requests. Do not cap aggregate route flow. |
| Destination submission check | Each immediate request must satisfy current API headroom validation. |
| Destination arrival capacity | Existing and new incoming shipments must be considered at arrival times. |
| Lead times | Include verified acceptance-to-departure delay and route transit time. |
| Existing commitments | Preserve in-transit shipments and account for pending shipments. |
| Known future closures | Disallow actions whose verified submission/departure behavior would fail. |
| Finite supply | Use only observed future arrivals, with known delay/shortfall effects. |
| Execution window | Current actions must still be relevant when they are submitted. |

**Splitting:** the solver plans aggregate flow. The executor splits each immediate `x[r,f,0]` into equal chunks no larger than `max_shipment`, using a declared quantity precision. It then submits them in order, re-reading source stock and destination headroom before each POST and clipping the quantity when needed. If a chunk is rejected, stop that route/fuel and let the next replan handle the remainder. Do not assume splitting preserves feasibility automatically.

### 9.6 Conservative safety restrictions

It can be sensible to reserve station headroom against all locally committed arrivals even if the server validates only current stock plus one request. This avoids overbooking but can exclude otherwise feasible time-separated deliveries.

Track such rules in the plan metadata as **application safety restrictions**. A model solved with them is optimal only within those restrictions. Prefer time-indexed arrival checks over unnecessarily reserving all future fuel against present headroom.

### 9.7 Objective hierarchy

Until official scoring is supplied, use one weighted LP objective:

```text
minimize   Σ (1 + ε(H − k)) · u[s,f,k]        time-decreasing unmet demand (primary)
         + c_over · Σ w[·,f,k]                  overflow = fuel lost (c_over < ε)
         + c_tx   · Σ transit_ticks(r) · x[r,f,k]   transit-exposure tie-break (c_tx · max_transit < ε)
```

Under supply scarcity (§5.4) this objective does the right thing automatically. Every liter that can reach demand in the horizon is delivered, overflow is avoided because lost fuel means later unmet demand, and stock moves across regions when the other region would otherwise run dry first.

Rules:

- Demand input is the nominal projection plus the §8.3 buffer inside each station's lead-time window.
- Do not invent monetary costs. Transit exposure is a labeled proxy, not currency, distance, or emissions.
- Keep secondary coefficients below ε per liter so they cannot trade away service (§9.4).
- Fairness (worst station/fuel service ratio) is **reported**, not optimized. If the official brief scores fairness, add a separate policy profile with per-station weights and rerun comparisons.
- Use stable variable ordering for reproducible plans.

Display the objective and coefficients in every plan. If official judging weights differ, create a separate profile rather than claiming this objective matches the official score.

### 9.8 Solver policy

- Begin with correctness on small cases, then benchmark the full time-indexed formulation.
- Use sparse constraints, stable variable order, pinned solver versions, and recorded options.
- Set a solve deadline derived from measured operational timing; unlimited project time does not imply unlimited decision latency.
- Check solver status before using result arrays.
- Independently check finite numbers, bounds, conservation, constraints, and current-action feasibility.
- Record objective values, solve duration, and solver status.
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
| Perfect-hindsight bound | **Benchmark only.** The same LP solved once over the whole run using the demand actually recorded in a previous identical run (valid only if C19 confirms identical demand). It gives a ceiling no online policy can beat. Never feed recorded demand into the live policy; judges may inject different events. |

For an initial reproducible threshold baseline, use a declared reorder threshold of 30% and order-up-to target of 70% of station/fuel capacity. Count confirmed incoming commitments when calculating the refill amount; keep current API headroom and future receiving feasibility checks. Choose the fastest feasible route, then stable route ID for ties. These percentages are baseline configuration choices, not simulator rules; also report a reasonable threshold sensitivity sweep so the comparison is not against an intentionally weak setting.

The threshold policy and optimizer must share the same reliable integration/execution layer. Otherwise a benchmark may measure different retry implementations rather than better decisions.

Fallback when optimization fails but state is usable:

1. Rank station/fuel pairs by earliest shortage relative to feasible delivery time.
2. Prefer actions preventing immediate unmet demand; account for route dependency.
3. Compute a limited replenishment target from the same deterministic demand rules.
4. Select a feasible route and quantity using current source, dispatch, and destination checks.
5. Submit through the same outbox, then recompute remaining capacity.

If state is stale-flagged or partial, keep dispatching conservatively from an estimated state (§12.1). Hold new allocations only when reset is uncertain, because old-run intents must never leak into a new world.

## 10. Decision loop and safe shipment execution

### 10.1 Operational pseudocode

```text
on startup:
    load configuration and unresolved intents
    establish run continuity
    refresh public state and reconcile ledger
    keep automatic sending disabled until reconciliation succeeds
    start stream consumer and polling scheduler

every 8 ticks, or on public event / FAILED allocation / supply change / reset notice:
    coalesce work into one coordinator cycle
    collect a snapshot (FRESH, DEGRADED, or RESET_UNCERTAIN)
    reconcile existing allocations and reservations
    if RESET_UNCERTAIN:
        publish held state; create no new intents until the run boundary is resolved
    else:
        if DEGRADED:
            estimate current state = last good snapshot
                                     − projected demand since then
                                     + own shipment ledger (departures/arrivals)
            apply the conservative quantity factor (§12.1)
        build deterministic projections
        solve the LP; replay-validate the plan
        publish plan and reasons
        if automatic mode is enabled:
            for each immediate chunk, in order:
                re-read source depot and destination station (if reachable)
                clip quantity; POST; a 409 is free, refresh and continue
    persist outcomes
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

**Staging:** Milestones 1–4 (§17) use the minimal safe core: persist the key and body before the POST, and after a timeout, look up the key in the ledger before retrying the identical body. The full state machine above arrives in Milestone 5; the rules in §10.4–10.7 apply from the start.

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
| `latency` | Bound request concurrency, coalesce refreshes, skip overlapping cycles; **keep dispatching**. | Normal cadence resumes. |
| `unavailable` | Keep the plan current from the estimated state; retry POSTs of the current plan's immediate chunks with bounded backoff (same keys) so the first chunk lands as soon as the API returns. | Full state and outbox reconciliation. |
| `error_rate` | Retry transient reads; handle uncertain writes with same immutable key and ledger reconciliation; **keep dispatching**. | Successful authoritative refresh; unresolved writes accounted for. |
| `stale_data` | Treat flagged responses as `DEGRADED`; **keep dispatching conservatively** (see below). C15 determines whether the flagged body is actually old. | Unflagged refresh. |
| `stream_disconnect` | Reconnect with bounded backoff; keep REST polling active. | Stream recovered or operational polling verified; full resync after reconnect. |

**Why not hold.** At default speed, 60 real seconds ≈ 5 simulated days (§12.2), while station buffers are 0.75–1.6 days. A one-minute hold empties every tank. Holding is also unnecessary:

- A rejected POST (404/409/422) never becomes an allocation, so it is not counted in `allocation_failures` (§15.1). The server validates source stock, route, station status, and destination headroom on every POST.
- The `stale_data` header may only flag responses without replaying old data (C15).

**Conservative degraded dispatch:** plan from the estimated state; multiply immediate quantities by a declared factor (for example 0.7) so an overestimate of headroom wastes little; prefer stations whose estimated shortage is nearest; and record every degraded-mode decision in the plan explanation.

Keep last-known values visible for diagnosis, labeled with age and degraded status.

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

Consequence: any fault response that stops dispatch for more than a few real seconds costs whole simulated days of service. Fault handling must degrade, not halt (§12.1).

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

> **Superseded by Revision 4 (R4.5):** five views covering all twelve PS §6 items.

**Milestone 4 builds three views only:**

| View | Required contents and actions |
|---|---|
| Overview | Simulation clock, mode, data freshness, service level, unmet liters, supply-adequacy summary (§5.4), six-route network, ranked shortage list, per-station tank levels. |
| Shipments | Filter by lifecycle, station, depot, fuel; inspect request/arrival times; cancel pending shipments. |
| Plans | Snapshot time, horizon, objective and coefficients, solver result, immediate proposals, future tentative actions, approve/recalculate controls. |

**Deferred to Milestone 5 or cut:** station detail and depot detail (fold the key numbers into Overview), incidents (show the active event/fault banner on Overview instead), test lab (the CLI harness covers it), and reports (the benchmark CLI writes CSV/JSON).

These may be tabs or routes. Do not duplicate operational state across independent frontend stores.

### 13.3 Essential user journeys

1. **Start safely:** connect → view snapshot quality → inspect proposed plan → enable automatic mode.
2. **Understand a shipment:** select allocation → see demand risk, route choice, quantity bounds, solver/policy, and actual outcome.
3. **Review manually:** generate plan → review current actions → approve → revalidate snapshot → submit → show partial or complete results.
4. **Create a manual allocation:** choose station/fuel → show valid depots/routes → enter quantity → validate → persist intent → submit.
5. **Respond to crisis:** see event → inspect affected station/route → view changed risk → see replanned allocation or explicit infeasibility.
6. **Ride through a fault:** see the degraded banner and the estimated values with their age → controller keeps dispatching conservatively → public reads recover → intents reconcile → normal mode resumes.
7. **Run a benchmark (CLI in Milestones 1–4):** select recipe and policies → confirm reset → run sequentially → inspect measured results → export.

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

Basic semantics (labels, headers, text-plus-color warnings, no double submit) apply from Milestone 4. Automated Playwright accessibility and mobile checks move to Milestone 5.

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

**Headline metric: share of the achievable gap closed.**

```text
gap closed %
  = (baseline_unmet − policy_unmet) / (baseline_unmet − hindsight_unmet) × 100
```

`hindsight_unmet` comes from the perfect-hindsight LP (§9.9) on the same scenario. Under supply scarcity (§5.4), much unmet demand is unavoidable, so "unmet reduction %" alone understates a good policy; the gap-closed figure shows how close the policy gets to the best possible. Report it only when C19 confirms identical demand across runs and the event recipe is the same. If the denominator is zero or negative, report absolute values instead.

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
| S12 | **Main regime:** supply-limited run through and beyond the final listed supply | Near-zero overflow at depots and stations; minimal fuel stranded in a depot while its region's stations are short; cross-region routes used; never invents new resupply. Compare against the hindsight bound. |
| B01 | Perfect-hindsight bound | Recorded demand from an identical run; LP ceiling for S01 and S12; gap-closed % reported (§15.3). |
| F01 | Latency | Bounded queue, no concurrent writers, dispatch continues. |
| F02 | API unavailability | Plan kept current from estimated state; first chunk lands soon after recovery; reconciliation after recovery. |
| F03 | Probabilistic errors | Safe retries without duplicate logical shipments. |
| F04 | Stale-data header | **Dispatch continues** in conservative degraded mode; unmet demand during the fault compared with a hold-dispatch variant. |
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
- Counterexample for voluntary withholding: a fixture where holding stock would help a later tick. The decreasing-weight LP must still serve `min(A, q)` at every tick (§9.4).
- A depot-overflow fixture: a large supply arrival into a nearly full depot. The LP must ship ahead of the arrival rather than let fuel overflow.
- Supply overflow and station outage cases matching confirmed semantics.
- Lexicographic priority test: secondary convenience cannot worsen primary service beyond tolerance.
- Numerical rounding and request-splitting feasibility.
- Solver objective compared with a brute-force search on small quantized fixtures; label quantization and compare within the same model.
- Independent trajectory replay of every proposed plan before accepting solver feasibility claims.

Use deliberately small fixtures to test modeling errors. Do not reproduce the optimizer matrix construction verbatim in tests and call that independent verification.

## 17. Implementation milestones and completion gates

> **Revision 4:** Milestones 0–2 below are done. Milestones 3–5 are superseded by R4.6 (M3–M9).

There is no imposed deadline, but the order is built around a **working slice**: a policy that ships fuel against the real simulator and produces a score exists from the first day of implementation. Plumbing, dashboard polish, and hardening come after the score exists, never before it.

Each milestone ends with a runnable system and a recorded benchmark. Advance only when the gate passes.

**Execution scope (owner decision, 29 Sep 2026):** execute now only the components that will **not** receive AI/ML integration later. Components listed as AI/ML targets in §1.2 and §25 are frozen at their current working version and resumed with the next phase:

| Execute now (no future AI/ML) | Frozen now, resumed with the AI/ML phase |
|---|---|
| Simulator client, contract probes, error normalization | Demand projection refinements (§8.2) and residual report |
| Executor: splitting, headroom, dispatch budget, idempotency, request consolidation | Safety margins and stress profiles (§8.3) |
| Stepped benchmark harness, metrics, hindsight bound, reports | Decision-policy work: LP horizon sweeps, tuning, fallback refinement (§9); learned/RL policies |
| Fault handling, degraded mode, SSE consumer, event detection and replan triggers | Crisis-specific planning logic (e.g. pre-positioning for announced disruptions, §11) |
| Persistence, outbox, restart/reset reconciliation | Automatic parameter tuning |
| Dashboard (Overview, Shipments, Plans), packaging, demo | Plan explanations (§13.4 templates → optional LLM) |

The LP planner built in Milestone 2 (measured within 9 L of the hindsight bound over 7 days) stays in use as the current policy without further tuning.

### Milestone 0 — Supply adequacy and blocking probes (first hours)

**Implement:** C00 supply sum (§5.4); probes C01–C04, C06, C10, C15 (§4.4). Minimal scripts; no application framework yet.

**Read/copy:** guide §§4–5, §7.5–7.6 (step/reset), §8.7; this plan §4.4 and §5.4.

**Gate:** the semantics section of `devlog.md` records the supply regime (scarce or ample), departure/arrival timing, dispatch-budget window, overflow behavior, replay status code, and what `stale_data` actually does.

### Milestone 1 — Working slice (first day)

**Implement:**

- Minimal typed simulator client: the public reads, `POST /v1/allocations`, error-envelope normalization.
- Threshold policy (§9.9) running **automatically** against the real simulator.
- Execution: split into `max_shipment` chunks, re-read source/destination before each POST, persist key+body before sending, look up key after a timeout (§10.3 staging).
- Step-based test harness: reset → pause → decide → step, for a declared horizon; capture `/v1/metrics` and demand history; write CSV/JSON.
- No-replenishment baseline through the same harness.

**Gate:** the threshold policy completes a stepped run from reset without crashing; the report shows its service level against no-replenishment. **A score exists.**

**Deferred on purpose:** database migrations, the full outbox state machine, the dashboard, SSE (polling is enough at this stage).

### Milestone 2 — LP planner and upper bound

**Implement:** deterministic demand projection (§8.2); residual report and hand-set stress profiles (§8.1, §8.3); time-indexed LP (§9.2–9.7) with the decreasing weights; post-solve split; independent trajectory replay; earliest-shortage fallback; C19 probe; perfect-hindsight bound (§9.9); gap-closed reporting (§15.3).

**Read/copy:** official SciPy `linprog` reference (§24); guide §8.5–8.6; verified probe fixtures.

**Gate:** §16.5 correctness fixtures pass (including withholding and overflow fixtures); LP beats threshold on S01 and S12, or the report explains why not; horizon comparison 48/96/192/full-schedule recorded; hindsight gap-closed % reported.

### Milestone 3 — Events and fault handling

**Implement:** SSE consumer with polling fallback; event-triggered replanning (§9.1); crisis handling (§11); degraded-mode dispatch from estimated state (§12.1); remaining probes C05, C07–C09, C11–C14, C16–C18.

**Gate:** S02–S12 and F01–F05 executed; F04 shows degraded dispatch beating a hold-dispatch variant (or the report explains why not); R01 and R03 pass (no duplicate shipment after a lost response; no old-run intent after reset).

### Milestone 4 — Dashboard: Overview, Shipments, Plans

**Implement:** FastAPI application endpoints needed by the three views (§14 subset: status, overview, allocations, plans, recalculate, execute, cancel, operating mode); React + TypeScript + Vite with shadcn/ui and Tailwind CSS; the three views in §13.2; observe/manual/automatic modes.

**Gate:** live data throughout; approve/cancel/recalculate flows work; degraded banner visible during a fault; no duplicate submissions on repeated clicks.

### Milestone 5 — Hardening and delivery (after the score exists)

**Implement, in value order:**

1. Full outbox state machine (§10.3), restart reconciliation (R02), reset boundaries, remaining R-scenarios.
2. SQLite persistence of runs, plans, intents, and history, with gap detection (§7.3–7.5).
3. Docker Compose packaging, README, runbook, demo script (§20).
4. Playwright critical-flow and accessibility checks; CSRF/origin guard (§19).
5. Deferred views (station/depot detail, incidents, test lab, reports) only if time and value justify them.

**Gate:** the §22 definition of done, with any skipped item explicitly listed as a known limitation.

### Next phase — AI/ML extensions (§25)

Not part of this phase. Starts only after Milestone 5's gate passes, against the scored deterministic baseline.

**Anti-pattern audit (before release):** search for unauthorized simulator database access, ML dependencies, invented API paths, random dashboard metrics, undocumented hard-coded capacity reductions, multiple controller startup sites, recorded demand reaching the live policy, and new idempotency keys inside blind retry loops. Review findings rather than relying on keyword search alone.

## 18. Configuration specification

Separate simulator configuration from application policy configuration.

| Configuration | Meaning / initial policy |
|---|---|
| Simulator base URL | Backend connection target; container and host URLs differ. |
| Tick size | Read from instance; simulator environment controls actual value. |
| Simulation speed | Test metadata / simulator setup; do not infer solely from wall-clock assumption. |
| Start mode | Observe/manual by default until run reconciliation completes. |
| Horizon hours | Starting experiment 24 hours; compare 12, 48 hours, and full remaining supply schedule. |
| Replan cadence | Every 8 ticks, plus immediately on events, FAILED allocations, supply changes, and reset notices. |
| Degraded quantity factor | Multiplier on immediate quantities in degraded mode (start 0.7). |
| Demand profile version | Versioned fixed tables and verified factor semantics. |
| Demand stress multiplier | Explicit configurable assumption; baseline nominal = 1.0. |
| Delay allowance | Fixed extra planning ticks after verified physical lead time. |
| Coverage target | Simulated duration, not an unlabelled liters constant. |
| Single-route reserve preference | Visible policy option evaluated in benchmarks. |
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
- Keep browser mutations same-origin; add an origin/CSRF guard for local state-changing endpoints in Milestone 5.
- Validate all user-entered quantities, IDs, durations, and event parameters on the backend.
- Route all UI mutations through the coordinator; do not allow a UI shortcut to bypass execution validation.
- Keep simulator base URL in trusted configuration rather than an unrestricted arbitrary URL-fetch endpoint.
- Store SQLite in a named persistent volume or documented local data directory; back up/export before reset-driven benchmark sessions.
- Preserve run logs outside the simulator, since simulator reset deletes its tables and audit history.
- On shutdown, stop generating intents, persist unresolved requests, and reconcile on restart.
- Keep one controller owner and one test-harness owner; locks must fail visibly if conflicting work is requested.

No authentication platform is needed for a loopback-only MVP. If later deployed to a shared network, access control and deployment security become a separate required workstream.

## 20. Demo and presentation plan

> **Superseded by Revision 4 (R4.8):** follow the 14-step story from PS §22.

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
| Missing participant brief | MVP might miss official deliverables or objective weights. | **Resolved:** brief received; mapped in Revision 4 (R4.2, R4.7). |
| Incorrect tick ordering | Optimizer uses stock too early or misses departures. | C02/C03 probes and independent trajectory tests. |
| Demand model mismatch | Model-optimal plan performs poorly in actual runs. | Compare nominal projection with actual demand; expose discrepancy; fixed stress profiles. |
| LP withholding service | False optimum that simulator cannot execute. | Time-decreasing unmet weights and no terminal reward (§9.4); replay check of `y = min(A, q)` on every plan. |
| Holding dispatch during faults | Tanks run dry within a real minute. | Conservative degraded dispatch; server validation as safety net (§12.1); F04 comparison. |
| Plumbing before score | Demo arrives with infrastructure but no measured result. | Working-slice milestone order (§17). |
| Too much optimization latency | Plan expires before dispatch. | Measure full cycle, bound solve time, simplify horizon, safe fallback. |
| Inconsistent REST snapshots | Overspending or rejected actions. | Re-read source and destination before each POST; server validation; serialized execution. |
| Ambiguous POST outcome | Duplicate or obsolete shipment. | Durable immutable intent, ledger reconciliation, same-key replay only when appropriate. |
| Hidden reset | Old intents replay into a new world. | Run isolation, continuity checks, hold on ambiguity. |
| Sole-route isolation | Unavoidable local shortage. | Public-notice pre-positioning where possible; report physical limitation honestly. |
| Finite total supply (likely main regime) | Service falls regardless of controller; overflow or stranding wastes scarce fuel. | C00 first; objective counts lost fuel; hindsight bound shows what was achievable (§5.4, §9.9). |
| Lost history during outage | Misleading station-level reports. | Frequent persistence, explicit gap detection and completeness flags. |
| Overfitting scenario recipes | Attractive demo but fragile general performance. | Hold-out recipes, varied event times and severities, report failures. |
| Incorrect “optimal” marketing | Claims exceed evidence. | Record exact model, objective, tolerance, solve status, and information assumptions. |

## 22. Final definition of done

> **Revision 4:** the required deliverables in R4.7 (PS §19) are the primary definition of done; the checklist below still applies to integration safety.

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
- [ ] Reset-uncertain state cannot trigger new dispatch; degraded state dispatches conservatively and is labeled.

### Deterministic planning

- [ ] No AI/ML/LLM dependency participates in decisions or explanations in this phase; deferred items are listed in §25.
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
- [ ] Dashboard (Overview, Shipments, Plans) uses the user-selected shadcn/ui + Tailwind CSS foundation with consistent theme tokens.
- [ ] Reports include the hindsight bound and gap-closed % where C19 allows it.
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
| Finite 22-arrival schedule (§8.7) | §§5, 9, 16 | C00 supply sum; S12 scarcity scenario. |
| Use history for prediction (guide line 29) | This phase: §8.1 residual reporting. Learning: §25 (next phase). | Residual report per station/fuel. |
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
- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/): manage HTTP clients, storage connections, and controller startup/shutdown through the application lifespan mechanism. Ensure one owner of the controller.
- [HTTPX async support](https://www.python-httpx.org/async/): reuse an `AsyncClient` and use its streaming interface for long-lived responses. Avoid creating a new client inside every hot-loop request.
- [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/): configure connect, read, write, and pool timeouts separately, with a distinct policy for the SSE connection.

### 24.3 Implementation handoff instructions

Execute one milestone at a time. At the start of each milestone:

1. Read that phase's listed source sections and previously verified contract fixtures.
2. Identify its dependencies and unresolved assumptions.
3. Implement only the stated deliverables and necessary supporting code.
4. Run its verification checklist and document actual outcomes.
5. Update the contract/model document if observations differ from the guide.
6. Advance only when the completion gate passes or a clearly documented limitation has an accepted conservative treatment.

The first concrete implementation milestone is the C00 supply sum, followed by an automatic threshold policy running against the official image with a stepped harness and a measured score. The final milestone is a complete, tested deterministic operations application with measured benchmark evidence.

## 25. Next phase: AI/ML extensions (deferred, not in this phase)

Starts only after this phase's definition of done (§22) is met and a scored deterministic baseline exists. Every AI/ML component must be compared against the deterministic LP on identical scenarios (§16) and must beat it, or stay off.

| Extension | Replaces or augments | Entry condition | Guard |
|---|---|---|---|
| Learned demand forecast from `/v1/demand-history` | Formula projection (§8.2) | Residual report (§8.1) shows systematic error the formula misses | Train only on history already observed in the current run; never on recorded future demand. |
| Data-driven safety margins (e.g. error quantiles) | Hand-set stress multiplier (§8.3) | Hand-tuned sweeps show margins matter | Report margins and sample sizes in every plan. |
| Learned or RL dispatch policy | LP planner (§9) as primary | LP gap to hindsight bound (§15.3) is large enough to be worth closing | The LP remains as fallback; the executor's safety checks (§10) still apply to every action. |
| Automatic parameter tuning | Manual sensitivity sweeps (§16) | Stable benchmark harness | Hold-out scenarios; no tuning on judge-like recipes only. |
| LLM explanations | Constraint templates (§13.4) | Templates exist and are correct | Grounded only in recorded plan data; never makes or changes decisions. |

This phase is the guide's "use the historical and simulated data … to build predictive capabilities and continuously improve your decisions" (line 29). Confirm with organizers whether it is expected for judging.
