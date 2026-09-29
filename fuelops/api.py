"""Application API (plan §14) for the dashboard. Application-owned /api/* endpoints, never simulator paths.

Run: uvicorn fuelops.api:app --port 8100
Env: FUELOPS_POLICY (default threshold), FUELOPS_MODE (default observe — plan §18 start mode).
"""
import os
import pathlib
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .controller import MODES, Controller
from .policies import POLICIES
from .projection import nominal
from .sim import FUELS, SimError

ctl: Controller | None = None
WEB = pathlib.Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(_app):
    global ctl
    ctl = Controller(policy=os.environ.get("FUELOPS_POLICY", "threshold"),
                     mode=os.environ.get("FUELOPS_MODE", "observe"))
    ctl.start()  # the one operational writer (plan §6.1)
    yield
    ctl.stop()


app = FastAPI(title="Fuel Operations", lifespan=lifespan)


def _snap():
    if ctl.snap is None:
        raise HTTPException(503, "No simulator snapshot yet")
    return ctl.snap


@app.get("/api/status")
def status():
    s = ctl.snap
    return {
        "run_id": ctl.run_id, "mode": ctl.mode, "policy": ctl.policy_name, "policies": list(POLICIES),
        "degraded": ctl.degraded, "tick": s["tick"] if s else None, "sim_status": s["status"] if s else None,
        "tick_minutes": s["tick_minutes"] if s else None,
        "snapshot_age_s": round(time.time() - ctl.snap_wall, 2) if ctl.snap_wall else None,
        "cycles": ctl.cycles, "exec_delay": getattr(ctl.policy, "exec_delay", None),
    }


@app.get("/api/overview")
def overview():
    s = _snap()
    try:
        metrics = ctl.sim.metrics()
    except (SimError, httpx.TransportError):
        metrics = None  # shown as unavailable, never invented
    region = {r["id"]: r["demand_factor"] for r in s["regions"]}
    tm, tick = s["tick_minutes"], s["tick"]
    stations, risks, day_demand = [], [], 0.0
    for st in s["stations"].values():
        fuels = []
        for f in FUELS:
            per_day = sum(nominal(st, f, t, region[st["region_id"]], tm) for t in range(tick, tick + 1440 // tm))
            day_demand += per_day
            incoming = sum(q for _, q in s["incoming"].get((st["id"], f), ()))
            cover_h = st["inventory"][f] / per_day * 24 if per_day else None
            fuels.append({"fuel": f, "inventory": st["inventory"][f], "capacity": st["capacity"][f],
                          "incoming": incoming, "demand_per_day": per_day, "cover_hours": cover_h})
            if cover_h is not None:
                risks.append({"station": st["name"], "station_id": st["id"], "fuel": f, "cover_hours": cover_h,
                              "incoming": incoming})
        stations.append({"id": st["id"], "name": st["name"], "status": st["status"], "region_id": st["region_id"],
                         "demand_multiplier": st["demand_multiplier"], "fuels": fuels})
    depots = [{"id": d["id"], "name": d["name"], "status": d["status"],
               "dispatch_capacity_per_tick": d["dispatch_capacity_per_tick"],
               "fuels": [{"fuel": f, "inventory": d["inventory"][f], "capacity": d["capacity"][f]} for f in FUELS]}
              for d in s["depots"].values()]
    in_world = sum(sum(d["inventory"].values()) for d in s["depots"].values()) + \
        sum(sum(x["inventory"].values()) for x in s["stations"].values()) + \
        sum(a["quantity"] for a in s["allocs"] if a["status"] in ("PENDING", "IN_TRANSIT"))
    future_supply = sum(r["quantity"] for r in s["supply"] if r["status"] != "ARRIVED")
    return {
        "tick": tick, "metrics": metrics, "stations": stations, "depots": depots,
        "routes": list(s["routes"].values()),
        "events": [e for e in s["events"] if e["status"] != "RESOLVED"],
        "risks": sorted(risks, key=lambda r: r["cover_hours"])[:8],
        "supply": {"fuel_in_world": in_world, "future_supply": future_supply, "demand_per_day": day_demand,
                   "days_of_fuel": (in_world + future_supply) / day_demand if day_demand else None,
                   "last_supply_tick": max((r["planned_tick"] for r in s["supply"]), default=None)},
    }


@app.get("/api/allocations")
def allocations(status: str | None = None, station: str | None = None, fuel: str | None = None):
    rows = _snap()["allocs"]
    return [a for a in rows if (not status or a["status"] == status)
            and (not station or a["destination_station_id"] == station) and (not fuel or a["fuel_type"] == fuel)]


@app.get("/api/plans")
def plans():
    s = _snap()
    return {
        "tick": s["tick"], "policy": ctl.policy_name, "mode": ctl.mode,
        "proposals": [{"route_id": r, "fuel": f, "liters": q,
                       "source": s["routes"][r]["source_depot_id"], "destination": s["routes"][r]["destination_station_id"]}
                      for r, f, q in ctl.proposals],
        "solves": (getattr(ctl.policy, "log", None) or [])[-20:],
        "exec_delay": getattr(ctl.policy, "exec_delay", None),
        "executor": ctl.executor.stats,
    }


@app.post("/api/plans/execute")
def execute_plan():
    if ctl.mode != "manual":
        raise HTTPException(409, f"Plan approval is only for manual mode (current: {ctl.mode})")
    try:
        return {"submitted_actions": ctl.execute_proposals()}
    except (SimError, httpx.TransportError) as e:
        raise HTTPException(503, f"Simulator unavailable: {e}") from e


@app.post("/api/allocations/{allocation_id}/cancel")
def cancel(allocation_id: int):
    with ctl.lock:
        try:
            return ctl.sim.cancel(allocation_id)
        except SimError as e:
            raise HTTPException(e.status if e.status < 500 else 503, f"{e.code}: {e.message}") from e


class ModeIn(BaseModel):
    mode: str


class PolicyIn(BaseModel):
    policy: str


@app.put("/api/operating-mode")
def set_mode(body: ModeIn):
    if body.mode not in MODES:
        raise HTTPException(422, f"mode must be one of {MODES}")
    with ctl.lock:
        ctl.mode = body.mode
        ctl._incident("mode", f"mode → {body.mode}")
    return status()


@app.put("/api/policy")
def set_policy(body: PolicyIn):
    if body.policy not in POLICIES:
        raise HTTPException(422, f"policy must be one of {list(POLICIES)}")
    with ctl.lock:
        ctl.set_policy(body.policy)
    return status()


@app.get("/api/incidents")
def incidents():
    return list(reversed(ctl.incidents))


if WEB.exists():  # built dashboard (web/dist)
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        return FileResponse(WEB / "index.html")
