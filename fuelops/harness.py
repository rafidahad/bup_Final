"""Stepped benchmark harness (plan §16.1). Owns the simulator: reset → pause → decide → step.

Usage: python -m fuelops.harness threshold lp --ticks 672 [--recipe s04_primary_route_down] [--announced]
"""
import argparse
import json
import pathlib
import time
import uuid

from .execute import Executor, snapshot
from .policies import POLICIES
from .scenarios import RECIPES
from .sim import Sim

REPORTS = pathlib.Path(__file__).resolve().parent.parent / "reports"


def world_stock(snap):
    depots = sum(sum(d["inventory"].values()) for d in snap["depots"].values())
    stations = sum(sum(s["inventory"].values()) for s in snap["stations"].values())
    transit = sum(a["quantity"] for a in snap["allocs"] if a["status"] in ("PENDING", "IN_TRANSIT"))
    return depots + stations + transit


def _event(e):
    typ, start, dur, params = e
    return {"type": typ, "start_tick": start, "duration_ticks": dur, "parameters": params}


def run(policy_name, ticks, sim=None, recipe="baseline", announced=False):
    sim = sim or Sim()
    policy = POLICIES[policy_name]
    if isinstance(policy, type) or getattr(policy, "__name__", "") == "<lambda>":
        policy = policy()
    run_id = uuid.uuid4().hex[:8]
    REPORTS.mkdir(exist_ok=True)
    sim.reset()
    sim.pause()
    pending_events = sorted(RECIPES[recipe], key=lambda e: e[1])
    if announced:  # visible in /v1/events as SCHEDULED from tick 0
        for e in pending_events:
            sim.inject_event(_event(e))
        pending_events = []
    ex = Executor(sim, run_id, REPORTS / f"{run_id}_{policy_name}_intents.jsonl",
                  reserve_incoming=getattr(policy, "reserve_incoming", True))
    start_stock = world_stock(snapshot(sim))
    curve, t0 = [], time.perf_counter()

    history = {}  # observation id -> row; a station's 2000-row window spans ~666 ticks
    station_ids = list(snapshot(sim)["stations"])

    def pull_history():
        for sid in station_ids:
            for h in sim.demand_history(sid, 2000):
                history[h["id"]] = h

    for _ in range(ticks):
        tick = sim.instance()["tick"]
        while pending_events and pending_events[0][1] <= tick:  # surprise: appears when it starts
            sim.inject_event(_event(pending_events.pop(0)))
        snap = snapshot(sim)
        ex.execute(snap, policy(snap))
        sim.step()
        if snap["tick"] % 8 == 0:
            m = sim.metrics()
            curve.append({"tick": snap["tick"], **m})
        if snap["tick"] % 300 == 299:
            pull_history()
    pull_history()
    demand = sorted((h["tick"], h["station_id"], h["fuel_type"], h["demand_liters"], h["served_liters"])
                    for h in history.values())
    (REPORTS / f"{run_id}_{policy_name}_demand.json").write_text(json.dumps(demand))
    failed = [a for a in sim.allocations() if a["status"] == "FAILED"]

    end = snapshot(sim)
    m = sim.metrics()
    supplied = sum(r["quantity"] for r in sim.supply() if r["status"] == "ARRIVED")
    # conservation: whatever entered the world and was neither served nor still held was lost to overflow
    lost = start_stock + supplied - m["served_demand_liters"] - world_stock(end)
    report = {
        "run_id": run_id, "policy": policy_name, "ticks": ticks, "sim_days": ticks / 96,
        "recipe": recipe, "announced": announced, "failed_allocations": len(failed),
        "instance": sim.instance(), "metrics": m, "fuel_lost_liters": round(lost, 1),
        "executor": ex.stats, "wall_seconds": round(time.perf_counter() - t0, 1), "curve": curve,
        "solves": getattr(policy, "log", None),
    }
    (REPORTS / f"{run_id}_{policy_name}.json").write_text(json.dumps(report, indent=1))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policies", nargs="+", choices=list(POLICIES))
    ap.add_argument("--ticks", type=int, default=672)
    ap.add_argument("--recipe", default="baseline", choices=list(RECIPES))
    ap.add_argument("--announced", action="store_true")
    a = ap.parse_args()
    for p in a.policies:
        r = run(p, a.ticks, recipe=a.recipe, announced=a.announced)
        m = r["metrics"]
        print(f"{p:10s} {a.recipe}{' (announced)' if a.announced else ''} {r['sim_days']:.1f}d  service={m['service_level']:.4f}  unmet={m['unmet_demand_liters']:,.0f} L  "
              f"shipped={m['allocation_liters']:,.0f} L  lost={r['fuel_lost_liters']:,.0f} L  "
              f"failed={r['failed_allocations']}  rejected={r['executor']['rejected']}  wall={r['wall_seconds']}s  run={r['run_id']}")
        if r["solves"]:
            secs = sorted(x["seconds"] for x in r["solves"])
            bad = sum(x["status"] != 0 for x in r["solves"])
            print(f"           solves={len(secs)} p50={secs[len(secs)//2]}s max={secs[-1]}s non-optimal={bad}")


if __name__ == "__main__":
    main()
