"""Chronos-2-Small demand forecasting service (pretrained, no training or fine-tuning).

POST /forecast  {tick_minutes, horizon, series: [{id, start_tick, values: [liters per tick]}]}
             →  {model, revision, latency_ms, series: [{id, start_tick, q10: [...], q50: [...], q90: [...]}]}
GET  /health →  {status: loading | ok | error, ...}

Weights are downloaded once at the pinned revision into MODEL_DIR (a named volume) and loaded once.
Ticks are simulator ticks; timestamps are synthesized from them only because the library wants a time index.
"""
import json
import math
import os
import pathlib
import threading
import time

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_ID = os.environ.get("MODEL_ID", "autogluon/chronos-2-small")
REVISION = os.environ.get("MODEL_REVISION", "ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a")
MODEL_DIR = pathlib.Path(os.environ.get("MODEL_DIR", "/models/chronos-2-small"))
QUANTILES = [0.1, 0.5, 0.9]
EPOCH = pd.Timestamp("2026-01-01T00:00:00")

state = {"status": "loading", "detail": None, "loaded_at": None, "load_seconds": None,
         "last_latency_ms": None, "requests": 0, "errors": 0}
pipeline = None
lock = threading.Lock()  # one inference at a time on CPU


def _load():
    global pipeline
    t0 = time.time()
    try:
        manifest = MODEL_DIR / "manifest.json"
        if not (MODEL_DIR / "model.safetensors").exists():
            from huggingface_hub import snapshot_download
            state["detail"] = f"downloading {MODEL_ID}@{REVISION[:12]}"
            snapshot_download(MODEL_ID, revision=REVISION, local_dir=MODEL_DIR)
            import chronos
            import torch
            manifest.write_text(json.dumps({"model_id": MODEL_ID, "revision": REVISION, "downloaded_at": time.time(),
                                            "chronos": getattr(chronos, "__version__", "?"), "torch": torch.__version__}))
        from chronos import BaseChronosPipeline
        pipeline = BaseChronosPipeline.from_pretrained(str(MODEL_DIR), device_map="cpu")
        state.update(status="ok", detail=None, loaded_at=time.time(), load_seconds=round(time.time() - t0, 1))
    except Exception as e:  # noqa: BLE001 — reported through /health; the backend falls back to the formula
        state.update(status="error", detail=repr(e)[:300])


app = FastAPI(title="Chronos forecaster")
threading.Thread(target=_load, daemon=True).start()


class Series(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    start_tick: int = Field(ge=0)
    values: list[float] = Field(min_length=8, max_length=4000)


class ForecastIn(BaseModel):
    tick_minutes: int = Field(gt=0, le=1440)
    horizon: int = Field(gt=0, le=512)
    series: list[Series] = Field(min_length=1, max_length=64)


@app.get("/health")
def health():
    return {**state, "model_id": MODEL_ID, "revision": REVISION, "device": "cpu"}


@app.post("/forecast")
def forecast(body: ForecastIn):
    if pipeline is None:
        raise HTTPException(503, f"model {state['status']}: {state['detail']}")
    rows = []
    for s in body.series:
        if any(not math.isfinite(v) or v < 0 for v in s.values):
            raise HTTPException(422, f"series {s.id} has negative or non-finite values")
        for i, v in enumerate(s.values):
            rows.append((s.id, EPOCH + pd.Timedelta(minutes=(s.start_tick + i) * body.tick_minutes), v))
    df = pd.DataFrame(rows, columns=["item_id", "timestamp", "target"])
    t0 = time.perf_counter()
    with lock:
        state["requests"] += 1
        try:
            import torch
            with torch.inference_mode():
                pred = pipeline.predict_df(df, prediction_length=body.horizon, quantile_levels=QUANTILES,
                                           id_column="item_id", timestamp_column="timestamp", target="target")
        except Exception as e:  # noqa: BLE001
            state["errors"] += 1
            raise HTTPException(500, f"inference failed: {e!r}"[:300]) from e
    ms = round((time.perf_counter() - t0) * 1000, 1)
    state["last_latency_ms"] = ms
    qcols = {q: _col(pred, q) for q in QUANTILES}
    out = []
    for s in body.series:
        part = pred[pred["item_id"] == s.id].sort_values("timestamp")
        if len(part) != body.horizon:
            raise HTTPException(500, f"series {s.id}: expected {body.horizon} predictions, got {len(part)}")
        out.append({"id": s.id, "start_tick": s.start_tick + len(s.values),
                    **{f"q{int(q * 100)}": [float(x) for x in part[qcols[q]]] for q in QUANTILES}})
    return {"model": MODEL_ID, "revision": REVISION, "latency_ms": ms, "series": out}


def _col(df, q):
    """Quantile columns are named by level; accept '0.1' or 0.1 spellings."""
    for c in df.columns:
        if str(c) in (str(q), f"{q:.1f}"):
            return c
    raise HTTPException(500, f"no column for quantile {q}; got {list(df.columns)}")
