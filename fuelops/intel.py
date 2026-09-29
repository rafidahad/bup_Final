"""Detect / Predict / Simulate for the operator (plan Revision 4, R4.4; owner decision D1).

Deterministic projection + statistics of the demand noise actually observed in /v1/demand-history.
No trained model. Stockout risk uses a normal approximation of cumulative demand noise:
  cumulative demand to tick k ~ N(mu_k, (sigma * sqrt(sum q_t^2))^2)
  risk = max_k P(demand_to_k > stock available by k)   (a lower bound on P(stockout in window))
"""
import math
from collections import defaultdict

from .projection import closed_ticks, nominal
from .sim import FUELS

GUIDE_NOISE = {"urban_high": 0.10, "industrial": 0.08, "highway": 0.12, "regional": 0.10}  # prior, guide §8.5
MIN_ROWS = 30
WINDOW = 288  # ticks of history used for noise statistics (3 simulated days)


def _phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


class NoiseModel:
    """Relative demand noise per demand profile, measured from observed history.

    Each residual is computed once, when its row arrives (the multiplier in force at that tick comes
    from the snapshots we saw), so per-tick statistics are a cheap aggregation.
    """

    def __init__(self):
        self.rows = {}   # observation id -> (station, fuel, tick, demand)
        self.resid = {}  # observation id -> (profile, tick, relative error)
        self.mult = {}   # (station, tick) -> demand_multiplier seen in a snapshot

    def observe_snapshot(self, snap):
        self.events, self.station_meta = snap["events"], snap["stations"]
        for sid, st in snap["stations"].items():
            self.mult[(sid, snap["tick"])] = st["demand_multiplier"]

    def _mult_at(self, sid, tick):
        for t in range(tick, max(tick - 64, -1), -1):
            if (sid, t) in self.mult:
                return self.mult[(sid, t)]
        # Before this app was watching: rebuild from public demand_spike events (C12: multipliers multiply).
        st = getattr(self, "station_meta", {}).get(sid)
        if st is None:
            return None
        m = 1.0
        for e in getattr(self, "events", ()):
            p = e["parameters"]
            if e["type"] == "demand_spike" and e["start_tick"] <= tick < e["end_tick"] and (
                    (not p.get("station_ids") and not p.get("region_ids")) or sid in p.get("station_ids", [])
                    or st["region_id"] in p.get("region_ids", [])):
                m *= float(p.get("multiplier", 1.5))
        return m

    def add_history(self, rows, snap, keep_ticks=WINDOW):
        """Adds rows; returns the new ones as (station, fuel, tick, demand)."""
        region = {r["id"]: r["demand_factor"] for r in snap["regions"]}
        new = []
        for h in rows:
            if h["id"] in self.rows:
                continue
            new.append((h["station_id"], h["fuel_type"], h["tick"], h["demand_liters"]))
            self.rows[h["id"]] = (h["station_id"], h["fuel_type"], h["tick"], h["demand_liters"])
            st, m = snap["stations"].get(h["station_id"]), self._mult_at(h["station_id"], h["tick"])
            if st is None or m is None:
                continue
            base = nominal({**st, "demand_multiplier": m}, h["fuel_type"], h["tick"], region[st["region_id"]],
                           snap["tick_minutes"])
            if base > 0:
                self.resid[h["id"]] = (st["demand_profile"], h["tick"], h["demand_liters"] / base - 1)
        cutoff = snap["tick"] - keep_ticks  # bounded memory
        self.rows = {k: r for k, r in self.rows.items() if r[2] > cutoff}
        self.resid = {k: r for k, r in self.resid.items() if r[1] > cutoff}
        self.mult = {k: m for k, m in self.mult.items() if k[1] > cutoff - 64}
        return new

    def stats(self, snap=None):
        """{profile: (sigma, n)} plus the mean absolute % error of the projection."""
        errs = defaultdict(list)
        for prof, _tick, e in self.resid.values():
            errs[prof].append(e)
        out = {}
        for prof, prior in GUIDE_NOISE.items():
            e = errs.get(prof, [])
            if len(e) >= MIN_ROWS:
                mu = sum(e) / len(e)
                out[prof] = (math.sqrt(sum((x - mu) ** 2 for x in e) / (len(e) - 1)), len(e))
            else:
                out[prof] = (prior, len(e))
        allv = [abs(e) for _, _, e in self.resid.values()]
        return out, (sum(allv) / len(allv) if allv else None)


