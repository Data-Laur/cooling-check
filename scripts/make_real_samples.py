"""Make the two REAL sample files for the app from the Building Data Genome 2 (BDG2) raw chilled-water meter data.
Subset only: the 7 largest buildings per site (>= 4,000 hourly readings in 2016), 2016 only, long format, kWh.
BDG2: Miller et al. (2020), Scientific Data 7:368, https://doi.org/10.1038/s41597-020-00712-x
Zenodo release CC BY 4.0, GitHub repo LICENSE CC BY-SA 4.0: this subset is shared under CC BY-SA 4.0 with attribution, changes noted.
    python scripts/make_real_samples.py path/to/bdg2_folder"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = sys.argv[1]
meta = pd.read_csv(f'{d}/metadata.csv')
cw = pd.read_csv(f'{d}/chilledwater_raw.csv', parse_dates=['timestamp'])
cw = cw[(cw['timestamp'] >= '2016-01-01') & (cw['timestamp'] < '2017-01-01')]
hours = cw.drop(columns='timestamp').notna().sum()
for site, fname in [('Panther', 'sample_C_real_orlando_kwh.csv'), ('Peacock', 'sample_D_real_princeton_kwh.csv')]:
    m = meta[(meta['site_id'] == site) & meta['building_id'].isin(hours.index[hours >= 4000])]
    names = list(m.sort_values('sqft', ascending=False).head(7)['building_id'])
    long = cw[['timestamp'] + names].melt('timestamp', var_name='building_id', value_name='cooling_kwh').dropna()
    long['cooling_kwh'] = long['cooling_kwh'].round(2)
    long.sort_values(['building_id', 'timestamp']).to_csv(os.path.join(ROOT, 'samples', fname), index=False)
    print(fname, len(long), 'rows', names)
