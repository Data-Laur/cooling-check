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
            'name': f"{p['place name']}, {p['state abbreviation']}", 'state': p['state abbreviation']}


@lru_cache(maxsize=256)
def standard_offset_hours(lat, lon, year):
    """UTC offset in standard time (no daylight saving): the smaller of the January and July offsets."""
    offs = []
    for md in ('01-15', '07-15'):
        d = _get_json('https://archive-api.open-meteo.com/v1/archive?'
                      f'latitude={lat:.4f}&longitude={lon:.4f}&start_date={year}-{md}&end_date={year}-{md}'
                      '&hourly=temperature_2m&timezone=auto')
        offs.append(d['utc_offset_seconds'] / 3600)
    return min(offs)


@lru_cache(maxsize=64)
def fetch_weather(lat, lon, start, end, clock):
    """clock 'local' = local clock time (daylight saving applies); 'standard' = local standard time all year
    (no daylight saving); 'utc' = UTC. Returns naive timestamps."""
    last_ok = (dt.date.today() - dt.timedelta(days=7)).isoformat()  # the archive lags a few days
    end = min(end, last_ok)
    tz = 'auto' if clock == 'local' else 'GMT'
    shift = standard_offset_hours(lat, lon, int(start[:4])) if clock == 'standard' else 0.0
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
    if shift:
        w['timestamp'] = w['timestamp'] + pd.Timedelta(hours=shift)
    return w
