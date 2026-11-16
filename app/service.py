"""Glue between the upload, the weather lookup and pipeline.run_site(). No web code here."""
import dataclasses
import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import Config, KBTU_PER_KWH, UNIT_TO_KBTU, describe_excess, run_site, status_as_of  # noqa: E402
from app.weather import WeatherError, fetch_weather, zip_to_place  # noqa: E402

UNIT_LABELS = {'kwh': 'kWh (electric-equivalent thermal energy)', 'kbtu': 'kBTU', 'ton_hours': 'ton-hours'}
PRICES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'state_prices.json')
with open(PRICES_PATH) as _f:
    STATE_PRICES = json.load(_f)
MIN_SPAN_DAYS = 270
AS_OF_FLOOR_PCT = 5.0  # materiality floor chosen in the planted-fault tests (README: How far to trust it)
RESULT_COLS = ['use', 'calib CV(RMSE) %', 'hours above band %', 'verdict', 'note', 'excess ton-hours', 'excess % of cooling']


def split_dates(start, end):
    """Test = roughly the last 5 whole months, calibration = the month before, fit = everything earlier."""
    test_start = (pd.Timestamp(end).normalize() + pd.Timedelta(days=1) - pd.DateOffset(months=5)).replace(day=1)
    cal_start = test_start - pd.DateOffset(months=1)
    return cal_start, test_start


def plain_error(msg):
    return msg


def typical_load(long, unit):
    """Peak and average cooling in tons, if the file's unit were `unit` (for the units sanity check)."""
    kbtu = long['meter_reading'] * UNIT_TO_KBTU[unit]
    per_b = kbtu.groupby(long['building_id'])
    return {'mean_tons': float(per_b.mean().median() / 12.0), 'peak_tons': float(per_b.max().max() / 12.0)}


def resolve_zips(long, info, zip_mode, single_zip, mapping_text):
    """Return dict building_id -> 5-digit ZIP, or raise WeatherError with a plain message."""
    buildings = list(info['buildings'])
    norm = lambda x: re.sub(r'[\s_]+', ' ', str(x)).strip().lower()  # "Science_Hall" == "science hall"
    if zip_mode == 'column' and 'zip' in long.columns:
        m = long.dropna(subset=['zip']).groupby('building_id')['zip'].agg(lambda s: s.mode().iloc[0]).to_dict()
    elif zip_mode == 'table':
        m = {}
        for line in (mapping_text or '').splitlines():
            parts = [p.strip() for p in line.replace('\t', ',').split(',')]
            if len(parts) >= 2 and parts[0]:
                m[norm(parts[0])] = parts[1]
        m = {b: m.get(norm(b), '') for b in buildings}
    else:
        m = {b: single_zip for b in buildings}
    missing = [b for b in buildings if not str(m.get(b, '')).strip()]
    if missing:
        raise WeatherError('No ZIP code for: ' + ', '.join(missing[:8]) + ('...' if len(missing) > 8 else ''))
    return {b: str(m[b]).strip()[:5] for b in buildings}


