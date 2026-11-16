"""Cooling Check web app (FastAPI). Run locally:  uvicorn app.main:app --reload --port 8000"""
import os
import secrets
import shutil
import tempfile
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from app import pages, service
from app.ingest import IngestError, read_upload
from app.weather import WeatherError

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(APP_DIR), 'samples')
MAX_BYTES = 10 * 1024 * 1024
TTL_SECONDS = 30 * 60
UPLOADS = {}  # token -> {'dir': tmp dir, 'path': csv, 'made': time}

app = FastAPI(title='Cooling Check')


def _sweep():
    now = time.time()
    for t in [t for t, u in UPLOADS.items() if now - u['made'] > TTL_SECONDS]:
        shutil.rmtree(UPLOADS.pop(t)['dir'], ignore_errors=True)


def _drop(token):
    u = UPLOADS.pop(token, None)
    if u:
        shutil.rmtree(u['dir'], ignore_errors=True)


@app.get('/healthz')
def healthz():
    return {'ok': True}


@app.get('/', response_class=HTMLResponse)
def home():
    return HTMLResponse(pages.home())


@app.get('/trust', response_class=HTMLResponse)
def trust():
    return HTMLResponse(pages.trust())


@app.get('/limits', response_class=HTMLResponse)
def limits():
    return HTMLResponse(pages.limits())


@app.get('/static/{name}')
def static(name: str):
    p = os.path.join(APP_DIR, 'static', os.path.basename(name))
    if not os.path.exists(p):
        raise HTTPException(404, 'not found')
    return FileResponse(p)


@app.get('/samples/{name}')
def sample(name: str):
    safe = os.path.basename(name)
    p = os.path.join(SAMPLES, safe)
    if not safe.endswith('.csv') or not os.path.exists(p):
        raise HTTPException(404, 'sample not found')
    return FileResponse(p, media_type='text/csv', filename=safe)


def _verify_page(token, long, info, msg=''):
    loads = {u: service.typical_load(long, u) for u in ('kwh', 'kbtu', 'ton_hours')}
    return pages.verify(token, info, long, loads, msg)


@app.post('/upload', response_class=HTMLResponse)
async def upload(file: UploadFile = File(...)):
    _sweep()
    if not file.filename or not file.filename.lower().endswith('.csv'):
        return HTMLResponse(pages.error('Please upload a .csv file.'), status_code=400)
    data = await file.read()
    if len(data) > MAX_BYTES:
        return HTMLResponse(pages.error('That file is over 10 MB.'), status_code=413)
    tmp = tempfile.mkdtemp(prefix='coolingcheck_')
    path = os.path.join(tmp, 'upload.csv')
    with open(path, 'wb') as f:
        f.write(data)
    try:
        long, info = read_upload(path)
    except IngestError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return HTMLResponse(pages.error(str(e)), status_code=400)
    token = secrets.token_urlsafe(16)
    UPLOADS[token] = {'dir': tmp, 'path': path, 'made': time.time()}
    return HTMLResponse(_verify_page(token, long, info))


@app.post('/score', response_class=HTMLResponse)
def score(token: str = Form(...), unit: str = Form(''), clock: str = Form('local'), zip_mode: str = Form('one'),
          zip: str = Form(''), mapping: str = Form(''), winter: str = Form('no'), price_mode: str = Form('state'), price: str = Form(''), cop: str = Form('3.5')):
    u = UPLOADS.get(token)
    if not u:
        return HTMLResponse(pages.error('That upload expired (files are deleted after 30 minutes). Please upload it again.'), status_code=410)
    try:
        long, info = read_upload(u['path'])
    except IngestError as e:
        _drop(token)
        return HTMLResponse(pages.error(str(e)), status_code=400)

    def back(msg):
        return HTMLResponse(_verify_page(token, long, info, msg), status_code=400)
    if clock not in ('local', 'standard', 'utc'):
        clock = 'local'
    if unit not in ('kwh', 'kbtu', 'ton_hours'):
        return back('Please choose the unit of your readings.')
    try:
        price_v = float(price) / 100 if price.strip() else 0.0  # the form asks for cents per kWh
        cop_v = float(cop) if cop.strip() else 3.5
    except ValueError:
        return back('Price and COP must be numbers.')
    if price_mode not in ('state', 'own', 'none'):
        price_mode = 'none'
    if price_mode == 'own' and price_v <= 0:
        return back('Enter your price in cents per kWh, or choose another option.')
    if cop_v < 1:
        return back('COP must be at least 1.')
    try:
        zips = service.resolve_zips(long, info, zip_mode, zip, mapping)
        out = service.score(long, info, unit, clock, zips, winter == 'yes', price_mode, price_v, cop_v)
    except WeatherError as e:
        return back(f'Weather or ZIP lookup problem: {e}')
    except ValueError as e:
        return HTMLResponse(pages.error(str(e)), status_code=400)
    _drop(token)  # delete the upload once results are produced
    return HTMLResponse(pages.results(out))
