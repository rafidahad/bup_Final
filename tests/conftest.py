"""Tests never talk to the forecaster container or to Groq."""
import os

os.environ.setdefault("FORECAST_ENABLED", "false")
os.environ.setdefault("SUMMARIES_ENABLED", "false")
