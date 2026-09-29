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
    # Hold-out recipes: other timings and severities, so parameters are not tuned to s02–s11 alone.
    "h1_tongi_late": [("route_disruption", 330, 40, {"route_ids": ["route-gazipur-tongi"]})],
    "h2_coxs_long": [("route_disruption", 120, 90, {"route_ids": ["route-patiya-coxsbazar"]})],
    "h3_mirpur_outage_spike": [
        ("station_outage", 250, 30, {"station_ids": ["station-mirpur"]}),
        ("demand_spike", 240, 48, {"region_ids": ["region-dhaka"], "multiplier": 1.4}),
    ],
    "h4_gazipur_shortfall": [("supply_shortfall", 40, 5, {"depot_ids": ["depot-gazipur"], "factor": 0.6})],
    "h5_cross_routes_spike": [
        ("route_disruption", 150, 80, {"route_ids": ["route-patiya-mirpur", "route-gazipur-karnaphuli"]}),
        ("demand_spike", 150, 60, {"region_ids": ["region-chattogram"], "multiplier": 1.3}),
    ],
    "h6_delay_and_route": [
        ("shipment_delay", 100, 5, {"depot_ids": ["depot-patiya"], "delay_ticks": 24}),
        ("route_disruption", 110, 40, {"route_ids": ["route-patiya-karnaphuli"]}),
    ],
}
