"""Prometheus metrics (PS §14): application, intelligence, and integration layers.
System CPU/memory come from prometheus_client's default process collector inside the Linux container."""
from prometheus_client import Counter, Gauge, Histogram

# application layer (API middleware)
HTTP_REQUESTS = Counter("fuelops_http_requests_total", "API requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("fuelops_http_request_seconds", "API request latency", ["route"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))

# simulator integration
SIM_SNAPSHOT_SECONDS = Histogram("fuelops_sim_snapshot_seconds", "Parallel snapshot latency",
                                 buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
SIM_ERRORS = Counter("fuelops_sim_errors_total", "Failed simulator reads", ["kind"])
SIM_TICK = Gauge("fuelops_sim_tick", "Last simulator tick processed")
DEGRADED = Gauge("fuelops_degraded", "1 while running on cached state")
BREAKER_OPEN = Gauge("fuelops_circuit_open", "1 while the simulator circuit breaker is open")

# intelligence / decisions
DECISION_CYCLES = Counter("fuelops_decision_cycles_total", "Decision cycles run")
DECISIONS = Counter("fuelops_decisions_total", "Recommendation decisions", ["status"])
FALLBACKS = Counter("fuelops_fallback_activations_total", "Fallback policy activations", ["reason"])
ALERTS = Counter("fuelops_alerts_raised_total", "New alerts raised", ["kind"])
ACTIVE_ALERTS = Gauge("fuelops_active_alerts", "Alerts currently active")
OPEN_RECOMMENDATIONS = Gauge("fuelops_open_recommendations", "Recommendations awaiting action")
PREDICTION_MAPE = Gauge("fuelops_prediction_mape", "Mean absolute % error of demand projection vs observed")
MEAN_CONFIDENCE = Gauge("fuelops_recommendation_confidence", "Mean confidence of current recommendations")
SOLVE_SECONDS = Histogram("fuelops_solve_seconds", "Optimizer solve time", buckets=(0.05, 0.1, 0.25, 0.5, 1, 2))
SHIPPED_LITERS = Counter("fuelops_shipped_liters_total", "Liters accepted by the simulator")
