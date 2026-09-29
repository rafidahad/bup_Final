"""Deterministic demand projection from the published formula (plan §8.2). No learning."""

DAILY = {  # liters per simulated day, guide §8.5
    "urban_high": {"DIESEL": 8500, "PETROL": 10500, "OCTANE": 5600},
    "industrial": {"DIESEL": 14000, "PETROL": 4500, "OCTANE": 2200},
    "highway": {"DIESEL": 10500, "PETROL": 11000, "OCTANE": 6200},
    "regional": {"DIESEL": 7200, "PETROL": 7600, "OCTANE": 3600},
}

BUSY = {  # guide §8.6: (busy hours, busy factor, off-peak factor)
    "industrial": (set(range(6, 18)), 1.55, 0.45),
    "highway": (set(range(6, 10)) | set(range(16, 21)), 1.35, 0.75),
    "urban_high": (set(range(7, 10)) | set(range(16, 21)), 1.45, 0.70),
    "regional": (set(range(7, 21)), 1.25, 0.65),
}


def hour_factor(profile, tick, tick_minutes=15):
    hours, busy, off = BUSY[profile]
    # sim_time starts at 00:00 on tick 0 (guide §4.2); demand uses the tick's start hour (checked by residuals)
    return busy if (tick * tick_minutes // 60) % 24 in hours else off


def nominal(station, fuel, tick, region_factor, tick_minutes=15, stress=1.0):
    p = station["demand_profile"]
    return (DAILY[p][fuel] * tick_minutes / 1440 * hour_factor(p, tick, tick_minutes)
            * region_factor * station["demand_multiplier"] * stress)


def closed_ticks(snap, station_id):
    """Function t -> True while the station cannot sell (C09: demand unmet, stock frozen, arrivals still land).

    Uses the current status plus public station_outage events (active or scheduled). A station that is
    closed now with no visible end is treated as closed for the whole horizon."""
    windows = []
    for e in snap.get("events", ()):
        ids = e["parameters"].get("station_ids") or []
        if e["type"] == "station_outage" and e["status"] != "RESOLVED" and (not ids or station_id in ids):
            windows.append((e["start_tick"], e["end_tick"]))
    closed_now = snap["stations"][station_id]["status"] != "OPEN"
    if closed_now and not any(a <= snap["tick"] < b for a, b in windows):
        windows.append((snap["tick"], 10 ** 9))
    return lambda t: any(a <= t < b for a, b in windows)


def route_closed_ticks(snap, route_id):
    """Function t -> True while the route is disrupted (public route_disruption events, window [start, end), C08).
    A route disrupted now with no visible end is treated as closed for the whole horizon."""
    windows = []
    for e in snap.get("events", ()):
        ids = e["parameters"].get("route_ids") or []
        if e["type"] == "route_disruption" and e["status"] != "RESOLVED" and (not ids or route_id in ids):
            windows.append((e["start_tick"], e["end_tick"]))
    if snap["routes"][route_id]["status"] != "AVAILABLE" and not any(a <= snap["tick"] < b for a, b in windows):
        windows.append((snap["tick"], 10 ** 9))
    return lambda t: any(a <= t < b for a, b in windows)


def _spike_hits(e, station, region_id):
    p = e["parameters"]
    return ((not p.get("station_ids") or station["id"] in p["station_ids"])
            and (not p.get("region_ids") or region_id in p["region_ids"]))


def multiplier_change(snap, station):
    """Function t -> factor on top of the station's current demand_multiplier (C12: spikes multiply).
    Scheduled spikes apply inside their window; active ones are divided back out from their end tick."""
    spikes = [(e["start_tick"], e["end_tick"], e["status"], e["parameters"].get("multiplier", 1.5))
              for e in snap.get("events", ())
              if e["type"] == "demand_spike" and e["status"] != "RESOLVED" and _spike_hits(e, station, station["region_id"])]

    def factor(t):
        f = 1.0
        for start, end, status, m in spikes:
            if status == "SCHEDULED" and start <= t < end:
                f *= m
            elif status == "ACTIVE" and t >= end:
                f /= m
        return f
    return factor


def supply_after_events(snap):
    """Supply rows not yet arrived, with scheduled shipment_delay / supply_shortfall applied as the simulator
    will at activation (C13: every not-yet-arrived row of the filtered depots/fuels; one-shot)."""
    rows = [dict(s) for s in snap["supply"] if s["status"] != "ARRIVED"]
    for e in sorted(snap.get("events", ()), key=lambda e: e["start_tick"]):
        if e["status"] != "SCHEDULED" or e["type"] not in ("shipment_delay", "supply_shortfall"):
            continue
        p = e["parameters"]
        for s in rows:
            if s["planned_tick"] < e["start_tick"]:
                continue  # arrives before the event starts
            if (p.get("depot_ids") and s["depot_id"] not in p["depot_ids"]) or \
               (p.get("fuel_types") and s["fuel_type"] not in p["fuel_types"]):
                continue
            if e["type"] == "shipment_delay":
                s["planned_tick"] += p.get("delay_ticks", 2)
            else:
                s["quantity"] *= p.get("factor", 0.5)
    return rows
