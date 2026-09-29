"""Live fault tests at normal speed (plan §16.4, F01–F05). Wall-clock based, so NOT byte-identical:
repeat and compare ranges, never single numbers.

Usage: python -m fuelops.livetest none latency unavailable error_rate stale_data stream_disconnect
       [--ticks 400] [--policy lp] [--fault-at 10] [--fault-secs 15]
"""
import argparse
import json
import time

from .controller import Controller
from .harness import REPORTS
from .sim import Sim

PARAMS = {"latency": {"delay_ms": 500}, "error_rate": {"rate": 0.25}}


def live_run(fault, ticks, policy, fault_at, fault_secs):
    sim = Sim()
    sim.reset()
    sim.pause()
    ctl = Controller(sim, policy=policy, mode="auto")
    ctl.cycle()  # decide on tick 0 before the clock starts
    ctl.start()
    sim.run()
    t0, injected = time.perf_counter(), False
    while True:
        tick = sim.health()["simulation"]["tick"]  # /v1/health bypasses faults
        if fault != "none" and not injected and time.perf_counter() - t0 >= fault_at:
            sim.inject_fault({"type": fault, "duration_seconds": fault_secs, "parameters": PARAMS.get(fault, {})})
            injected, fault_tick = True, tick
        if tick >= ticks:
            break
        time.sleep(0.05)
    sim.pause()
    ctl.stop()
    sim.clear_faults()
    m = sim.metrics()
    failed = sum(a["status"] == "FAILED" for a in sim.allocations())
    return {"fault": fault, "policy": policy, "end_tick": sim.instance()["tick"], "metrics": m,
            "fault_tick": fault_tick if injected else None, "fault_secs": fault_secs if injected else 0,
            "wall_seconds": round(time.perf_counter() - t0, 1), "cycles": ctl.cycles, "failed": failed,
            "executor": ctl.executor.stats, "incidents": list(ctl.incidents)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("faults", nargs="+",
                    choices=["none", "latency", "unavailable", "error_rate", "stale_data", "stream_disconnect"])
    ap.add_argument("--ticks", type=int, default=400)
    ap.add_argument("--policy", default="lp")
    ap.add_argument("--fault-at", type=float, default=10)
    ap.add_argument("--fault-secs", type=int, default=15)
    a = ap.parse_args()
    REPORTS.mkdir(exist_ok=True)
    for f in a.faults:
        r = live_run(f, a.ticks, a.policy, a.fault_at, a.fault_secs)
        (REPORTS / f"live_{f}_{int(time.time())}.json").write_text(json.dumps(r, indent=1))
        m = r["metrics"]
        kinds = {}
        for i in r["incidents"]:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        print(f"{f:17s} end_tick={r['end_tick']} service={m['service_level']:.4f} unmet={m['unmet_demand_liters']:,.0f} L "
              f"failed={r['failed']} cycles={r['cycles']} posts={r['executor']['sent']} "
              f"rejected={r['executor']['rejected']} incidents={kinds} wall={r['wall_seconds']}s")


if __name__ == "__main__":
    main()
