"""Rebuild app/data/state_prices.json: average COMMERCIAL electricity price by state, from the U.S. EIA
Electric Power Monthly, Table 5.6.A (cents per kWh). Needs internet. Run from the repo root."""
import json
import os
import re
import urllib.request

URL = 'https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a'
STATES = {'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA', 'Colorado': 'CO',
          'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC', 'Florida': 'FL', 'Georgia': 'GA',
          'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
          'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA',
          'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT',
          'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM',
          'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK',
          'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
          'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA',
          'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'}

req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
page = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')
text = re.sub(r'\s+', ' ', re.sub(r'\|(\s*\|)+', '|', re.sub(r'<[^>]+>', '|', page)))
period = re.search(r'\|((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{4})\|', text).group(1)
prices = {}
for name, abbr in STATES.items():
    m = re.search(r'\|' + re.escape(name) + r'\|([^|]+)\|([^|]+)\|([^|]+)\|', text)  # residential now/last yr, commercial now
    v = float(m.group(3))
    assert 5 < v < 60, (name, v)
    prices[abbr] = v
assert len(prices) == 51 - 1 + 0 or len(prices) >= 50
out = {'source': 'U.S. EIA, Electric Power Monthly, Table 5.6.A, average commercial price', 'period': period,
       'url': URL, 'cents_per_kwh': prices}
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'data', 'state_prices.json'), 'w') as f:
    json.dump(out, f, indent=1)
print(period, len(prices), {k: prices[k] for k in ('MA', 'AZ', 'FL', 'TX', 'CA', 'HI')})
