"""Application API (plan §14, Revision 4) for the operator web app. Application-owned /api/* only.

Run: uvicorn fuelops.api:app --port 8100
Env: SIM_URL, FUELOPS_POLICY (lp-buffer), FUELOPS_MODE (auto; low-confidence recommendations still wait for review, PS §24),
     FUELOPS_OPERATOR_TOKEN (when set, required as X-Operator-Token for sensitive actions, PS §18),
     FUELOPS_AUTOSTART (1 = start the controller thread; tests set 0).
"""
import json
import os
import pathlib
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import metrics as M
from . import store
from .controller import MODES, Controller, PlanChanged
from .policies import POLICIES
from .intel import project
from .projection import nominal
from .sim import FUELS, SimError

ctl: Controller | None = None
WEB = pathlib.Path(os.environ.get("FUELOPS_WEB", pathlib.Path(__file__).resolve().parent.parent / "web" / "dist"))
TOKEN = os.environ.get("FUELOPS_OPERATOR_TOKEN")
RECENT = deque(maxlen=2000)  # (latency seconds, is_error) for p95 / error rate on the health view


@asynccontextmanager
async def lifespan(_app):
    global ctl
    ctl = Controller(policy=os.environ.get("FUELOPS_POLICY", "lp-buffer"),
                     mode=os.environ.get("FUELOPS_MODE", "auto"))
    if os.environ.get("FUELOPS_AUTOSTART", "1") == "1":
        ctl.start()  # the one operational writer (plan §6.1)
    yield
    if ctl.alive():
        ctl.stop()


app = FastAPI(title="Fuel Operations", lifespan=lifespan)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        dt = time.perf_counter() - t0
        route = request.scope.get("route")
        path = getattr(route, "path", "other")
        if path.startswith("/api") or path == "/metrics":
            M.HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
            M.HTTP_LATENCY.labels(path).observe(dt)
            if path.startswith("/api"):
                RECENT.append((dt, status >= 500))


def operator(x_operator_token: str | None = Header(default=None)):
    """Sensitive actions (lab, mode, policy, intelligence switch) need the operator token when one is set."""
    if TOKEN and x_operator_token != TOKEN:
        raise HTTPException(401, "Operator token required for this action")


def _snap():
    if ctl.snap is None:
        raise HTTPException(503, "Waiting for the first simulator snapshot")
    return ctl.snap


_cache: dict = {}
_cache_lock = threading.Lock()


def _per_tick(name, build):
    """Serve read models from JSON serialized once per simulator tick (and per decision change).

    Load test run 1 showed per-request recomputation and encoding capped the backend at ~120 req/s
    with p95 ~2.7 s; the underlying data only changes when the controller processes a tick."""
    key = (ctl.run_id, ctl.last_tick, ctl.cycles, len(ctl.cards))
    with _cache_lock:
        hit = _cache.get(name)
        if hit and hit[0] == key:
            return Response(hit[1], media_type="application/json")
    body = json.dumps(build(), default=float).encode()
    with _cache_lock:
        _cache[name] = (key, body)
    return Response(body, media_type="application/json")


# ---- read models ----------------------------------------------------------------------------------
@app.get("/api/status")
def status():
    s = ctl.snap
    return {
        "run_id": ctl.run_id, "mode": ctl.mode, "policy": ctl.policy_name, "policies": list(POLICIES),
        "source": ctl.source, "intelligence_enabled": ctl.intel_enabled, "degraded": ctl.degraded,
        "tick": s["tick"] if s else None, "sim_status": s["status"] if s else None,
        "tick_minutes": s["tick_minutes"] if s else None,
        "snapshot_age_s": round(time.time() - ctl.snap_wall, 2) if ctl.snap_wall else None,
        "cycles": ctl.cycles, "exec_delay": getattr(ctl.policy, "exec_delay", None),
        "token_required": bool(TOKEN),
    }


@app.get("/api/overview")
def overview():
    _snap()
    return _per_tick("overview", _overview)


