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


def event(type_, start, duration, **params):
    return sim.inject_event({"type": type_, "start_tick": start, "duration_ticks": duration, "parameters": params})


def c07():
    """What does depot CONSTRAINED change numerically?"""
    fresh()
    event("depot_constraint", 0, 3, depot_ids=["depot-gazipur"])
    # fill the 12,000 budget with small requests to stations that have room, then try 1 L more
    legs = [("station-tongi", "route-gazipur-tongi", "DIESEL"), ("station-mirpur", "route-gazipur-mirpur", "DIESEL")]
    for t in range(4):
        d = depot("depot-gazipur")
        res = [try_alloc(f"c07-{t}-{i}", "depot-gazipur", s, r, f, 1500) for i, (s, r, f) in enumerate(legs * 4)]
        extra = try_alloc(f"c07-{t}-x", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "OCTANE", 1)
        print("tick", t, d["status"], "cap field", d["dispatch_capacity_per_tick"],
              "| 8x1500 accepted:", sum(r.startswith("OK") for r in res), "| +1 L:", extra)
        sim.step()


def c08():
    """Route disruption vs pending and in-transit shipments; C18 refund on failure."""
    fresh()
    a = sim.allocate("c08-transit", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 1000)
    sim.step()  # a departs at tick 0
    b = sim.allocate("c08-pending", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "PETROL", 1000)
    stock = depot("depot-gazipur")["inventory"]["PETROL"]
    ev = event("route_disruption", 1, 3, route_ids=["route-gazipur-mirpur"])
    print("event", ev["status"], "route now", sim.routes()[0]["status"])
    for _ in range(4):
        sim.step()
        t = sim.instance()["tick"]
        r = next(x for x in sim.routes() if x["id"] == "route-gazipur-mirpur")
        print("tick", t, "route", r["status"], "| in-transit", show(alloc_row(a["id"]))["status"],
              "| pending", {k: alloc_row(b["id"])[k] for k in ("status", "failure_reason")},
              "| gazipur petrol", depot("depot-gazipur")["inventory"]["PETROL"], "(after POST:", stock, ")")
    print("metrics", sim.metrics())
    print("POST during disruption:", try_alloc("c08-x", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 10))


def c09():
    """Station outage: inventory, demand, served/unmet, arrivals during outage."""
    fresh()
    sim.allocate("c09", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "DIESEL", 2000)  # arrives tick 2
    event("station_outage", 1, 3, station_ids=["station-tongi"])
    for _ in range(6):
        t = sim.instance()["tick"]
        st = station("station-tongi")
        print("tick", t, st["status"], "diesel", round(st["inventory"]["DIESEL"], 1),
              "| POST:", try_alloc(f"c09-{t}", "depot-gazipur", "station-tongi", "route-gazipur-tongi", "OCTANE", 10))
        sim.step()
    rows = sorted((h["tick"], round(h["demand_liters"], 1), round(h["served_liters"], 1), round(h["unmet_liters"], 1))
                  for h in sim.demand_history("station-tongi", 100) if h["fuel_type"] == "DIESEL")
    print("tongi diesel (tick, demand, served, unmet):", rows)
    print("allocations", [a["status"] for a in sim.allocations() if a["fuel_type"] == "DIESEL"])


def c12():
    """Overlapping demand spikes: composition and resolution."""
    fresh()
    event("demand_spike", 1, 4, station_ids=["station-mirpur"], multiplier=1.5)
    event("demand_spike", 2, 4, region_ids=["region-dhaka"], multiplier=2.0)
    for _ in range(8):
        t = sim.instance()["tick"]
        print("tick", t, "mirpur mult", station("station-mirpur")["demand_multiplier"],
              "tongi mult", station("station-tongi")["demand_multiplier"],
              [(e["id"], e["status"]) for e in sim.events()])
        sim.step()


def c13():
    """Which supply rows do shipment_delay / supply_shortfall mutate, and when?"""
    fresh()
    before = {s["id"]: (s["planned_tick"], s["quantity"]) for s in sim.supply()}
    event("shipment_delay", 2, 5, depot_ids=["depot-gazipur"], delay_ticks=3)
    event("supply_shortfall", 2, 5, depot_ids=["depot-patiya"], fuel_types=["DIESEL"], factor=0.5)
    for _ in range(4):
        sim.step()
        t = sim.instance()["tick"]
        now = {s["id"]: (s["planned_tick"], s["quantity"], s["status"]) for s in sim.supply()}
        changed = {k: (before[k], v) for k, v in now.items() if v[:2] != before[k]}
        print("tick", t, "changed rows:", len(changed), dict(list(changed.items())[:4]))
    for _ in range(12):
        sim.step()
    print("after resolve+arrivals:", [(s["id"], s["planned_tick"], s["actual_tick"], s["quantity"], s["status"])
                                      for s in sim.supply()[:4]])


def _stream_events(seconds, out, name):
    import httpx
    try:
        with httpx.Client(base_url=sim.http.base_url, timeout=seconds + 5) as c, \
                c.stream("GET", "/v1/stream") as r:
            out.append((name, "status", r.status_code))
            t0 = time.perf_counter()
            for line in r.iter_lines():
                if line:
                    out.append((name, round(time.perf_counter() - t0, 2), line[:80]))
                if time.perf_counter() - t0 > seconds:
                    break
    except Exception as e:  # noqa: BLE001 — probe records whatever happens
        out.append((name, "error", repr(e)[:120]))


def c14():
    """stream_disconnect: does it cut existing streams or only block new ones?"""
    import threading
    fresh()
    out = []
    old = threading.Thread(target=_stream_events, args=(6, out, "existing"))
    old.start()
    while not out:  # wait until the existing stream is really open
        time.sleep(0.05)
    sim.inject_fault({"type": "stream_disconnect", "duration_seconds": 3})
    time.sleep(0.2)
    _stream_events(0.5, out, "new")
    sim.step(); sim.step()
    old.join()
    sim.clear_faults()
    for o in out:
        print(o)


def c16():
    """How can an external reset be recognized?"""
    import threading
    fresh()
    sim.allocate("c16", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 1000)
    for _ in range(5):
        sim.step()
    before = sim.instance()
    out = []
    th = threading.Thread(target=_stream_events, args=(2, out, "sse"))
    th.start()
    time.sleep(0.5)
    sim.reset()
    th.join()
    after = sim.instance()
    print("before", before)
    print("after ", after)
    print("allocations after reset", sim.allocations())
    for o in out:
        print(o)


def c17():
    """Fractional quantities; demand-history ordering and limit."""
    fresh()
    print("fractional 1234.567:", try_alloc("c17", "depot-gazipur", "station-mirpur", "route-gazipur-mirpur", "DIESEL", 1234.567))
    print("depot after", depot("depot-gazipur")["inventory"]["DIESEL"])
    for _ in range(3):
        sim.step()
    h = sim.demand_history("station-mirpur", 5)
    print("limit 5 →", [(x["id"], x["tick"], x["fuel_type"]) for x in h])
    g = sim.demand_history(None, 3)
    print("global limit 3 →", [(x["id"], x["tick"], x["station_id"]) for x in g])


if __name__ == "__main__":
    names = sys.argv[1:] or [n for n in dir() if n[0] == "c" and n[1:].isdigit()]
    for n in names:
        print(f"\n=== {n}: {globals()[n].__doc__.strip()}")
        t0 = time.perf_counter()
        globals()[n]()
        print(f"({time.perf_counter() - t0:.1f}s)")
