"""Thin HTTP client for the official simulator. REST only; no state kept here."""
import os
import time

import httpx

BASE_URL = os.environ.get("SIM_URL", "http://localhost:18000")
FUELS = ("DIESEL", "PETROL", "OCTANE")


class SimError(Exception):
    """Non-2xx simulator response, normalized across the three documented envelopes."""

    def __init__(self, status, code, message, body=None):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.body = status, code, message, body


def _raise_for(r):
    if r.is_success:
        return
    try:
        body = r.json()
    except ValueError:
        raise SimError(r.status_code, "NON_JSON", r.text[:500]) from None
    inner = body.get("detail", body.get("error")) if isinstance(body, dict) else None
    if isinstance(inner, dict):
        raise SimError(r.status_code, inner.get("code", "UNKNOWN"), inner.get("message", ""), body)
    raise SimError(r.status_code, "VALIDATION" if isinstance(inner, list) else "UNKNOWN", str(inner)[:500], body)


class Sim:
    def __init__(self, base_url=BASE_URL, timeout=10.0):
        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self.last_stale = False  # X-Simulator-Stale seen on the most recent GET

    def get(self, path, retries=3, **params):
        """Reads are safe to retry: 503 (injected fault) and transport errors back off briefly."""
        for attempt in range(retries + 1):
            try:
                r = self.http.get(path, params=params or None)
                if r.status_code == 503 and attempt < retries:
                    time.sleep(0.02 * 2 ** attempt)
                    continue
                self.last_stale = r.headers.get("X-Simulator-Stale") == "true"
                _raise_for(r)
                return r.json()
            except httpx.TransportError:
                if attempt == retries:
                    raise
                time.sleep(0.02 * 2 ** attempt)

    def post(self, path, json=None):
        r = self.http.post(path, json=json)
        _raise_for(r)
        return r.json()

    # public reads
    def health(self): return self.get("/v1/health")
    def instance(self): return self.get("/v1/instance")
    def depots(self): return self.get("/v1/depots")
    def stations(self): return self.get("/v1/stations")
    def routes(self): return self.get("/v1/routes")
    def regions(self): return self.get("/v1/regions")
    def supply(self): return self.get("/v1/supply-arrivals")
    def events(self): return self.get("/v1/events")
    def allocations(self): return self.get("/v1/allocations")
    def metrics(self): return self.get("/v1/metrics")

    def demand_history(self, station_id=None, limit=2000):
        params = {"limit": limit}
        if station_id:
            params["station_id"] = station_id
        return self.get("/v1/demand-history", **params)

    # the only domain writes
    def allocate(self, key, depot, station, route, fuel, qty):
        return self.post("/v1/allocations", {
            "idempotency_key": key, "source_depot_id": depot, "destination_station_id": station,
            "route_id": route, "fuel_type": fuel, "quantity": qty,
        })

    def cancel(self, allocation_id):
        return self.post(f"/v1/allocations/{allocation_id}/cancel")

    # admin: test harness only, never the operational policy
    def reset(self): return self.post("/admin/reset")
    def pause(self): return self.post("/admin/pause")
    def run(self): return self.post("/admin/run")
    def step(self): return self.post("/admin/step")
    def inject_event(self, body): return self.post("/admin/events", body)
    def inject_fault(self, body): return self.post("/admin/faults", body)
    def clear_faults(self): return self.post("/admin/faults/clear")
    def audit(self, limit=200): return self.get("/admin/audit", limit=limit)
