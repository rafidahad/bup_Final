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
