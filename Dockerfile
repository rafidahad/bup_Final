# Fuel Operations platform: web app build + Python backend in one image.
# Stage 1 builds the operator web app; stage 2 runs the FastAPI backend that serves it.
ARG NODE_IMAGE=node:22-alpine
FROM ${NODE_IMAGE} AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    FUELOPS_WEB=/app/web/dist FUELOPS_DB=/app/data/fuelops.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fuelops/ fuelops/
COPY tests/ tests/
COPY --from=web /web/dist web/dist
RUN useradd --create-home app && mkdir -p /app/data /app/reports && chown -R app /app
USER app
EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8100/api/status', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "fuelops.api:app", "--host", "0.0.0.0", "--port", "8100"]
