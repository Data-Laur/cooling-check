"""End-to-end test of the app with the sample files. Needs internet (ZIP lookup and weather archive).
    python tests/test_app.py"""
import os
import re
import sys

from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.main import app  # noqa: E402

c = TestClient(app)
S = os.path.join(ROOT, 'samples')


def upload(name):
    with open(os.path.join(S, name), 'rb') as f:
        r = c.post('/upload', files={'file': (name, f, 'text/csv')})
    assert r.status_code == 200, r.text[:300]
    return r.text, re.search(r'name="token" value="([^"]+)"', r.text).group(1)


def text(html):
    html = re.sub(r'(?s)<script.*?</script>', ' ', html)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


for p in ('/', '/upload', '/method', '/healthz'):
    assert c.get(p).status_code == 200
for p in ('/trust', '/limits'):
    r0 = c.get(p, follow_redirects=False)
    assert r0.status_code in (302, 307) and r0.headers['location'].startswith('/method#')
m = text(c.get('/method').text)
assert 'How it works' in m and 'How far to trust it' in m and "What we can't see" in m and 'Data and credits' in m
h = text(c.get('/').text)
assert 'Priorities: 7 real buildings' in h and 'id="nav-detail"' in c.get('/').text and 'id="nav-detail"' in c.get('/method').text and 'Panther lodging Cora' in h and 'Check your own data' in h
d = c.get('/demo').text
assert 'value="32816"' in d and 'name="clock" value="standard" checked' in d

# Sample A: long, kWh, one ZIP. Expect Science_Hall flagged (planted +40% from Sep 1).
html, tok = upload('sample_A_long_kwh.csv')
assert 'one row per reading' in html and 'checked' in html
r = c.post('/score', data={'token': tok, 'unit': 'kwh', 'clock': 'local', 'zip_mode': 'one', 'zip': '02110', 'price_mode': 'state'})
t = text(r.text)
print(t[t.index('Results'):][:1500])
assert r.status_code == 200 and 'Science Hall' in t and 'Flagged' in t and 'Science_Hall' not in t
assert 'Where to look first' in t and 'October 1, 2023' in t and 'Check the meter first' in t, t[t.index('Results'):][:200]
assert 'window.DETAIL' in r.text and 'data-b="Science_Hall"' in r.text and '/static/detail.js' in r.text
assert c.get('/static/detail.js').status_code == 200
assert 'EIA' in t and 'suitable for import' in text(html) and 'January 1, 2023' in text(html) and '12-31-2023' in t
assert c.post('/score', data={'token': tok, 'unit': 'kwh', 'zip_mode': 'one', 'zip': '02110'}).status_code == 410  # deleted after use

# Sample B: wide, ton-hours, two places via the mapping table.
html, tok = upload('sample_B_wide_tonhours.csv')
assert 'one column per building' in html
r = c.post('/score', data={'token': tok, 'unit': 'ton_hours', 'clock': 'local', 'zip_mode': 'table',
                           'mapping': 'Library, 02110\nlab, 85004', 'price_mode': 'state'})
t = text(r.text)
print('\n' + t[t.index('Results'):][:1500])
assert r.status_code == 200 and 'Phoenix' in t and 'Boston' in t

# Sample C: real Orlando campus data. Expect the two residence halls flagged, and the third clock option to work.
html, tok = upload('sample_C_real_orlando_kwh.csv')
r = c.post('/score', data={'token': tok, 'unit': 'kwh', 'clock': 'standard', 'zip_mode': 'one', 'zip': '32816', 'price_mode': 'none'})
t = text(r.text)
assert r.status_code == 200 and 'Panther lodging Cora Orlando, FL Flagged' in t and 'Panther lodging Kara Orlando, FL Flagged' in t, t[:1500]
assert t.count(' Flagged ') >= 2 and 'Results 2 flagged' in t

# Bad inputs are stopped with a plain message.
html, tok = upload('sample_A_long_kwh.csv')
r = c.post('/score', data={'token': tok, 'unit': '', 'zip_mode': 'one', 'zip': '02110'})
assert r.status_code == 400 and 'choose the unit' in r.text
r = c.post('/score', data={'token': tok, 'unit': 'kwh', 'zip_mode': 'one', 'zip': '99'})
assert r.status_code == 400 and 'ZIP' in r.text
r = c.post('/upload', files={'file': ('x.csv', b'a,b\n1,2\n', 'text/csv')})
assert r.status_code == 400
print('\nOK: app end to end')
