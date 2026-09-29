"""Regression benchmark: every policy × every crisis recipe, stepped (plan §16).

Each simulator runs one job at a time (the harness resets it), so several simulators run in parallel.
Start extra ones with `docker compose --profile bench up -d` (sim-b, sim-c, sim-d).

Usage: python -m fuelops.bench lp-buffer threshold [--ticks 480] [--announced]
           [--sims http://simulator-api:8000,http://sim-b:8000] [--recipes s05_tongi_isolated,...]
           [--max-total 23783]
Exit code 1 when the first policy's total unmet exceeds --max-total (use as a gate after model changes).
"""
import argparse
import json
import multiprocessing as mp
import time

from .harness import REPORTS
from .scenarios import RECIPES


def _worker(url, jobs, out):
    from .harness import run
    from .sim import Sim
    sim = Sim(base_url=url)
    for policy, recipe, ticks, announced in jobs:
        try:
            r = run(policy, ticks, sim=sim, recipe=recipe, announced=announced)
            out.put((policy, recipe, r["metrics"]["unmet_demand_liters"], r["fuel_lost_liters"],
                     r["failed_allocations"], r["run_id"]))
        except Exception as e:  # noqa: BLE001 — report and continue with the other jobs
            out.put((policy, recipe, None, None, None, repr(e)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policies", nargs="+")
    ap.add_argument("--ticks", type=int, default=480)
    ap.add_argument("--announced", action="store_true")
    ap.add_argument("--sims", default="http://localhost:18000")
    ap.add_argument("--recipes", default=",".join(RECIPES))
    ap.add_argument("--max-total", type=float)
    a = ap.parse_args()
    sims, recipes = a.sims.split(","), a.recipes.split(",")
    jobs = [(p, r, a.ticks, a.announced) for p in a.policies for r in recipes]
    out, t0 = mp.Queue(), time.perf_counter()
    procs = [mp.Process(target=_worker, args=(url, jobs[i::len(sims)], out)) for i, url in enumerate(sims)]
    for p in procs:
        p.start()
    res = {}
    for _ in jobs:
        policy, recipe, *rest = out.get()
        res[policy, recipe] = rest
    for p in procs:
        p.join()

    width = max(len(r) for r in recipes)
    print(f"{'recipe':{width}s}" + "".join(f"{p:>14s}" for p in a.policies))
    totals = {p: 0.0 for p in a.policies}
    for r in recipes:
        cells = []
        for p in a.policies:
            unmet, lost, failed, run_id = res[p, r]
            if unmet is None:
                cells.append(f"{'ERROR':>14s}")
                totals[p] = float("inf")
                print(f"  {p} {r}: {run_id}")
                continue
            totals[p] += unmet
            flag = "*" if (lost or 0) > 1 or failed else " "
            cells.append(f"{unmet:>13,.0f}{flag}")
        print(f"{r:{width}s}" + "".join(cells))
    print(f"{'TOTAL':{width}s}" + "".join(f"{totals[p]:>14,.0f}" for p in a.policies))
    print(f"* = fuel lost > 1 L or FAILED allocations. {a.ticks} ticks, "
          f"{'announced' if a.announced else 'surprise'} events, {time.perf_counter() - t0:.0f} s wall")

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"bench_{int(time.time())}.json").write_text(json.dumps(
        {"ticks": a.ticks, "announced": a.announced, "totals": totals,
         "cells": {f"{p}|{r}": v for (p, r), v in res.items()}}, indent=1))
    if a.max_total is not None and round(totals[a.policies[0]]) > a.max_total:
        print(f"FAIL: {a.policies[0]} total {totals[a.policies[0]]:,.0f} L > {a.max_total:,.0f} L")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
