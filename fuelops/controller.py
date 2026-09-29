"""Live operating loop (plan §10.1, §12). One controller = the one operational writer.

Polls /v1/instance; on each new tick takes a parallel snapshot, asks the policy, and in
automatic mode executes. Faults degrade instead of halting (plan §12.1):
- read failures keep the last good snapshot visible and retry next loop;
- stale_data is recorded but ignored (C15: bodies are current);
- tick going backwards = external reset (C16: no SSE notice) → new run id, fresh policy state.
"""
import threading
import time
import uuid
from collections import deque

import httpx

from .execute import Executor, snapshot
from .harness import REPORTS
from .policies import POLICIES
from .sim import Sim, SimError

MODES = ("observe", "manual", "auto")


class Controller:
    def __init__(self, sim=None, policy="lp", mode="auto"):
        assert mode in MODES
        self.sim, self.policy_name, self.mode = sim or Sim(), policy, mode
        self.lock = threading.Lock()  # one decision/execution cycle at a time
        self.incidents = deque(maxlen=200)
        self.snap, self.snap_wall, self.proposals = None, None, []
        self.degraded = None  # reason string while degraded
        self.cycles, self.last_tick = 0, None
        self.lags = deque(maxlen=8)  # ticks from snapshot to end of execution
        self._new_run("start")

    def _new_run(self, reason):
        p = POLICIES[self.policy_name]
        self.policy = p() if isinstance(p, type) or getattr(p, "__name__", "") == "<lambda>" else p
        self.run_id = uuid.uuid4().hex[:8]
        REPORTS.mkdir(exist_ok=True)
        self.executor = Executor(self.sim, self.run_id, REPORTS / f"{self.run_id}_live_intents.jsonl",
                                 reserve_incoming=getattr(self.policy, "reserve_incoming", True))
        self.last_tick = None
        self._incident("run", f"new run {self.run_id} ({reason})")

    def set_policy(self, name):
        """Switch decision policy; same run, same executor and idempotency sequence. Caller holds the lock."""
        p = POLICIES[name]
        self.policy_name = name
        self.policy = p() if isinstance(p, type) or getattr(p, "__name__", "") == "<lambda>" else p
        self.executor.reserve_incoming = getattr(self.policy, "reserve_incoming", True)
        self.proposals = []
        self._incident("policy", f"policy → {name}")

    def _incident(self, kind, detail):
        tick = self.snap["tick"] if self.snap else None
        self.incidents.append({"wall": time.time(), "tick": tick, "kind": kind, "detail": detail})

    def cycle(self):
        """One loop iteration. Returns True if a new tick was processed."""
        with self.lock:
            try:
                tick = self.sim.instance()["tick"]
                if self.last_tick is not None and tick < self.last_tick:
                    self._new_run(f"reset detected: tick {self.last_tick} → {tick}")
                if tick == self.last_tick:
                    return False
                snap = snapshot(self.sim)
            except (SimError, httpx.TransportError) as e:
                if not self.degraded:
                    self._incident("degraded", str(e)[:200])
                self.degraded = str(e)[:200]
                return False
            if self.degraded:
                self._incident("recovered", f"after: {self.degraded}")
                self.degraded = None
            if self.sim.last_stale:
                self._incident("stale_flag", "X-Simulator-Stale seen; data used (C15)")
            self.snap, self.snap_wall, self.last_tick = snap, time.time(), snap["tick"]
            self.proposals = self.policy(snap)
            if self.mode == "auto" and self.proposals:
                self.executor.execute(snap, self.proposals)
                self._measure_lag(snap["tick"])
            self.cycles += 1
            return True

    def _measure_lag(self, snap_tick):
        """Plan shipments no earlier than they can really be submitted (plan §9.5 execution window)."""
        try:
            now = self.sim.health()["simulation"]["tick"]  # fault-exempt
        except httpx.TransportError:
            return
        self.lags.append(now - snap_tick)
        if hasattr(self.policy, "exec_delay"):
            self.policy.exec_delay = min(16, max(self.lags) + 1)

    def execute_proposals(self):
        """Manual mode: approve the current proposals. Revalidates against a fresh snapshot."""
        with self.lock:
            snap = snapshot(self.sim)
            wants, self.proposals = self.proposals, []
            self.executor.execute(snap, wants)
            return len(wants)

    def run_forever(self, stop, poll=0.02):
        while not stop.is_set():
            self.cycle()
            stop.wait(poll)

    def start(self):
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self.run_forever, args=(self._stop,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()
