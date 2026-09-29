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
import json
import threading
import time
import uuid
from collections import deque

import httpx

from . import metrics as M
from . import store
from .decisions import AT_RISK, build_cards
from .execute import Executor, _pool, snapshot
from .forecast import ForecastClient
from .summary import CaseBook, SummaryWorker
from .intel import GUIDE_NOISE, NoiseModel, detect
from .policies import POLICIES, threshold
from .sim import FUELS, Sim, SimError

MODES = ("observe", "manual", "auto")
INTENTS = store.DB_PATH.parent / "intents"
ALLOC_STATUS = {"PENDING", "IN_TRANSIT", "ARRIVED", "FAILED", "CANCELLED"}
BREAKER_AFTER, BREAKER_SECONDS = 5, 2.0


class InvalidResponse(Exception):
    pass


class PlanChanged(Exception):
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
        self.lags, self.lag_tick = deque(maxlen=8), None
        self.intel_enabled, self.source = True, policy
        self.alerts, self.cards, self.last_proposals = [], {}, []
        self.mape = None
        self.sim_metrics, self.ref_snap, self.world_sig = None, None, None
        self.forecast = ForecastClient()  # one per app, survives runs
        self.summaries = SummaryWorker()
        self.cases = CaseBook(self.summaries)
        try:
            self.resume = store.get_meta("run")  # {run_id, tick} of the run before this app start
        except Exception:  # noqa: BLE001
            self.resume = None
        self._new_run("start")

    # ---- run lifecycle ----------------------------------------------------------------------------
    def _new_run(self, reason, run_id=None):
        self.policy = _make(self.policy_name)
        self.run_id = run_id or uuid.uuid4().hex[:8]
        INTENTS.mkdir(parents=True, exist_ok=True)  # durable volume, not reports/ (survives container rebuilds)
        self.executor = Executor(self.sim, self.run_id, INTENTS / f"{self.run_id}.jsonl",
                                 reserve_incoming=getattr(self.policy, "reserve_incoming", True))
        self.noise = NoiseModel()
        if hasattr(self, "forecast"):
            self.forecast.invalidate("simulation restarted")
            self.forecast.bundles = []
        self.last_tick = self.last_history_tick = self.prev = self.ref_snap = None
        self.cards, self.last_proposals, self.alerts = {}, [], []
        self._incident("run", f"new run {self.run_id} ({reason})")

    def _resume_or_start(self, tick):
        """After an app restart: same simulator world (tick did not go back) -> continue the run and
        reconcile shipments whose outcome was unknown; otherwise keep the fresh run."""
        prev, self.resume = self.resume, None
        if not prev or tick < prev.get("tick", 0):
            return
        self._new_run(f"continued after app restart at tick {tick}", run_id=prev["run_id"])
        state = {}
        journal = INTENTS / f"{prev['run_id']}.jsonl"
        if journal.exists():
            for line in journal.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                key = r.get("idempotency_key") or r.get("key")
                if key:
                    state[key] = r.get("state")
        unknown = [k for k, st in state.items() if st in ("SENDING", "UNKNOWN_OUTCOME")]
        if not unknown:
            return
        ledger = {a["idempotency_key"]: a for a in self.sim.allocations()}
        for k in unknown:
            a = ledger.get(k)
            self._incident("reconciled", f"shipment {k}: " + (
                f"accepted by the simulator (#{a['id']}, {a['status'].lower()})" if a
                else "never reached the simulator; not re-sent"))

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
                if self.resume is not None:
                    self._resume_or_start(tick)
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
                self._update_cases()
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
            if snap["tick"] % 4 == 0:
                store.set_meta("run", {"run_id": self.run_id, "tick": snap["tick"]})
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
        # every 32 ticks: 200 rows per station cover ~66 ticks, and each pull costs a round trip per station
        if self.last_history_tick is not None and snap["tick"] - self.last_history_tick < 32:
            return
        limit = 2000 if self.last_history_tick is None else 200  # first pull after start: as much as allowed
        try:
            new = []
            for rows in _pool.map(lambda sid: self.sim.demand_history(sid, limit), list(snap["stations"])):
                new += self.noise.add_history(rows, snap)
            self.last_history_tick = snap["tick"]
            self.forecast.score_rows(snap, self.noise, new)
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
        if self.world_sig is not None and sig != self.world_sig:
            self.forecast.invalidate("conditions changed")
        if self.world_sig is not None and sig != self.world_sig and hasattr(self.policy, "invalidate"):
            self.policy.invalidate()
            self._incident("replan", "world changed (event, multiplier, route, station, depot or supply) → re-solving now")
        self.world_sig = sig
        if self.intel_enabled:
            self._pull_history(snap)
            stats, self.mape = self.noise.stats(snap)
            self.forecast.maybe_request(snap, self.noise)
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
        self._update_cases()
        if self.mode == "auto":
            # most urgent first: dispatch budget is shared per depot per tick
            urgent = sorted(self.cards.values(), key=lambda c: (-c["before"]["risk"], c["before"]["stockout_hours"] or 1e9))
            for card in urgent:
                if not card["allocations"]:
                    continue
                if not card["review_required"]:
                    self._execute_card(snap, card, "auto_approved", "controller")
                elif card["before"]["stockout_hours"] is not None or card["before"]["risk"] >= AT_RISK:
                    # low confidence but a stockout is coming: holding it would cost the demand (PS §11 review
                    # still happens — the decision is recorded as low-confidence for the operator to check)
                    self._execute_card(snap, card, "auto_low_confidence", "controller")

    def clock(self, tick):
        tm = self.snap["tick_minutes"] if self.snap else 15
        mins = tick * tm
        return f"Day {mins // 1440 + 1}, {mins % 1440 // 60:02d}:{mins % 60:02d}"

    def _update_cases(self):
        if self.snap is None:
            return
        try:
            self.cases.update(self.snap, self.cards, self.alerts, self.run_id, self.degraded, self.intel_enabled, self.clock)
        except Exception as e:  # noqa: BLE001 — summaries must never stop operations
            self.incidents.append({"wall": time.time(), "tick": self.snap["tick"], "kind": "error",
                                   "detail": f"incident summary bookkeeping failed: {e!r}"[:200]})

    @staticmethod
    def _alert_key(a):
        return (a["kind"], a.get("station_id"), a.get("fuel"), a.get("depot_id"), a.get("event_id"))

    # ---- acting -----------------------------------------------------------------------------------
    def _execute_card(self, snap, card, status, who):
        wants = [(a["route_id"], card["fuel"], a["liters"]) for a in card["allocations"]]
        sent_by = self.executor.execute(snap, wants)
        sent = sum(sent_by.values())
        # keep what could not be sent this tick (e.g. depot dispatch budget used up); it goes next tick
        left = []
        for r, f, q in self.last_proposals:
            rest = q - sent_by.get((r, f), 0.0) if f == card["fuel"] and any(a["route_id"] == r for a in card["allocations"]) else q
            if rest > 1:
                left.append((r, f, rest))
        self.last_proposals = left
        self.cards.pop(card["id"], None)
        if sent > 0 or status != "auto_approved":
            store.record_decision(self.run_id, snap["tick"], card, status, who,
                                  {"liters_accepted": sent, "executor_rejections": dict(self.executor.stats["rejected"])})
            M.DECISIONS.labels(status).inc()
            M.SHIPPED_LITERS.inc(sent)
            self._measure_lag(snap["tick"])
        return sent

    def approve(self, card_id, seen, who="operator"):
        """Operator approval (PS §24) of exactly the shipments the operator saw.

        seen = [{route_id, liters}] from the screen. If the current plan differs materially (other roads,
        or more than 10% / 250 L different) the approval is refused (PlanChanged -> HTTP 409) instead of
        executing a plan nobody reviewed. Revalidates against a fresh snapshot before any POST."""
        with self.lock:
            if self.mode == "observe":
                raise PermissionError("Observe mode: switch to manual or auto to act")
            card = self.cards.get(card_id)
            if card is None or not card["allocations"]:
                raise KeyError(card_id)
            now = {a["route_id"]: a["liters"] for a in card["allocations"]}
            saw = {a["route_id"]: float(a["liters"]) for a in seen}
            if set(now) != set(saw) or any(abs(now[r] - saw[r]) > max(250.0, 0.1 * saw[r]) for r in saw):
                raise PlanChanged(f"The plan changed since you looked (now {now}); please review it again")
            approved = {**card, "allocations": [{**a, "liters": saw[a["route_id"]]} for a in card["allocations"]]}
            snap = snapshot(self.sim)
            validate(snap)
            return self._execute_card(snap, approved, "approved", who)

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
        if snap_tick == self.lag_tick:
            return  # one health read per cycle, not per card (each read waits behind simulator steps)
        self.lag_tick = snap_tick
        try:
            now = self.sim.health()["simulation"]["tick"]  # fault-exempt
        except httpx.TransportError:
            return
        self.lags.append(now - snap_tick)
        if hasattr(self.policy, "exec_delay"):
            # cap 64, not 16: an externally stepped simulator was measured at 29–54 ticks of lag
            self.policy.exec_delay = min(64, max(self.lags) + 1)
        self.executor.lookahead = max(1, max(self.lags) + 1)  # don't POST onto a road that closes before it lands

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
