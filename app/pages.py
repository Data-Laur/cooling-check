"""HTML for the Cooling Check app. Same layout ideas as Heat Check, different colors."""
import html
import json
import os

import pandas as pd

E = html.escape


def dn(name):
    """Building name for display: underscores become spaces."""
    return str(name).replace('_', ' ')


def long_dt(ts):
    """January 1, 2023, 12:00 AM (2023-01-01 00:00)"""
    ts = pd.Timestamp(ts)
    return f"{ts.strftime('%B')} {ts.day}, {ts.year}, {ts.hour % 12 or 12}:{ts.minute:02d} {'AM' if ts.hour < 12 else 'PM'} ({ts.strftime('%Y-%m-%d %H:%M')})"


def us_date(ts):
    return pd.Timestamp(ts).strftime('%m-%d-%Y')


def short_range(a, b):
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    return f"{a.strftime('%b')} {a.day}, {a.year} to {b.strftime('%b')} {b.day}, {b.year}"


def span_days_text(a, b):
    days = (pd.Timestamp(b).normalize() - pd.Timestamp(a).normalize()).days + 1
    return f'{days} days ({days / 30.4:.0f} months)'


def hour12(h):
    return f"{int(h) % 12 or 12}:00 {'AM' if int(h) < 12 else 'PM'}"

HEAD = """<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cooling Check</title>
<link rel="icon" type="image/svg+xml" href="/static/logo.svg">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#1D2459;--cyan:#0891B2;--cyan-text:#0E7490;--amber:#D97706;--mist:#F3F5FB;--card:#fff;--border:#D9DEEC;--body:#1f2937;--muted:#566079;}
*{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,sans-serif;background:var(--mist);color:var(--body);line-height:1.5}
header{display:flex;align-items:center;gap:.6rem;background:var(--ink);color:#fff;padding:.7rem 1.25rem;flex-wrap:wrap}
header .brand{display:flex;align-items:center;gap:.6rem;color:#fff;text-decoration:none}
header .brand:hover .wordmark{text-decoration:underline}
header img{width:34px;height:34px} header .wordmark{font-weight:700;font-size:1.15rem}
header .tagline{color:#B8C0E0;font-size:16pt;margin-left:.5rem;padding-left:.5rem;border-left:1px solid #3a4580}
header nav{display:flex;gap:.25rem;margin-left:auto;flex-wrap:wrap}
header nav a{color:#DCE1F5;text-decoration:none;font-weight:600;padding:.4rem .7rem;border-radius:8px}
header nav a:hover{background:rgba(255,255,255,.1);color:#fff} header nav a[aria-current="page"]{background:#0E7490;color:#fff}
main{max-width:960px;margin:0 auto;padding:1.5rem} a{color:var(--cyan-text)} h1,h2,h3{color:var(--ink)}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:1rem}
.btn{display:inline-block;background:#0E7490;color:#fff;border:none;border-radius:8px;padding:.55rem 1rem;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn:hover{background:#0c6479} .btn-outline{display:inline-block;background:#fff;color:var(--cyan-text);border:1px solid var(--cyan);border-radius:8px;padding:.5rem .9rem;font-weight:600;text-decoration:none;margin:0 .4rem .4rem 0}
.notebox{background:#EEF7FA;border:1px solid var(--border);border-radius:8px;padding:.6rem .9rem;margin-bottom:1rem}
.warn{border-left:4px solid var(--amber);background:#FFF8EB;padding:.6rem .9rem;border-radius:6px;margin-bottom:.8rem}
.ok{border-left:4px solid #15803D;background:#F0FAF3;padding:.6rem .9rem;border-radius:6px;margin-bottom:.8rem}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums} th,td{border-bottom:1px solid var(--border);padding:.55rem .65rem;text-align:left;vertical-align:top;overflow-wrap:break-word}
th{background:#E8ECF8;color:var(--ink);text-transform:uppercase;font-size:.85rem;letter-spacing:.04em} td.num,th.num{text-align:right}
.badge{display:inline-block;padding:.25rem .8rem;border-radius:999px;font-weight:600;font-size:.85rem;text-align:center;line-height:1.3}
th.nw{white-space:nowrap}
.stats{display:flex;gap:.75rem;flex-wrap:wrap;margin:.2rem 0 .8rem}.stat{background:#EEF7FA;border:1px solid var(--border);border-radius:10px;padding:.6rem .9rem;min-width:9rem}
.stat b{display:block;font-size:1.35rem;color:var(--ink);line-height:1.2}.stat span{color:var(--muted);font-size:.85rem}
.chips{display:flex;gap:.4rem;flex-wrap:wrap;margin:.3rem 0 .8rem}.chip{background:#fff;border:1px solid var(--border);border-radius:999px;padding:.15rem .7rem;font-size:.9rem}
.b-flag{background:#FDE7C7;color:#8A4B00}.b-ok{background:#D9F2E3;color:#14532D}.b-no{background:#E5E7EF;color:#374151}
label{font-weight:600} .field{margin:.9rem 0} .hint{color:var(--muted);font-size:.9rem} input[type=text],input[type=number],textarea,select{font:inherit;padding:.4rem .5rem;border:1px solid var(--border);border-radius:6px;max-width:100%}
.stack{display:none} .srow{border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:10px}.srow .l{display:flex;justify-content:space-between;gap:.7rem;padding:.15rem 0}.srow .l span:first-child{color:var(--muted)}
@media(max-width:720px){header .tagline{display:none}.tw{display:none}.stack{display:block}}
</style></head><body>
<header><a class="brand" href="/" aria-label="Cooling Check home"><img src="/static/logo.svg" alt=""><span class="wordmark">Cooling Check</span></a>
<span class="tagline">Is a building using more cooling than the weather explains?</span>
<nav aria-label="Main"><a href="/" {e}>Example</a><a href="/upload" {c}>Check your data</a><a href="/trust" {t}>How far to trust it</a><a href="/limits" {l}>What we can't see</a></nav></header><main>"""
FOOT = "</main></body></html>"


