"""Hand-checkable LP fixtures (plan §16.5). No simulator needed."""
import pytest

from fuelops.lp import solve

FUELS = ("DIESEL", "PETROL", "OCTANE")


def world(station_inv=100.0, station_cap=1000.0, depot_inv=0.0, depot_cap=10_000.0,
          supply=(), transit=2, route=True, dispatch=10_000):
    """One depot, one station (DIESEL only matters), flat 'industrial' profile at night = 0.45 factor."""
    def fuels(v):
        return {f: (v if f == "DIESEL" else 0.0) for f in FUELS}
    snap = {
        "tick": 72, "tick_minutes": 15,  # 18:00 → industrial off-peak, constant factor over short horizons
        "regions": [{"id": "r", "demand_factor": 1.0}],
        "depots": {"d": {"id": "d", "dispatch_capacity_per_tick": dispatch,
                         "capacity": fuels(depot_cap), "inventory": fuels(depot_inv)}},
        "stations": {"s": {"id": "s", "region_id": "r", "status": "OPEN", "demand_profile": "industrial",
                           "demand_multiplier": 1.0, "capacity": fuels(station_cap), "inventory": fuels(station_inv)}},
        "routes": {}, "allocs": [], "incoming": {},
        "supply": [{"depot_id": "d", "fuel_type": "DIESEL", "quantity": q, "planned_tick": 72 + k, "status": "SCHEDULED"}
                   for k, q in supply],
    }
    if route:
        snap["routes"]["rt"] = {"id": "rt", "source_depot_id": "d", "destination_station_id": "s",
                                "transit_ticks": transit, "max_shipment": 5000, "status": "AVAILABLE"}
    return snap


PER_TICK = 14000 * 15 / 1440 * 0.45  # industrial diesel, off-peak ≈ 65.6 L


def test_serves_greedily_without_binaries():
    # 100 L on hand, no resupply possible: must serve min(A, q) now, not hold stock for later ticks
    r = solve(world(station_inv=100.0, route=False), horizon=6, headroom_margin=0)
    assert r["status"] == 0
    assert r["served_by_k"][0] == pytest.approx(PER_TICK, abs=1e-6)
    assert r["served_by_k"][1] == pytest.approx(100 - PER_TICK, abs=1e-6)
    assert sum(r["served_by_k"][2:]) == pytest.approx(0, abs=1e-6)


def test_late_stock_cannot_serve_earlier_demand():
    # empty station, plenty at the depot, transit 2: ticks 0 and 1 are unavoidably unmet
    r = solve(world(station_inv=0.0, depot_inv=5000.0, transit=2), horizon=6, headroom_margin=0)
    assert r["served_by_k"][0] == pytest.approx(0, abs=1e-6)
    assert r["served_by_k"][1] == pytest.approx(0, abs=1e-6)
    assert r["served_by_k"][2] == pytest.approx(PER_TICK, abs=1e-6)
    assert sum(r["served_by_k"]) == pytest.approx(4 * PER_TICK, abs=1e-3)  # ticks 2..5 fully served


def test_ships_ahead_of_supply_to_avoid_depot_overflow():
    # depot full; 3,000 L arrives at k=3; station has room; demand over the horizon exceeds what the station holds.
    # Best: move stock out before the arrival so nothing overflows.
    snap = world(station_inv=0.0, station_cap=6000.0, depot_inv=9000.0, depot_cap=9000.0, supply=[(3, 3000.0)])
    r = solve(snap, horizon=96, headroom_margin=0)
    assert r["status"] == 0
    shipped_before_arrival = sum(q for (_, _, k), q in r["x"].items() if k <= 3)
    assert shipped_before_arrival >= 3000 - 1e-6


def test_dispatch_budget_limits_each_tick():
    r = solve(world(station_inv=0.0, station_cap=20000.0, depot_inv=9000.0, dispatch=1000), horizon=10,
              headroom_margin=0)
    per_tick = {}
    for (_, _, k), q in r["x"].items():
        per_tick[k] = per_tick.get(k, 0) + q
    assert max(per_tick.values()) <= 1000 + 1e-6


