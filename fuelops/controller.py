"""Live operating loop (plan §10.1, §12, Revision 4). One controller = the one operational writer.

Observe → Detect → Predict → Decide → Simulate → Act → Monitor → Recover (PS §2), every new tick:
- Observe: parallel snapshot, validated (invalid response → rejected + alert, PS §11).
- Detect/Predict: rule-based detectors, stockout projection and risk from observed demand noise.
- Decide/Simulate: policy proposals → recommendation cards with what-if impact.
- Act: observe = never; manual = operator approves; auto = executes cards whose confidence is high
  enough, low-confidence cards wait for review (PS §11, §24).
- Recover: read failures keep cached state (degraded), a circuit breaker backs off after repeated
  failures, tick rollback = external reset (C16), intelligence off/failing → threshold fallback.
"""
import threading
import time
import uuid
from collections import deque

import httpx

from . import metrics as M
from . import store
from .decisions import build_cards
from .execute import Executor, _pool, snapshot
from .harness import REPORTS
from .intel import GUIDE_NOISE, NoiseModel, detect
from .policies import POLICIES, threshold
from .sim import FUELS, Sim, SimError

MODES = ("observe", "manual", "auto")
ALLOC_STATUS = {"PENDING", "IN_TRANSIT", "ARRIVED", "FAILED", "CANCELLED"}
BREAKER_AFTER, BREAKER_SECONDS = 5, 2.0


class InvalidResponse(Exception):
    pass


def validate(snap):
    """Reject simulator data that cannot be right (PS §11: invalid simulator response → reject + alert)."""
    if not isinstance(snap["tick"], int) or snap["tick"] < 0:
        raise InvalidResponse(f"bad tick {snap['tick']!r}")
    for kind in ("depots", "stations"):
        if not snap[kind]:
            raise InvalidResponse(f"no {kind}")
        for e in snap[kind].values():
            for f in FUELS:
                inv, cap = e["inventory"].get(f), e["capacity"].get(f)
                if not isinstance(inv, (int, float)) or not isinstance(cap, (int, float)) or inv < 0 or cap <= 0 \
                        or inv > cap * 1.01:
                    raise InvalidResponse(f"{e['id']} {f}: inventory {inv!r} / capacity {cap!r}")
    for r in snap["routes"].values():
        if r["transit_ticks"] < 1 or r["max_shipment"] <= 0:
            raise InvalidResponse(f"route {r['id']} has invalid limits")
    for a in snap["allocs"]:
        if a["status"] not in ALLOC_STATUS:
            raise InvalidResponse(f"allocation {a['id']} has unknown status {a['status']!r}")


def _make(name):
    p = POLICIES[name]
    return p() if isinstance(p, type) or getattr(p, "__name__", "") == "<lambda>" else p


