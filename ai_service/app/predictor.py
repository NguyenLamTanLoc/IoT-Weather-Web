"""Inference code copied from Best_IoT_fixed.ipynb (sections 8, 15, 18, 20).

Ensemble = LSTM + ARIMA + RandomForest (Prophet was excluded in notebook section 15,
so it is not needed here).
"""
import os
import threading
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

# ---- Constants: MUST match the notebook (section 2 and 9) ----
N_IN = 24                                   # hours of history the models need
N_OUT = 6                                   # hours predicted
CAC_COT = ["Temperature (C)", "Humidity (%)"]
LAT, LON = 10.762, 106.660                  # Ho Chi Minh City
TZ = "Asia/Ho_Chi_Minh"

# Alert thresholds (notebook defaults, can be overridden with env vars)
T_MIN = float(os.environ.get("T_MIN", 20.0))
T_MAX = float(os.environ.get("T_MAX", 35.0))
H_MIN = float(os.environ.get("H_MIN", 40.0))
H_MAX = float(os.environ.get("H_MAX", 80.0))

MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).resolve().parent.parent / "models"))

_predict_lock = threading.Lock()            # keras/statsmodels calls: one at a time per worker


class Artifacts:
    """Everything loaded from the files saved by the notebook."""

    def __init__(self):
        import keras  # imported here so Django can start/check without loading TensorFlow

        self.model = keras.models.load_model(MODEL_DIR / "model_lstm.keras")
        self.scaler = joblib.load(MODEL_DIR / "scaler.pkl")
        self.rf = joblib.load(MODEL_DIR / "random_forest.pkl")
        ens = joblib.load(MODEL_DIR / "arima_ensemble.pkl")
        self.arima_params = ens["arima_params"]
        self.weights = ens["weights"]       # {"LSTM": (N_OUT, 2), "ARIMA": ..., "RandomForest": ...}
        self.K = ens["K"]
        self.ORDER = ens["ORDER"]
        unsupported = set(self.weights) - {"LSTM", "ARIMA", "RandomForest"}
        if unsupported:
            raise RuntimeError(f"Ensemble contains {unsupported}; add Prophet support or retrain without it.")


@lru_cache(maxsize=1)
def get_artifacts() -> Artifacts:
    return Artifacts()


# ---------------- helpers (from the notebook) ----------------
def ve_don_vi_that(art, arr):
    """Scaled 0..1 -> real units (C and %). Returns (n, N_OUT, 2)."""
    return art.scaler.inverse_transform(arr.reshape(-1, 2)).reshape(-1, N_OUT, 2)


def gioi_han_do_am(a):
    a = a.copy()
    a[..., 1] = np.clip(a[..., 1], 0, 100)  # humidity only in 0..100 %
    return a


def fourier(times, K):
    gio = (times.dt.hour + times.dt.minute / 60).to_numpy(dtype=float)
    cot = []
    for j in range(1, K + 1):
        cot.append(np.sin(2 * np.pi * j * gio / 24))
        cot.append(np.cos(2 * np.pi * j * gio / 24))
    return np.column_stack(cot)


def gio_sin_cos(times):
    h = pd.Series(pd.to_datetime(times)).dt.hour.to_numpy(dtype=float)
    return np.column_stack([np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)])


def _arima(art, yw, Fw, Ff, k):
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    r = SARIMAX(yw, exog=Fw, order=art.ORDER, trend="c").smooth(art.arima_params[k])
    return r.forecast(N_OUT, exog=Ff)


# ---------------- building the 24h window ----------------
def lay_open_meteo_gan_day(lat=LAT, lon=LON, past_days=2):
    """Recent hourly data from Open-Meteo (used as fallback / demo source)."""
    r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=30, params={
        "latitude": lat, "longitude": lon, "hourly": "temperature_2m,relative_humidity_2m",
        "past_days": past_days, "forecast_days": 1, "timezone": TZ})
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.rename(columns={"temperature_2m": CAC_COT[0], "relative_humidity_2m": CAC_COT[1]})
    return df.set_index("time")[CAC_COT]


def readings_to_hourly(readings):
    """Raw sensor readings (list of dicts) -> hourly mean table (like notebook doc_dht)."""
    if not readings:
        return pd.DataFrame(columns=CAC_COT, index=pd.DatetimeIndex([])).astype(float)
    d = pd.DataFrame(readings)
    for c in ("time", "temperature", "humidity"):
        if c not in d.columns:
            raise ValueError(f"Each reading needs 'time', 'temperature', 'humidity' (missing '{c}').")
    t = pd.to_datetime(d["time"], utc=True, errors="coerce").dt.tz_convert(TZ).dt.tz_localize(None)
    d = pd.DataFrame({CAC_COT[0]: pd.to_numeric(d["temperature"], errors="coerce").values,
                      CAC_COT[1]: pd.to_numeric(d["humidity"], errors="coerce").values},
                     index=pd.DatetimeIndex(t, name="time"))
    d = d[d.index.notna()]
    d = d[d[CAC_COT[0]].between(-40, 80) & d[CAC_COT[1]].between(0, 100)]   # drop bad readings
    return d.sort_index().resample("h").mean().interpolate(limit=2).dropna()


