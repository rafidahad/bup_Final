"""Black-box contract probes (plan §4.4). Each probe resets the simulator.

Usage: python -m fuelops.probes c01 c02 ...   (no args = all)
Findings are recorded by hand in devlog.md; this script only prints observations.
"""
import sys
import time

from .sim import Sim, SimError

sim = Sim()


def fresh():
    sim.reset()
    sim.pause()
    assert sim.instance()["tick"] == 0


def depot(did):
    return next(d for d in sim.depots() if d["id"] == did)


def station(sid):
    return next(s for s in sim.stations() if s["id"] == sid)


def alloc_row(aid):
    return next(a for a in sim.allocations() if a["id"] == aid)


def show(a):
    return {k: a[k] for k in ("id", "status", "created_tick", "departure_tick", "expected_arrival_tick", "actual_arrival_tick")}


def try_alloc(key, depot_id, station_id, route, fuel, qty):
    try:
        a = sim.allocate(key, depot_id, station_id, route, fuel, qty)
        return f"OK id={a['id']} {a['status']}"
    except SimError as e:
        return f"{e.status} {e.code}"


def c01():
    """Inventory deducted at acceptance or departure?"""
    fresh()
    print("depot before", depot("depot-gazipur")["inventory"]["DIESEL"])
    a = sim.allocate("c01", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 3000)
    print("depot after POST", depot("depot-gazipur")["inventory"]["DIESEL"], show(a))
    sim.step()
    print("depot after step", depot("depot-gazipur")["inventory"]["DIESEL"], show(alloc_row(a["id"])))


def c02():
    """Departure/arrival timing for transit 2, 3, 4; when does arrived stock appear?"""
    fresh()
    legs = [("route-gazipur-mirpur", "depot-gazipur", "station-mirpur"),
            ("route-patiya-coxsbazar", "depot-patiya", "station-coxsbazar"),
            ("route-gazipur-karnaphuli", "depot-gazipur", "station-karnaphuli")]
    ids = [sim.allocate(f"c02-{i}", d, s, r, "OCTANE", 1000)["id"] for i, (r, d, s) in enumerate(legs)]
    for _ in range(7):
        t = sim.instance()["tick"]
        inv = {s: station(s)["inventory"]["OCTANE"] for _, _, s in legs}
        print("tick", t, [show(alloc_row(i)) for i in ids], inv)
        sim.step()


def c03():
    """Execution order within a tick, from the audit log (diagnostic only)."""
    fresh()
    sim.allocate("c03", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 1000)
    for _ in range(13):
        sim.step()
    rows = [r for r in reversed(sim.audit(1000)) if r["action"] != "demand.observed"]
    for r in rows:
        if r["tick"] in (0, 1, 2, 3, 11, 12, 13):
            print(r["tick"], r["action"], r["entity_type"], r["entity_id"], r.get("result"))


def c04():
    """Which allocations count against dispatch_capacity_per_tick (Gazipur 12,000)?"""
    fresh()
    print("t0 5000 mirpur", try_alloc("c04-1", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 5000))
    print("t0 5000 tongi", try_alloc("c04-2", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "DIESEL", 5000))
    print("t0 +2001", try_alloc("c04-3", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "PETROL", 2001))
    print("t0 +2000", try_alloc("c04-4", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "PETROL", 2000))
    sim.step()
    print("after 1 step:", [show(a) for a in sim.allocations()])
    print("t1 +5000", try_alloc("c04-5", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "PETROL", 5000))
    sim.step()
    print("t2 +3000", try_alloc("c04-6", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "OCTANE", 3000))
    sim.step(); sim.step()
    print("t4 +2500", try_alloc("c04-7", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "OCTANE", 2500))


def c06():
    """C05+C06: is in-transit reserved against station capacity; what happens on overflow?"""
    fresh()
    s = station("station-mirpur")
    print("mirpur diesel", s["inventory"]["DIESEL"], "/", s["capacity"]["DIESEL"])
    print("A 6000", try_alloc("c06-1", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 6000))
    print("B 6000", try_alloc("c06-2", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 6000))
    for _ in range(5):
        sim.step()
        t = sim.instance()["tick"]
        print("tick", t, "mirpur diesel", round(station("station-mirpur")["inventory"]["DIESEL"], 1),
              [a["status"] for a in sim.allocations()])
    hist = [h for h in sim.demand_history("station-mirpur", 200) if h["fuel_type"] == "DIESEL"]
    print("demand rows", sorted((h["tick"], round(h["demand_liters"], 1)) for h in hist))


def c10():
    """Idempotent replay status code; changed body; replay after cancel."""
    fresh()
    body = {"idempotency_key": "c10", "source_depot_id": "depot-gazipur", "destination_station_id": "station-mirpur",
            "route_id": "route-gazipur-mirpur", "fuel_type": "DIESEL", "quantity": 1000}
    r1 = sim.http.post("/v1/allocations", json=body)
    r2 = sim.http.post("/v1/allocations", json=body)
    print("first", r1.status_code, "replay", r2.status_code, "same id", r1.json()["id"] == r2.json()["id"])
    r3 = sim.http.post("/v1/allocations", json={**body, "quantity": 1001})
    print("changed body", r3.status_code, r3.text[:200])
    print("cancel", sim.cancel(r1.json()["id"])["status"])
    r4 = sim.http.post("/v1/allocations", json=body)
    print("replay after cancel", r4.status_code, r4.json().get("status"))
    print("allocation count", len(sim.allocations()))


def c15():
    """Does stale_data only add a header, or serve old bodies?"""
    fresh()
    sim.inject_fault({"type": "stale_data", "duration_seconds": 30})
    for _ in range(3):
        sim.step()
        inst = sim.instance()
        flagged = sim.last_stale
        print("v1 tick", inst["tick"], "stale header", flagged, "| health tick", sim.health()["simulation"]["tick"],
              "| mirpur diesel", round(station("station-mirpur")["inventory"]["DIESEL"], 1))
    sim.clear_faults()
    sim.instance()
    print("after clear, stale header", sim.last_stale)


if __name__ == "__main__":
    names = sys.argv[1:] or [n for n in dir() if n[0] == "c" and n[1:].isdigit()]
    for n in names:
        print(f"\n=== {n}: {globals()[n].__doc__.strip()}")
        t0 = time.perf_counter()
        globals()[n]()
        print(f"({time.perf_counter() - t0:.1f}s)")