def page(body, active=''):
    h = HEAD.replace('{e}', 'aria-current="page"' if active == 'example' else '').replace('{c}', 'aria-current="page"' if active == 'check' else '') \
            .replace('{t}', 'aria-current="page"' if active == 'trust' else '') \
            .replace('{l}', 'aria-current="page"' if active == 'limits' else '')
    return h + body + FOOT


def upload_page():
    return page("""
<h1>Check your building's cooling</h1>
<p>Upload hourly chilled-water readings. Cooling Check compares each hour with what the <strong>weather</strong> says the building should use,
and tells you which buildings are using more than expected, or that it can't judge. You'll confirm what it found in your file before you see any results.</p>
<div class="card"><form action="/upload" method="post" enctype="multipart/form-data">
<p><label for="f">CSV file (hourly, at least 9 months, up to 25 buildings, 10 MB)</label><br><input id="f" type="file" name="file" accept=".csv" required></p>
<p><button class="btn" type="submit">Read my file</button></p>
<p class="hint">Your file is kept only until you see results (or 30 minutes), then deleted. Weather is looked up from a public service using the ZIP codes you give.</p></div>
<div class="card"><h3>No data handy? Try a sample</h3>
<h4 style="margin-bottom:.2rem">Real meter data</h4>
<p class="hint">Hourly chilled-water meters for 7 university buildings each, 2016, from the Building Data Genome 2 project. Buildings are anonymized. Enter the ZIP code shown, choose <strong>kWh</strong> and <strong>Local standard time all year</strong> (this dataset has no daylight saving).</p>
<a class="btn-outline" href="/samples/sample_C_real_orlando_kwh.csv">Sample C: Orlando, FL campus (ZIP 32816)</a>
<a class="btn-outline" href="/samples/sample_D_real_princeton_kwh.csv">Sample D: Princeton, NJ campus (ZIP 08544)</a>
<p class="hint">Sample D has long winter shutdowns. Try it with "Do the chillers shut off in winter?" set to No, then Yes, and compare.</p>
<h4 style="margin-bottom:.2rem">Made-up buildings</h4>
<p class="hint">Their cooling is simulated from <strong>real 2023 weather</strong> (Boston, MA, ZIP 02110; Sample B also Phoenix, AZ, ZIP 85004). <strong>Not real meter data.</strong> One building has extra cooling added from October.</p>
<a class="btn-outline" href="/samples/sample_A_long_kwh.csv">Sample A (one row per reading, kWh, ZIP 02110)</a>
<a class="btn-outline" href="/samples/sample_B_wide_tonhours.csv">Sample B (one column per building, ton-hours, two cities)</a>
<p class="hint">Sample B has buildings in two places. Choose "Buildings are in different places" and enter <code>Library, 02110</code> and <code>Lab, 85004</code>, one per line. Choose ton-hours for the unit.</p>
<p class="hint">Samples C and D are a subset of data from Miller et al. (2020), <em>Scientific Data</em> 7:368 (<a href="https://doi.org/10.1038/s41597-020-00712-x">doi:10.1038/s41597-020-00712-x</a>).
The authors' Zenodo release is licensed <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> and their GitHub repository carries <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>, so this subset is shared under CC BY-SA 4.0, which satisfies both.
Changes: 2016 only, 7 buildings per site, reformatted to CSV.</p></div>
<p class="hint">Portfolio project, not a production system. See <a href="/trust">how far to trust it</a> and <a href="/limits">what it can't see</a>.</p>""", 'check')