def _overview():
    s = ctl.snap
    metrics = ctl.sim_metrics  # cached by the controller; None = unavailable, never invented
    region = {r["id"]: r for r in s["regions"]}
    tm, tick = s["tick_minutes"], s["tick"]
    per_day = 1440 // tm
    stations, regional = [], {rid: {"id": rid, "name": r["name"], "demand_per_day": 0.0, "demand_factor": r["demand_factor"]}
                              for rid, r in region.items()}
    for st in s["stations"].values():
        fuels = []
        for f in FUELS:
            d = sum(nominal(st, f, t, region[st["region_id"]]["demand_factor"], tm) for t in range(tick, tick + per_day))
            regional[st["region_id"]]["demand_per_day"] += d
            arrivals = s["incoming"].get((st["id"], f), ())
            sigma = ctl.noise.stats()[0].get(st["demand_profile"], (0.1, 0))[0]
            proj = project(s, st["id"], f, 48, sigma=sigma)  # same 12 h projection the recommendations use
            fuels.append({"fuel": f, "inventory": st["inventory"][f], "capacity": st["capacity"][f],
                          "incoming": sum(q for _, q in arrivals), "demand_per_day": d,
                          "next_arrival_tick": min((eta for eta, _ in arrivals), default=None),
                          "stockout_hours": proj["stockout_hours"], "risk": proj["risk"]})
        stations.append({"id": st["id"], "name": st["name"], "status": st["status"], "region_id": st["region_id"],
                         "demand_profile": st["demand_profile"], "demand_multiplier": st["demand_multiplier"], "fuels": fuels})
    depots = [{"id": d["id"], "name": d["name"], "status": d["status"], "region_id": d["region_id"],
               "dispatch_capacity_per_tick": d["dispatch_capacity_per_tick"],
               "fuels": [{"fuel": f, "inventory": d["inventory"][f], "capacity": d["capacity"][f]} for f in FUELS]}
              for d in s["depots"].values()]
    in_world = sum(sum(d["inventory"].values()) for d in s["depots"].values()) + \
        sum(sum(x["inventory"].values()) for x in s["stations"].values()) + \
        sum(a["quantity"] for a in s["allocs"] if a["status"] in ("PENDING", "IN_TRANSIT"))
    upcoming = [r for r in s["supply"] if r["status"] != "ARRIVED"]
    total_day = sum(r["demand_per_day"] for r in regional.values())
    return {
        "tick": tick, "tick_minutes": tm, "metrics": metrics, "stations": stations, "depots": depots,
        "regions": list(regional.values()), "routes": list(s["routes"].values()),
        "events": [e for e in s["events"] if e["status"] != "RESOLVED"],
        "incoming_supply": upcoming[:12],
        "supply": {"fuel_in_world": in_world, "future_supply": sum(r["quantity"] for r in upcoming),
                   "demand_per_day": total_day,
                   "days_of_fuel": (in_world + sum(r["quantity"] for r in upcoming)) / total_day if total_day else None,
                   "last_supply_tick": max((r["planned_tick"] for r in s["supply"]), default=None)},
    }


@app.get("/api/recommendations")
def recommendations():
    return _per_tick("recommendations", _recommendations)


def _recommendations():
    cards = sorted(ctl.cards.values(), key=lambda c: (-(c["before"]["risk"]), c["before"]["stockout_hours"] or 1e9))
    return {"tick": ctl.snap["tick"] if ctl.snap else None, "mode": ctl.mode, "source": ctl.source, "cards": cards}


@app.get("/api/alerts")
def alerts():
    return {"tick": ctl.snap["tick"] if ctl.snap else None, "alerts": ctl.alerts}


@app.get("/api/allocations")
def allocations(status: str | None = None, station: str | None = None, fuel: str | None = None, limit: int = 200):
    """Newest first (simulator order), capped: the ledger grows all run long."""
    rows = _snap()["allocs"]
    limit = min(max(limit, 1), 1000)
    if not (status or station or fuel) and limit == 200:
        return _per_tick("allocations", lambda: rows[:200])
    return [a for a in rows if (not status or a["status"] == status)
            and (not station or a["destination_station_id"] == station) and (not fuel or a["fuel_type"] == fuel)][:limit]


@app.get("/api/decisions")
def decisions(limit: int = 200):
    return store.decisions(min(max(limit, 1), 1000))


@app.get("/api/incidents")
def incidents():
    return list(reversed(ctl.incidents))


@app.get("/api/forecasts")
def forecasts():
    """Observed demand, the formula, and the Chronos forecast band per station/fuel (next 12 h)."""
    s = _snap()
    fc = ctl.forecast
    region = {r["id"]: r["demand_factor"] for r in s["regions"]}
    tick, tm = s["tick"], s["tick_minutes"]
    b = fc.bundle
    obs = {}
    for sid, f, t, d in ctl.noise.rows.values():
        if t >= tick - 48:
            obs.setdefault((sid, f), []).append((t, d))
    series = []
    for sid, st in s["stations"].items():
        for f in FUELS:
            ahead = list(range(tick, tick + 48))
            item = {"station_id": sid, "fuel": f,
                    "observed": [{"tick": t, "liters": d} for t, d in sorted(obs.get((sid, f), []))],
                    "formula": [{"tick": t, "liters": nominal(st, f, t, region[st["region_id"]], tm)} for t in ahead],
                    "chronos": None}
            if b and (sid, f) in b["q50"]:
                pts = [{"tick": t, "q10": b["q10"][(sid, f)][t - b["start"]], "q50": b["q50"][(sid, f)][t - b["start"]],
                        "q90": b["q90"][(sid, f)][t - b["start"]]} for t in ahead if 0 <= t - b["start"] < b["horizon"]]
                item["chronos"] = pts
            series.append(item)
    return {"tick": tick, "tick_minutes": tm, "status": fc.status, "evaluation": fc.evaluation(),
            "bundle": {k: b[k] for k in ("cutoff", "issued_view_tick", "model", "revision", "service_ms")} if b else None,
            "planner_uses": "formula", "series": series}


