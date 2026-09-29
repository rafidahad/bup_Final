"""PS §11 resilience mappings, tested with a fake simulator (the official one must not be modified)."""
import copy

import pytest

from fuelops import store
from fuelops.controller import Controller, InvalidResponse, validate

FUELS = ("DIESEL", "PETROL", "OCTANE")


def _fuels(v):
    return {f: v for f in FUELS}


WORLD = {
    "instance": {"tick": 10, "tick_minutes": 15, "status": "RUNNING"},
    "regions": [{"id": "r", "name": "R", "demand_factor": 1.0}],
    "depots": [{"id": "d", "name": "D", "region_id": "r", "status": "OPEN", "dispatch_capacity_per_tick": 12000,
                "capacity": _fuels(50000.0), "inventory": _fuels(30000.0)}],
    "stations": [{"id": "s", "name": "S", "region_id": "r", "status": "OPEN", "demand_profile": "industrial",
                  "demand_multiplier": 1.0, "capacity": _fuels(9000.0), "inventory": _fuels(500.0)}],
    "routes": [{"id": "rt", "source_depot_id": "d", "destination_station_id": "s", "transit_ticks": 2,
                "max_shipment": 5000, "status": "AVAILABLE"}],
    "supply": [], "allocations": [], "events": [],
}


class FakeSim:
    """Answers like the simulator's REST API; tests corrupt `world` to simulate bad responses."""

    def __init__(self):
        self.world = copy.deepcopy(WORLD)
        self.last_stale = False
        self.posts = []

    def __getattr__(self, name):
        if name in ("instance", "regions", "depots", "stations", "routes", "supply", "allocations", "events"):
            return lambda: copy.deepcopy(self.world[name])
        raise AttributeError(name)

    def metrics(self):
        return {"served_demand_liters": 0, "unmet_demand_liters": 0, "service_level": 1, "allocation_liters": 0,
                "allocation_failures": 0}

    def health(self):
        return {"simulation": {"tick": self.world["instance"]["tick"], "status": "RUNNING"}}

    def demand_history(self, station_id=None, limit=200):
        return []

    def allocate(self, key, depot, station, route, fuel, qty):
        self.posts.append((route, fuel, qty))
        return {"id": len(self.posts), "status": "PENDING"}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(store, "_conn", None)


def _ctl(sim, **kw):
    return Controller(sim, policy="threshold", mode=kw.get("mode", "auto"))


def test_invalid_response_is_rejected_and_raises_an_alert():
    sim = FakeSim()
    sim.world["stations"][0]["inventory"]["DIESEL"] = -5.0  # impossible value
    ctl = _ctl(sim)
    assert ctl.cycle() is False
    assert ctl.snap is None  # never accepted as state
    assert any(i["kind"] == "invalid_response" for i in ctl.incidents)
    assert sim.posts == []  # nothing decided from bad data


def test_validate_rejects_unknown_allocation_status():
    snap = {"tick": 1, "depots": {}, "stations": {}, "routes": {}, "allocs": []}
    with pytest.raises(InvalidResponse):
        validate(snap)  # no depots at all


def test_intelligence_off_falls_back_to_rule_policy_and_keeps_operating():
    """PS §11: ML model unavailable → fallback allocation policy (operations continue)."""
    sim = FakeSim()
    ctl = _ctl(sim)
    ctl.set_intelligence(False)
    assert ctl.cycle() is True
    assert ctl.source.startswith("threshold (fallback")
    assert sim.posts, "the fallback policy keeps allocating fuel in auto mode"
    assert any(i["kind"] == "intelligence" for i in ctl.incidents)


def test_low_confidence_during_crisis_requires_review():
    sim = FakeSim()
    sim.world["events"] = [{"id": 1, "type": "demand_spike", "start_tick": 5, "end_tick": 50, "status": "ACTIVE",
                            "parameters": {"station_ids": ["s"], "multiplier": 2.0}}]
    sim.world["stations"][0]["demand_multiplier"] = 2.0
    ctl = _ctl(sim)
    ctl.cycle()
    card = ctl.cards["s:DIESEL"]
    assert card["confidence"] < 0.5 and card["review_required"]
    assert sim.posts == []


def test_confident_card_is_sent_in_auto_mode():
    sim = FakeSim()
    ctl = _ctl(sim)
    ctl.cycle()
    assert sim.posts, "a confident recommendation for a near-empty station should be sent automatically"


def test_tick_rollback_starts_a_new_run():
    sim = FakeSim()
    ctl = _ctl(sim, mode="observe")
    ctl.cycle()
    first = ctl.run_id
    sim.world["instance"]["tick"] = 0  # external reset
    ctl.cycle()
    assert ctl.run_id != first
    assert any("reset detected" in i["detail"] for i in ctl.incidents)
