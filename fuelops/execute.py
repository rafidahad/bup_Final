"""Snapshot + safe shipment execution shared by every policy (plan §9.5, §10).

Rules baked in from probes (devlog "Simulator semantics"):
- C05/C06: server ignores in-transit when checking headroom and overflow is lost,
  so we reserve headroom for our own incoming shipments.
- C04: dispatch budget = allocations created this tick, per depot.
- C10: same key + same body replays safely (201, same allocation).
- C08/C18: a shipment whose route is disrupted in its creation tick FAILS and its fuel is
  NOT refunded, so never POST on a route with a disruption starting now or next tick.
"""
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from .sim import SimError

OPEN_ALLOC = ("PENDING", "IN_TRANSIT")


_pool = ThreadPoolExecutor(max_workers=9)


def snapshot(sim):
    """All reads in parallel: under a latency fault this costs one delay, not nine (plan §12.1)."""
    names = ("instance", "supply", "regions", "depots", "stations", "routes", "allocations", "events")
    got = dict(zip(names, _pool.map(lambda n: getattr(sim, n)(), names)))
    inst = got["instance"]
    s = {
        "tick": inst["tick"],
        "tick_minutes": inst["tick_minutes"],
        "status": inst["status"],
        "supply": got["supply"],
        "regions": got["regions"],
        "depots": {d["id"]: d for d in got["depots"]},
        "stations": {x["id"]: x for x in got["stations"]},
        "routes": {r["id"]: r for r in got["routes"]},
        "allocs": got["allocations"],
        "events": got["events"],
    }
    s["incoming"] = {}  # (station, fuel) -> [(arrival_tick, qty)]
    for a in s["allocs"]:
        if a["status"] in OPEN_ALLOC:
            eta = a["expected_arrival_tick"]
            if eta is None:  # pending: departs this tick (C02)
                eta = s["tick"] + s["routes"][a["route_id"]]["transit_ticks"]
            s["incoming"].setdefault((a["destination_station_id"], a["fuel_type"]), []).append((eta, a["quantity"]))
    return s


def blocked_routes(snap, lookahead=1):
    """Routes with a disruption active now or starting within `lookahead` ticks (C08: POSTing loses the fuel)."""
    out = set()
    for e in snap["events"]:
        if e["type"] == "route_disruption" and e["status"] != "RESOLVED" and e["start_tick"] <= snap["tick"] + lookahead:
            ids = e["parameters"].get("route_ids") or list(snap["routes"])  # empty filter = all routes
            out.update(ids)
    return out


def incoming_total(snap, station, fuel):
    return sum(q for _, q in snap["incoming"].get((station, fuel), ()))


class Executor:
    """Turns desired (route, fuel, liters) into validated, idempotent POSTs."""

    def __init__(self, sim, run_id, log_path, reserve_incoming=True):
        """reserve_incoming: subtract our in-transit from headroom (threshold policy).
        The LP models arrival-time clipping itself, so it only needs the server's per-request rule."""
        self.sim, self.run_id, self.reserve_incoming = sim, run_id, reserve_incoming
        self.log = open(log_path, "a", encoding="utf-8")
        self.seq = 0
        self.stats = {"sent": 0, "accepted": 0, "rejected": {}, "liters": 0.0}

    def execute(self, snap, wants):
        tick = snap["tick"]
        depot_stock = {(d, f): v for d, dep in snap["depots"].items() for f, v in dep["inventory"].items()}
        budget = {d: dep["dispatch_capacity_per_tick"] for d, dep in snap["depots"].items()}
        for a in snap["allocs"]:
            if a["created_tick"] == tick and a["status"] != "CANCELLED":
                budget[a["source_depot_id"]] -= a["quantity"]
        room = {}
        for sid, st in snap["stations"].items():
            for f, cap in st["capacity"].items():
                room[(sid, f)] = cap - st["inventory"][f] - (incoming_total(snap, sid, f) if self.reserve_incoming else 0)

        blocked = blocked_routes(snap)
        sent = {}  # (route, fuel) -> liters accepted, so callers can carry unsent remainders forward
        for route_id, fuel, liters in wants:
            r = snap["routes"][route_id]
            d, s = r["source_depot_id"], r["destination_station_id"]
            if r["status"] != "AVAILABLE" or route_id in blocked or snap["stations"][s]["status"] != "OPEN":
                self.stats["skipped_blocked"] = self.stats.get("skipped_blocked", 0) + (route_id in blocked)
                continue
            qty = min(liters, depot_stock[(d, fuel)], budget[d])
            if self.reserve_incoming:
                qty = min(qty, room[(s, fuel)])
            # server checks each request alone: quantity <= max_shipment and <= capacity - current inventory
            per_req = min(r["max_shipment"], math.floor(room[(s, fuel)]))
            qty = math.floor(qty)  # ponytail: whole liters; never rounds up across a limit
            while qty > 0 and per_req > 0:
                chunk = min(per_req, qty)
                qty -= chunk
                if self._post(tick, d, s, route_id, fuel, chunk):
                    sent[(route_id, fuel)] = sent.get((route_id, fuel), 0.0) + chunk
                    depot_stock[(d, fuel)] -= chunk
                    budget[d] -= chunk
                    if self.reserve_incoming:
                        room[(s, fuel)] -= chunk
                else:
                    break  # rejected: let the next decision re-read state
        return sent

    def _post(self, tick, depot, station, route, fuel, qty):
        self.seq += 1
        key = f"{self.run_id}:{tick}:{self.seq}"
        body = dict(idempotency_key=key, source_depot_id=depot, destination_station_id=station,
                    route_id=route, fuel_type=fuel, quantity=qty)
        self.log.write(json.dumps({"tick": tick, "state": "SENDING", **body}) + "\n")
        self.log.flush()  # persist before the HTTP call (plan §10.3 staging)
        self.stats["sent"] += 1
        last_error = None
        for attempt in range(3):
            try:
                a = self.sim.allocate(key, depot, station, route, fuel, qty)
                self._record(key, "CONFIRMED", a["id"])
                self.stats["accepted"] += 1
                self.stats["liters"] += qty
                return True
            except SimError as e:
                if e.status == 503:  # injected fault: request never processed, same key is safe
                    last_error = e
                    time.sleep(0.05 * 2 ** attempt)
                    continue
                self._record(key, "REJECTED", e.code)
                self.stats["rejected"][e.code] = self.stats["rejected"].get(e.code, 0) + 1
                return False
            except httpx.TransportError:
                # outcome unknown: look for the key before replaying the identical body
                try:
                    hit = next((a for a in self.sim.allocations() if a["idempotency_key"] == key), None)
                except (SimError, httpx.TransportError):
                    hit = None
                if hit:
                    self._record(key, "CONFIRMED", hit["id"])
                    self.stats["accepted"] += 1
                    self.stats["liters"] += qty
                    return True
                last_error = SimError(503, "UNREACHABLE", "simulator did not answer the allocation request")
                time.sleep(0.05 * 2 ** attempt)
        # The simulator is down: stop this whole batch (no point retrying every other shipment)
        # and let the controller go degraded. The key and body stay in the intent log.
        self._record(key, "UNKNOWN_OUTCOME" if isinstance(last_error, SimError) and last_error.code == "UNREACHABLE"
                     else "NOT_SENT_SIMULATOR_DOWN", None)
        raise last_error

    def _record(self, key, state, detail):
        self.log.write(json.dumps({"key": key, "state": state, "detail": detail}) + "\n")
        self.log.flush()