@app.get("/api/cases")
def cases():
    """Incident cases with their latest summary (AI or template)."""
    return {"ai_enabled": ctl.summaries.enabled(), "worker": ctl.summaries.status, "cases": store.latest_summaries(30)}


@app.get("/api/plans")
def plans():
    return {"policy": ctl.policy_name, "source": ctl.source, "solves": (getattr(ctl.policy, "log", None) or [])[-20:],
            "exec_delay": getattr(ctl.policy, "exec_delay", None), "executor": ctl.executor.stats,
            "prediction_mape": ctl.mape}


_health_cache = {"at": 0.0, "value": None}


def _sim_health():
    """Simulator liveness, cached 1 s so health polling and load tests do not load the simulator."""
    if time.time() - _health_cache["at"] > 1.0:
        _health_cache["value"], _health_cache["at"] = None, time.time()
        _health_cache["value"] = ctl.sim.health()
    if _health_cache["value"] is None:
        raise httpx.TransportError("simulator health unavailable")
    return _health_cache["value"]


@app.get("/api/health")
def health():
    """Component health for operators and judges (PS §15)."""
    comps = {"backend_api": {"status": "healthy"}}
    comps["database"] = {"status": "healthy" if store.healthy() else "down"}
    try:
        h = _sim_health()
        sim_status = "degraded" if ctl.degraded else "healthy"
        comps["simulator"] = {"status": sim_status, "tick": h["simulation"]["tick"], "state": h["simulation"]["status"],
                              "detail": ctl.degraded}
    except (SimError, httpx.TransportError) as e:
        comps["simulator"] = {"status": "down", "detail": str(e)[:160]}
    fs = ctl.forecast.status
    comps["forecaster"] = {"status": "healthy" if fs["state"] == "ok" else "degraded" if fs["state"] in ("loading", "waiting", "starting") else "down",
                           "detail": fs["detail"], "latency_ms": fs["latency_ms"]} if ctl.forecast.enabled else \
        {"status": "healthy", "detail": "switched off in settings"}
    ws = ctl.summaries.status
    comps["ai_summaries"] = {"status": "healthy" if ctl.summaries.enabled() and ws["state"] != "failing" else "degraded",
                             "detail": None if ctl.summaries.enabled() and ws["state"] != "failing" else
                             (ws["detail"] or "no Groq API key; rule-based summaries in use")}
    if not ctl.intel_enabled:
        comps["prediction_service"] = {"status": "down", "detail": "disabled by operator; threshold fallback active"}
    else:
        comps["prediction_service"] = {"status": "healthy", "prediction_mape": ctl.mape,
                                       "history_rows": len(ctl.noise.rows)}
    age = time.time() - ctl.snap_wall if ctl.snap_wall else None
    solves = getattr(ctl.policy, "log", None) or []
    paused = comps["simulator"].get("state") == "PAUSED"  # a paused clock means idle, not stuck
    engine_ok = ctl.alive() and age is not None and (age < 10 or paused)
    comps["decision_engine"] = {"status": "healthy" if engine_ok and "fallback" not in ctl.source else
                                ("degraded" if ctl.alive() else "down"),
                                "source": ctl.source, "last_cycle_age_s": round(age, 2) if age else None,
                                "last_solve": solves[-1] if solves else None}
    lat = sorted(x[0] for x in RECENT)
    p95 = lat[int(0.95 * (len(lat) - 1))] * 1000 if lat else None
    err = sum(x[1] for x in RECENT) / len(RECENT) if RECENT else 0.0
    overall = "healthy" if all(c["status"] == "healthy" for c in comps.values()) else \
        ("down" if comps["backend_api"]["status"] != "healthy" else "degraded")
    return {"status": overall, "components": comps, "p95_latency_ms": round(p95, 1) if p95 else None,
            "error_rate": round(err, 4), "window_requests": len(RECENT)}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---- operator actions -----------------------------------------------------------------------------
class SeenAllocation(BaseModel):
    route_id: str = Field(min_length=1, max_length=64)
    liters: float = Field(gt=0, le=100000)


class ApproveIn(BaseModel):
    allocations: list[SeenAllocation] = Field(min_length=1, max_length=12)


