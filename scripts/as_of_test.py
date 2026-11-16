"""As-of planted-fault test: if someone checks on a given date, does the tool say the right thing?

Pre-registered grid (written before running; see LEARNING_LOG section 14b):
  fault size 10/25/50%, start Sep 1 or Oct 15, ending never / after 14 days / after 60 days,
  checked on the last day of every month Aug-Dec (Dec 31 doubles as "first of next month").
Only buildings with no episode in their untouched run are eligible, so every alert is one we caused.
The fit and calibration windows end before August, so a planted fault cannot change the model;
we apply the fault to the test-period readings directly and check this shortcut against a full rerun.

    python scripts/as_of_test.py path/to/bdg2_folder
"""
import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import Config, KBTU_PER_KWH, run_site, status_as_of  # noqa: E402

SITES = {'Orlando': 'Panther', 'Tempe': 'Fox', 'Princeton': 'Peacock', 'Austin': 'Bull'}
SIZES = [0.10, 0.25, 0.50]
ONSETS = [pd.Timestamp('2016-09-01'), pd.Timestamp('2016-10-15')]
DURATIONS = {'never fixed': None, 'fixed after 14 days': 14, 'fixed after 60 days': 60}
CHECKS = pd.to_datetime(['2016-08-31', '2016-09-30', '2016-10-31', '2016-11-30', '2016-12-31'])
N_BUILDINGS, MIN_HOURS_2016 = 7, 4000
cfg = Config(unit='kwh')

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


def plant(test, buildings, onset, days, size):
    t = test[test['building_id'].isin(buildings)].copy()
    end = onset + pd.Timedelta(days=days) if days else pd.Timestamp.max
    hit = (t['timestamp'] >= onset) & (t['timestamp'] < end)
    t.loc[hit, 'meter_reading'] *= 1 + size
    t['above'] = t['meter_reading'] > t['upper']
    t['excess_kbtu'] = (t['meter_reading'] - t['upper']).clip(lower=0) * KBTU_PER_KWH
    return t


def truth(check, onset, days):
    if check < onset:
        return 'no fault yet'
    if days is None or check < onset + pd.Timedelta(days=days):
        return 'fault ongoing'
    return 'fault fixed'


rows, untouched_rows = [], []
for label, site in SITES.items():
    names = select_buildings(site)
    long = cw[['timestamp'] + names].melt('timestamp', var_name='building_id', value_name='meter_reading').dropna()
    w = wx_all[wx_all['site_id'] == site].rename(columns={'airTemperature': 'air_temperature', 'dewTemperature': 'dew_temperature'})
    w = w[['timestamp', 'air_temperature', 'dew_temperature']]
    res = run_site(long, w, cfg, use_meta)
    judged = sorted(b for b in res.test['building_id'].unique() if res.impact.loc[b, 'verdict'] != "Can't judge")  # keep the trust gate
    res.test = res.test[res.test['building_id'].isin(judged)]
    base = status_as_of(res.test, CHECKS[-1], cfg, KBTU_PER_KWH)
    for b in judged:
        untouched_rows.append({'site': label, 'building': b, 'status on Dec 31 (untouched)': base.loc[b, 'status'],
                               'ever flagged': base.loc[b, 'first_flagged'] is not None})
    eligible = [b for b in judged if base.loc[b, 'first_flagged'] is None]
    print(f"{label}: {len(names)} buildings, {len(judged)} judged, {len(eligible)} with no episode untouched (eligible)", flush=True)

    # shortcut check: planting into the test table == planting into the raw meter file and rerunning everything
    if label == 'Orlando' and eligible:
        mod = long.copy()
        mod.loc[mod['timestamp'] >= ONSETS[0], 'meter_reading'] *= 1.25
        full = run_site(mod, w, cfg, use_meta).test
        short = plant(res.test, eligible, ONSETS[0], None, 0.25)
        full = full[full['building_id'].isin(eligible)].sort_values(['building_id', 'timestamp'])
        short = short.sort_values(['building_id', 'timestamp'])
        assert len(full) == len(short) and (full['above'].values == short['above'].values).all()
        print('  shortcut check passed: same above-band hours as a full rerun', flush=True)

    if not eligible:
        continue
    for size, onset, (dur_label, days) in itertools.product(SIZES, ONSETS, DURATIONS.items()):
        t = plant(res.test, eligible, onset, days, size)
        for check in CHECKS:
            st = status_as_of(t, check, cfg, KBTU_PER_KWH)
            for b in eligible:
                rows.append({'site': label, 'building': b, 'size %': int(size * 100), 'onset': onset.date(),
                             'fix': dur_label, 'check': check.date(), 'truth': truth(check, onset, days),
                             'status': st.loc[b, 'status']})

out = pd.DataFrame(rows)
untouched = pd.DataFrame(untouched_rows)
print('\nUNTOUCHED judged buildings: status on Dec 31')
print(untouched.groupby('site')['status on Dec 31 (untouched)'].value_counts().unstack(fill_value=0).to_string())
print('\nWHAT THE TOOL SAID, by what was true (all eligible buildings, all scenarios; each row sums to 100%)')
print((100 * pd.crosstab(out['truth'], out['status'], normalize='index')).round(0).to_string())
print('\nBY FAULT SIZE: when a fault is ongoing, % saying "Flagged, ongoing"')
on = out[out['truth'] == 'fault ongoing']
print((100 * (on['status'] == 'Flagged, ongoing').groupby(on['size %']).mean()).round(0).to_string())
print('\nBY FAULT SIZE: after a fix, % saying "Was flagged, back to normal" (right), "Flagged, ongoing" (wrong), "Within" (never noticed)')
fx = out[out['truth'] == 'fault fixed']
print((100 * pd.crosstab(fx['size %'], fx['status'], normalize='index')).round(0).to_string())
print('\nBY DAYS SINCE ONSET (ongoing faults, 25% size): % flagged')
on25 = out[(out['truth'] == 'fault ongoing') & (out['size %'] == 25)].copy()
on25['days since onset'] = (pd.to_datetime(on25['check']) - pd.to_datetime(on25['onset'])).dt.days
bins = pd.cut(on25['days since onset'], [-1, 14, 30, 60, 120])
print((100 * (on25['status'] == 'Flagged, ongoing').groupby(bins, observed=True).mean()).round(0).to_string())
print('\nrows:', len(out), ' buildings eligible per site:', out.groupby('site')['building'].nunique().to_dict())
out.to_csv(os.path.join(ROOT, 'as_of_results.csv'), index=False)
