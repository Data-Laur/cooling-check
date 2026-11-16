"""Test the "check first" hints with planted faults whose start, end and timing are known.

Pre-registered (before running): describe_excess() defaults (margin 2%, at least 7 days, at least 5% average excess,
pattern gap 15 points). Plant into every judged building whose untouched verdict is "Within expected range":
  all-day faults (+25%, +50%), after-hours-only faults (+50%, +100% on nights/weekends),
  occupied-hours-only faults (+50%, +100% on weekdays 7:00 to 19:00),
  starting Sep 1 or Oct 15, never fixed or fixed after 60 days. Check as of Dec 31.
Reported: how often a clear hint appears, onset and end errors in days, and whether the timing pattern is named right.

    python scripts/hints_test.py path/to/bdg2_folder --year 2016
"""
import argparse
import itertools
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from pipeline import (Config, OCCUPIED_END_HOUR, OCCUPIED_START_HOUR, describe_excess, run_site)  # noqa: E402

SITES = {'Orlando': 'Panther', 'Tempe': 'Fox', 'Princeton': 'Peacock', 'Austin': 'Bull'}
ap = argparse.ArgumentParser()
ap.add_argument('bdg2_dir')
ap.add_argument('--year', type=int, default=2016)
a = ap.parse_args()
Y, d = a.year, a.bdg2_dir
cfg = Config(unit='kwh', cal_start=f'{Y}-07-01', test_start=f'{Y}-08-01', min_excess_pct=5.0)
meta = pd.read_csv(f'{d}/metadata.csv')
cw = pd.read_csv(f'{d}/chilledwater_raw.csv', parse_dates=['timestamp'])
cw = cw[(cw['timestamp'] >= f'{Y}-01-01') & (cw['timestamp'] < f'{Y + 1}-01-01')]
wx_all = pd.read_csv(f'{d}/weather.csv', parse_dates=['timestamp'])
wx_all = wx_all[(wx_all['timestamp'] >= f'{Y}-01-01') & (wx_all['timestamp'] < f'{Y + 1}-01-01')]
hours = cw.drop(columns='timestamp').notna().sum()
ONSETS = [pd.Timestamp(f'{Y}-09-01'), pd.Timestamp(f'{Y}-10-15')]
# (label, size, which hours)
FAULTS = [('all-day +25%', 0.25, 'all'), ('all-day +50%', 0.50, 'all'), ('after-hours +50%', 0.50, 'after'),
          ('after-hours +100%', 1.00, 'after'), ('occupied +50%', 0.50, 'occ'), ('occupied +100%', 1.00, 'occ')]
TRUTH = {'all': 'all_day', 'after': 'after_hours', 'occ': 'occupied_hours'}


def select(site):
    m = meta[(meta['site_id'] == site) & meta['building_id'].isin(hours.index[hours >= 4000])]
    return list(m.sort_values('sqft', ascending=False).head(7)['building_id'])


def plant(test, onset, days, size, which):
    t = test.copy()
    end = onset + pd.Timedelta(days=days) if days else pd.Timestamp.max
    h = t['timestamp'].dt.hour
    after = (h < OCCUPIED_START_HOUR) | (h >= OCCUPIED_END_HOUR) | (t['timestamp'].dt.dayofweek >= 5)
    sel = {'all': pd.Series(True, index=t.index), 'after': after, 'occ': ~after}[which]
    hit = (t['timestamp'] >= onset) & (t['timestamp'] < end) & sel
    t.loc[hit, 'meter_reading'] *= 1 + size
    return t


rows = []
for label, site in SITES.items():
    names = select(site)
    long = cw[['timestamp'] + names].melt('timestamp', var_name='building_id', value_name='meter_reading').dropna()
    w = wx_all[wx_all['site_id'] == site].rename(columns={'airTemperature': 'air_temperature', 'dewTemperature': 'dew_temperature'})
    res = run_site(long, w[['timestamp', 'air_temperature', 'dew_temperature']], cfg, None)
    ok = [b for b in res.impact.index if res.impact.loc[b, 'verdict'] == 'Within expected range']
    print(f'{label} {Y}: {len(ok)} eligible buildings', flush=True)
    for b in ok:
        base = res.test[res.test['building_id'] == b]
        untouched_hint = describe_excess(base)
        for (fl, size, which), onset, days in itertools.product(FAULTS, ONSETS, [None, 60]):
            hint = describe_excess(plant(base, onset, days, size, which))
            end_true = (onset + pd.Timedelta(days=days - 1)) if days else None
            rows.append({'site': label, 'building': b, 'fault': fl, 'onset': onset.date(), 'ended': bool(days),
                         'clear': hint is not None,
                         'onset_err_days': None if hint is None else abs((pd.Timestamp(hint['onset']) - onset).days),
                         'end_err_days': None if (hint is None or not days) else abs((pd.Timestamp(hint['end']) - end_true).days),
                         'said_ongoing': None if hint is None else hint['ongoing'],
                         'truth': TRUTH[which], 'pattern': None if hint is None else hint['pattern']})
        rows.append({'site': label, 'building': b, 'fault': 'none (untouched)', 'onset': None, 'ended': False,
                     'clear': untouched_hint is not None, 'onset_err_days': None, 'end_err_days': None, 'said_ongoing': None,
                     'truth': 'none', 'pattern': None if untouched_hint is None else untouched_hint['pattern']})
out = pd.DataFrame(rows)
out.to_csv(os.path.join(ROOT, f'hints_results_{Y}.csv'), index=False)
f = out[out['fault'] != 'none (untouched)']
print(f'\n=== {Y} ===')
print('UNTOUCHED eligible buildings that still got a "clear" hint:', int(out[out['fault'] == 'none (untouched)']['clear'].sum()),
      'of', int((out['fault'] == 'none (untouched)').sum()))
g = f.groupby('fault').agg(runs=('clear', 'size'), clear_pct=('clear', lambda s: round(100 * s.mean())),
                           onset_within_7d_pct=('onset_err_days', lambda s: round(100 * (s.dropna() <= 7).mean()) if s.notna().any() else None),
                           onset_median_err_days=('onset_err_days', 'median'))
print('\nBY FAULT (all onsets and durations):'); print(g.to_string())
e = f[f['ended'] & f['clear']]
print('\nFAULTS THAT ENDED after 60 days: end-date error (days), median / within 7 days %:',
      e['end_err_days'].median(), round(100 * (e['end_err_days'] <= 7).mean()))
print('said "ongoing" for a fault that ended: %', round(100 * e['said_ongoing'].mean()),
      '| said "ongoing" for a fault never fixed: %', round(100 * f[~f['ended'] & f['clear']]['said_ongoing'].mean()))
c = f[f['clear']]
print('\nTIMING PATTERN NAMED (rows = what we planted, columns = what the hint said, % of clear hints):')
print((100 * pd.crosstab(c['truth'], c['pattern'], normalize='index')).round(0).to_string())
