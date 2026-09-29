"""Chronos demand forecasts in shadow mode (plan Revision 5, P2/P3). Pretrained model, no training.

The forecaster runs in its own container. This client sends it demand history from a background thread
(never under the controller lock), validates what comes back, and scores every forecast against the
demand that later actually happens — side by side with the published formula. The optimizer keeps using
the formula unless Chronos passes the promotion gate (P4 is not built in this cut, so promotion is reported only).

Spikes: history is divided by the demand multiplier that applied at each tick (recorded from snapshots),
Chronos forecasts that base demand, and the known future multiplier is applied once afterwards.
"""
import math
import os
import threading
import time

import httpx

from . import metrics as M
from .projection import nominal
from .sim import FUELS

URL = os.environ.get("FORECAST_URL", "http://localhost:8200")
ENABLED = os.environ.get("FORECAST_ENABLED", "true").lower() == "true"
CONTEXT, MIN_CONTEXT, HORIZON, REFRESH = 288, 96, 96, 8
EVAL_LEAD = 32          # score the first 8 simulated hours of each forecast
PROMOTE_MIN_POINTS = 96 * 12


class ForecastClient:
    def __init__(self, url=URL, enabled=ENABLED):
        self.url, self.enabled = url.rstrip("/"), enabled
        self.http = httpx.Client(timeout=httpx.Timeout(30.0, connect=3.0))
        self.lock = threading.Lock()
        self.job = None                      # latest pending request only (older ones are dropped)
        self.wake = threading.Event()
        self.bundle = None                   # latest valid forecast
        self.bundles = []                    # recent bundles, for scoring
        self.status = {"state": "starting", "detail": None, "latency_ms": None, "last_ok_wall": None}
        self.last_request_tick = None
        self.score = {"n": 0, "chronos_abs": 0.0, "formula_abs": 0.0, "covered": 0}
        self.scored = set()
        if enabled:
            threading.Thread(target=self._run, daemon=True).start()
        else:
            self.status["state"] = "disabled"

    # ---- called by the controller (cheap, non-blocking) -----------------------------------------
    def maybe_request(self, snap, noise):
        if not self.enabled or (self.last_request_tick is not None and snap["tick"] - self.last_request_tick < REFRESH):
            return
        job = build_job(snap, noise)
        if job is None:
            self.status.update(state="waiting", detail=f"needs {MIN_CONTEXT} ticks of demand history")
            return
        self.last_request_tick = snap["tick"]
        with self.lock:
            self.job = job
        self.wake.set()

    def invalidate(self, reason):
        with self.lock:
            self.bundle = None
        self.last_request_tick = None
        self.status.update(detail=reason)

    # ---- worker thread ------------------------------------------------------------------------------
    def _run(self):
        while True:
            self.wake.wait(timeout=5)
            self.wake.clear()
            with self.lock:
                job, self.job = self.job, None
            if job is None:
                self._probe_health()
                continue
            t0 = time.perf_counter()
            try:
                r = self.http.post(f"{self.url}/forecast", json=job["request"])
                r.raise_for_status()
                bundle = to_bundle(job, r.json())
            except (httpx.HTTPError, ValueError, KeyError) as e:
                M.FORECAST_ERRORS.labels(type(e).__name__).inc()
                self.status.update(state="down" if isinstance(e, httpx.TransportError) else "error",
                                   detail=f"{type(e).__name__}: {str(e)[:160]}; the formula is used")
                continue
            dt = time.perf_counter() - t0
            M.FORECAST_SECONDS.observe(dt)
            with self.lock:
                self.bundle = bundle
                self.bundles = (self.bundles + [bundle])[-24:]
            self.status.update(state="ok", detail=None, latency_ms=round(dt * 1000), last_ok_wall=time.time())

    def _probe_health(self):
        try:
            h = self.http.get(f"{self.url}/health", timeout=3).json()
            if h.get("status") != "ok":
                self.status.update(state=h.get("status", "error"), detail=h.get("detail"))
            elif self.status["state"] in ("starting", "down", "error", "loading"):
                self.status.update(state="ok", detail=None)
        except httpx.HTTPError as e:
            self.status.update(state="down", detail=f"forecaster unreachable ({type(e).__name__}); the formula is used")

    # ---- scoring against what actually happened --------------------------------------------------
    def score_rows(self, snap, noise, rows):
        """rows: new history rows (station, fuel, tick, demand). Compare Chronos q50 and the formula."""
        region = {r["id"]: r["demand_factor"] for r in snap["regions"]}
        with self.lock:
            bundles = list(self.bundles)
        for sid, f, t, actual in rows:
            if (sid, f, t) in self.scored or actual <= 0:
                continue
            b = next((b for b in reversed(bundles) if b["cutoff"] < t <= b["cutoff"] + EVAL_LEAD), None)
            st = snap["stations"].get(sid)
            m = noise._mult_at(sid, t)
            if b is None or st is None or m is None or (sid, f) not in b["q50"]:
                continue
            i = t - b["start"]
            q50, q10, q90 = b["q50"][(sid, f)][i], b["q10"][(sid, f)][i], b["q90"][(sid, f)][i]
            formula = nominal({**st, "demand_multiplier": m}, f, t, region[st["region_id"]], snap["tick_minutes"])
            self.scored.add((sid, f, t))
            s = self.score
            s["n"] += 1
            s["chronos_abs"] += abs(q50 - actual) / actual
            s["formula_abs"] += abs(formula - actual) / actual
            s["covered"] += q10 <= actual <= q90
        if len(self.scored) > 20000:
            self.scored = {k for k in self.scored if k[2] > snap["tick"] - 400}
        s = self.score
        if s["n"]:
            M.FORECAST_MAPE.labels("chronos").set(s["chronos_abs"] / s["n"])
            M.FORECAST_MAPE.labels("formula").set(s["formula_abs"] / s["n"])
            M.FORECAST_COVERAGE.set(s["covered"] / s["n"])

    def evaluation(self):
        s = self.score
        if not s["n"]:
            return {"points": 0, "chronos_mape": None, "formula_mape": None, "coverage_10_90": None,
                    "promoted": False, "verdict": "Not enough forecasts have come true yet to compare."}
        c, f, cov = s["chronos_abs"] / s["n"], s["formula_abs"] / s["n"], s["covered"] / s["n"]
        enough = s["n"] >= PROMOTE_MIN_POINTS
        promoted = enough and c <= f and 0.70 <= cov <= 0.95
        verdict = ("Chronos is at least as accurate as the formula and its range is well calibrated."
                   if promoted else
                   "Still collecting evidence." if not enough else
                   "The published formula is more accurate, so the planner keeps using it." if c > f else
                   "Chronos' 10–90% range is not well calibrated yet.")
        return {"points": s["n"], "chronos_mape": c, "formula_mape": f, "coverage_10_90": cov,
                "promoted": promoted, "verdict": verdict}