def error(msg):
    return page(f'<h1>We stopped</h1><div class="warn">{E(msg)}</div><p><a class="btn" href="/upload">Try another file</a></p>', 'check')


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'state_prices.json')) as _f:
    PRICE_PERIOD = json.load(_f)['period']
PRICE_NOTE = "a statewide average, not your utility's rate"


def verify(token, info, long, loads, form_error='', defaults=None):
    defaults = defaults or {}
    zip_val = E(defaults.get('zip', ''))
    clock_std = defaults.get('clock') == 'standard'
    cols = info['columns']
    if info['format'] == 'long':
        found = (f"one row per reading: time = <code>{E(str(cols['time']))}</code>, building = <code>{E(str(cols['building']))}</code>, "
                 f"reading = <code>{E(str(cols['value']))}</code>" + (f", ZIP = <code>{E(str(cols['zip']))}</code>" if cols['zip'] else ''))
    else:
        found = (f"one column per building: time = <code>{E(str(cols['time']))}</code>, "
                 f"{len(cols['buildings'])} building columns")
    if info['notes']:
        notes_box = ('<div class="notebox"><strong>What we fixed or set aside</strong><ul>'
                     + ''.join(f'<li>{E(n)}</li>' for n in info['notes']) + '</ul></div>')
    else:
        notes_box = '<div class="ok"><strong>This file is suitable for import.</strong></div>'
    hint = info['unit_hint']
    unit_rows = ''
    for u, label in (('kwh', 'kWh'), ('kbtu', 'kBTU'), ('ton_hours', 'ton-hours')):
        l = loads[u]
        chk = 'checked' if hint == u else ''
        unit_rows += (f'<tr><td><label><input type="radio" name="unit" value="{u}" {chk} required> {label}</label></td>'
                      f'<td class="num">{l["mean_tons"]:,.0f}</td><td class="num">{l["peak_tons"]:,.0f}</td></tr>')
    zip_opts = ''
    if info['has_zip']:
        zip_opts += '<label><input type="radio" name="zip_mode" value="column" checked> Use the ZIP column in my file</label><br>'
    zip_opts += (f'<label><input type="radio" name="zip_mode" value="one" {"" if info["has_zip"] else "checked"}> All buildings are in one place</label>'
                 f' &nbsp; ZIP <input type="text" name="zip" size="6" maxlength="5" inputmode="numeric" placeholder="02110" value="{zip_val}"><br>'
                 '<label><input type="radio" name="zip_mode" value="table"> Buildings are in different places</label>')
    names = ', '.join(E(dn(b)) for b in info['buildings'][:12]) + ('...' if len(info['buildings']) > 12 else '')
    chips = ''.join(f'<span class="chip">{E(dn(b))}</span>' for b in info['buildings'])
    err = f'<div class="warn">{E(form_error)}</div>' if form_error else ''
    return page(f"""
<h1>Check what we found</h1>{err}
<div class="card"><h3>Your file</h3>
<div class="stats">
<div class="stat"><b>{info['rows']:,}</b><span>hourly readings</span></div>
<div class="stat"><b>{len(info['buildings'])}</b><span>buildings</span></div>
<div class="stat"><b>{E(short_range(info['start'], info['end']))}</b><span>{E(span_days_text(info['start'], info['end']))}</span></div></div>
<div class="chips">{chips}</div>
<p class="hint">Read as {found}. First reading {E(long_dt(info['start']))}; last reading {E(long_dt(info['end']))}.</p>
{notes_box}</div>
<form action="/score" method="post"><input type="hidden" name="token" value="{E(token)}">
<div class="card"><h3>1. Units</h3><p class="hint">What unit are your readings in? To help you check, here is what your numbers would mean as tons of cooling in each case.
A typical large building averages from tens to a few hundred tons; a campus building rarely peaks above a few thousand.</p>
<table><thead><tr><th>If your readings are in</th><th class="num">Typical building, average tons</th><th class="num">Biggest hour, tons</th></tr></thead><tbody>{unit_rows}</tbody></table></div>
<div class="card"><h3>2. Where are the <u>buildings</u>?</h3>
<p class="hint">ZIP code of the <strong>buildings</strong>, not where you live or work. We use it to look up the weather.</p>
<div class="field">{zip_opts}</div>
<div class="field"><label for="m">Different places: one line per building, <code>building name, ZIP</code></label><br>
<textarea id="m" name="mapping" rows="5" cols="44" placeholder="{E(dn(info['buildings'][0]))}, 02110"></textarea>
<div class="hint">Building names in your file: {names}</div></div></div>
<div class="card"><h3>3. Time clock</h3><div class="field">
<label><input type="radio" name="clock" value="local" {'' if clock_std else 'checked'}> Local clock time at each building (changes with daylight saving)</label><br>
<label><input type="radio" name="clock" value="standard" {'checked' if clock_std else ''}> Local standard time all year (no daylight saving change)</label><br>
<label><input type="radio" name="clock" value="utc"> UTC</label></div>
<p class="hint">After scoring we show the hottest hour of the day. If it isn't mid-afternoon, the clock is probably wrong.</p></div>
<div class="card"><h3>4. Do the chillers shut off in winter?</h3><div class="field">
<label><input type="radio" name="winter" value="no" checked> No, or I'm not sure</label><br>
<label><input type="radio" name="winter" value="yes"> Yes, long stretches of zero are real</label></div>
<p class="hint">By default, runs of zero longer than 24 hours are treated as bad data and set aside. Choose Yes in cold climates.</p></div>
<div class="card"><h3>5. Dollars</h3>
<p class="hint">Dollars are estimates of what the excess cooling cost in electricity. You don't need to look anything up.</p>
<div class="field"><label><input type="radio" name="price_mode" value="state" checked> Use my state's average commercial electricity price</label>
<div class="hint" style="margin-left:1.6rem">We find the state from the ZIP code. Source: U.S. EIA, {E(PRICE_PERIOD)} average ({E(PRICE_NOTE)}).</div>
<label><input type="radio" name="price_mode" value="own"> I know my rate:</label> <input type="number" name="price" step="0.01" min="0" style="width:6rem"> cents per kWh<br>
<label><input type="radio" name="price_mode" value="none"> Skip dollars</label></div>
<details><summary>Advanced</summary><div class="field"><label>Chiller plant efficiency (COP) <input type="number" name="cop" step="0.1" min="1" value="3.5" style="width:5rem"></label>
<div class="hint">How many units of cooling the whole plant makes per unit of electricity. 3.5 is a typical assumption.</div></div></details></div>
<p><button class="btn" type="submit">Score my buildings</button></p></form>""", 'check')


