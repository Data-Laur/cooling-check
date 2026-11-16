"""Build app/static/demo_result.html: the saved example shown on the home page (real Orlando sample, run through the app's
own code). Re-run after any change that affects results. Needs internet. Run from the repo root: python scripts/build_home.py"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app import pages, service  # noqa: E402
from app.ingest import read_upload  # noqa: E402

long, info = read_upload(os.path.join(ROOT, 'samples', 'sample_C_real_orlando_kwh.csv'))
zips = service.resolve_zips(long, info, 'one', '32816', '')
out = service.score(long, info, 'kwh', 'standard', zips, False, 'state', 0.0, 3.5)
body = pages.results_body(out, heading='Example result: 7 real buildings, Orlando FL', buttons=False)
with open(os.path.join(ROOT, 'app', 'static', 'demo_result.html'), 'w') as f:
    f.write(body)
print(out['results'][['building', 'verdict', 'as_of']].to_string())