def _future_multiplier(snap, sid):
    """Multiplier per future tick from public events: active spikes end, scheduled spikes start."""
    st = snap["stations"][sid]
    now = st["demand_multiplier"]
    changes = []
    for e in snap["events"]:
        if e["type"] != "demand_spike" or e["status"] == "RESOLVED":
            continue
        p = e["parameters"]
        hits = (not p.get("station_ids") and not p.get("region_ids")) or sid in p.get("station_ids", []) \
            or st["region_id"] in p.get("region_ids", [])
        if not hits:
            continue
        m = float(p.get("multiplier", 1.5))
        if e["status"] == "ACTIVE":
            changes.append((e["end_tick"], 1 / m))
        else:
            changes += [(e["start_tick"], m), (e["end_tick"], 1 / m)]

    def at(t):
        v = now
        for tick, factor in changes:
            if t >= tick:
                v *= factor
        return v
    return at


def build_job(snap, noise):
    """Latest contiguous, multiplier-normalised demand history per station/fuel (≤ CONTEXT ticks)."""
    series, meta = [], {}
    by_sf = {}
    for sid, f, t, d in noise.rows.values():
        by_sf.setdefault((sid, f), {})[t] = d
    for sid in snap["stations"]:
        for f in FUELS:
            hist = by_sf.get((sid, f), {})
            if not hist:
                return None
            last = max(hist)
            values, t = [], last
            while t in hist and len(values) < CONTEXT:
                m = noise._mult_at(sid, t)
                if m is None or m <= 0:
                    break
                values.append(hist[t] / m)
                t -= 1
            if len(values) < MIN_CONTEXT:
                return None
            values.reverse()
            series.append({"id": f"{sid}|{f}", "start_tick": last - len(values) + 1, "values": values})
            meta[(sid, f)] = last
    cutoff = min(meta.values())  # common cut-off: never let one series see further than another
    for s in series:
        extra = s["start_tick"] + len(s["values"]) - 1 - cutoff
        if extra > 0:
            s["values"] = s["values"][:-extra]
    horizon = HORIZON + (snap["tick"] - cutoff) + REFRESH
    return {"cutoff": cutoff, "view_tick": snap["tick"], "tick_minutes": snap["tick_minutes"],
            "mult": {sid: _future_multiplier(snap, sid) for sid in snap["stations"]},
            "request": {"tick_minutes": snap["tick_minutes"], "horizon": horizon, "series": series}}


def to_bundle(job, resp):
    """Validate the service answer; apply the future multiplier once; reject anything malformed."""
    q = {"q10": {}, "q50": {}, "q90": {}}
    start = job["cutoff"] + 1
    horizon = job["request"]["horizon"]
    for s in resp["series"]:
        sid, f = s["id"].split("|")
        if s["start_tick"] != start or any(len(s[k]) != horizon for k in q):
            raise ValueError(f"forecast for {s['id']} has the wrong ticks")
        mult = job["mult"][sid]
        vals = {}
        for k in q:
            row = s[k]
            if any(not math.isfinite(x) or x < -1.0 for x in row):
                raise ValueError(f"forecast for {s['id']} has invalid values")
            vals[k] = [max(0.0, x) * mult(start + i) for i, x in enumerate(row)]
        if any(not (a <= b + 1e-6 <= c + 2e-6) for a, b, c in zip(vals["q10"], vals["q50"], vals["q90"])):
            raise ValueError(f"forecast for {s['id']} has crossing quantiles")
        for k in q:
            q[k][(sid, f)] = vals[k]
    if len(q["q50"]) != len(job["request"]["series"]):
        raise ValueError("forecast is missing series")
    return {"cutoff": job["cutoff"], "start": start, "horizon": horizon, "issued_view_tick": job["view_tick"],
            "model": resp.get("model"), "revision": resp.get("revision"), "service_ms": resp.get("latency_ms"), **q}
