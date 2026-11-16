"""Run the Cooling Check pipeline, unchanged, on several BDG2 sites.

Needs the Building Data Genome 2 files (metadata.csv, chilledwater_raw.csv, weather.csv) in one folder:
    python scripts/compare_sites.py path/to/bdg2_folder
"""
import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import Config, run_site  # noqa: E402

SITES = {'Orlando, FL (UCF)': 'Panther', 'Tempe, AZ (ASU)': 'Fox',
         'Princeton, NJ': 'Peacock', 'Austin, TX (UT Austin)': 'Bull'}
N_BUILDINGS = 7
MIN_HOURS_2016 = 4000
ORLANDO_KAGGLE_IDS = [95, 96, 98, 97, 76, 7, 29]
NOTEBOOK_VERDICTS = {97: 'Flagged', 95: 'Flagged', 7: "Can't judge", 29: 'Within expected range',
                     76: 'Within expected range', 96: 'Within expected range', 98: "Can't judge"}
SHOW = ['use', 'calib CV(RMSE) %', 'hours above band %', 'verdict', 'excess ton-hours', 'excess % of cooling', 'note']

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
meta_by_name = meta.set_index('building_id')


def select_buildings(site):
    m = meta[(meta['site_id'] == site) & meta['building_id'].isin(hours_2016.index[hours_2016 >= MIN_HOURS_2016])]
    return list(m.sort_values('sqft', ascending=False).head(N_BUILDINGS)['building_id'])


def run_and_print(label, names, site):
    long = cw[['timestamp'] + list(names)].melt('timestamp', var_name='building_id', value_name='meter_reading').dropna()
    w = wx_all[wx_all['site_id'] == site].rename(columns={'airTemperature': 'air_temperature', 'dewTemperature': 'dew_temperature'})
    res = run_site(long, w[['timestamp', 'air_temperature', 'dew_temperature']], Config(unit='kwh'), use_meta)
    sqft = meta_by_name.loc[names, 'sqft']
    kwh_per_sqft_yr = (long.groupby('building_id')['meter_reading'].mean() * 8760 / sqft).round(1)
    print(f"\n{'=' * 110}\n{label}  [BDG2 site '{site}', {meta[meta['site_id'] == site]['timezone'].iloc[0]}]")
    print(f"buildings: {len(names)}, sq ft {int(sqft.min()):,} to {int(sqft.max()):,}")
    print(f"units sanity, cooling kWh per sq ft per year: min {kwh_per_sqft_yr.min()}, median {kwh_per_sqft_yr.median()}, max {kwh_per_sqft_yr.max()}")
    c = res.checks
    print(f"hottest hour of day: {c['hottest_hour']}:00 (plausible: {c['hottest_hour_plausible']}), "
          f"meter rows without weather: {c['meter_rows_without_weather']}, data {c['date_range'][0][:10]} to {c['date_range'][1][:10]}")
    print("hours flagged as bad data, per building:")
    print(c['flagged_hours'].to_string() if len(c['flagged_hours']) else '  none')
    print(res.impact[SHOW].to_string(na_rep='-'))
    print(f"flagged buildings: {len(res.totals['flagged_buildings'])}, total excess {res.totals['excess_ton_hours']:,.0f} ton-hours")
    return res


for label, site in SITES.items():
    run_and_print(label, select_buildings(site), site)

print(f"\n{'=' * 110}\nCROSS-CHECK: Orlando's 7 Kaggle buildings, run through the authors' BDG2 files")
orl = meta[meta['building_id_kaggle'].isin(ORLANDO_KAGGLE_IDS)]
rule_names = set(select_buildings('Panther'))
print("rule-selected 7 for Orlando are the same 7 as the notebook's:", rule_names == set(orl['building_id']))
res = run_and_print('Orlando via BDG2', list(orl['building_id']), 'Panther')
name_to_kaggle = dict(zip(orl['building_id'], orl['building_id_kaggle'].astype(int)))
same = all(NOTEBOOK_VERDICTS[name_to_kaggle[n]] == v for n, v in res.impact['verdict'].items())
print("verdicts identical to the notebook's (Kaggle route):", same)
