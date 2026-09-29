# Chronos-2-Small forecasting service (CPU). Kept separate so torch never enters the main app image.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 HF_HUB_DISABLE_TELEMETRY=1 \
    MODEL_ID=autogluon/chronos-2-small \
    MODEL_REVISION=ddec01313e50b6bc58ebaa92ede81bc24a3d9f9a \
    MODEL_DIR=/models/chronos-2-small
COPY requirements.txt .
# Optional pre-downloaded wheels (slow networks): forecaster/wheels/*.whl are installed first if present.
COPY wheels/ /tmp/wheels/
RUN if ls /tmp/wheels/*.whl >/dev/null 2>&1; then pip install --no-cache-dir /tmp/wheels/*.whl; fi  && pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt && rm -rf /tmp/wheels
COPY app.py .
RUN useradd --create-home svc && mkdir -p /models && chown -R svc /models /srv
USER svc
EXPOSE 8200
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
  CMD python -c "import urllib.request,json,sys; sys.exit(0 if json.load(urllib.request.urlopen('http://localhost:8200/health', timeout=4))['status']=='ok' else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
