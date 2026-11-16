"""Per-building data for the detail view (week by week charts). JSON-ready, rounded to keep the page small.
Cooling is shown in tons (1 ton = 12,000 BTU per hour); outdoor temperature in degrees F."""
import numpy as np
import pandas as pd


def _r(x, n=1):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), n) for v in x]


def build_detail(g, f_tons):
    """g: one building's test hours (timestamp, meter_reading, pred, lower, upper, above, air_temperature, wet_bulb),
    f_tons: multiply a reading in the user's unit by this to get tons."""
    g = g.sort_values('timestamp')
    start = g['timestamp'].min().normalize()
    h = ((g['timestamp'] - start) / pd.Timedelta(hours=1)).round().astype(int)
    act, exp = g['meter_reading'] * f_tons, g['pred'] * f_tons
    lo, up = (g['lower'] * f_tons).clip(lower=0), g['upper'] * f_tons  # cooling cannot go below zero
    over = (act - up).clip(lower=0)
    temp_f = g['air_temperature'] * 9 / 5 + 32
    wb_f = g['wet_bulb'] * 9 / 5 + 32
    day = g['timestamp'].dt.normalize()
    daily = pd.DataFrame({'day': day, 'over': over, 'act': act, 'exp': exp}).groupby('day').sum()
    month = g['timestamp'].dt.to_period('M')
    monthly = pd.DataFrame({'m': month, 'act': act, 'exp': exp}).groupby('m').sum()
    heat = np.zeros((7, 24))
    np.add.at(heat, (g['timestamp'].dt.dayofweek.values, g['timestamp'].dt.hour.values), over.values)
    week_over = over.groupby((h // 168).values).sum()
    return {
        'start': start.strftime('%Y-%m-%d %H:%M'),
        'h': h.tolist(), 'actual': _r(act), 'expected': _r(exp), 'lower': _r(lo), 'upper': _r(up),
        'temp_f': _r(temp_f, 0), 'wb_f': _r(wb_f, 0), 'above': g['above'].astype(int).tolist(),
        'daily': {'days': [d.strftime('%Y-%m-%d') for d in daily.index], 'over': _r(daily['over'], 0),
                  'actual': _r(daily['act'], 0), 'expected': _r(daily['exp'], 0)},
        'monthly': {'months': [m.strftime('%b %Y') for m in monthly.index], 'actual': _r(monthly['act'], 0),
                    'expected': _r(monthly['exp'], 0)},
        'heat': [_r(row, 0) for row in heat],
        'worst_week': int(week_over.idxmax()) if len(week_over) and week_over.max() > 0 else 0,
        'n_weeks': int(h.max() // 168 + 1),
    }