def _has(v):
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v) != ''


def _badge(v):
    cls = {'Flagged': 'b-flag', 'Within expected range': 'b-ok'}.get(v, 'b-no')
    return f'<span class="badge {cls}">{E(str(v))}</span>'


def _fmt(v, kind=''):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return '-'
    if kind == 'pct':
        return f'{float(v):.1f}%'
    if kind == 'int':
        return f'{float(v):,.0f}'
    if kind == 'usd':
        return f'${float(v):,.0f}'
    return E(str(v))


def _hints(r):
    items = ''
    for _, row in r.iterrows():
        if row.get('verdict') != 'Flagged':
            continue
        h = row.get('hint')
        lines = ['<li><strong>Check the meter first.</strong> A meter change or recalibration looks the same as extra cooling.</li>']
        if not h:
            lines.append('<li>No clear start date or timing pattern stood out.</li>')
        else:
            o = pd.Timestamp(h['onset'])
            lines.append(f"<li>The extra cooling began around <strong>{o.strftime('%B')} {o.day}, {o.year}</strong>. Ask what changed then: controls, setpoints, tenants, equipment.</li>")
            pct = lambda x: f'{100 * x:.0f}%'
            if h['pattern'] == 'after_hours':
                lines.append(f"<li>Most of the extra ({pct(h['excess_after_hours_share'])}) is on nights and weekends, against {pct(h['normal_after_hours_share'])} of normal use. Check schedules, setpoint setbacks and after-hours operation.</li>")
            elif h['pattern'] == 'occupied_hours':
                lines.append(f"<li>Most of the extra is on weekdays between 7 AM and 7 PM (only {pct(h['excess_after_hours_share'])} is after hours, against {pct(h['normal_after_hours_share'])} of normal use). Check what runs during the day: setpoints, ventilation, occupancy changes.</li>")
            else:
                lines.append('<li>The extra is spread across the day and the week, so timing does not narrow it down.</li>')
        items += f"<h4 style='margin:.8rem 0 .2rem'>{E(dn(row['building']))}</h4><ul>{''.join(lines)}</ul>"
    if not items:
        return ''
    return ('<div class="card"><h3>Where to look first</h3><p class="hint">Hints from when and how the extra cooling shows up, '
            '<strong>not a diagnosis</strong>. In planted-fault tests the start date landed within a week about 60% of the time, and the '
            'timing pattern was named correctly 80 to 98% of the time. See <a href="/trust">how far to trust it</a>.</p>' + items + '</div>')


