"""Make the two sample files for the app: made-up buildings driven by real 2023 weather (Open-Meteo).
These are NOT real meter data. Needs internet. Run from the repo root: python scripts/make_samples.py"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.weather import fetch_weather, zip_to_place  # noqa: E402
from pipeline import wet_bulb_temperature  # noqa: E402

rng = np.random.default_rng(7)


def tons(wx, base, slope, balance_c=10.0, day_amp=0.25, fault_from=None, fault=0.0, zero_run=None):
    wb = wet_bulb_temperature(wx['air_temperature'], wx['dew_temperature'])
    hour, dow = wx['timestamp'].dt.hour, wx['timestamp'].dt.dayofweek
    schedule = 1 + day_amp * np.sin((hour - 9) / 24 * 2 * np.pi) - 0.1 * (dow >= 5)
    t = (base + slope * np.maximum(0, wb - balance_c)) * schedule * rng.normal(1, 0.04, len(wx))
    t = pd.Series(t.values, index=wx.index).clip(lower=0)
    if fault_from:
        t[wx['timestamp'] >= fault_from] *= 1 + fault
    if zero_run:
        t[(wx['timestamp'] >= zero_run[0]) & (wx['timestamp'] < zero_run[1])] = 0.0
    return t


def weather(zip_code):
    p = zip_to_place(zip_code)
    return fetch_weather(round(p['lat'], 4), round(p['lon'], 4), '2023-01-01', '2023-12-31', 'local')


bos, phx = weather('02110'), weather('85004')
rows = []
for name, base, slope, kw in [('Library', 25, 9, {}), ('Science_Hall', 40, 14, {'fault_from': '2023-10-01', 'fault': 0.80}),
                              ('Dorm', 20, 7, {'zero_run': ('2023-03-04', '2023-03-06')})]:
    t = tons(bos, base, slope, **kw)
    rows.append(pd.DataFrame({'building_id': name, 'timestamp': bos['timestamp'], 'cooling_kwh': (t * 12 / 3.412).round(1)}))
a = pd.concat(rows, ignore_index=True)
a.to_csv(os.path.join(ROOT, 'samples', 'sample_A_long_kwh.csv'), index=False)

b = pd.DataFrame({'timestamp': bos['timestamp'], 'Boston_Library_tonhours': tons(bos, 25, 9).round(2)})
b['Phoenix_Lab_tonhours'] = tons(phx.set_index('timestamp').reindex(bos['timestamp']).reset_index().ffill(), 45, 6, 8.0).round(2).values
b.to_csv(os.path.join(ROOT, 'samples', 'sample_B_wide_tonhours.csv'), index=False)
print(a.groupby('building_id')['cooling_kwh'].describe().round(0))
print(b.describe().round(1))
