"""Weather for a ZIP code: ZIP -> latitude/longitude (zippopotam.us), then hourly air and dew-point temperature
from the Open-Meteo historical archive. Both are free public services; this is a portfolio app, not a production service."""
import datetime as dt
import json
import urllib.request
from functools import lru_cache

import pandas as pd

TIMEOUT = 40


class WeatherError(Exception):
    pass


def _get_json(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # network, 404, bad JSON
        raise WeatherError(str(e))


@lru_cache(maxsize=256)
def zip_to_place(zip_code):
    z = str(zip_code).strip()[:5]
    if not (z.isdigit() and len(z) == 5):
        raise WeatherError(f"'{zip_code}' is not a 5-digit US ZIP code")
    d = _get_json(f'https://api.zippopotam.us/us/{z}')
    p = d['places'][0]
    return {'zip': z, 'lat': float(p['latitude']), 'lon': float(p['longitude']),
            'name': f"{p['place name']}, {p['state abbreviation']}"}


@lru_cache(maxsize=64)
def fetch_weather(lat, lon, start, end, clock):
    """clock 'local' = local time at the place (daylight saving applies); 'utc' = UTC. Returns naive timestamps."""
    last_ok = (dt.date.today() - dt.timedelta(days=7)).isoformat()  # the archive lags a few days
    end = min(end, last_ok)
    tz = 'auto' if clock == 'local' else 'GMT'
    url = ('https://archive-api.open-meteo.com/v1/archive?'
           f'latitude={lat:.4f}&longitude={lon:.4f}&start_date={start}&end_date={end}'
           f'&hourly=temperature_2m,dew_point_2m&timezone={tz}')
    d = _get_json(url)
    h = d.get('hourly')
    if not h:
        raise WeatherError('no weather returned for that location and dates')
    w = pd.DataFrame({'timestamp': pd.to_datetime(h['time']), 'air_temperature': h['temperature_2m'],
                      'dew_temperature': h['dew_point_2m']}).dropna()
    if w.empty:
        raise WeatherError('weather came back empty for those dates')
    return w
