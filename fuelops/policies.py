"""Decision policies. Each takes a snapshot and returns [(route_id, fuel, liters)].

The executor clips every want to depot stock, dispatch budget, and reserved headroom.
"""
from .execute import incoming_total
from .sim import FUELS


def no_replenishment(snap):
    return []


def threshold(snap, reorder=0.30, target=0.70):
    """Plan Â§9.9 baseline: reorder at 30% of capacity, fill to 70%, counting in-transit.

    Most urgent station/fuel first; fastest available route, ties by route id.
    """
    wants = []
    for sid, st in snap["stations"].items():
        for f in FUELS:
            cap = st["capacity"][f]
            position = st["inventory"][f] + incoming_total(snap, sid, f)
            if position < reorder * cap:
                wants.append((position / cap, sid, f, target * cap - position))
    out = []
    for _, sid, f, need in sorted(wants):
        routes = sorted((r["transit_ticks"], r["id"]) for r in snap["routes"].values()
                        if r["destination_station_id"] == sid and r["status"] == "AVAILABLE"
                        and snap["depots"][r["source_depot_id"]]["inventory"][f] > 0)
        # ponytail: whole need on the fastest route; the executor clips, leftover retried next tick
        if routes:
            out.append((routes[0][1], f, need))
    return out


POLICIES = {"none": no_replenishment, "threshold": threshold}


class LPPolicy:
    """Receding-horizon LP (plan §9.1): re-solve every `replan` ticks.

    batch=True (execution glue, not a model change): at each solve, send the whole next `replan`
    ticks of planned flow per route/fuel at once, with the executor reserving headroom for
    in-transit stock. Cuts requests ~50x; batch=False executes the plan tick by tick.
    """

    def __init__(self, horizon=96, replan=8, stress=1.0, batch=True, buffer_ticks=0, window=None):
        self.horizon, self.replan, self.stress, self.batch = horizon, replan, stress, batch
        self.buffer_ticks = buffer_ticks
        self.window = window or replan  # ticks of planned flow sent per batch
        self.reserve_incoming = batch  # unbatched: LP models arrival clipping itself
        self.plan, self.solved_at, self.log = None, None, []
        self.exec_delay = 0  # ticks between snapshot and submission; the live controller measures it

    def __call__(self, snap):
        from .lp import solve  # scipy import only when used
        v = snap["tick"]
        if self.plan is None or v - self.solved_at >= self.replan:
            try:
                res = solve(snap, self.horizon, stress=self.stress, earliest=self.exec_delay,
                            buffer_ticks=self.buffer_ticks)
            except Exception as e:  # noqa: BLE001 — any solver failure → rule-based fallback (PS §11)
                res = {"status": -1, "seconds": 0.0, "unmet": None, "message": repr(e)}
            self.log.append({"tick": v, "status": res["status"], "seconds": round(res["seconds"], 3),
                             "unmet_forecast": res["unmet"]})
            if res["status"] != 0:
                self.plan = None
                return threshold(snap)  # plan §9.9 fallback; labeled in the solve log
            self.plan, self.solved_at = res["x"], v
            if self.batch:
                total = {}
                for (r, f, k), q in self.plan.items():
                    if k < self.exec_delay + self.window:
                        total[r, f] = total.get((r, f), 0.0) + q
                return [(r, f, q) for (r, f), q in sorted(total.items())]
        if self.batch:
            return []
        k = v - self.solved_at
        return [(r, f, q) for (r, f, kk), q in sorted(self.plan.items()) if kk == k]


POLICIES["lp"] = LPPolicy
POLICIES["lp-tick"] = lambda: LPPolicy(batch=False)
# D4: hand-set 4 h safety buffer; sends 12 h of planned flow per batch (operator-sized recommendations)
POLICIES["lp-buffer"] = lambda: LPPolicy(buffer_ticks=16, window=48)