def results(out):
    return page(results_body(out), 'check')


def results_body(out, heading='Results', buttons=True):
    price = out['price_mode'] != 'none'
    r, checks = out['results'], out['checks']
    warns = []
    for c in checks:
        if not c['hottest_hour_plausible']:
            warns.append(f"At {c['place']} (ZIP {c['zip']}), the hottest hour of the day came out as {hour12(c['hottest_hour'])}. "
                         'It should be mid-afternoon, so the clock or the location may be wrong. Do not trust these results until that is checked.')
        if c['median_corr'] == c['median_corr'] and c['median_corr'] < 0.3:
            warns.append(f"At {c['place']}, cooling barely follows the outdoor temperature (median correlation {c['median_corr']:.2f}). "
                         'The ZIP code may be wrong, or this equipment may not be weather-driven. Most buildings here will come back as "Can\'t judge".')
        if c['rows_without_weather']:
            warns.append(f"At {c['place']}, {c['rows_without_weather']:,} meter readings had no weather (the file may run past the latest dates the weather archive has) and were not used.")
    for c in checks:
        g = r[r['zip'] == c['zip']]
        if len(g) and (g['verdict'] == "Can't judge").all():
            warns.append(f"Every building at {c['place']} (ZIP {c['zip']}) came back as \"Can't judge\". Common causes: the ZIP code, the time clock, "
                         'or the units are wrong. Go back and check those first.')
    chk_rows = ''.join(
        f"<tr><td>{E(c['place'])} ({E(c['zip'])})</td><td class='num'>{c['buildings']}</td>"
        f"<td class='num'>{hour12(c['hottest_hour'])} {'OK' if c['hottest_hour_plausible'] else 'CHECK'}</td>"
        f"<td class='num'>{'-' if c['median_corr'] != c['median_corr'] else format(c['median_corr'], '.2f')}</td>"
        f"<td class='num'>{int(c['flagged_hours'].values.sum()) if len(c['flagged_hours']) else 0:,}</td></tr>" for c in checks)
    n = r['verdict'].value_counts()
    cant = int(n.get("Can't judge", 0))
    summary = (f"{int(n.get('Flagged', 0))} flagged, {int(n.get('Within expected range', 0))} within expected range, "
               f"{cant} can't judge.")
    cols = [('building', 'Building', ''), ('place', 'Place', ''), ('verdict', 'Verdict', 'badge'),
            ('as_of', f"Status on {us_date(out['last_day'])}", ''), ('hours above band %', 'Hours above band', 'pct'),
            ('excess % of cooling', 'Excess, % of its cooling', 'pct'), ('excess ton-hours', 'Excess ton-hours', 'int')]
    if price:
        cols.append(('cost $', 'Potential cost', 'usd'))
    def cell(row, k, kind):
        v = dn(row.get(k)) if k == 'building' else row.get(k)
        return _badge(v) if kind == 'badge' else _fmt(v, kind)
    head = ''.join(f"<th class='{'num' if kind in ('pct', 'int', 'usd') else ''}'>{E(l)}</th>" for _, l, kind in cols)
    body = ''.join('<tr>' + ''.join(f"<td class='{'num' if kind in ('pct', 'int', 'usd') else ''}'>{cell(row, k, kind)}</td>"
                                    for k, _, kind in cols) + '</tr>' for _, row in r.iterrows())
    cards = ''.join('<div class="srow"><strong>' + E(dn(row['building'])) + '</strong>' + ''.join(
        f"<div class='l'><span>{E(l)}</span><span>{cell(row, k, kind)}</span></div>" for k, l, kind in cols[1:]) +
        (f"<div class='hint'>{E(str(row['note']))}</div>" if _has(row.get('note')) else '') + '</div>' for _, row in r.iterrows())
    notes = ''.join(f"<div class='hint'><strong>{E(dn(row['building']))}:</strong> {E(str(row['note']))}</div>"
                    for _, row in r.iterrows() if _has(row.get('note')))
    if price:
        src = ('your own rate' if out['price_mode'] == 'own' else 'average commercial price by state, U.S. EIA, '
               + PRICE_PERIOD + ' (' + '; '.join(out['price_notes']) + ')')
        cost_note = (f'<div class="notebox"><strong>How dollars were estimated:</strong> excess cooling above the band, converted to electricity '
                     f'with a plant COP of {out["cop"]:g}, priced at {E(src)}. They are potential savings, not realized ones.</div>')
    else:
        cost_note = ''
    hints_html = _hints(r)
    wtxt = ''.join(f'<div class="warn">{E(w)}</div>' for w in warns) or '<div class="ok">Clock, weather and weather-following checks passed for every location.</div>'
    return (f"""
<h1>{E(heading)}</h1><p><strong>{E(summary)}</strong></p>
<div class="card"><h3>Checks before you trust this</h3>{wtxt}
<table><thead><tr><th>Location</th><th class="num">Buildings</th><th class="num nw">Hottest hour</th><th class="num">Cooling vs temp</th><th class="num">Hours set aside<br>as bad data</th></tr></thead><tbody>{chk_rows}</tbody></table></div>
<div class="card"><h3>Buildings</h3>
{cost_note}<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div><div class="stack">{cards}</div>
<div style="margin-top:.8rem">{notes}</div></div>
{hints_html}
<div class="card"><h3>How to read this</h3><ul>
<li><strong>Flagged</strong>: more than 10% of the hours in the test period (about the last five months) were above the 90% band <em>and</em> the excess is at least 5% of the building's cooling. Excess is only the part above the band's upper edge, so it is conservative.</li>
<li><strong>Status on {E(us_date(out['last_day']))}</strong> looks at the most recent weeks only: "Flagged, ongoing", "Was flagged, not above band lately", or "Within expected range".</li>
<li><strong>Can't judge</strong> means the model wasn't accurate enough on this building (or there wasn't enough clean data), so we don't guess.</li>
<li>Excess cooling is <strong>potential</strong>, not realized: a meter change or a legitimate change in use looks the same. Check the meter first.</li></ul>
<p class="hint">Test period {E(us_date(out['test_start']))} onward; the month before was used to calibrate the band; earlier data to fit the baseline.</p></div>
""" + ('<p><a class="btn" href="/upload">Check another file</a> <a class="btn-outline" href="/trust">How far to trust it</a></p>' if buttons else ''))


