"""Read an uploaded CSV of hourly cooling readings into one long table and report what we found and did.
Flag, don't delete: nothing is changed silently; every fix is listed in `notes`."""
import re

import pandas as pd

TIME_NAMES = ('timestamp', 'time', 'datetime', 'date')
BUILDING_NAMES = ('building_id', 'building', 'meter_id', 'meter', 'site', 'id', 'name')
VALUE_NAMES = ('meter_reading', 'reading', 'value', 'kwh', 'kbtu', 'usage', 'energy', 'load', 'cooling', 'ton')
ZIP_NAMES = ('zip', 'zipcode', 'zip_code', 'postal', 'postcode', 'postal_code')
MAX_BUILDINGS = 25


class IngestError(Exception):
    pass


def _find(cols, names, exact=False):
    low = {c: c.lower().strip() for c in cols}
    for n in names:
        for c, l in low.items():
            if l == n:
                return c
    if not exact:
        for n in names:
            for c, l in low.items():
                if n in l:
                    return c
    return None


def unit_hint(text):
    t = text.lower()
    if re.search(r'ton[\s_-]*h|tonhr|ton_hr|\btr\b', t):
        return 'ton_hours'
    if 'kbtu' in t:
        return 'kbtu'
    if 'kwh' in t:
        return 'kwh'
    return None


def read_upload(path):
    """Returns (long_df [building_id, timestamp, meter_reading, zip?], info). Raises IngestError with a plain message."""
    try:
        raw = pd.read_csv(path, low_memory=False)
    except Exception:
        raise IngestError('Could not read that file as a CSV.')
    if raw.shape[1] < 2 or len(raw) < 24:
        raise IngestError('The file needs a time column and at least one reading column, and at least a day of rows.')
    notes = []
    tcol = _find(raw.columns, TIME_NAMES) or raw.columns[0]
    ts = pd.to_datetime(raw[tcol], errors='coerce')
    bad_ts = int(ts.isna().sum())
    if bad_ts > 0.5 * len(raw):
        raise IngestError(f"Could not read '{tcol}' as dates and times. Use a format like 2023-07-01 14:00.")
    if bad_ts:
        notes.append(f'{bad_ts:,} rows had an unreadable timestamp and were set aside.')
    if getattr(ts.dt, 'tz', None) is not None:
        ts = ts.dt.tz_localize(None)
        notes.append('Timestamps had a time-zone label; it was dropped and the written clock time kept.')
    raw = raw.assign(_ts=ts).dropna(subset=['_ts'])
    zcol = _find([c for c in raw.columns if c not in (tcol, '_ts')], ZIP_NAMES)
    others = [c for c in raw.columns if c not in (tcol, '_ts', zcol)]
    bcol = _find(others, BUILDING_NAMES, exact=True)
    vcol = _find([c for c in others if c != bcol], VALUE_NAMES)
    hint = unit_hint(' '.join(map(str, raw.columns)))
    if bcol is not None and vcol is not None:
        fmt = 'long'
        long = pd.DataFrame({'building_id': raw[bcol].astype(str), 'timestamp': raw['_ts'],
                             'meter_reading': pd.to_numeric(raw[vcol], errors='coerce')})
        if zcol:
            long['zip'] = raw[zcol].astype(str).str.extract(r'(\d{5})')[0]
        info_cols = {'time': tcol, 'building': bcol, 'value': vcol, 'zip': zcol}
    else:
        fmt = 'wide'
        num = {c: pd.to_numeric(raw[c], errors='coerce') for c in others}
        num = {c: s for c, s in num.items() if s.notna().mean() > 0.5}
        if not num:
            raise IngestError('Found no numeric reading columns.')
        long = pd.concat([pd.DataFrame({'building_id': str(c), 'timestamp': raw['_ts'], 'meter_reading': s})
                          for c, s in num.items()], ignore_index=True)
        info_cols = {'time': tcol, 'buildings': list(num), 'zip': None}
    long = long.dropna(subset=['meter_reading'])
    neg = int((long['meter_reading'] < 0).sum())
    if neg:
        long.loc[long['meter_reading'] < 0, 'meter_reading'] = float('nan')
        long = long.dropna(subset=['meter_reading'])
        notes.append(f'{neg:,} negative readings were set aside (cooling energy cannot be negative).')
    dup = int(long.duplicated(['building_id', 'timestamp']).sum())
    if dup:
        long = long.drop_duplicates(['building_id', 'timestamp'], keep='first')
        notes.append(f'{dup:,} duplicate rows (same building and time) were dropped, keeping the first.')
    if long['building_id'].nunique() > MAX_BUILDINGS:
        raise IngestError(f"This demo handles up to {MAX_BUILDINGS} buildings per file; this file has {long['building_id'].nunique()}.")
    step = (long.sort_values('timestamp').groupby('building_id')['timestamp'].diff().dropna().dt.total_seconds() / 3600)
    median_step = float(step.median()) if len(step) else float('nan')
    if not (0.99 <= median_step <= 1.01):
        raise IngestError(f'Readings are not hourly (typical spacing is {median_step:.2f} hours). '
                          'This tool needs one reading per hour per building.')
    info = {'format': fmt, 'columns': info_cols, 'unit_hint': hint, 'notes': notes,
            'rows': len(long), 'buildings': sorted(long['building_id'].unique()),
            'start': long['timestamp'].min(), 'end': long['timestamp'].max(),
            'has_zip': 'zip' in long.columns and long['zip'].notna().any()}
    return long, info