class Controller:
    def __init__(self, sim=None, policy="lp-buffer", mode="manual"):
        assert mode in MODES
        self.sim, self.policy_name, self.mode = sim or Sim(), policy, mode
        self.lock = threading.Lock()  # one decision/execution cycle at a time
        self.incidents = deque(maxlen=300)
        self.snap = self.prev = self.snap_wall = None
        self.degraded = None
        self.failures, self.breaker_until = 0, 0.0
        self.cycles, self.last_tick, self.last_history_tick = 0, None, None
        self.lags = deque(maxlen=8)
        self.intel_enabled, self.source = True, policy
        self.alerts, self.cards, self.last_proposals = [], {}, []
        self.mape = None
        self.sim_metrics, self.ref_snap, self.world_sig = None, None, None
        self._new_run("start")

    # ---- run lifecycle ----------------------------------------------------------------------------
    def _new_run(self, reason):
        self.policy = _make(self.policy_name)
        self.run_id = uuid.uuid4().hex[:8]
        REPORTS.mkdir(exist_ok=True)
        self.executor = Executor(self.sim, self.run_id, REPORTS / f"{self.run_id}_live_intents.jsonl",
                                 reserve_incoming=getattr(self.policy, "reserve_incoming", True))
        self.noise = NoiseModel()
        self.last_tick = self.last_history_tick = self.prev = self.ref_snap = None
        self.cards, self.last_proposals, self.alerts = {}, [], []
        self._incident("run", f"new run {self.run_id} ({reason})")

    def set_policy(self, name):
        """Switch policy (also the rollback path, PS §20). Caller holds the lock."""
        self.policy_name = name
        self.policy = _make(name)
        self.executor.reserve_incoming = getattr(self.policy, "reserve_incoming", True)
        self.last_proposals, self.cards = [], {}
        self._incident("policy", f"policy → {name}")

    def set_intelligence(self, enabled):
        """Kill switch for the demo: 'ML model unavailable → fallback allocation policy' (PS §11)."""
        self.intel_enabled = enabled
        self.last_proposals, self.cards = [], {}
        self._incident("intelligence", "enabled" if enabled else "disabled → threshold fallback policy takes over allocation")
        if not enabled:
            M.FALLBACKS.labels("intelligence_disabled").inc()

    def _incident(self, kind, detail):
        tick = self.snap["tick"] if self.snap else None
        self.incidents.append({"wall": time.time(), "tick": tick, "kind": kind, "detail": detail})
        try:
            store.record_incident(self.run_id, tick, kind, detail)
        except Exception:  # noqa: BLE001 — the audit DB must never stop operations
            pass

    # ---- the loop ---------------------------------------------------------------------------------
    def cycle(self):
        """One loop iteration. Returns True if a new tick was processed."""
        with self.lock:
            if time.time() < self.breaker_until:
                return False
            M.BREAKER_OPEN.set(0)
            try:
                tick = self.sim.instance()["tick"]
                if self.last_tick is not None and tick < self.last_tick:
                    self._new_run(f"reset detected: tick {self.last_tick} → {tick}")
                if tick == self.last_tick:
                    self.failures = 0
                    return False
                t0 = time.perf_counter()
                snap = snapshot(self.sim)
                M.SIM_SNAPSHOT_SECONDS.observe(time.perf_counter() - t0)
                validate(snap)
            except InvalidResponse as e:
                M.SIM_ERRORS.labels("invalid").inc()
                self._incident("invalid_response", f"rejected simulator data: {e}")
                return False
            except (SimError, httpx.TransportError) as e:
                M.SIM_ERRORS.labels("unavailable").inc()
                self.failures += 1
                if not self.degraded:
                    self._incident("degraded", f"simulator unreachable, showing cached state: {str(e)[:160]}")
                self.degraded = str(e)[:200]
                M.DEGRADED.set(1)
                if self.failures >= BREAKER_AFTER:
                    self.breaker_until = time.time() + BREAKER_SECONDS
                    M.BREAKER_OPEN.set(1)
                return False
            self.failures = 0
            if self.degraded:
                self._incident("recovered", f"simulator reachable again after: {self.degraded[:120]}")
                self.degraded = None
                M.DEGRADED.set(0)
            if self.sim.last_stale:
                self._incident("stale_flag", "X-Simulator-Stale seen; data used (C15: bodies are current)")
            self.prev, self.snap, self.snap_wall, self.last_tick = self.snap, snap, time.time(), snap["tick"]
            M.SIM_TICK.set(snap["tick"])
            if self.sim_metrics is None or snap["tick"] % 4 == 0:
                try:
                    self.sim_metrics = self.sim.metrics()  # cached for the API: load tests never hit the simulator
                except (SimError, httpx.TransportError):
                    pass
            try:
                self._decide(snap)
            except (SimError, httpx.TransportError) as e:  # writes failing: simulator went down mid-batch
                M.SIM_ERRORS.labels("write").inc()
                self.failures += 1
                if not self.degraded:
                    self._incident("degraded", f"shipment requests failing, batch stopped: {str(e)[:150]}")
                self.degraded = str(e)[:200]
                M.DEGRADED.set(1)
                return False
            self.cycles += 1
            M.DECISION_CYCLES.inc()
            return True

    def _pull_history(self, snap):
        if self.last_history_tick is not None and snap["tick"] - self.last_history_tick < 8:
            return
        try:
            for rows in _pool.map(lambda sid: self.sim.demand_history(sid, 200), list(snap["stations"])):
                self.noise.add_history(rows, snap)
            self.last_history_tick = snap["tick"]
        except (SimError, httpx.TransportError):
            M.SIM_ERRORS.labels("history").inc()

    @staticmethod
    def _world_signature(snap):
        """What the plan depends on besides stock: events, multipliers, route/station/depot status, supply."""
        return (tuple((e["id"], e["status"]) for e in snap["events"]),
                tuple((s, st["status"], st["demand_multiplier"]) for s, st in sorted(snap["stations"].items())),
                tuple((r, rt["status"]) for r, rt in sorted(snap["routes"].items())),
                tuple((d, dep["status"]) for d, dep in sorted(snap["depots"].items())),
                tuple((x["id"], x["planned_tick"], x["quantity"]) for x in snap["supply"] if x["status"] != "ARRIVED"))

    def _decide(self, snap):
        self.noise.observe_snapshot(snap)
        sig = self._world_signature(snap)
        if self.world_sig is not None and sig != self.world_sig and hasattr(self.policy, "invalidate"):
            self.policy.invalidate()
            self._incident("replan", "world changed (event, multiplier, route, station, depot or supply) → re-solving now")
        self.world_sig = sig
        if self.intel_enabled:
            self._pull_history(snap)
            stats, self.mape = self.noise.stats(snap)
            if self.mape is not None:
                M.PREDICTION_MAPE.set(self.mape)
            proposals = self.policy(snap)
            solves = getattr(self.policy, "log", None)
            if solves and solves[-1]["tick"] == snap["tick"]:
                M.SOLVE_SECONDS.observe(solves[-1]["seconds"])
                if solves[-1]["status"] != 0:
                    M.FALLBACKS.labels("solver").inc()
                    self._incident("fallback", f"optimizer status {solves[-1]['status']} → threshold fallback")
            fell_back = bool(solves) and solves[-1]["status"] != 0
            self.source = "threshold (fallback)" if fell_back else self.policy_name
        else:
            stats = {p: (s, 0) for p, s in GUIDE_NOISE.items()}  # no measured statistics → confidence 0
            proposals = threshold(snap)
            self.source = "threshold (fallback: intelligence disabled)"
        if proposals:
            self.last_proposals = proposals
        budget_used = {d: 0.0 for d in snap["depots"]}
        for a in snap["allocs"]:
            if a["created_tick"] == snap["tick"] and a["status"] != "CANCELLED":
                budget_used[a["source_depot_id"]] += a["quantity"]
        if self.ref_snap is None or snap["tick"] - self.ref_snap["tick"] > 16:
            self.ref_snap = snap
        alerts = detect(snap, self.ref_snap, stats, list(self.noise.rows.values()), budget_used)             if self.intel_enabled else []
        if snap["tick"] - self.ref_snap["tick"] >= 8:
            self.ref_snap = snap
        old = {self._alert_key(a) for a in self.alerts}
        for a in alerts:
            if self._alert_key(a) not in old:
                M.ALERTS.labels(a["kind"]).inc()
                self._incident("alert", f"{a['kind']}: {a['detail']}")
        self.alerts = alerts
        M.ACTIVE_ALERTS.set(len(alerts))
        self.cards = build_cards(snap, self.last_proposals, stats, bool(self.degraded), self.source)
        M.OPEN_RECOMMENDATIONS.set(sum(1 for c in self.cards.values() if c["allocations"]))
        confs = [c["confidence"] for c in self.cards.values()]
        M.MEAN_CONFIDENCE.set(sum(confs) / len(confs) if confs else 0)
        if self.mode == "auto":
            for card in list(self.cards.values()):
                if card["allocations"] and not card["review_required"]:
                    self._execute_card(snap, card, "auto_approved", "controller")

    @staticmethod
    def _alert_key(a):
        return (a["kind"], a.get("station_id"), a.get("fuel"), a.get("depot_id"), a.get("event_id"))

    # ---- acting -----------------------------------------------------------------------------------
    def _execute_card(self, snap, card, status, who):
        before = self.executor.stats["liters"]
        wants = [(a["route_id"], card["fuel"], a["liters"]) for a in card["allocations"]]
        self.executor.execute(snap, wants)
        sent = self.executor.stats["liters"] - before
        done = {(a["route_id"], card["fuel"]) for a in card["allocations"]}
        self.last_proposals = [p for p in self.last_proposals if (p[0], p[1]) not in done]
        self.cards.pop(card["id"], None)
        if sent > 0 or status != "auto_approved":
            store.record_decision(self.run_id, snap["tick"], card, status, who,
                                  {"liters_accepted": sent, "executor_rejections": dict(self.executor.stats["rejected"])})
            M.DECISIONS.labels(status).inc()
            M.SHIPPED_LITERS.inc(sent)
            self._measure_lag(snap["tick"])
        return sent

    def approve(self, card_id, who="operator"):
        """Operator approval (PS §24). Revalidates against a fresh snapshot before any POST."""
        with self.lock:
            if self.mode == "observe":
                raise PermissionError("Observe mode: switch to manual or auto to act")
            card = self.cards.get(card_id)
            if card is None or not card["allocations"]:
                raise KeyError(card_id)
            snap = snapshot(self.sim)
            validate(snap)
            return self._execute_card(snap, card, "approved", who)

    def reject(self, card_id, who="operator"):
        with self.lock:
            card = self.cards.pop(card_id, None)
            if card is None:
                raise KeyError(card_id)
            done = {(a["route_id"], card["fuel"]) for a in card["allocations"]}
            self.last_proposals = [p for p in self.last_proposals if (p[0], p[1]) not in done]
            store.record_decision(self.run_id, self.snap["tick"] if self.snap else None, card, "rejected", who)
            M.DECISIONS.labels("rejected").inc()

    def _measure_lag(self, snap_tick):
        """Plan shipments no earlier than they can really be submitted (plan §9.5 execution window)."""
        try:
            now = self.sim.health()["simulation"]["tick"]  # fault-exempt
        except httpx.TransportError:
            return
        self.lags.append(now - snap_tick)
        if hasattr(self.policy, "exec_delay"):
            self.policy.exec_delay = min(16, max(self.lags) + 1)

    # ---- thread -----------------------------------------------------------------------------------
    def run_forever(self, stop, poll=0.02):
        while not stop.is_set():
            try:
                self.cycle()
            except Exception as e:  # noqa: BLE001 — the loop must survive; the error is visible as an incident
                self._incident("error", f"controller cycle failed: {e!r}"[:300])
                stop.wait(0.5)
            stop.wait(poll)

    def start(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.run_forever, args=(self._stop,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def alive(self):
        return getattr(self, "_thread", None) is not None and self._thread.is_alive()
