"""LLM incident summaries with a mocked Groq endpoint (no network, no key)."""
import json

import httpx
import pytest

from fuelops import store, summary

PACKET = {"incident_id": "event:1", "incident_version": 1, "run_id": "r", "as_of_tick": 40, "as_of_time": "Day 1, 10:00",
          "kind": "route_disruption", "status": "active",
          "evidence": [{"id": "event:1", "kind": "incident", "facts": {"title": "Road closed", "description": "Road closed (active)"}},
                       {"id": "station:station-mirpur", "kind": "station_state",
                        "facts": {"name": "Mirpur", "runs_out_in_hours": {"diesel": 3.5}}}],
          "known_limitations": []}


def _reply(text, finish="stop"):
    """Groq chat-completions shape (OpenAI compatible)."""
    return {"id": "chatcmpl_1", "usage": {"prompt_tokens": 900, "completion_tokens": 150},
            "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": text}}]}


def _worker(handler, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(summary, "PER_MINUTE", 10_000)
    w = summary.SummaryWorker.__new__(summary.SummaryWorker)  # no background thread
    w.http = httpx.Client(transport=httpx.MockTransport(handler))
    w.last_call, w.status = 0.0, {"state": "idle", "detail": None, "calls": 0, "failures": 0}
    return w


def test_valid_structured_summary_is_accepted(monkeypatch):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        good = {"title": "Road to Mirpur closed", "summary": "The Gazipur road is closed; Mirpur diesel lasts about 3.5 hours.",
                "evidence_ids": ["event:1", "station:station-mirpur"], "uncertainties": [], "next_checks": ["Check Mirpur tanks"]}
        return httpx.Response(200, json=_reply(json.dumps(good)))

    r = _worker(handler, monkeypatch)._call(PACKET)
    assert r["source"] == "groq" and r["title"].startswith("Road")
    fmt = seen["body"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"]["additionalProperties"] is False
    assert seen["body"]["model"] == "openai/gpt-oss-120b" and seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer test-key"


def test_made_up_evidence_falls_back_to_template(monkeypatch):
    bad = {"title": "x", "summary": "y", "evidence_ids": ["event:999"], "uncertainties": [], "next_checks": []}
    r = _worker(lambda req: httpx.Response(200, json=_reply(json.dumps(bad))), monkeypatch)._call(PACKET)
    assert r["source"] == "template" and "does not exist" in r["reason"]


def test_rejected_key_falls_back_without_retry(monkeypatch):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    r = _worker(handler, monkeypatch)._call(PACKET)
    assert r["source"] == "template" and "key" in r["reason"] and len(calls) == 1


def test_busy_service_retries_then_falls_back(monkeypatch):
    monkeypatch.setattr(summary.time, "sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "1"})

    r = _worker(handler, monkeypatch)._call(PACKET)
    assert r["source"] == "template" and len(calls) == summary.MAX_ATTEMPTS


def test_cut_off_answer_falls_back(monkeypatch):
    r = _worker(lambda req: httpx.Response(200, json=_reply("{\"title\": \"x", finish="length")), monkeypatch)._call(PACKET)
    assert r["source"] == "template" and "incomplete" in r["reason"]


def test_template_uses_only_packet_facts():
    t = summary.template_summary(PACKET, "no Groq API key configured")
    assert "Mirpur diesel runs out in 3.5 h" in t["summary"]
    assert set(t["evidence_ids"]) <= {e["id"] for e in PACKET["evidence"]}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(store, "_conn", None)