def test_buffer_never_withholds_service():
    # with a safety buffer the LP still serves min(A, q) now instead of keeping stock for the buffer
    r = solve(world(station_inv=100.0, route=False), horizon=6, headroom_margin=0, buffer_ticks=16)
    assert r["served_by_k"][0] == pytest.approx(PER_TICK, abs=1e-6)
    assert r["served_by_k"][1] == pytest.approx(100 - PER_TICK, abs=1e-6)


def test_incomplete_demand_override_is_rejected():
    snap = world(station_inv=100.0, route=False)
    demand = {("s", "DIESEL", 72): 50.0}  # every other key missing
    with pytest.raises(ValueError, match="incomplete"):
        solve(snap, horizon=4, demand=demand)


def test_outage_sells_nothing_and_keeps_stock():
    """C09: during a station outage demand is unmet and stock is frozen."""
    snap = world(station_inv=1000.0, route=False)
    snap["events"] = [{"id": 1, "type": "station_outage", "status": "ACTIVE", "start_tick": 70, "end_tick": 74,
                       "parameters": {"station_ids": ["s"]}}]
    snap["stations"]["s"]["status"] = "OUTAGE"
    r = solve(snap, horizon=4, headroom_margin=0)
    assert r["served_by_k"][:2] == pytest.approx([0, 0], abs=1e-6)       # ticks 72, 73 closed
    assert r["served_by_k"][2] == pytest.approx(PER_TICK, abs=1e-6)       # reopened at tick 74


def test_projection_counts_outage_demand_as_unmet():
    from fuelops.intel import project
    snap = world(station_inv=5000.0, route=False)
    snap["events"] = [{"id": 1, "type": "station_outage", "status": "ACTIVE", "start_tick": 70, "end_tick": 76,
                       "parameters": {"station_ids": ["s"]}}]
    snap["stations"]["s"]["status"] = "OUTAGE"
    p = project(snap, "s", "DIESEL", 8)
    assert p["unmet"] == pytest.approx(4 * PER_TICK, rel=1e-6)  # ticks 72..75 closed, stock untouched
    assert p["stockout_hours"] is None


def _event(typ, start, end, status, **params):
    return {"type": typ, "start_tick": start, "end_tick": end, "status": status, "parameters": params}


def test_known_disruption_blocks_only_its_window():
    # route disrupted for offsets 0..4 (ticks 72..76): no shipment then, shipping allowed after it ends
    snap = world(station_inv=0.0, depot_inv=5000.0)
    snap["routes"]["rt"]["status"] = "DISRUPTED"
    snap["events"] = [_event("route_disruption", 72, 77, "ACTIVE", route_ids=["rt"])]
    r = solve(snap, horizon=12, headroom_margin=0)
    ks = sorted(k for (_, _, k), q in r["x"].items() if q > 1e-6)
    assert ks and min(ks) >= 5


def test_scheduled_disruption_makes_the_lp_ship_ahead():
    # sole route closes from offset 2 for the rest of the horizon: everything must leave at offsets 0..1
    snap = world(station_inv=0.0, station_cap=6000.0, depot_inv=5000.0)
    snap["events"] = [_event("route_disruption", 74, 200, "SCHEDULED", route_ids=["rt"])]
    r = solve(snap, horizon=24, headroom_margin=0)
    assert all(k < 2 for (_, _, k), q in r["x"].items() if q > 1e-6)
    assert sum(r["x"].values()) >= 20 * PER_TICK - 1e-3


def test_scheduled_spike_and_shortfall_are_projected():
    base = solve(world(station_inv=0.0, depot_inv=0.0, supply=[(5, 1000.0)]), horizon=10, headroom_margin=0)
    snap = world(station_inv=0.0, depot_inv=0.0, supply=[(5, 1000.0)])
    snap["events"] = [_event("demand_spike", 72, 82, "SCHEDULED", multiplier=2.0),
                      _event("supply_shortfall", 74, 75, "SCHEDULED", depot_ids=["d"], factor=0.5)]
    r = solve(snap, horizon=10, headroom_margin=0)
    assert r["demand"] == pytest.approx(2 * base["demand"], rel=1e-9)
    assert sum(r["x"].values()) <= 500 + 1e-6  # only half the scheduled supply will exist
