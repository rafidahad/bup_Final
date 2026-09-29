"""Time-indexed replenishment LP (plan §9). Plain LP, no binaries.

Timing follows the probes (devlog "Simulator semantics"), for offset k = tick v+k:
  POST at k deducts depot stock at once (C01), counts against that tick's dispatch budget (C04),
  arrives in tick k+transit (C02); inside a tick: arrivals, clip to capacity (lost), then demand (C03/C06).

Greedy service without binaries (plan §9.4): unmet at offset k weighs 1 + eps*(H-k), strictly
decreasing, and nothing rewards stock held at the horizon end.
"""
import math
import time

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from .projection import closed_ticks, multiplier_change, nominal, route_closed_ticks, supply_after_events
from .sim import FUELS


class _Vars:
    def __init__(self):
        self.n, self.lo, self.hi, self.cost = 0, [], [], []

    def add(self, lo=0.0, hi=None, cost=0.0):
        self.lo.append(lo); self.hi.append(hi); self.cost.append(cost)
        self.n += 1
        return self.n - 1


class _Rows:
    def __init__(self):
        self.r, self.c, self.v, self.b, self.n = [], [], [], [], 0

    def add(self, terms, rhs):
        for col, val in terms:
            self.r.append(self.n); self.c.append(col); self.v.append(val)
        self.b.append(rhs)
        self.n += 1

    def matrix(self, ncols):
        if not self.n:
            return None, None
        return coo_matrix((self.v, (self.r, self.c)), shape=(self.n, ncols)).tocsr(), np.array(self.b)


