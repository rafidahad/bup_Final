"""Incident summaries with an LLM on Groq (plan Revision 5, P5). The LLM only explains; it never decides or acts.

Cases: each public crisis event, each simulator outage, each switch-off of smart planning. A case gets a new
version when its state changes (starts, resolves, recovers). Every version gets one bounded evidence packet
built from our own records, a background call to Groq's OpenAI-compatible chat completions endpoint with a
strict JSON schema (model openai/gpt-oss-120b by default), evidence-id checks, and a factual template if the
LLM is disabled, has no key, fails, or answers with unsupported references.
"""
import hashlib
import json
import os
import pathlib
import queue
import threading
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import metrics as M
from . import store

ENABLED = os.environ.get("SUMMARIES_ENABLED", "true").lower() == "true"
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
TIMEOUT = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "20"))
MAX_ATTEMPTS = int(os.environ.get("GROQ_MAX_ATTEMPTS", "2"))
PER_MINUTE = int(os.environ.get("GROQ_MAX_CALLS_PER_MINUTE", "6"))
MAX_OUTPUT_TOKENS = int(os.environ.get("GROQ_MAX_OUTPUT_TOKENS", "2000"))  # includes the model's reasoning tokens

# Groq strict mode: every field required, additionalProperties false, plain types (lengths enforced by us below).
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["title", "summary", "evidence_ids", "uncertainties", "next_checks"],
          "properties": {"title": {"type": "string"}, "summary": {"type": "string"},
                         "evidence_ids": {"type": "array", "items": {"type": "string"}},
                         "uncertainties": {"type": "array", "items": {"type": "string"}},
                         "next_checks": {"type": "array", "items": {"type": "string"}}}}
PROMPT_VERSION = "incident_summary.v1"
PROMPT = (pathlib.Path(__file__).parent / "prompts" / "incident_summary.txt").read_text(encoding="utf-8")


class IncidentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=100)
    summary: str = Field(max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    uncertainties: list[str] = Field(max_length=6)
    next_checks: list[str] = Field(max_length=6)


def _key():
    return os.environ.get("GROQ_API_KEY", "").strip()


def evidence_hash(packet):
    return hashlib.sha256(json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest()[:16]


def template_summary(packet, reason):
    """Factual fallback built only from the packet (no model)."""
    ev = packet["evidence"]
    head = ev[0]["facts"] if ev else {}
    stations = [e for e in ev if e["kind"] == "station_state"]
    recs = [e for e in ev if e["kind"] == "recommendation"]
    decisions = [e for e in ev if e["kind"] == "decision"]
    parts = [head.get("description", packet["kind"].replace("_", " ")) + "."]
    short = [f"{s['facts']['name']} {fuel} runs out in {h:.1f} h" for s in stations
             for fuel, h in s["facts"].get("runs_out_in_hours", {}).items() if h is not None and h < 12]
    if short:
        parts.append("At risk now: " + "; ".join(short[:4]) + ".")
    if recs:
        parts.append(f"{len(recs)} shipment recommendation(s) are open for the affected stations.")
    if decisions:
        parts.append(f"{len(decisions)} related decision(s) recorded so far.")
    if packet["status"] in ("resolved", "recovered"):
        parts.append("The incident is over; watch the affected stations until their tanks recover.")
    return {"title": head.get("title", packet["kind"].replace("_", " ").capitalize())[:100],
            "summary": " ".join(parts)[:1200], "evidence_ids": [e["id"] for e in ev[:6]],
            "uncertainties": [], "next_checks": ["Open Home and look at the affected stations' tanks."],
            "source": "template", "reason": reason}


class SummaryWorker:
    """One background thread, bounded queue, local rate limit, results persisted in SQLite."""

    def __init__(self):
        self.q = queue.Queue(maxsize=100)
        self.http = httpx.Client(timeout=httpx.Timeout(TIMEOUT, connect=5.0))
        self.last_call = 0.0
        self.status = {"state": "idle", "detail": None, "calls": 0, "failures": 0}
        threading.Thread(target=self._run, daemon=True).start()

    def enabled(self):
        return ENABLED and bool(_key())

    def submit(self, case_id, version, packet):
        h = evidence_hash(packet)
        if store.get_summary(case_id, version, h):
            return
        try:
            self.q.put_nowait((case_id, version, h, packet))
        except queue.Full:
            self.status.update(detail="summary queue full; older cases skipped")

    def _run(self):
        while True:
            case_id, version, h, packet = self.q.get()
            if not self.enabled():
                reason = "AI summaries switched off" if not ENABLED else "no Groq API key configured"
                store.save_summary(case_id, version, h, template_summary(packet, reason), MODEL, PROMPT_VERSION)
                M.SUMMARY_CALLS.labels("template").inc()
                continue
            wait = self.last_call + 60.0 / PER_MINUTE - time.time()
            if wait > 0:
                time.sleep(wait)
            result = self._call(packet)
            store.save_summary(case_id, version, h, result, MODEL, PROMPT_VERSION)

    def _call(self, packet):
        body = {"model": MODEL, "temperature": 0.2, "max_completion_tokens": MAX_OUTPUT_TOKENS, "reasoning_effort": "low",
                "messages": [{"role": "system", "content": PROMPT},
                             {"role": "user", "content": json.dumps(packet, allow_nan=False, default=str)}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "incident_summary", "strict": True, "schema": SCHEMA}}}
        reason = "unknown error"
        for attempt in range(MAX_ATTEMPTS):
            self.last_call = time.time()
            self.status["calls"] += 1
            t0 = time.perf_counter()
            try:
                r = self.http.post(f"{BASE_URL}/chat/completions", json=body,
                                   headers={"Authorization": f"Bearer {_key()}"})
                M.SUMMARY_SECONDS.observe(time.perf_counter() - t0)
                if r.status_code in (401, 403):
                    reason = "Groq rejected the API key"
                    break
                if r.status_code == 429 or r.status_code >= 500:
                    reason = f"Groq busy ({r.status_code})"
                    time.sleep(min(10.0, float(r.headers.get("retry-after", 2 ** attempt * 2))))
                    continue
                if r.status_code >= 400:
                    reason = f"request refused ({r.status_code}: {r.text[:120]})"
                    break
                data = r.json()
                usage = data.get("usage") or {}
                M.SUMMARY_TOKENS.labels("input").inc(usage.get("prompt_tokens", 0) or 0)
                M.SUMMARY_TOKENS.labels("output").inc(usage.get("completion_tokens", 0) or 0)
                choice = (data.get("choices") or [{}])[0]
                if choice.get("finish_reason") != "stop":
                    reason = f"answer incomplete ({choice.get('finish_reason')})"
                    break
                raw = json.loads(choice["message"]["content"])
                raw = {"title": str(raw["title"])[:100], "summary": str(raw["summary"])[:1200],
                       "evidence_ids": list(raw["evidence_ids"])[:12], "uncertainties": list(raw["uncertainties"])[:6],
                       "next_checks": list(raw["next_checks"])[:6]}
                s = IncidentSummary.model_validate(raw)
                known = {e["id"] for e in packet["evidence"]}
                if not s.evidence_ids or not set(s.evidence_ids) <= known:
                    reason = "summary cited evidence that does not exist"
                    break
                M.SUMMARY_CALLS.labels("llm").inc()
                self.status.update(state="ok", detail=None)
                return {**s.model_dump(), "source": "groq", "reason": None,
                        "tokens": {"input": usage.get("prompt_tokens"), "output": usage.get("completion_tokens")},
                        "response_id": data.get("id")}
            except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError) as e:
                reason = f"{type(e).__name__}: {str(e)[:120]}"
        self.status.update(state="failing", detail=reason, failures=self.status["failures"] + 1)
        M.SUMMARY_CALLS.labels("fallback").inc()
        return template_summary(packet, reason)


# ---- building cases and evidence from the controller's state -------------------------------------------
EVENT_TITLES = {"demand_spike": "Demand surge", "route_disruption": "Road closed", "station_outage": "Station closed",
                "depot_constraint": "Depot restricted", "shipment_delay": "Supply delayed", "supply_shortfall": "Supply cut"}


def affected_stations(snap, event):
    p = event["parameters"]
    ids = set(p.get("station_ids") or [])
    for r in p.get("route_ids") or []:
        if r in snap["routes"]:
            ids.add(snap["routes"][r]["destination_station_id"])
    for rg in p.get("region_ids") or []:
        ids |= {s for s, st in snap["stations"].items() if st["region_id"] == rg}
    for d in p.get("depot_ids") or []:
        ids |= {r["destination_station_id"] for r in snap["routes"].values() if r["source_depot_id"] == d}
    return sorted(ids) or sorted(snap["stations"])


