"""Planted-anomaly test: does the unchanged pipeline catch extra cooling we add on purpose?

For each BDG2 site, take the same buildings as compare_sites.py. Run once untouched. Then, for each
fault size and start date, multiply every meter reading from the start date on by (1 + size) and rerun.
Detection is counted only among buildings that were judged and "Within expected range" untouched,
so a building that was already flagged (or can't be judged) never counts as a catch.

    python scripts/planted_anomaly_test.py path/to/bdg2_folder
"""
import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import Config, run_site  # noqa: E402

SITES = {'Orlando': 'Panther', 'Tempe': 'Fox', 'Princeton': 'Peacock', 'Austin': 'Bull'}
SIZES = [0.10, 0.25, 0.50]
ONSETS = ['2016-09-01', '2016-11-01']
N_BUILDINGS, MIN_HOURS_2016 = 7, 4000

ap = argparse.ArgumentParser()
ap.add_argument('bdg2_dir')
d = ap.parse_args().bdg2_dir
meta = pd.read_csv(f'{d}/metadata.csv')
cw = pd.read_csv(f'{d}/chilledwater_raw.csv', parse_dates=['timestamp'])
cw = cw[cw['timestamp'] < '2017-01-01']
wx_all = pd.read_csv(f'{d}/weather.csv', parse_dates=['timestamp'])
wx_all = wx_all[wx_all['timestamp'] < '2017-01-01']
hours_2016 = cw.drop(columns='timestamp').notna().sum()
use_meta = meta[['building_id', 'primaryspaceusage']].rename(columns={'primaryspaceusage': 'primary_use'})


def select_buildings(site):
    m = meta[(meta['site_id'] == site) & meta['building_id'].isin(hours_2016.index[hours_2016 >= MIN_HOURS_2016])]
    return list(m.sort_values('sqft', ascending=False).head(N_BUILDINGS)['building_id'])


rows = []
for label, site in SITES.items():
    names = select_buildings(site)
    long = cw[['timestamp'] + names].melt('timestamp', var_name='building_id', value_name='meter_reading').dropna()
    w = wx_all[wx_all['site_id'] == site].rename(columns={'airTemperature': 'air_temperature', 'dewTemperature': 'dew_temperature'})
    w = w[['timestamp', 'air_temperature', 'dew_temperature']]
    base = run_site(long, w, Config(unit='kwh'), use_meta).impact
    eligible = list(base.index[base['verdict'] == 'Within expected range'])
    print(f"{label}: untouched verdicts {base['verdict'].value_counts().to_dict()}; eligible for the test: {len(eligible)}", flush=True)
    for onset in ONSETS:
        for size in SIZES:
            mod = long.copy()
            hit = mod['timestamp'] >= onset
            mod.loc[hit, 'meter_reading'] *= 1 + size
            res = run_site(mod, w, Config(unit='kwh'), use_meta).impact
            for b in eligible:
                r = res.loc[b]
                rows.append({'site': label, 'building': b, 'onset': onset, 'size %': int(size * 100),
                             'verdict': r['verdict'], 'hours above band %': r['hours above band %'],
                             'excess % of cooling': r['excess % of cooling']})

out = pd.DataFrame(rows)
out['caught'] = out['verdict'] == 'Flagged'
out['lost'] = out['verdict'] == "Can't judge"
summary = (out.groupby(['onset', 'size %'])
           .agg(buildings=('caught', 'size'), caught=('caught', 'sum'), became_cant_judge=('lost', 'sum'),
                median_above_band=('hours above band %', 'median'),
                median_excess_pct_of_cooling_when_caught=('excess % of cooling', 'median')))
summary['catch rate %'] = (100 * summary['caught'] / summary['buildings']).round(0)
print('\nALL SITES')
print(summary.to_string())
print('\nBY SITE (catch rate %)')
print(out.groupby(['site', 'onset', 'size %'])['caught'].mean().mul(100).round(0).unstack('size %').to_string())
out.to_csv(os.path.join(ROOT, 'planted_anomaly_results.csv'), index=False)