def solve(snap, horizon=96, demand=None, stress=1.0, weights="decreasing",
          c_over=1e-3, c_tx=1e-5, headroom_margin=100.0, earliest=0, buffer_ticks=0):
    """Returns dict(status, x={(route, fuel, k): liters}, served, unmet, demand, seconds).

    demand: optional {(station, fuel, tick): liters} overriding the formula (hindsight bound only).
    earliest: first offset at which a new shipment can really be submitted (measured execution lag;
    0 in stepped mode). Shipments before it are impossible, so they are fixed to zero (plan §9.5).
    buffer_ticks: hand-set safety stock (owner decision D4) = that many ticks of demand, as a soft target.
    Withholding a liter for m ticks earns m * c_buf of buffer credit but costs m * eps of unmet weight
    (the liter still serves later demand at a lower weight). c_buf = eps / 2 < eps keeps the greedy-service
    property (§9.4); c_buf still exceeds any transit cost, so buffers do get filled.
    """
    t0 = time.perf_counter()
    v, H = snap["tick"], horizon
    tm = snap.get("tick_minutes", 15)
    eps = 1.0 / (10 * H)
    c_buf = eps / 2
    region = {r["id"]: r["demand_factor"] for r in snap["regions"]}
    routes = [r for r in snap["routes"].values()]
    V, eq, ub = _Vars(), _Rows(), _Rows()

    # shipments
    x = {}
    for r in routes:
        road_closed = route_closed_ticks(snap, r["id"])  # public disruption windows (C08: departs in its POST tick)
        st_closed = closed_ticks(snap, r["destination_station_id"])  # the server rejects POSTs while closed
        for f in FUELS:
            for k in range(H):
                ok = not road_closed(v + k) and k >= earliest and not st_closed(v + k)
                x[r["id"], f, k] = V.add(hi=None if ok else 0.0, cost=c_tx * r["transit_ticks"])

    # depots
    created_now = {d: 0.0 for d in snap["depots"]}
    for a in snap["allocs"]:
        if a["created_tick"] == v and a["status"] != "CANCELLED":
            created_now[a["source_depot_id"]] += a["quantity"]
    supply = {}
    for s in supply_after_events(snap):
        if v <= s["planned_tick"] < v + H:
            key = (s["depot_id"], s["fuel_type"], s["planned_tick"] - v)
            supply[key] = supply.get(key, 0.0) + s["quantity"]
    for d, dep in snap["depots"].items():
        out = [r["id"] for r in routes if r["source_depot_id"] == d]
        for k in range(H):
            budget = dep["dispatch_capacity_per_tick"] - (created_now[d] if k == 0 else 0.0)
            ub.add([(x[r, f, k], 1.0) for r in out for f in FUELS], max(budget, 0.0))
        for f in FUELS:
            D = [V.add(lo=dep["inventory"][f], hi=dep["inventory"][f])]
            for k in range(H):
                over = V.add(cost=c_over)
                D.append(V.add(hi=dep["capacity"][f]))
                ship = [(x[r, f, k], 1.0) for r in out]
                ub.add(ship + [(D[k], -1.0)], 0.0)  # cannot ship more than is on hand
                # D[k+1] = D[k] - ship + supply - overflow
                eq.add([(D[k + 1], 1.0), (D[k], -1.0), (over, 1.0)] + ship, supply.get((d, f, k), 0.0))

    # stations
    served_cols, unmet_cols, total_demand = [], [], 0.0
    served_by_k = [[] for _ in range(H)]
    for sid, st in snap["stations"].items():
        into = [r for r in routes if r["destination_station_id"] == sid]
        for f in FUELS:
            existing = {}
            for eta, q in snap["incoming"].get((sid, f), ()):
                existing[eta - v] = existing.get(eta - v, 0.0) + q
            cap = st["capacity"][f]
            closed = closed_ticks(snap, sid)
            spike = multiplier_change(snap, st)
            I = [V.add(lo=st["inventory"][f], hi=st["inventory"][f])]
            for k in range(H):
                t = v + k
                if demand is not None:
                    q = demand.get((sid, f, t))
                    if q is None or not math.isfinite(q) or q < 0:  # a missing key must never mean 0 L demand
                        raise ValueError(f"demand override incomplete or invalid at {(sid, f, t)}: {q!r}")
                else:
                    q = nominal({**st, "status": "OPEN"}, f, t, region[st["region_id"]], tm, stress) * spike(t)
                total_demand += q
                w = 1.0 if weights == "flat" else 1.0 + eps * (H - k)
                # C09: during an outage nothing is sold (y = 0), the demand is unmet, stock stays frozen
                y, u, over = V.add(hi=0.0 if closed(t) else q), V.add(cost=w), V.add(cost=c_over)
                I.append(V.add(hi=cap))
                if buffer_ticks:
                    b = V.add(cost=c_buf)  # shortfall below the buffer after serving tick k
                    ub.add([(I[k + 1], -1.0), (b, -1.0)], -min(q * buffer_ticks, cap))
                arr = [(x[r["id"], f, k - r["transit_ticks"]], 1.0) for r in into if k - r["transit_ticks"] >= 0]
                pre = existing.get(k, 0.0)
                # after arrival (clipped): I[k] + arr + pre - over <= cap - margin
                ub.add([(I[k], 1.0), (over, -1.0)] + arr, cap - headroom_margin - pre)
                # serve only what is there: y <= I[k] + arr + pre - over
                ub.add([(y, 1.0), (I[k], -1.0), (over, 1.0)] + [(c, -1.0) for c, _ in arr], pre)
                eq.add([(y, 1.0), (u, 1.0)], q)
                # I[k+1] = I[k] + arr + pre - over - y
                eq.add([(I[k + 1], 1.0), (I[k], -1.0), (over, 1.0), (y, 1.0)] + [(c, -1.0) for c, _ in arr], pre)
                served_cols.append(y); unmet_cols.append(u); served_by_k[k].append(y)

    A_ub, b_ub = ub.matrix(V.n)
    A_eq, b_eq = eq.matrix(V.n)
    res = linprog(np.array(V.cost), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                  bounds=list(zip(V.lo, V.hi)), method="highs")
    out = {"status": res.status, "message": res.message, "seconds": time.perf_counter() - t0,
           "demand": total_demand, "x": {}, "served": None, "unmet": None}
    if res.status == 0:
        sol = res.x
        out["x"] = {key: sol[col] for key, col in x.items() if sol[col] > 0.5}
        out["served"] = float(sol[served_cols].sum())
        out["unmet"] = float(sol[unmet_cols].sum())
        out["objective"] = res.fun
        out["served_by_k"] = [float(sol[cols].sum()) for cols in served_by_k]
    return out