def trust():
    return page("""
<h1>How far to trust it</h1>
<p>There are no confirmed real faults in public cooling data, so the method was tested by <strong>planting faults</strong>: multiplying a building's readings by 1.10, 1.25 or 1.50 from a chosen date, then scoring it on month-end dates using only data up to that date.</p>
<div class="card"><table><thead><tr><th>Planted fault</th><th class="num">Flagged while running, 2016</th><th class="num">Same, 2017 (never tuned on)</th></tr></thead><tbody>
<tr><td>+50%</td><td class="num">57%</td><td class="num">53%</td></tr><tr><td>+25%</td><td class="num">27%</td><td class="num">23%</td></tr><tr><td>+10%</td><td class="num">6%</td><td class="num">7%</td></tr></tbody></table>
<p class="hint">16 judged buildings in 2016, 19 in 2017, from four university campuses. After a planted fix, about 54 to 62% of the time the tool said "was flagged, not above band lately". That label also appears for faults that never ended, so it does not confirm a fix.</p></div>
<div class="card"><h3>What this does and doesn't show</h3><ul>
<li>It catches big, long faults and misses small or late ones, especially in the cool season: the 90% band is a fixed width, so a +25% fault is about 1.1 times the band in August and 0.3 times in December.</li>
<li><strong>"Where to look first" hints:</strong> tested with faults planted at known dates and times. The start date was within a week of the truth about 60% of the time (median error 0 to 2 days). The pattern (nights and weekends, weekday daytime, or all day) was named correctly about 80 to 98% of the time. The tool cannot tell a faulty valve from a changed setpoint or a meter change, and when a fault ends it often cannot say so reliably.</li>
<li>With the 5% materiality floor, about a quarter of unmodified buildings still showed an alert episode. With no labels we can't say how many are false alarms.</li>
<li>A planted fault is a steady percentage increase, not a real fault. Thresholds were tuned on 2016 after seeing results.</li>
<li>On four sites, 2 to 6 of 7 buildings could be judged; the rest are marked "Can't judge" instead of guessed.</li></ul>
<p>Full details, code and tests: the <a href="https://github.com/Data-Laur/cooling-check">GitHub repo</a>.</p></div>""", 'trust')


