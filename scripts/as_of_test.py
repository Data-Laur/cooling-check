"""As-of planted-fault test: if someone checks on a given date, does the tool say the right thing?

Design (written down before running; see LEARNING_LOG sections 14b and 14c):
  - Score each building using only data up to a check date (pipeline.status_as_of).
  - Plant a fault in ALL judged buildings (multiply readings by 1+size from a start date, optionally ending).
  - Compare with the same building's UNTOUCHED status on the same date. Only (building, date) pairs where the
    untouched status is "Within expected range" are scored, so every change we see is one we caused.
  - Grid: size 10/25/50%, start Sep 1 or Oct 15, never fixed / fixed after 14 days / after 60 days,
    checked at every month end Aug-Dec. Materiality floors tried: --min-excess 0 2 5 10 (% of cooling).
  - The fit and calibration windows end before August, so a planted fault cannot change the model; planting
    into the test table equals planting into the raw file and rerunning (checked once for Orlando).

    python scripts/as_of_test.py path/to/bdg2_folder --year 2016 --min-excess 0 2 5 10
"""
import argparse
import dataclasses
import itertools
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import Config, KBTU_PER_KWH, run_site, status_as_of  # noqa: E402

SITES = {'Orlando': 'Panther', 'Tempe': 'Fox', 'Princeton': 'Peacock', 'Austin': 'Bull'}
SIZES = [0.10, 0.25, 0.50]
DURATIONS = {'never fixed': None, 'fixed after 14 days': 14, 'fixed after 60 days': 60}
N_BUILDINGS, MIN_HOURS = 7, 4000

ap = argparse.ArgumentParser()
ap.add_argument('bdg2_dir')
ap.add_argument('--year', type=int, default=2016)
ap.add_argument('--band', default='absolute', choices=['absolute', 'relative'])
ap.add_argument('--min-excess', type=float, nargs='+', default=[0.0])
a = ap.parse_args()
Y = a.year
ONSETS = [pd.Timestamp(f'{Y}-09-01'), pd.Timestamp(f'{Y}-10-15')]
CHECKS = pd.to_datetime([f'{Y}-08-31', f'{Y}-09-30', f'{Y}-10-31', f'{Y}-11-30', f'{Y}-12-31'])
base_cfg = Config(unit='kwh', cal_start=f'{Y}-07-01', test_start=f'{Y}-08-01', band=a.band)

d = a.bdg2_dir
meta = pd.read_csv(f'{d}/metadata.csv')
cw = pd.read_csv(f'{d}/chilledwater_raw.csv', parse_dates=['timestamp'])
cw = cw[(cw['timestamp'] >= f'{Y}-01-01') & (cw['timestamp'] < f'{Y + 1}-01-01')]
wx_all = pd.read_csv(f'{d}/weather.csv', parse_dates=['timestamp'])
wx_all = wx_all[(wx_all['timestamp'] >= f'{Y}-01-01') & (wx_all['timestamp'] < f'{Y + 1}-01-01')]
hours = cw.drop(columns='timestamp').notna().sum()
use_meta = meta[['building_id', 'primaryspaceusage']].rename(columns={'primaryspaceusage': 'primary_use'})


def select_buildings(site):
    m = meta[(meta['site_id'] == site) & meta['building_id'].isin(hours.index[hours >= MIN_HOURS])]
    return list(m.sort_values('sqft', ascending=False).head(N_BUILDINGS)['building_id'])


def plant(test, onset, days, size):
    t = test.copy()
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


