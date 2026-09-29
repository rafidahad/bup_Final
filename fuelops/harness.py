"""Stepped benchmark harness (plan §16.1). Owns the simulator: reset → pause → decide → step.

Usage: python -m fuelops.harness threshold none --ticks 672
"""
import argparse
import json
import pathlib
import time
import uuid

from .execute import Executor, snapshot
from .policies import POLICIES
from .sim import Sim

REPORTS = pathlib.Path(__file__).resolve().parent.parent / "reports"


def world_stock(snap):
    depots = sum(sum(d["inventory"].values()) for d in snap["depots"].values())
    stations = sum(sum(s["inventory"].values()) for s in snap["stations"].values())
    transit = sum(a["quantity"] for a in snap["allocs"] if a["status"] in ("PENDING", "IN_TRANSIT"))
    return depots + stations + transit


def run(policy_name, ticks, sim=None):
    sim = sim or Sim()
    policy = POLICIES[policy_name]
    if isinstance(policy, type) or getattr(policy, "__name__", "") == "<lambda>":
        policy = policy()
    run_id = uuid.uuid4().hex[:8]
    REPORTS.mkdir(exist_ok=True)
    sim.reset()
    sim.pause()
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

    end = snapshot(sim)
    m = sim.metrics()
    supplied = sum(r["quantity"] for r in sim.supply() if r["status"] == "ARRIVED")
    # conservation: whatever entered the world and was neither served nor still held was lost to overflow
    lost = start_stock + supplied - m["served_demand_liters"] - world_stock(end)
    report = {
        "run_id": run_id, "policy": policy_name, "ticks": ticks, "sim_days": ticks / 96,
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
    a = ap.parse_args()
    for p in a.policies:
        r = run(p, a.ticks)
        m = r["metrics"]
        print(f"{p:10s} {r['sim_days']:.1f}d  service={m['service_level']:.4f}  unmet={m['unmet_demand_liters']:,.0f} L  "
              f"shipped={m['allocation_liters']:,.0f} L  lost={r['fuel_lost_liters']:,.0f} L  "
              f"rejected={r['executor']['rejected']}  wall={r['wall_seconds']}s  run={r['run_id']}")
        if r["solves"]:
            secs = sorted(x["seconds"] for x in r["solves"])
            bad = sum(x["status"] != 0 for x in r["solves"])
            print(f"           solves={len(secs)} p50={secs[len(secs)//2]}s max={secs[-1]}s non-optimal={bad}")


if __name__ == "__main__":
    main()