def packet_for(case_id, version, kind, status, head, snap, cards, alerts, run_id, stations, clock):
    ev = [{"id": case_id, "kind": "incident", "facts": head}]
    for sid in stations[:4]:
        st = snap["stations"][sid]
        runs_out = {c["fuel"].lower(): c["before"]["stockout_hours"] for c in cards.values() if c["station_id"] == sid}
        ev.append({"id": f"station:{sid}", "kind": "station_state", "facts": {
            "name": st["name"], "open": st["status"] == "OPEN", "demand_multiplier": st["demand_multiplier"],
            "stock_liters": {f.lower(): round(v) for f, v in st["inventory"].items()},
            "runs_out_in_hours": {k: (round(v, 1) if v is not None else None) for k, v in runs_out.items()}}})
    for c in cards.values():
        if c["station_id"] in stations and c["allocations"]:
            ev.append({"id": f"recommendation:{c['id']}", "kind": "recommendation", "facts": {
                "station": c["station"], "fuel": c["fuel"].lower(), "send_liters": sum(a["liters"] for a in c["allocations"]),
                "from_depots": sorted({a["depot_id"] for a in c["allocations"]}),
                "stockout_risk_now": round(c["before"]["risk"], 2),
                "stockout_risk_if_sent": round(c["after"]["risk"], 2) if c["after"] else None,
                "needs_operator_review": c["review_required"], "planned_by": c["source"]}})
    for a in alerts:
        if a.get("station_id") in stations:
            ev.append({"id": f"detection:{a['kind']}:{a.get('station_id')}:{a.get('fuel')}", "kind": "detection",
                       "facts": {"detector": a["kind"], "detail": a["detail"]}})
    try:
        for d in store.decisions(50):
            if d["run_id"] == run_id and d["station_id"] in stations and d["tick"] >= head.get("start_tick", 0):
                ev.append({"id": f"decision:{d['id']}", "kind": "decision", "facts": {
                    "action": d["status"], "station": d["station_id"], "fuel": d["fuel"].lower(),
                    "liters_planned": d["liters"], "liters_accepted": (d["outcome"] or {}).get("liters_accepted"),
                    "at": clock(d["tick"])}})
    except Exception:  # noqa: BLE001 — evidence is best effort; the summary says what is missing
        pass
    return {"incident_id": case_id, "incident_version": version, "run_id": run_id, "as_of_tick": snap["tick"],
            "as_of_time": clock(snap["tick"]), "kind": kind, "status": status, "evidence": ev[:14],
            "known_limitations": ["Simulated environment.", "Delivery outcomes after this moment are not known yet."]}


class CaseBook:
    """Tracks incident cases and asks the worker for a summary whenever a case changes state."""

    def __init__(self, worker):
        self.worker, self.state = worker, {}

    def update(self, snap, cards, alerts, run_id, degraded, intel_enabled, clock):
        seen = {}
        for e in snap["events"]:
            status = {"ACTIVE": "active", "RESOLVED": "resolved"}.get(e["status"], "scheduled")
            title = EVENT_TITLES.get(e["type"], e["type"].replace("_", " ").capitalize())
            desc = f"{title} ({e['status'].lower()}), {clock(e['start_tick'])} to {clock(e['end_tick'])}"
            seen[f"event:{e['id']}"] = (e["type"], status, {"title": title, "description": desc, "start_tick": e["start_tick"],
                                                             "end_tick": e["end_tick"], "parameters": e["parameters"]},
                                        affected_stations(snap, e))
        if degraded:
            seen["outage:simulator"] = ("simulator_unreachable", "active", {
                "title": "Fuel simulator unreachable", "description": f"The simulator stopped answering: {degraded[:120]}",
                "start_tick": snap["tick"]}, sorted(snap["stations"]))
        elif "outage:simulator" in self.state and self.state["outage:simulator"][1] == "active":
            seen["outage:simulator"] = ("simulator_unreachable", "recovered", {
                "title": "Fuel simulator back", "description": "The simulator answers again; state was refreshed.",
                "start_tick": snap["tick"]}, sorted(snap["stations"]))
        if not intel_enabled:
            seen["fallback:intelligence"] = ("intelligence_off", "active", {
                "title": "Smart planning switched off", "description": "Forecasting and the optimizer are off; the "
                "simple refill rule decides shipments.", "start_tick": snap["tick"]}, sorted(snap["stations"]))
        for case_id, (kind, status, head, stations) in seen.items():
            old = self.state.get(case_id)
            if old and old[1] == status:
                continue
            version = old[0] + 1 if old else 1
            self.state[case_id] = (version, status)
            if status == "scheduled":
                continue  # summarise when it starts
            self.worker.submit(case_id, version, packet_for(case_id, version, kind, status, head, snap, cards, alerts,
                                                            run_id, stations, clock))