sites = {}
for label, site in SITES.items():
    names = select_buildings(site)
    long = cw[['timestamp'] + names].melt('timestamp', var_name='building_id', value_name='meter_reading').dropna()
    w = wx_all[wx_all['site_id'] == site].rename(columns={'airTemperature': 'air_temperature', 'dewTemperature': 'dew_temperature'})
    w = w[['timestamp', 'air_temperature', 'dew_temperature']]
    res = run_site(long, w, base_cfg, use_meta)
    judged = sorted(b for b in res.test['building_id'].unique() if res.impact.loc[b, 'verdict'] != "Can't judge")
    sites[label] = (res.test[res.test['building_id'].isin(judged)], judged, long, w)
    print(f"{label} {Y}: {len(names)} buildings, {len(judged)} judged (trust gate kept)", flush=True)
    if label == 'Orlando' and Y == 2016 and judged:  # shortcut check
        mod = long.copy()
        mod.loc[mod['timestamp'] >= ONSETS[0], 'meter_reading'] *= 1.25
        full = run_site(mod, w, base_cfg, use_meta).test
        full = full[full['building_id'].isin(judged)].sort_values(['building_id', 'timestamp'])
        short = plant(sites[label][0], ONSETS[0], None, 0.25).sort_values(['building_id', 'timestamp'])
        assert len(full) == len(short) and (full['above'].values == short['above'].values).all()
        print('  shortcut check passed: same above-band hours as a full rerun', flush=True)

rows, untouched_rows = [], []
for floor in a.min_excess:
    cfg = dataclasses.replace(base_cfg, min_excess_pct=floor)
    for label, (test, judged, _, _) in sites.items():
        base = {c: status_as_of(test, c, cfg, KBTU_PER_KWH) for c in CHECKS}
        for b in judged:
            untouched_rows.append({'floor %': floor, 'site': label, 'building': b,
                                   'ever flagged': base[CHECKS[-1]].loc[b, 'first_flagged'] is not None,
                                   'status Dec 31': base[CHECKS[-1]].loc[b, 'status'],
                                   'excess ton-hours Dec 31': base[CHECKS[-1]].loc[b, 'excess ton-hours']})
        for size, onset, (dur_label, days) in itertools.product(SIZES, ONSETS, DURATIONS.items()):
            t = plant(test, onset, days, size)
            for check in CHECKS:
                st = status_as_of(t, check, cfg, KBTU_PER_KWH)
                for b in judged:
                    clean = base[check].loc[b, 'status'] == 'Within expected range'
                    rows.append({'floor %': floor, 'site': label, 'building': b, 'size %': int(size * 100),
                                 'onset': onset.date(), 'fix': dur_label, 'check': check.date(),
                                 'truth': truth(check, onset, days), 'status': st.loc[b, 'status'],
                                 'clean_untouched': clean})

out = pd.DataFrame(rows)
untouched = pd.DataFrame(untouched_rows)
scored = out[out['clean_untouched']].copy()
out.to_csv(os.path.join(ROOT, f'as_of_results_{Y}_{a.band}.csv'), index=False)

print(f'\n=== band: {a.band}, year {Y} ===')
print(f'\nUNTOUCHED data ({Y}): judged buildings with any episode, by materiality floor')
u = untouched.groupby('floor %').agg(judged=('building', 'size'), with_episode=('ever flagged', 'sum'),
                                     median_excess_ton_hours_of_those=('excess ton-hours Dec 31', 'median'))
print(u.to_string())
print('\n(building, date) pairs scored (untouched status was "Within expected range") per floor:')
print(scored.groupby('floor %').size().to_string())

on = scored[scored['truth'] == 'fault ongoing'].copy()
on['days since onset'] = (pd.to_datetime(on['check']) - pd.to_datetime(on['onset'])).dt.days
on['caught'] = on['status'] == 'Flagged, ongoing'
print('\nFAULT ONGOING: % saying "Flagged, ongoing", by floor and fault size')
print((100 * on.groupby(['floor %', 'size %'])['caught'].mean()).round(0).unstack('size %').to_string())
print('\nFAULT ONGOING, size 25%: % flagged by days since onset')
o25 = on[on['size %'] == 25]
print((100 * o25.groupby(['floor %', pd.cut(o25['days since onset'], [-1, 14, 30, 60, 120])], observed=True)['caught']
       .mean()).round(0).unstack().to_string())
fx = scored[scored['truth'] == 'fault fixed']
print('\nFAULT FIXED: what the tool said, % by floor')
print((100 * pd.crosstab(fx['floor %'], fx['status'], normalize='index')).round(0).to_string())
nf = scored[scored['truth'] == 'no fault yet']
print('\nNO FAULT YET (identical to untouched data, so should all be Within): % not Within =',
      round(100 * (nf['status'] != 'Within expected range').mean(), 1))
