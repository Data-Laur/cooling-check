"""Cooling Check pipeline: weather-normalized anomaly detection for chilled water meters.

run_site() takes hourly meter readings and weather for one site and returns a verdict per
building plus the checks behind it. The logic is the notebook's, in one reusable place.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

KBTU_PER_KWH = 3.412
KBTU_PER_TON_HOUR = 12.0
UNIT_TO_KBTU = {'kbtu': 1.0, 'kwh': KBTU_PER_KWH, 'ton_hours': KBTU_PER_TON_HOUR}
RESIDUAL_FEATURES = ['hour', 'day_of_week', 'dew_temperature']
COP_SENSITIVITY = (2.5, 3.5, 5.0)
IMPACT_COLUMNS = ['building_id', 'use', 'calib CV(RMSE) %', 'hours above band %', 'verdict', 'note',
                  'excess ton-hours', 'excess % of cooling', 'electricity kWh', 'cost $', 'CO2 tonnes']


@dataclass
class Config:
    unit: str                         # 'kbtu', 'kwh', or 'ton_hours'
    cal_start: str = '2016-07-01'     # fit before this date, calibrate the band on the month after
    test_start: str = '2016-08-01'    # test from this date on
    zero_run_limit_hrs: int = 24      # Miller et al. 2020 (BDG2): zero runs longer than this are bad data
    low_fraction: float = 0.10        # our choice: "stuck low" = daily median below 10% of usual
    min_stuck_days: int = 7           # our choice: only flag low stretches lasting a week or more
    coverage: float = 0.90
    trust_cv_rmse_max: float = 30.0   # ASHRAE Guideline 14 hourly accuracy bar
    flag_above_pct: float = 10.0      # our choice: 2x the ~5% of hours expected above a 90% band
    min_hours: int = 168              # need a week of clean data in each period to judge a building
    band: str = 'absolute'            # 'absolute' = one fixed width per building (the notebook); 'relative' = width scales with predicted load
    rel_floor_frac: float = 0.10      # relative band: predictions below this fraction of the building's calibration mean use that value as the scale
    min_excess_pct: float = 0.0       # as-of scoring: window must also have excess above the band of at least this % of its cooling
    window_days: int = 7              # as-of scoring: rolling window for "share of hours above the band"
    min_episode_days: int = 3         # as-of scoring: window share must stay above flag_above_pct this many days in a row
    plant_cop: float = 3.5            # assumption: whole chilled-water plant
    price_per_kwh: float = 0.11       # assumption: Florida commercial, ~11-12 cents
    co2_kg_per_kwh: float = 0.37      # assumption: EPA eGRID2022 Florida (FRCC)


@dataclass
class SiteResult:
    impact: pd.DataFrame
    totals: dict
    sensitivity: pd.DataFrame
    checks: dict
    test: pd.DataFrame
    halfwidth: pd.Series


def wet_bulb_temperature(dry_bulb, dew_point):
    a, b = 17.27, 237.7
    rh = 100 * np.exp((a * dew_point) / (b + dew_point) - (a * dry_bulb) / (b + dry_bulb))
    rh = np.clip(rh, 0, 100)
    return (dry_bulb * np.arctan(0.151977 * (rh + 8.313659) ** 0.5) + np.arctan(dry_bulb + rh)
            - np.arctan(rh - 1.676331) + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def enthalpy(dry_bulb, dew_point):
    p_w = 610.5 * np.exp((17.27 * dew_point) / (237.7 + dew_point))
    w = 0.622 * p_w / (101325 - p_w)
    return 1.006 * dry_bulb + w * (2501 + 1.86 * dry_bulb)


def cv_rmse(actual, pred):
    return 100 * np.sqrt(np.mean((actual - pred) ** 2)) / np.mean(actual)


def find_stuck_low_start(df, cfg):
    daily = df.set_index('timestamp')['meter_reading'].resample('D').median()
    is_low = daily < cfg.low_fraction * daily.median()
    if not is_low.iloc[-1]:
        return None
    start = is_low[~is_low].index.max() + pd.Timedelta(days=1)
    if (daily.index.max() - start).days + 1 < cfg.min_stuck_days:
        return None
    return start


def clean_building(df, cfg):
    df = df.sort_values('timestamp').drop_duplicates(subset='timestamp', keep='first').reset_index(drop=True)
    df['flag'] = ''
    is_zero = df['meter_reading'] == 0
    run_id = (is_zero != is_zero.shift()).cumsum()
    run_length = is_zero.groupby(run_id).transform('size')
    df.loc[is_zero & (run_length > cfg.zero_run_limit_hrs), 'flag'] = 'long_zero_run'
    low_start = find_stuck_low_start(df, cfg)
    if low_start is not None:
        df.loc[(df['timestamp'] >= low_start) & (df['flag'] == ''), 'flag'] = 'stuck_low'
    return df


def fit_changepoint_model(x, y, n_candidates=50):
    candidates = np.percentile(x, np.linspace(5, 95, n_candidates))
    best = None
    for cp in candidates:
        X = np.column_stack([np.ones_like(x), np.maximum(0, x - cp)])
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        sse = np.sum((y - X @ coef) ** 2)
        if best is None or sse < best['sse']:
            best = {'balance_point_c': cp, 'base_load': coef[0], 'slope': coef[1], 'sse': sse}
    return best


def predict_changepoint(params, x):
    return params['base_load'] + params['slope'] * np.maximum(0, x - params['balance_point_c'])


def fit_hybrid(train_df):
    fitted = {}
    for b_id, b in train_df.groupby('building_id'):
        cp = fit_changepoint_model(b['wet_bulb'].values, b['meter_reading'].values)
        resid = b['meter_reading'].values - predict_changepoint(cp, b['wet_bulb'].values)
        rm = HistGradientBoostingRegressor(random_state=0).fit(b[RESIDUAL_FEATURES], resid)
        fitted[b_id] = (cp, rm)
    return fitted


def predict_hybrid(fitted, df):
    pred = pd.Series(np.nan, index=df.index)
    for b_id, (cp, rm) in fitted.items():
        m = df['building_id'] == b_id
        if m.any():
            pred[m] = predict_changepoint(cp, df.loc[m, 'wet_bulb'].values) + rm.predict(df.loc[m, RESIDUAL_FEATURES])
    return pred


def conformal_halfwidths(fitted, cal_df, coverage=0.90):
    abs_err = (cal_df['meter_reading'] - predict_hybrid(fitted, cal_df)).abs()
    halfwidths = {}
    for b_id, e in abs_err.groupby(cal_df['building_id']):
        n = len(e)
        level = min(1.0, np.ceil((n + 1) * coverage) / n)
        halfwidths[b_id] = e.quantile(level)
    return pd.Series(halfwidths)


def conformal_relative(fitted, cal_df, coverage=0.90, floor_frac=0.10):
    """Like conformal_halfwidths, but on error as a share of the prediction, so the band scales with load.
    Returns per building: q (relative half-width) and floor (the smallest prediction value used as the scale)."""
    pred = predict_hybrid(fitted, cal_df)
    out = {}
    for b_id, g in cal_df.groupby('building_id'):
        floor = floor_frac * pred[g.index].mean()
        scale = np.maximum(pred[g.index], floor)
        e = ((g['meter_reading'] - pred[g.index]).abs() / scale)
        n = len(e)
        out[b_id] = {'q': e.quantile(min(1.0, np.ceil((n + 1) * coverage) / n)), 'floor': floor}
    return pd.DataFrame(out).T


def to_impact(excess_kbtu, cfg):
    electricity_kwh = excess_kbtu / KBTU_PER_KWH / cfg.plant_cop
    return electricity_kwh, electricity_kwh * cfg.price_per_kwh, electricity_kwh * cfg.co2_kg_per_kwh / 1000


def run_site(meters, weather, cfg, metadata=None):
    """meters: [building_id, timestamp, meter_reading]; weather: [timestamp, air_temperature, dew_temperature].
    Both must already be on the same clock (see checks['hottest_hour'] for a sanity test)."""
    to_kbtu = UNIT_TO_KBTU[cfg.unit]
    meters = meters.copy()
    meters['timestamp'] = pd.to_datetime(meters['timestamp'])
    weather = weather.copy()
    weather['timestamp'] = pd.to_datetime(weather['timestamp'])
    weather = (weather[['timestamp', 'air_temperature', 'dew_temperature']]
               .dropna().drop_duplicates(subset='timestamp'))

    cleaned = pd.concat([clean_building(g[['timestamp', 'meter_reading']], cfg).assign(building_id=b)
                         for b, g in meters.groupby('building_id')], ignore_index=True)
    cleaned = cleaned.sort_values(['building_id', 'timestamp'])
    data = cleaned.merge(weather, on='timestamp', how='inner')
    data['hour'] = data['timestamp'].dt.hour
    data['day_of_week'] = data['timestamp'].dt.dayofweek
    data['wet_bulb'] = wet_bulb_temperature(data['air_temperature'], data['dew_temperature'])
    ok = data[data['flag'] == ''].copy()

    cal_start, test_start = pd.Timestamp(cfg.cal_start), pd.Timestamp(cfg.test_start)
    fit_part = ok[ok['timestamp'] < cal_start]
    cal_part = ok[(ok['timestamp'] >= cal_start) & (ok['timestamp'] < test_start)]
    test_part = ok[ok['timestamp'] >= test_start].copy()

    hours = {name: part.groupby('building_id').size() for name, part in
             [('fit', fit_part), ('cal', cal_part), ('test', test_part)]}
    judged = [b for b in sorted(meters['building_id'].unique())
              if all(hours[p].get(b, 0) >= cfg.min_hours for p in hours)]

    hybrid_fit = fit_hybrid(fit_part[fit_part['building_id'].isin(judged)])
    cal_j = cal_part[cal_part['building_id'].isin(judged)]
    halfwidth = conformal_halfwidths(hybrid_fit, cal_j, cfg.coverage)
    rel = conformal_relative(hybrid_fit, cal_j, cfg.coverage, cfg.rel_floor_frac) if cfg.band == 'relative' else None
    cal_pred = predict_hybrid(hybrid_fit, cal_j)
    cal_cv = {b: cv_rmse(g['meter_reading'], cal_pred[g.index]) for b, g in cal_j.groupby('building_id')}

    tp = test_part[test_part['building_id'].isin(judged)].copy()
    tp['pred'] = predict_hybrid(hybrid_fit, tp)
    if rel is None:
        hw = tp['building_id'].map(halfwidth)
    else:
        hw = tp['building_id'].map(rel['q']) * np.maximum(tp['pred'], tp['building_id'].map(rel['floor']))
        halfwidth = rel['q']
    tp['lower'] = tp['pred'] - hw
    tp['upper'] = tp['pred'] + hw
    tp['above'] = tp['meter_reading'] > tp['upper']
    tp['excess_kbtu'] = (tp['meter_reading'] - tp['upper']).clip(lower=0) * to_kbtu

    use = metadata.set_index('building_id')['primary_use'] if metadata is not None else {}
    rows = []
    for b in sorted(meters['building_id'].unique()):
        row = {'building_id': b, 'use': use.get(b, '') if len(use) else ''}
        if b not in judged:
            short = [p for p in hours if hours[p].get(b, 0) < cfg.min_hours]
            row.update({'verdict': "Can't judge", 'note': f"not enough clean data in: {', '.join(short)}"})
        else:
            g = tp[tp['building_id'] == b]
            above_pct = 100 * g['above'].mean()
            row.update({'calib CV(RMSE) %': round(cal_cv[b], 1), 'hours above band %': round(above_pct, 1)})
            exc_pct = 100 * g['excess_kbtu'].sum() / max(g['meter_reading'].sum() * to_kbtu, 1e-9)
            if cal_cv[b] > cfg.trust_cv_rmse_max:
                acc = 'no cooling in the calibration month' if not np.isfinite(cal_cv[b]) else f"{cal_cv[b]:.1f}% is worse than {cfg.trust_cv_rmse_max:.0f}%"
                row.update({'verdict': "Can't judge", 'note': f"model accuracy: {acc}"})
            elif above_pct > cfg.flag_above_pct and exc_pct < cfg.min_excess_pct:
                row.update({'verdict': 'Within expected range',
                            'note': f"above the band in {above_pct:.0f}% of hours, but the excess is only {exc_pct:.1f}% of its cooling (below the {cfg.min_excess_pct:g}% floor)"})
            elif above_pct > cfg.flag_above_pct:
                kwh, dollars, tonnes = to_impact(g['excess_kbtu'].sum(), cfg)
                row.update({'verdict': 'Flagged',
                            'excess ton-hours': round(g['excess_kbtu'].sum() / KBTU_PER_TON_HOUR),
                            'excess % of cooling': round(100 * g['excess_kbtu'].sum() / (g['meter_reading'].sum() * to_kbtu), 1),
                            'electricity kWh': round(kwh), 'cost $': round(dollars), 'CO2 tonnes': round(tonnes, 1)})
            else:
                row['verdict'] = 'Within expected range'
        rows.append(row)
    impact = pd.DataFrame(rows, columns=IMPACT_COLUMNS).set_index('building_id')
    impact = impact.sort_values('cost $', ascending=False, na_position='last')

    flagged = tp[tp['building_id'].isin(impact.index[impact['verdict'] == 'Flagged'])]
    total_kbtu = flagged['excess_kbtu'].sum()
    vs_pred_kbtu = (flagged['meter_reading'] - flagged['pred']).clip(lower=0).sum() * to_kbtu
    _, cost_edge, co2_edge = to_impact(total_kbtu, cfg)
    _, cost_pred, co2_pred = to_impact(vs_pred_kbtu, cfg)
    totals = {'flagged_buildings': list(flagged['building_id'].unique()),
              'excess_ton_hours': total_kbtu / KBTU_PER_TON_HOUR,
              'cost': cost_edge, 'co2_tonnes': co2_edge,
              'cost_if_measured_from_prediction': cost_pred, 'co2_if_measured_from_prediction': co2_pred}
    sens = []
    for cop in COP_SENSITIVITY:
        kwh = total_kbtu / KBTU_PER_KWH / cop
        sens.append({'COP': cop, 'electricity kWh': kwh, 'cost $': kwh * cfg.price_per_kwh,
                     'CO2 tonnes': kwh * cfg.co2_kg_per_kwh / 1000})

    mean_by_hour = weather.groupby(weather['timestamp'].dt.hour)['air_temperature'].mean()
    hottest = int(mean_by_hour.idxmax())
    checks = {
        'buildings': len(meters['building_id'].unique()),
        'date_range': (str(data['timestamp'].min()), str(data['timestamp'].max())),
        'hottest_hour': hottest,
        'hottest_hour_plausible': 13 <= hottest <= 17,
        'meter_rows_without_weather': int(len(cleaned) - len(data)),
        'flagged_hours': data.groupby(['building_id', 'flag']).size().unstack(fill_value=0).drop(columns='', errors='ignore'),
    }
    return SiteResult(impact, totals, pd.DataFrame(sens), checks, tp, halfwidth)


def hot_days(building_test, cfg, to_kbtu=1.0):
    """Per day: share of the last window_days of hours above the band, and whether it is past the flag line.
    Past the flag line = share above the band > flag_above_pct AND (if min_excess_pct > 0) the excess above the
    band's upper edge is at least min_excess_pct of the window's cooling. Windows with under half their hours
    are left blank. building_test needs columns timestamp, above, meter_reading, excess_kbtu."""
    t = building_test.set_index('timestamp')
    daily = pd.DataFrame({'above': t['above'].astype(float).resample('D').sum(),
                          'n': t['above'].resample('D').count(),
                          'excess': t['excess_kbtu'].resample('D').sum(),
                          'cooling': (t['meter_reading'] * to_kbtu).resample('D').sum()})
    r = daily.rolling(cfg.window_days, min_periods=1).sum()
    share = (100 * r['above'] / r['n']).where(r['n'] >= 12 * cfg.window_days)
    excess_pct = 100 * r['excess'] / r['cooling'].where(r['cooling'] > 0)
    hot = (share > cfg.flag_above_pct) & (excess_pct >= cfg.min_excess_pct)
    return share, hot


def status_as_of(test, as_of, cfg, to_kbtu):
    """Judge each building using only data up to and including the day `as_of`.
    test: SiteResult.test (judged buildings, with columns building_id, timestamp, above, excess_kbtu).
    Returns one row per building: 'Flagged, ongoing' | 'Was flagged, back to normal' | 'Within expected range'.
    An episode = the rolling share above the band stays over the flag line for min_episode_days days in a row."""
    end = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)
    rows = []
    for b, g in test[test['timestamp'] < end].groupby('building_id'):
        _, hot = hot_days(g, cfg, to_kbtu)
        run_id = (hot != hot.shift()).cumsum()
        runs = [(grp.index[0], grp.index[-1], len(grp)) for _, grp in hot[hot].groupby(run_id[hot])]
        runs = [r for r in runs if r[2] >= cfg.min_episode_days]
        last_day = hot.index[-1]
        row = {'building_id': b, 'status': 'Within expected range', 'first_flagged': None, 'back_to_normal_since': None,
               'excess ton-hours': 0.0}
        if runs:
            first = runs[0][0] - pd.Timedelta(days=cfg.window_days - 1)
            row['first_flagged'] = runs[0][0].date()
            row['excess ton-hours'] = round(g[g['timestamp'] >= first]['excess_kbtu'].sum() / KBTU_PER_TON_HOUR)
            if runs[-1][1] == last_day and hot.iloc[-1]:
                row['status'] = 'Flagged, ongoing'
            else:
                row['status'] = 'Was flagged, back to normal'
                row['back_to_normal_since'] = (runs[-1][1] + pd.Timedelta(days=1)).date()
        rows.append(row)
    cols = ['building_id', 'status', 'first_flagged', 'back_to_normal_since', 'excess ton-hours']
    return pd.DataFrame(rows, columns=cols).set_index('building_id')


OCCUPIED_START_HOUR, OCCUPIED_END_HOUR = 7, 19  # weekdays 7:00 to 18:59 count as occupied hours (our choice)


def describe_excess(b, margin=0.01, min_days=7, min_excess=0.05, pattern_gap=0.15):
    """When did a building start using more than expected, and when in the week does the extra happen?
    b: one building's test hours with columns timestamp, meter_reading, pred, upper (time-ordered, any units).
    Finds the stretch of days with the most cumulative excess ABOVE THE BAND: daily (reading above the band's upper
    edge) / prediction, minus a small margin, then the best contiguous run of days (largest-sum run). The first
    version used the gap to the prediction, which picked up ordinary drift in normal buildings (post-hoc change,
    see LEARNING_LOG 16). A hint, not a diagnosis.
    Returns None if no stretch of at least min_days has average excess of at least min_excess."""
    t = b.set_index('timestamp')
    daily = pd.DataFrame({'res': (t['meter_reading'] - t['pred']).resample('D').sum(),
                          'ex': (t['meter_reading'] - t['upper']).clip(lower=0).resample('D').sum(),
                          'pred': t['pred'].resample('D').sum(), 'n': t['pred'].resample('D').count()})
    daily = daily[daily['n'] >= 12]
    if len(daily) < min_days:
        return None
    d = (daily['ex'] / daily['pred']).values - margin
    best, cur, start, bs, be = -1e9, 0.0, 0, 0, 0
    for i, v in enumerate(d):
        if cur <= 0:
            cur, start = v, i
        else:
            cur += v
        if cur > best:
            best, bs, be = cur, start, i
    seg = daily.iloc[bs:be + 1]
    if len(seg) < min_days or seg['res'].sum() / seg['pred'].sum() < min_excess:
        return None
    onset, end = seg.index[0], seg.index[-1]
    inside = b[(b['timestamp'] >= onset) & (b['timestamp'] < end + pd.Timedelta(days=1))]
    resid = inside['meter_reading'] - inside['pred']
    after = (inside['timestamp'].dt.hour < OCCUPIED_START_HOUR) | (inside['timestamp'].dt.hour >= OCCUPIED_END_HOUR) | \
            (inside['timestamp'].dt.dayofweek >= 5)
    excess_after = resid[after].sum() / resid.sum() if resid.sum() > 0 else float('nan')
    base_after = inside.loc[after, 'pred'].sum() / inside['pred'].sum()
    gap = excess_after - base_after
    pattern = 'after_hours' if gap >= pattern_gap else ('occupied_hours' if gap <= -pattern_gap else 'all_day')
    last_day = daily.index[-1]
    return {'onset': onset.date(), 'end': end.date(), 'ongoing': bool(end >= last_day - pd.Timedelta(days=2)),
            'excess_pct': round(100 * seg['res'].sum() / seg['pred'].sum(), 1),
            'excess_after_hours_share': round(float(excess_after), 2), 'normal_after_hours_share': round(float(base_after), 2),
            'pattern': pattern}