@app.post("/api/recommendations/{card_id}/approve", dependencies=[Depends(operator)])
def approve(card_id: str, body: ApproveIn):
    try:
        sent = ctl.approve(card_id, [a.model_dump() for a in body.allocations])
    except PlanChanged as e:
        raise HTTPException(409, str(e)) from e
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e
    except KeyError:
        raise HTTPException(404, "Recommendation no longer open; refresh to see current ones") from None
    except (SimError, httpx.TransportError) as e:
        raise HTTPException(503, f"Simulator unavailable, nothing sent: {e}") from e
    return {"liters_accepted": sent}


@app.post("/api/recommendations/{card_id}/reject", dependencies=[Depends(operator)])
def reject(card_id: str):
    try:
        ctl.reject(card_id)
    except KeyError:
        raise HTTPException(404, "Recommendation no longer open") from None
    return {"rejected": card_id}


@app.post("/api/allocations/{allocation_id}/cancel", dependencies=[Depends(operator)])
def cancel(allocation_id: int):
    with ctl.lock:
        try:
            return ctl.sim.cancel(allocation_id)
        except SimError as e:
            raise HTTPException(e.status if e.status < 500 else 503, f"{e.code}: {e.message}") from e


class ModeIn(BaseModel):
    mode: Literal["observe", "manual", "auto"]


class PolicyIn(BaseModel):
    policy: str


class IntelIn(BaseModel):
    enabled: bool


@app.put("/api/operating-mode", dependencies=[Depends(operator)])
def set_mode(body: ModeIn):
    with ctl.lock:
        ctl.mode = body.mode
        ctl._incident("mode", f"mode → {body.mode}")
    return status()


@app.put("/api/policy", dependencies=[Depends(operator)])
def set_policy(body: PolicyIn):
    if body.policy not in POLICIES:
        raise HTTPException(422, f"policy must be one of {list(POLICIES)}")
    with ctl.lock:
        ctl.set_policy(body.policy)
    return status()


@app.put("/api/intelligence", dependencies=[Depends(operator)])
def set_intelligence(body: IntelIn):
    with ctl.lock:
        ctl.set_intelligence(body.enabled)
    return status()


# ---- lab: demo and self-test controls (admin endpoints; never used by the decision loop) -----------
class EventIn(BaseModel):
    type: Literal["demand_spike", "route_disruption", "station_outage", "depot_constraint",
                  "shipment_delay", "supply_shortfall"]
    start_tick: int | None = Field(default=None, ge=0)
    duration_ticks: int = Field(gt=0, le=2000)
    parameters: dict = Field(default_factory=dict)


class FaultIn(BaseModel):
    type: Literal["latency", "unavailable", "error_rate", "stale_data", "stream_disconnect"]
    duration_seconds: int = Field(gt=0, le=3600)
    parameters: dict = Field(default_factory=dict)


class ControlIn(BaseModel):
    action: Literal["run", "pause", "step", "reset"]


def _admin(fn, *args):
    try:
        return fn(*args)
    except SimError as e:
        raise HTTPException(e.status if e.status < 500 else 503, f"{e.code}: {e.message}") from e
    except httpx.TransportError as e:
        raise HTTPException(503, f"Simulator unreachable: {e}") from e


@app.post("/api/lab/events", dependencies=[Depends(operator)])
def lab_event(body: EventIn):
    ev = body.model_dump()
    if ev["start_tick"] is None:
        ev["start_tick"] = _admin(ctl.sim.health)["simulation"]["tick"]
    ctl._incident("lab", f"event injected: {ev['type']} {ev['parameters']} from tick {ev['start_tick']}")
    return _admin(ctl.sim.inject_event, ev)


@app.post("/api/lab/faults", dependencies=[Depends(operator)])
def lab_fault(body: FaultIn):
    ctl._incident("lab", f"fault injected: {body.type} for {body.duration_seconds}s")
    return _admin(ctl.sim.inject_fault, body.model_dump())


@app.post("/api/lab/faults/clear", dependencies=[Depends(operator)])
def lab_clear():
    ctl._incident("lab", "faults cleared")
    return _admin(ctl.sim.clear_faults)


@app.post("/api/lab/control", dependencies=[Depends(operator)])
def lab_control(body: ControlIn):
    if body.action != "step":  # single steps would flood the timeline
        ctl._incident("lab", f"simulator {body.action}")
    return _admin(getattr(ctl.sim, body.action))


# ---- web app --------------------------------------------------------------------------------------
if WEB.exists():  # built dashboard (web/dist)
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (WEB / path).resolve()
        inside = f.is_relative_to(WEB.resolve())  # no ../ escapes out of the build folder
        return FileResponse(f if path and inside and f.is_file() else WEB / "index.html")
