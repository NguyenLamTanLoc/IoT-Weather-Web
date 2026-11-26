from contextlib import asynccontextmanager

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import predictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    predictor.get_artifacts()          # load all models once at startup (the server only listens after this)
    yield


app = FastAPI(title="IoT forecast AI service", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "service": app.title,
        "docs": "/docs",
        "health": "/health",
        "forecast": "/forecast",
    }


class Reading(BaseModel):
    time: str                          # ISO time, e.g. "2026-11-26T08:00:00+07:00"
    temperature: float
    humidity: float


class ForecastRequest(BaseModel):
    readings: list[Reading]
    fill_with_open_meteo: bool = True  # fill missing hours from Open-Meteo (needs internet)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/forecast")
def forecast_demo():
    """Demo: forecast from the latest Open-Meteo data (no sensor needed)."""
    return _run(predictor.readings_to_hourly([]), fill=True, last_hour=None)


@app.post("/forecast")
def forecast_from_readings(req: ForecastRequest):
    """Forecast the next 6 hours from raw sensor readings (any frequency, averaged per hour)."""
    hourly = predictor.readings_to_hourly([r.model_dump() for r in req.readings])
    if hourly.empty:
        raise HTTPException(status_code=400, detail="No valid readings in body.")
    return _run(hourly, fill=req.fill_with_open_meteo, last_hour=hourly.index[-1])


# NOTE: plain `def` (not `async def`) on purpose: TensorFlow/ARIMA are blocking, so FastAPI
# runs these in a thread pool instead of freezing the event loop.
def _run(hourly, fill, last_hour):
    try:
        if fill:
            window, sources = predictor.dung_cua_so(hourly, gio_cuoi=last_hour)
        else:
            idx = pd.date_range(last_hour - pd.Timedelta(hours=predictor.N_IN - 1), last_hour, freq="h")
            window = hourly.reindex(idx)
            if window.isna().any().any():
                raise ValueError(f"Need {predictor.N_IN} consecutive hours of data.")
            sources = None
        return predictor.forecast(window, sources)
    except (ValueError, AssertionError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Open-Meteo: {e}")