def limits():
    return page("""
<h1>What we can't see</h1><div class="card"><ul>
<li><strong>Why</strong> a building uses extra cooling. A leak, a stuck valve, a changed setpoint, a new tenant and a meter change can all look the same. The tool says something changed and when.</li>
<li><strong>Your location, unless you tell us.</strong> We trust the ZIP code you give. A wrong ZIP often ends as "Can't judge", but not always.</li>
<li><strong>Cold-climate shutdowns, unless you tell us.</strong> Long runs of zero are treated as bad data by default.</li>
<li><strong>Calendars and occupancy.</strong> A semester break or a new use can look like a fault.</li>
<li><strong>Small faults in the cool season.</strong> The band is a fixed width calibrated on a single month.</li>
<li><strong>Dollars and carbon.</strong> Dollars use a statewide average price unless you give your own rate, and a plant COP you can change (default 3.5). Carbon is not estimated.</li>
<li><strong>Anything outside US ZIP codes</strong>, or data that isn't hourly.</li></ul>
<p>This is a portfolio project, not a production system.</p></div>""", 'limits')


import os as _os
DEMO_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'static', 'demo_result.html')


def home():
    """Landing page: a saved result on real data first, then the invitation to try your own."""
    if not _os.path.exists(DEMO_PATH):
        return upload_page()
    with open(DEMO_PATH) as f:
        demo = f.read()
    return page(f"""
<p>Cooling Check compares each hour's chilled-water use with what the weather says the building should use, and tells you which buildings to look at first, or that it can't judge. Below is a real example. <strong>Then check your own data.</strong></p>
<p><a class="btn" href="/upload">Check your own data</a> <a class="btn-outline" href="/demo">Run this example live</a></p>
<div class="card"><p class="hint"><strong>Real data, saved result.</strong> Hourly chilled-water meters for 7 university buildings in Orlando, Florida, 2016
(Building Data Genome 2, Miller et al. 2020, CC BY 4.0; subset). Buildings are anonymized. Weather is looked up for ZIP 32816. This page was generated ahead of time from the
sample file, so it loads instantly; "Run this example live" runs the same file through the app now.</p></div>
{demo}
<div class="card"><h3>How to read the "Status" column here</h3><p>The two flagged residence halls were well above their band over the whole test period. "Not above band lately" means the most recent weeks were not clearly above it. It does <strong>not</strong> confirm a fix: in the cool months the band is wide compared with the load, so a fixed amount of extra cooling can hide inside it (see <a href="/trust">how far to trust it</a>).</p></div>
<div class="card"><h3>What this example doesn't show</h3><p>Real files are messier. Try <a href="/samples/sample_D_real_princeton_kwh.csv">sample D</a> (Princeton, NJ, with long winter shutdowns) on the
<a href="/upload">upload page</a>: most buildings come back as "Can't judge", which is the tool being honest. See <a href="/trust">how far to trust it</a>.</p></div>""", 'example')
