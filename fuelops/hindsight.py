"""Perfect-hindsight upper bound (plan §9.9). BENCHMARK ONLY — never used by a live policy.

Solves the LP once over the whole run with the demand actually recorded in a previous run
(valid only if demand is identical across policies — probe C19, checked here too).

Usage: python -m fuelops.hindsight [--ticks N ...] reports/<run>_<policy>_demand.json [other_run_demand.json ...]
"""
import json
import sys

from .execute import snapshot
from .lp import solve
from .sim import Sim


def load(path):
    return {(s, f, t): d for t, s, f, d, _served in json.load(open(path))}


def main(paths, horizons=None):
    runs = [load(p) for p in paths]
    base = runs[0]
    for p, other in zip(paths[1:], runs[1:]):  # C19
        common = base.keys() & other.keys()
        diff = max(abs(base[k] - other[k]) for k in common)
        print(f"C19 {p}: {len(common)} shared rows, max |demand diff| = {diff:.6f} L")

    sim = Sim()
    sim.reset()
    sim.pause()
    snap = snapshot(sim)  # tick 0 of the baked scenario
    for ticks in horizons or [max(t for _, _, t in base) + 1]:
        # flat weights: pure max-served; allowing withholding only relaxes the model, so it stays an upper bound
        r = solve(snap, horizon=ticks, demand=base, weights="flat", headroom_margin=0)
        served = r["served"]
        print(f"hindsight bound {ticks:4d} ticks ({ticks / 96:.1f}d): status={r['status']} demand={r['demand']:,.0f} L "
              f"served={served:,.0f} L unmet={r['unmet']:,.0f} L service={served / r['demand']:.4f} "
              f"solve={r['seconds']:.1f}s")


if __name__ == "__main__":
    args, horizons = sys.argv[1:], []
    while args and args[0] == "--ticks":
        horizons.append(int(args[1])); args = args[2:]
    main(args, horizons)
