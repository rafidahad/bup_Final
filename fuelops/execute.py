"""Snapshot + safe shipment execution shared by every policy (plan §9.5, §10).

Rules baked in from probes (devlog "Simulator semantics"):
- C05/C06: server ignores in-transit when checking headroom and overflow is lost,
  so we reserve headroom for our own incoming shipments.
- C04: dispatch budget = allocations created this tick, per depot.
- C10: same key + same body replays safely (201, same allocation).
"""
import json
import math
import time

import httpx

from .sim import SimError

OPEN_ALLOC = ("PENDING", "IN_TRANSIT")


def snapshot(sim):
    inst = sim.instance()
    s = {
        "tick": inst["tick"],
        "tick_minutes": inst["tick_minutes"],
        "supply": sim.supply(),
        "regions": sim.regions(),
        "depots": {d["id"]: d for d in sim.depots()},
        "stations": {x["id"]: x for x in sim.stations()},
        "routes": {r["id"]: r for r in sim.routes()},
        "allocs": sim.allocations(),
    }
    s["incoming"] = {}  # (station, fuel) -> [(arrival_tick, qty)]
    for a in s["allocs"]:
        if a["status"] in OPEN_ALLOC:
            eta = a["expected_arrival_tick"]
            if eta is None:  # pending: departs this tick (C02)
                eta = s["tick"] + s["routes"][a["route_id"]]["transit_ticks"]
            s["incoming"].setdefault((a["destination_station_id"], a["fuel_type"]), []).append((eta, a["quantity"]))
    return s


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

        for route_id, fuel, liters in wants:
            r = snap["routes"][route_id]
            d, s = r["source_depot_id"], r["destination_station_id"]
            if r["status"] != "AVAILABLE" or snap["stations"][s]["status"] != "OPEN":
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
                    depot_stock[(d, fuel)] -= chunk
                    budget[d] -= chunk
                    if self.reserve_incoming:
                        room[(s, fuel)] -= chunk
                else:
                    break  # rejected: let the next decision re-read state

    def _post(self, tick, depot, station, route, fuel, qty):
        self.seq += 1
        key = f"{self.run_id}:{tick}:{self.seq}"
        body = dict(idempotency_key=key, source_depot_id=depot, destination_station_id=station,
                    route_id=route, fuel_type=fuel, quantity=qty)
        self.log.write(json.dumps({"tick": tick, "state": "SENDING", **body}) + "\n")
        self.log.flush()  # persist before the HTTP call (plan §10.3 staging)
        self.stats["sent"] += 1
        for attempt in range(4):
            try:
                a = self.sim.allocate(key, depot, station, route, fuel, qty)
                self._record(key, "CONFIRMED", a["id"])
                self.stats["accepted"] += 1
                self.stats["liters"] += qty
                return True
            except SimError as e:
                if e.status == 503:  # injected fault: request never processed, same key is safe
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
                time.sleep(0.05 * 2 ** attempt)
        self._record(key, "UNKNOWN_OUTCOME", None)
        return False

    def _record(self, key, state, detail):
        self.log.write(json.dumps({"key": key, "state": state, "detail": detail}) + "\n")
        self.log.flush()
