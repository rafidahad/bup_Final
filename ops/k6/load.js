// Load test (PS §17): the operator dashboard backend and the decision path, while the simulator runs.
// Run: see devlog "Load testing" for the exact command (k6 container on the compose network).
import http from "k6/http"
import { check, sleep } from "k6"
import { Trend } from "k6/metrics"

const BASE = __ENV.BASE || "http://localhost:8100"
// PROFILE=stress: no think time (finds the capacity limit). PROFILE=realistic: each dashboard polls once a second.
const REALISTIC = (__ENV.PROFILE || "stress") === "realistic"
const decisionLatency = new Trend("decision_path_ms", true)

export const options = {
  scenarios: {
    dashboard: {
      executor: "ramping-vus", exec: "dashboard", startVUs: 0,
      stages: [
        { duration: "20s", target: 10 },
        { duration: "30s", target: 50 },
        { duration: "30s", target: 100 },
        { duration: "20s", target: 0 },
      ],
    },
    decisions: {
      executor: "constant-arrival-rate", exec: "decisions", rate: REALISTIC ? 5 : 20, timeUnit: "1s",
      duration: "100s", preAllocatedVUs: 20, maxVUs: 60,
    },
  },
  thresholds: {
    "http_req_failed": ["rate<0.01"],
    "http_req_duration{scenario:dashboard}": ["p(95)<500"],
    "decision_path_ms": ["p(95)<500"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
}

// What an operator's browser polls every second on the overview.
export function dashboard() {
  const res = http.batch([
    ["GET", `${BASE}/api/status`], ["GET", `${BASE}/api/overview`], ["GET", `${BASE}/api/allocations`],
  ])
  for (const r of res) check(r, { "status 200": x => x.status === 200 })
  if (REALISTIC) sleep(1)
}

// Decision path: current recommendations with risk, impact, alternatives, plus health.
export function decisions() {
  const r = http.get(`${BASE}/api/recommendations`)
  decisionLatency.add(r.timings.duration)
  check(r, { "recommendations 200": x => x.status === 200 })
  http.get(`${BASE}/api/health`)
}
