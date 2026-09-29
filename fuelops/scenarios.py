"""Versioned crisis recipes (plan §16.3). Tick positions are chosen inside the days 1–5 window,
where policies can still differ (after ~6 days the world is out of fuel).

Each event: (type, start_tick, duration_ticks, parameters). Injection timing is set by the harness:
surprise = injected when the simulator reaches start_tick; announced = injected right after reset.
"""
RECIPES = {
    "baseline": [],
    "s02_spike_station": [("demand_spike", 150, 48, {"station_ids": ["station-mirpur"], "multiplier": 1.8})],
    "s03_spike_region": [("demand_spike", 260, 40, {"region_ids": ["region-chattogram"], "multiplier": 1.6})],
    "s04_primary_route_down": [("route_disruption", 100, 60, {"route_ids": ["route-gazipur-mirpur"]})],
    "s05_tongi_isolated": [("route_disruption", 200, 60, {"route_ids": ["route-gazipur-tongi"]})],
    "s06_coxsbazar_isolated": [("route_disruption", 220, 60, {"route_ids": ["route-patiya-coxsbazar"]})],
    "s07_depot_constraint": [("depot_constraint", 120, 48, {"depot_ids": ["depot-patiya"]})],
    "s08_supply_delay": [("shipment_delay", 60, 10, {"depot_ids": ["depot-gazipur"], "delay_ticks": 12})],
    "s09_supply_shortfall": [("supply_shortfall", 50, 10, {"depot_ids": ["depot-patiya"], "fuel_types": ["DIESEL"], "factor": 0.5})],
    "s10_station_outage": [("station_outage", 180, 24, {"station_ids": ["station-karnaphuli"]})],
    "s11_overlap": [
        ("route_disruption", 140, 50, {"route_ids": ["route-patiya-karnaphuli"]}),
        ("demand_spike", 150, 40, {"region_ids": ["region-chattogram"], "multiplier": 1.5}),
        ("supply_shortfall", 125, 5, {"depot_ids": ["depot-patiya"], "factor": 0.7}),
    ],
}
