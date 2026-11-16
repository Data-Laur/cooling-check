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
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


for p in ('/', '/trust', '/limits', '/healthz'):
    assert c.get(p).status_code == 200

# Sample A: long, kWh, one ZIP. Expect Science_Hall flagged (planted +40% from Sep 1).
html, tok = upload('sample_A_long_kwh.csv')
assert 'one row per reading' in html and 'checked' in html
r = c.post('/score', data={'token': tok, 'unit': 'kwh', 'clock': 'local', 'zip_mode': 'one', 'zip': '02110'})
t = text(r.text)
print(t[t.index('Results'):][:1500])
assert r.status_code == 200 and 'Science_Hall' in t and 'Flagged' in t
assert c.post('/score', data={'token': tok, 'unit': 'kwh', 'zip_mode': 'one', 'zip': '02110'}).status_code == 410  # deleted after use

# Sample B: wide, ton-hours, two places via the mapping table.
html, tok = upload('sample_B_wide_tonhours.csv')
assert 'one column per building' in html
r = c.post('/score', data={'token': tok, 'unit': 'ton_hours', 'clock': 'local', 'zip_mode': 'table',
                           'mapping': 'Boston_Library_tonhours, 02110\nPhoenix_Lab_tonhours, 85004'})
t = text(r.text)
print('\n' + t[t.index('Results'):][:1500])
assert r.status_code == 200 and 'Phoenix' in t and 'Boston' in t

# Bad inputs are stopped with a plain message.
html, tok = upload('sample_A_long_kwh.csv')
r = c.post('/score', data={'token': tok, 'unit': '', 'zip_mode': 'one', 'zip': '02110'})
assert r.status_code == 400 and 'choose the unit' in r.text
r = c.post('/score', data={'token': tok, 'unit': 'kwh', 'zip_mode': 'one', 'zip': '99'})
assert r.status_code == 400 and 'ZIP' in r.text
r = c.post('/upload', files={'file': ('x.csv', b'a,b\n1,2\n', 'text/csv')})
assert r.status_code == 400
print('\nOK: app end to end')