def dung_cua_so(dht, gio_cuoi=None, ngoai=None, noi_suy_toi_da=3):
    """Build N_IN consecutive hours ending at gio_cuoi.

    Missing hours are filled by: short interpolation -> Open-Meteo (shifted by the
    average sensor-vs-Open-Meteo bias). Returns (window, source_per_hour).
    """
    if gio_cuoi is None:
        gio_cuoi = pd.Timestamp.now(tz=TZ).tz_localize(None).floor("h") - pd.Timedelta(hours=1)
    truc = pd.date_range(gio_cuoi - pd.Timedelta(hours=N_IN - 1), gio_cuoi, freq="h")
    w = dht.reindex(truc).astype(float)
    nguon = pd.Series("sensor", index=truc)
    thieu = w[CAC_COT[0]].isna()
    nguon[thieu] = "thieu"

    nhom = (thieu != thieu.shift()).cumsum()
    do_dai = thieu.groupby(nhom).transform("sum")
    ngan = thieu & (do_dai <= noi_suy_toi_da)
    w_noi_suy = w.interpolate(limit_area="inside")
    w.loc[ngan] = w_noi_suy.loc[ngan]
    nguon[ngan & w[CAC_COT[0]].notna()] = "noi_suy"

    con_thieu = w[CAC_COT[0]].isna()
    if con_thieu.any():
        if ngoai is None:
            ngoai = lay_open_meteo_gan_day()
        om = ngoai.reindex(truc)
        if om.loc[con_thieu].isna().any().any():
            raise ValueError("Open-Meteo does not cover all the missing hours in the window.")
        co_ca_hai = (nguon == "sensor") & om[CAC_COT[0]].notna()
        lech = (w.loc[co_ca_hai] - om.loc[co_ca_hai]).mean() if co_ca_hai.any() else pd.Series(0.0, index=CAC_COT)
        w.loc[con_thieu] = (om + lech.values).loc[con_thieu]
        nguon[con_thieu] = "open-meteo"

    w[CAC_COT[1]] = w[CAC_COT[1]].clip(0, 100)
    assert w.notna().all().all() and len(w) == N_IN
    return w, nguon


# ---------------- prediction ----------------
def du_bao_ensemble(cua_so):
    """cua_so: DataFrame with N_IN consecutive hourly rows, DatetimeIndex, columns CAC_COT.
    Returns ({model_name: (N_OUT, 2) array}, forecast_times)."""
    art = get_artifacts()
    assert len(cua_so) == N_IN and (cua_so.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all(), \
        "Window must be exactly N_IN consecutive hours"

    gio_tl = pd.date_range(cua_so.index[-1] + pd.Timedelta(hours=1), periods=N_OUT, freq="h")
    x_scaled = art.scaler.transform(cua_so[CAC_COT].values)

    with _predict_lock:
        p_lstm = ve_don_vi_that(art, art.model.predict(x_scaled.reshape(1, N_IN, len(CAC_COT)), verbose=0))[0]

        Fw = fourier(pd.Series(cua_so.index), art.K)
        Ff = fourier(pd.Series(gio_tl), art.K)
        p_arima = np.column_stack([np.asarray(_arima(art, cua_so[c].values, Fw, Ff, k))
                                   for k, c in enumerate(CAC_COT)])

        x_rf = np.hstack([x_scaled.reshape(1, -1), gio_sin_cos([gio_tl[0]])])
        p_rf = ve_don_vi_that(art, art.rf.predict(x_rf))[0]

    tv = {"LSTM": p_lstm, "ARIMA": p_arima, "RandomForest": p_rf}
    p_ens = sum(art.weights[t] * tv[t] for t in art.weights)
    kq = {**tv, "Ensemble": p_ens}
    return {ten: gioi_han_do_am(v) for ten, v in kq.items()}, gio_tl


def canh_bao(du_doan, gio_tl):
    """Same rules as the notebook, but returns a list instead of printing."""
    alerts = []
    for h, ((t, hu), thoi_gian) in enumerate(zip(du_doan, gio_tl), start=1):
        reasons = []
        if t > T_MAX: reasons.append(f"temperature {t:.1f}C > {T_MAX}C")
        if t < T_MIN: reasons.append(f"temperature {t:.1f}C < {T_MIN}C")
        if hu > H_MAX: reasons.append(f"humidity {hu:.1f}% > {H_MAX}%")
        if hu < H_MIN: reasons.append(f"humidity {hu:.1f}% < {H_MIN}%")
        if reasons:
            alerts.append({"in_hours": h, "time": thoi_gian.isoformat(), "reasons": reasons})
    return alerts


def forecast(window, sources=None):
    """Main entry point used by the Django view."""
    kq, gio_tl = du_bao_ensemble(window)
    ens = kq["Ensemble"]
    return {
        "window_end": window.index[-1].isoformat(),
        "window_sources": (sources.value_counts().to_dict() if sources is not None else None),
        "predictions": [
            {"time": gio_tl[i].isoformat(),
             "temperature": round(float(ens[i, 0]), 2),
             "humidity": round(float(ens[i, 1]), 2),
             "by_model": {m: {"temperature": round(float(v[i, 0]), 2), "humidity": round(float(v[i, 1]), 2)}
                          for m, v in kq.items() if m != "Ensemble"}}
            for i in range(N_OUT)
        ],
        "alerts": canh_bao(ens, gio_tl),
        "thresholds": {"T_MIN": T_MIN, "T_MAX": T_MAX, "H_MIN": H_MIN, "H_MAX": H_MAX},
    }
