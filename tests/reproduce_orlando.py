"""Check that run_site() reproduces the notebook's Section 10 results for Orlando exactly.

Needs the Kaggle files in ashrae-energy-prediction/ (not in the repo). Run from the repo root:
    python tests/reproduce_orlando.py
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import Config, run_site  # noqa: E402

DATA = os.path.join(ROOT, 'ashrae-energy-prediction')
BUILDINGS = [95, 96, 98, 97, 76, 7, 29]

train = pd.read_csv(f'{DATA}/train.csv')
meters = train[(train['meter'] == 1) & train['building_id'].isin(BUILDINGS)][['building_id', 'timestamp', 'meter_reading']]
weather = pd.read_csv(f'{DATA}/weather_train.csv')
weather = weather[weather['site_id'] == 0].copy()
weather['timestamp'] = pd.to_datetime(weather['timestamp']) - pd.Timedelta(hours=5)
metadata = pd.read_csv(f'{DATA}/building_metadata.csv')

res = run_site(meters, weather, Config(unit='kbtu'), metadata)
print(res.impact.to_string(na_rep='-'))
print(res.totals)
print(res.sensitivity.round({'electricity kWh': 0, 'cost $': 0, 'CO2 tonnes': 1}).to_string(index=False))
print({k: v for k, v in res.checks.items() if k != 'flagged_hours'})

# Values copied from the reviewed notebook output (Section 10).
expected = {
    97: ('Flagged', 19.3, 69.9, 298874, 33036, 111.1),
    95: ('Flagged', 16.4, 76.9, 280669, 31024, 104.4),
    7: ("Can't judge", 38.7, 2.7, None, None, None),
    29: ('Within expected range', 11.4, 9.5, None, None, None),
    76: ('Within expected range', 9.0, 6.0, None, None, None),
    96: ('Within expected range', 18.7, 4.6, None, None, None),
    98: ("Can't judge", 103.3, 0.0, None, None, None),
}
for b, (verdict, cv, above, ton_hours, cost, co2) in expected.items():
    r = res.impact.loc[b]
    assert r['verdict'] == verdict, (b, r['verdict'])
    assert r['calib CV(RMSE) %'] == cv and r['hours above band %'] == above, (b, r.to_dict())
    if verdict == 'Flagged':
        assert (r['excess ton-hours'], r['cost $'], r['CO2 tonnes']) == (ton_hours, cost, co2), (b, r.to_dict())
assert round(res.totals['excess_ton_hours']) == 579543
assert round(res.totals['cost']) == 64059 and round(res.totals['cost_if_measured_from_prediction']) == 90211
print('\nOK: run_site() reproduces the notebook exactly.')