def project(snap, station_id, fuel, horizon, extra=(), sigma=0.1):
    """Stock trajectory for one station/fuel with optional extra arrivals [(tick, liters)].

    Returns hours to stockout (None if none in horizon), risk of stockout within horizon, expected unmet.
    Order inside a tick follows C03/C06: arrivals (clipped to capacity), then demand.
    """
    st = snap["stations"][station_id]
    region = {r["id"]: r["demand_factor"] for r in snap["regions"]}[st["region_id"]]
    tm, v = snap["tick_minutes"], snap["tick"]
    arrivals = defaultdict(float)
    for eta, q in snap["incoming"].get((station_id, fuel), ()):
        arrivals[eta] += q
    for eta, q in extra:
        arrivals[eta] += q
    stock, cap = st["inventory"][fuel], st["capacity"][fuel]
    closed = closed_ticks(snap, station_id)
    avail, cum_mu, cum_var, risk, stockout_k, unmet = stock, 0.0, 0.0, 0.0, None, 0.0
    for k in range(horizon):
        t = v + k
        stock = min(stock + arrivals.get(t, 0.0), cap)
        avail = min(avail + arrivals.get(t, 0.0), cap + cum_mu)  # total fuel usable up to t
        q = nominal({**st, "status": "OPEN"}, fuel, t, region, tm)
        if closed(t):  # C09: customers still come, nothing is sold, stock stays as it is
            unmet += q
            continue
        cum_mu += q
        cum_var += (sigma * q) ** 2
        if cum_var > 0:
            risk = max(risk, 1 - _phi((avail - cum_mu) / math.sqrt(cum_var)))
        if stock < q and stockout_k is None:
            stockout_k = k + stock / q if q else k
        unmet += max(0.0, q - stock)
        stock = max(0.0, stock - q)
    hours = stockout_k * tm / 60 if stockout_k is not None else None
    return {"stockout_hours": hours, "risk": risk, "unmet": unmet, "expected_demand": cum_mu}


def confidence(n_rows, degraded, active_events):
    """0..1. With no history the guide's documented noise level gives moderate confidence (0.5);
    measured history raises it to 1. Degraded data or an active crisis lowers it (PS §11)."""
    c = 0.5 + 0.5 * min(1.0, n_rows / 288)  # ~3 simulated days of rows for a profile → full weight
    if degraded:
        c *= 0.5
    if active_events:
        c *= 0.8
    return round(c, 2)


def detect(snap, prev, noise_stats, history_rows, budget_used):
    """Rule-based detectors (PS §7 Detection). Returns a list of alerts."""
    alerts = []
    region = {r["id"]: r["demand_factor"] for r in snap["regions"]}
    tm = snap["tick_minutes"]
    # 1. anomalous demand: the 4 newest observed ticks vs the base profile (multiplier 1), z > 4.
    #    History arrives in pulls, so use the newest rows we have if they are recent (no flicker).
    recent = defaultdict(list)
    for sid, fuel, tick, demand in history_rows:
        if tick >= snap["tick"] - 16:
            recent[(sid, fuel)].append((tick, demand))
    for (sid, fuel), obs in recent.items():
        obs = sorted(obs)[-4:]
        st = snap["stations"].get(sid)
        if not st or not obs:
            continue
        sigma = noise_stats.get(st["demand_profile"], (0.1, 0))[0]
        base = [nominal({**st, "demand_multiplier": 1.0}, fuel, t, region[st["region_id"]], tm) for t, _ in obs]
        act = sum(d for _, d in obs)
        exp = sum(base)
        sd = sigma * math.sqrt(sum(b * b for b in base)) or 1.0
        z = (act - exp) / sd
        if z > 4:  # a 1.5x spike gives z > 8; z > 4 keeps chance alarms rare across 12 series
            alerts.append({"kind": "anomalous_demand", "severity": "warning", "station_id": sid, "fuel": fuel,
                           "detail": f"Demand {act / exp:.2f}× the normal profile over the last {len(obs)} ticks (z={z:.1f})"})
    # 2. abnormal inventory change: station stock fell far more than demand explains, measured against a
    #    reference snapshot >= 8 ticks old. Live reads can straddle a tick, so allow 2 extra ticks of demand.
    if prev is not None and snap["tick"] - prev["tick"] >= 8:
        for sid, st in snap["stations"].items():
            p = prev["stations"].get(sid)
            if not p or st["status"] != "OPEN":
                continue
            for f in FUELS:
                arrived = sum(a["quantity"] for a in snap["allocs"] if a["destination_station_id"] == sid
                              and a["fuel_type"] == f and a["actual_arrival_tick"] is not None
                              and prev["tick"] <= a["actual_arrival_tick"] <= snap["tick"])
                exp = sum(nominal(st, f, t, region[st["region_id"]], tm) for t in range(prev["tick"], snap["tick"] + 2))
                drop = p["inventory"][f] + arrived - st["inventory"][f]
                if exp > 0 and drop > 1.5 * exp + 300:
                    alerts.append({"kind": "abnormal_inventory", "severity": "warning", "station_id": sid, "fuel": f,
                                   "detail": f"Stock fell {drop:,.0f} L over {snap['tick'] - prev['tick']} ticks; "
                                             f"demand explains about {exp:,.0f} L"})
    # 3. supply-chain bottleneck: depot dispatch budget nearly exhausted by planned work
    for did, used in budget_used.items():
        cap = snap["depots"][did]["dispatch_capacity_per_tick"]
        if cap and used / cap >= 0.9:
            alerts.append({"kind": "bottleneck", "severity": "warning", "depot_id": did,
                           "detail": f"Dispatch capacity {used / cap:.0%} used this tick ({used:,.0f} / {cap:,.0f} L)"})
    # 4. emerging regional disruption: public events + stations out of service
    for e in snap["events"]:
        if e["status"] == "ACTIVE" or (e["status"] == "SCHEDULED" and e["start_tick"] <= snap["tick"] + 8):
            alerts.append({"kind": "disruption", "severity": "critical" if e["status"] == "ACTIVE" else "info",
                           "event_id": e["id"], "detail": f"{e['type']} {e['status'].lower()} "
                           f"ticks {e['start_tick']}–{e['end_tick']} {e['parameters']}"})
    return alerts
