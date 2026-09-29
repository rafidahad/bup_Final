"""Recommendation cards (plan Revision 4, R4.4; PS §9): why at risk, signals, recommended allocation,
binding constraints, expected impact (what-if), confidence, alternatives."""
import math
from collections import defaultdict

from .execute import blocked_routes, incoming_total
from .intel import confidence, project
from .sim import FUELS

HORIZON_HOURS = 12    # risk window in simulated hours (converted with the live tick size)
REVIEW_BELOW = 0.5    # PS §11: low confidence → human review
AT_RISK = 0.2         # risk threshold for a card without any proposal


def build_cards(snap, proposals, noise_stats, degraded, source):
    by_sf = defaultdict(list)
    for route_id, fuel, liters in proposals:
        r = snap["routes"][route_id]
        by_sf[(r["destination_station_id"], fuel)].append((r, liters))
    blocked = blocked_routes(snap)
    tick = snap["tick"]
    budget = {d: dep["dispatch_capacity_per_tick"] for d, dep in snap["depots"].items()}
    for a in snap["allocs"]:
        if a["created_tick"] == tick and a["status"] != "CANCELLED":
            budget[a["source_depot_id"]] -= a["quantity"]

    cards = {}
    horizon = max(1, round(HORIZON_HOURS * 60 / snap.get("tick_minutes", 15)))
    for sid, st in snap["stations"].items():
        sigma, n = noise_stats.get(st["demand_profile"], (0.1, 0))
        for f in FUELS:
            before = project(snap, sid, f, horizon, sigma=sigma)
            wants = by_sf.get((sid, f), [])
            if not wants and before["risk"] < AT_RISK and before["stockout_hours"] is None:
                continue
            events = [e for e in snap["events"] if e["status"] == "ACTIVE" and _touches(e, snap, sid)]
            conf = confidence(n, degraded, bool(events))
            headroom = st["capacity"][f] - st["inventory"][f] - incoming_total(snap, sid, f)
            allocations, extra = [], []
            for r, liters in wants:
                d = snap["depots"][r["source_depot_id"]]
                limits = {"depot stock": d["inventory"][f], "dispatch budget this tick": budget[d["id"]],
                          "destination headroom": headroom}
                binding = min(limits, key=limits.get)
                arrival = tick + r["transit_ticks"]  # C02: departs in the creation tick
                allocations.append({"route_id": r["id"], "depot_id": d["id"], "liters": round(liters),
                                    "transit_ticks": r["transit_ticks"], "arrival_tick": arrival,
                                    "requests": math.ceil(liters / r["max_shipment"]), "limits": limits,
                                    "binding": binding if liters >= 0.99 * limits[binding] else None})
                extra.append((arrival, liters))
            after = project(snap, sid, f, horizon, extra=extra, sigma=sigma) if extra else None
            alternatives = []
            for r in snap["routes"].values():
                if r["destination_station_id"] != sid or any(a["route_id"] == r["id"] for a in allocations):
                    continue
                usable = r["status"] == "AVAILABLE" and r["id"] not in blocked
                liters = sum(a["liters"] for a in allocations) or min(r["max_shipment"], max(headroom, 0))
                alt = project(snap, sid, f, horizon, extra=[(tick + r["transit_ticks"], liters)], sigma=sigma) \
                    if usable and liters > 0 else None
                alternatives.append({"route_id": r["id"], "depot_id": r["source_depot_id"], "usable": usable,
                                     "reason": None if usable else "route disrupted or about to be",
                                     "transit_ticks": r["transit_ticks"], "liters": round(liters),
                                     "depot_stock": snap["depots"][r["source_depot_id"]]["inventory"][f],
                                     "risk_after": alt["risk"] if alt else None,
                                     "stockout_hours_after": alt["stockout_hours"] if alt else None})
            signals = [f"demand multiplier ×{st['demand_multiplier']:.2f}"] if st["demand_multiplier"] != 1 else []
            signals += [f"{e['type']} (event {e['id']}, until tick {e['end_tick']})" for e in events]
            if st["status"] != "OPEN":
                signals.append(f"station {st['status'].lower()}")
            cards[f"{sid}:{f}"] = {
                "id": f"{sid}:{f}", "tick": tick, "station_id": sid, "station": st["name"], "fuel": f,
                "region_id": st["region_id"], "inventory": st["inventory"][f], "capacity": st["capacity"][f],
                "incoming": incoming_total(snap, sid, f), "before": before, "after": after,
                "allocations": allocations, "alternatives": alternatives, "signals": signals,
                "confidence": conf, "noise_sigma": round(sigma, 4), "noise_rows": n, "source": source,
                "review_required": conf < REVIEW_BELOW or not allocations,
                "why": _why(before, st, f),
            }
    return cards


def _touches(e, snap, sid):
    p = e["parameters"]
    st = snap["stations"][sid]
    if e["type"] == "demand_spike":
        return (not p.get("station_ids") and not p.get("region_ids")) or sid in p.get("station_ids", []) \
            or st["region_id"] in p.get("region_ids", [])
    if e["type"] == "station_outage":
        return not p.get("station_ids") or sid in p["station_ids"]
    if e["type"] == "route_disruption":
        into = [r for r in snap["routes"].values() if r["destination_station_id"] == sid]
        return not p.get("route_ids") or any(r["id"] in p["route_ids"] for r in into)
    # depot / supply events: only stations served by an affected depot (empty filter = every depot)
    ids = p.get("depot_ids") or []
    return not ids or any(r["source_depot_id"] in ids for r in snap["routes"].values()
                          if r["destination_station_id"] == sid)


def _why(before, st, fuel):
    if st["status"] != "OPEN":
        return f"{st['name']} is closed; demand goes unmet until it reopens."
    if before["stockout_hours"] is not None:
        return (f"{fuel.title()} runs out in about {before['stockout_hours']:.1f} h: {before['expected_demand']:,.0f} L "
                f"expected demand in the next 12 h against current stock and scheduled arrivals.")
    return f"{before['risk']:.0%} chance of a stockout within 12 h given observed demand variability."
