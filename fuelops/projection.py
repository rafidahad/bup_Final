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