def score(long, info, unit, clock, zips, shuts_off_winter, price_mode, own_price, cop):
    """Run the pipeline once per ZIP. Returns dict with per-building results, per-ZIP checks, and notes."""
    span_days = (info['end'] - info['start']).days
    if span_days < MIN_SPAN_DAYS:
        raise ValueError(f'The file covers {span_days} days. This tool needs at least about 9 months '
                         '(to fit, calibrate and test) before it can judge a building.')
    cal_start, test_start = split_dates(info['start'], info['end'])
    if test_start - info['start'] < pd.Timedelta(days=120):
        raise ValueError('Not enough history before the last five months to fit a baseline. Upload a longer file.')
    cfg = Config(unit=unit, cal_start=str(cal_start.date()), test_start=str(test_start.date()),
                 zero_run_limit_hrs=10 ** 6 if shuts_off_winter else 24,
                 plant_cop=cop, price_per_kwh=0.0, min_excess_pct=AS_OF_FLOOR_PCT)  # also applied to the verdict, see README
    out_rows, group_checks, notes, price_notes = [], [], list(info['notes']), []
    by_zip = {}
    for b, z in zips.items():
        by_zip.setdefault(z, []).append(b)
    for z, blds in by_zip.items():
        place = zip_to_place(z)
        if price_mode == 'state':
            cents = STATE_PRICES['cents_per_kwh'].get(place['state'])
            price = cents / 100 if cents else 0.0
            if cents:
                price_notes.append(f"{place['state']}: {cents:.2f} cents/kWh")
        elif price_mode == 'own':
            price = own_price
        else:
            price = 0.0
        gcfg = dataclasses.replace(cfg, price_per_kwh=price)
        sub = long[long['building_id'].isin(blds)][['building_id', 'timestamp', 'meter_reading']]
        day = pd.Timedelta(days=1)  # one extra day each side, so a clock shift never leaves the edges without weather
        wx = fetch_weather(round(place['lat'], 4), round(place['lon'], 4),
                           str((sub['timestamp'].min() - day).date()), str((sub['timestamp'].max() + day).date()), clock)
        res = run_site(sub, wx, gcfg, None)
        last_day = sub['timestamp'].max()
        scored_ids = [b for b in res.impact.index if res.impact.loc[b, 'verdict'] != "Can't judge"]  # keep the trust gate
        asof_test = res.test[res.test['building_id'].isin(scored_ids)]
        asof = (status_as_of(asof_test, last_day, cfg, UNIT_TO_KBTU[unit]) if len(asof_test) else
                pd.DataFrame(columns=['status', 'first_flagged', 'back_to_normal_since']))
        # does cooling follow the weather here? daily mean cooling vs daily mean air temperature
        d = sub.merge(wx, on='timestamp').assign(day=lambda x: x['timestamp'].dt.date)
        dd = d.groupby(['building_id', 'day']).agg(c=('meter_reading', 'mean'), t=('air_temperature', 'mean')).reset_index()
        corr = pd.Series({b: (g['c'].corr(g['t']) if g['c'].std() > 0 else np.nan) for b, g in dd.groupby('building_id')})
        for b in blds:
            r = res.impact.loc[b] if b in res.impact.index else None
            row = {'building': b, 'zip': z, 'place': place['name']}
            for c in RESULT_COLS:
                row[c] = None if r is None else r.get(c)
            row['hint'] = None
            if r is not None and r.get('verdict') == 'Flagged':
                row['hint'] = describe_excess(res.test[res.test['building_id'] == b].sort_values('timestamp'))
            row['as_of'] = asof.loc[b, 'status'] if b in asof.index else 'not scored'
            row['back_to_normal_since'] = asof.loc[b, 'back_to_normal_since'] if b in asof.index else None
            row['cooling vs temperature (corr)'] = None if b not in corr.index else round(float(corr[b]), 2)
            if r is not None and price:
                row['cost $'] = r.get('cost $')
            out_rows.append(row)
        c = res.checks
        group_checks.append({'zip': z, 'place': place['name'], 'buildings': len(blds),
                             'hottest_hour': c['hottest_hour'], 'hottest_hour_plausible': c['hottest_hour_plausible'],
                             'rows_without_weather': c['meter_rows_without_weather'],
                             'flagged_hours': c['flagged_hours'], 'median_corr': float(np.nanmedian(corr.values)) if len(corr) else float('nan')})
    results = pd.DataFrame(out_rows)
    return {'results': results, 'checks': group_checks, 'notes': notes, 'cfg': cfg, 'test_start': test_start,
            'cal_start': cal_start, 'last_day': info['end'], 'price_mode': price_mode, 'price_notes': price_notes,
            'own_price': own_price, 'cop': cop}
