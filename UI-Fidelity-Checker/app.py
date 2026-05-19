"""Spec-to-UI Diff — local web app.

Run:
    python app.py
then open http://127.0.0.1:5000 in your browser.

Needs FIGMA_TOKEN and ANTHROPIC_API_KEY in the environment.
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, render_template_string, request

from core import DiffError, detect_sections, diff, diff_images, media_type_for

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB screenshot cap

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UI Fidelity Checker — Design vs Build</title>
<style>
  :root {
    --bg:#f4f6f9; --panel:#ffffff; --line:#dfe3e8; --text:#1f2937;
    --muted:#6b7280; --brand:#1d4ed8; --brand-dark:#1e3a8a;
    --high:#dc2626; --med:#d97706; --low:#6b7280; --ok:#059669;
  }
  * { box-sizing:border-box; }
  body { margin:0; font:16px/1.6 "Segoe UI",system-ui,sans-serif;
         background:var(--bg); color:var(--text); }
  .wrap { max-width:1320px; margin:0 auto; padding:0 48px; }
  header { background:var(--brand-dark); color:#fff; padding:34px 0; }
  header h1 { margin:0; font-size:30px; font-weight:700; letter-spacing:-.3px; }
  header p { margin:8px 0 0; color:#c7d2fe; font-size:16px; max-width:760px; }
  main { padding:34px 0 80px; }
  .env { font-size:14px; padding:12px 18px; border-radius:8px;
         margin-bottom:26px; border:1px solid transparent; font-weight:500; }
  .env.ok { background:#ecfdf5; color:#065f46; border-color:#a7f3d0; }
  .env.bad { background:#fef2f2; color:#991b1b; border-color:#fecaca; }
  .card { background:var(--panel); border:1px solid var(--line);
          border-radius:14px; padding:32px;
          box-shadow:0 1px 3px rgba(16,24,40,.06); }
  label { display:block; font-size:15px; font-weight:600; color:var(--text);
          margin:0 0 10px; }
  label .hint { color:var(--muted); font-weight:400; font-size:13px; }
  input[type=text], select { width:100%; padding:13px 14px; border-radius:8px;
        border:1px solid var(--line); background:#fff; color:var(--text);
        font-size:15px; }
  .uploads { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
  .controls { display:grid; grid-template-columns:1fr 1fr; gap:22px;
              margin-top:24px; align-items:start; }
  @media (max-width:900px){
    .uploads,.controls{ grid-template-columns:1fr; } .wrap{ padding:0 20px; }
  }
  .verdict-badge { display:inline-block; padding:8px 20px; border-radius:999px;
        font-size:16px; font-weight:800; letter-spacing:.6px; color:#fff; }
  .verdict-badge.pass { background:var(--ok); }
  .verdict-badge.fail { background:var(--high); }
  .drop { border:2px dashed var(--line); border-radius:12px; padding:24px;
          min-height:320px; display:flex; flex-direction:column;
          align-items:center; justify-content:center; text-align:center;
          color:var(--muted); cursor:pointer; background:#fafbfc;
          transition:border-color .15s,background .15s; }
  .drop:hover { background:#f3f4f6; }
  .drop.hover { border-color:var(--brand); background:#eff6ff; color:var(--text); }
  .drop span { font-size:15px; }
  .drop img { max-height:420px; max-width:100%; border-radius:8px;
              margin-top:14px; border:1px solid var(--line);
              box-shadow:0 2px 8px rgba(16,24,40,.10); }
  button#go { margin-top:26px; width:100%; padding:16px; font-size:17px;
           font-weight:700; border:0; border-radius:10px; cursor:pointer;
           background:var(--brand); color:#fff; letter-spacing:.2px;
           box-shadow:0 2px 6px rgba(29,78,216,.25); }
  button#go:hover:not(:disabled) { background:var(--brand-dark); }
  button#go:disabled { opacity:.5; cursor:not-allowed; box-shadow:none; }
  .results { margin-top:26px; display:none; }
  .summary { display:flex; align-items:center; gap:16px; flex-wrap:wrap;
             margin-bottom:10px; }
  .summary h2 { margin:0; font-size:22px; font-weight:700; }
  .bar { display:flex; gap:10px; flex-wrap:wrap; margin:18px 0 22px; }
  .filter { padding:8px 18px; border-radius:999px; font-size:14px;
            font-weight:600; border:1px solid var(--line); background:#fff;
            color:var(--text); cursor:pointer; }
  .filter[data-on="1"] { color:#fff; }
  .filter.high[data-on="1"] { background:var(--high); border-color:var(--high); }
  .filter.med[data-on="1"]  { background:var(--med);  border-color:var(--med); }
  .filter.low[data-on="1"]  { background:var(--low);  border-color:var(--low); }
  .filter.all[data-on="1"]  { background:var(--brand);border-color:var(--brand); }
  .filter.ok { background:#ecfdf5; color:var(--ok); border-color:#a7f3d0;
               cursor:default; }
  .acc { border:1px solid var(--line); border-left-width:5px;
         border-radius:10px; margin-bottom:12px; background:#fff;
         overflow:hidden; }
  .acc.high { border-left-color:var(--high); }
  .acc.medium { border-left-color:var(--med); }
  .acc.low { border-left-color:var(--low); }
  .acc-head { display:flex; align-items:center; gap:14px; padding:16px 20px;
              cursor:pointer; }
  .acc-head:hover { background:#f9fafb; }
  .badge { font-size:12px; font-weight:800; letter-spacing:.4px;
           padding:4px 10px; border-radius:6px; color:#fff; flex:none; }
  .badge.high { background:var(--high); }
  .badge.medium { background:var(--med); }
  .badge.low { background:var(--low); }
  .acc-title { font-weight:600; flex:1; font-size:15.5px; }
  .acc-title small { color:var(--muted); font-weight:400; }
  .chev { color:var(--muted); transition:transform .15s; flex:none;
          font-size:13px; }
  .acc.open .chev { transform:rotate(90deg); }
  .acc-body { display:none; padding:4px 20px 20px; }
  .acc.open .acc-body { display:block; }
  .acc-body .what { font-size:15px; margin:8px 0 16px; }
  .cmp { display:flex; gap:14px; flex-wrap:wrap; }
  .cmp > div { flex:1; min-width:220px; border:1px solid var(--line);
               border-radius:8px; padding:14px 16px; background:#fafafa; }
  .cmp h4 { margin:0 0 6px; font-size:12px; text-transform:uppercase;
            letter-spacing:.5px; color:var(--muted); }
  .cmp .val { font-size:16px; font-weight:600; word-break:break-word; }
  .cmp .expected { border-left:4px solid var(--ok); }
  .cmp .actual { border-left:4px solid var(--high); }
  .fix { margin-top:14px; font-size:15px; background:#eff6ff;
         border:1px solid #bfdbfe; color:#1e3a8a; padding:13px 16px;
         border-radius:8px; }
  .fix b { font-weight:700; }
  .matches { margin-top:24px; }
  .matches h3 { font-size:15px; color:var(--ok); margin:0 0 8px; }
  .matches div { color:var(--muted); font-size:14px; padding:2px 0; }
  .err { background:#fef2f2; color:#991b1b; border:1px solid #fecaca;
         padding:14px 16px; border-radius:8px; margin-top:20px;
         display:none; font-weight:500; }
  .spin { display:none; margin-top:20px; color:var(--muted); font-size:15px; }
  .actions { display:flex; gap:12px; flex-wrap:wrap; align-items:center;
             margin:10px 0 4px; }
  .act { width:auto; margin:0; padding:11px 18px; font-size:14px;
         font-weight:600; border:1px solid var(--brand); border-radius:8px;
         background:#fff; color:var(--brand); cursor:pointer; }
  .act:hover { background:#eff6ff; }
  .copied { font-size:14px; color:var(--ok); font-weight:600; }
  .annot-wrap { display:none; margin-top:26px; }
  .annot-title { font-size:16px; font-weight:600; margin:0 0 10px; }
  #annot { max-width:100%; border:1px solid var(--line); border-radius:10px;
           box-shadow:0 2px 8px rgba(16,24,40,.10); }
  .meta { color:var(--muted); font-size:13px; margin-top:22px;
          border-top:1px solid var(--line); padding-top:14px; }
</style>
</head>
<body>
<header>
  <div class="wrap" style="display:flex;justify-content:space-between;align-items:flex-start;gap:24px">
    <div>
      <h1>UI Fidelity Checker</h1>
      <p>Compare a Figma design against the built UI and catch implementation drift before QA does.</p>
    </div>
    <a href="/ai" style="color:#c7d2fe;font-size:14px;font-weight:600;text-decoration:none;white-space:nowrap;border:1px solid #4f6bd6;padding:8px 14px;border-radius:8px">How the AI works →</a>
  </div>
</header>
<main>
 <div class="wrap">
  <div class="env {{ 'ok' if env_ok else 'bad' }}">
    {{ env_msg }}
  </div>

  <div class="card">
    <div class="uploads">
      <div>
        <label>1 — Figma design <span class="hint">(screenshot the frame in Figma, or export as PNG)</span></label>
        <div class="drop" id="dropDesign">
          <span id="textDesign">Click or drop the design image</span>
          <div id="prevDesign"></div>
        </div>
      </div>
      <div>
        <label>2 — Running build screenshot <span class="hint">(screenshot of the screen in the app)</span></label>
        <div class="drop" id="dropBuild">
          <span id="textBuild">Click or drop the build screenshot</span>
          <div id="prevBuild"></div>
        </div>
      </div>
    </div>

    <div class="controls">
      <div>
        <label>3 — Section to compare</label>
        <select id="section">
          <option value="Whole screen">Whole screen (everything)</option>
          <option value="Header / top bar">Header / top bar</option>
          <option value="Left navigation sidebar">Left sidebar / navigation</option>
          <option value="Primary buttons and controls">Buttons &amp; controls</option>
          <option value="Cards / summary tiles">Cards / summary tiles</option>
          <option value="Charts and data visualisations">Charts &amp; data viz</option>
          <option value="Forms and input fields">Forms &amp; inputs</option>
          <option value="Tables / data grids">Tables / data grids</option>
          <option value="__custom__">Custom area… (type below)</option>
        </select>
        <input type="text" id="sectionCustom" placeholder="e.g. the date-range filter chips"
               style="display:none;margin-top:10px">
        <div id="secStatus" style="font-size:13px;color:var(--muted);margin-top:8px"></div>
      </div>
      <div>
        <label>Advanced <span class="hint">(optional)</span></label>
        <details>
          <summary style="cursor:pointer;color:var(--muted);font-size:14px;padding:11px 0">
            Use a Figma link instead of a design image (needs a Figma Dev/Full seat)
          </summary>
          <div style="margin-top:10px">
            <input type="text" id="figma" placeholder="https://www.figma.com/design/.../...?node-id=12-34">
          </div>
        </details>
      </div>
    </div>

    <button id="go" disabled>Compare design vs build</button>
    <div class="spin" id="spin">Comparing — this usually takes 10–40s…</div>
    <div class="err" id="err"></div>
  </div>

  <div class="results card" id="results">
    <div class="summary"><h2>Comparison report</h2><span id="verdict" style="color:var(--muted);font-size:13px"></span></div>
    <div class="actions">
      <button class="act" id="btnMd">⤓ Generate fix list (Markdown)</button>
      <button class="act" id="btnImg">⤓ Download annotated screenshot</button>
      <span id="copied" class="copied"></span>
    </div>
    <div class="bar" id="bar"></div>
    <div id="rows"></div>
    <div class="annot-wrap" id="annotWrap">
      <h3 class="annot-title">Annotated build screenshot</h3>
      <canvas id="annot"></canvas>
    </div>
    <div class="matches" id="matches"></div>
    <div class="meta" id="meta"></div>
  </div>
 </div>
</main>

<script>
const files = { design: null, build: null };

function refreshButton() {
  const haveBuild = !!files.build;
  const haveDesign = !!files.design ||
    !!document.getElementById('figma').value.trim();
  document.getElementById('go').disabled = !(haveBuild && haveDesign);
}
document.getElementById('figma').addEventListener('input', refreshButton);

function wireDrop(zoneId, textId, prevId, key) {
  const zone = document.getElementById(zoneId);
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/png,image/jpeg,image/webp,image/gif';

  function set(f) {
    files[key] = f;
    const r = new FileReader();
    r.onload = e => {
      document.getElementById(textId).textContent = f.name;
      document.getElementById(prevId).innerHTML =
        '<img src="' + e.target.result + '">';
    };
    r.readAsDataURL(f);
    refreshButton();
    if (key === 'design') detectSections(f);
  }

  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    if (input.files[0]) set(input.files[0]);
  });
  ['dragover','dragenter'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('hover'); }));
  ['dragleave','drop'].forEach(ev =>
    zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('hover'); }));
  zone.addEventListener('drop', e => {
    if (e.dataTransfer.files[0]) set(e.dataTransfer.files[0]);
  });
}
wireDrop('dropDesign', 'textDesign', 'prevDesign', 'design');
wireDrop('dropBuild', 'textBuild', 'prevBuild', 'build');

const _sectionSel = document.getElementById('section');
const _sectionCustom = document.getElementById('sectionCustom');
_sectionSel.addEventListener('change', () => {
  _sectionCustom.style.display =
    _sectionSel.value === '__custom__' ? 'block' : 'none';
});
function currentSection() {
  if (_sectionSel.value === '__custom__')
    return _sectionCustom.value.trim() || 'Whole screen';
  return _sectionSel.value;
}

async function detectSections(file) {
  const sel = _sectionSel;
  const status = document.getElementById('secStatus');
  status.textContent = 'Detecting sections from the design image…';
  const fd = new FormData();
  fd.append('design', file);
  try {
    const resp = await fetch('/sections', { method:'POST', body:fd });
    const data = await resp.json();
    if (!resp.ok || !data.sections || !data.sections.length) {
      status.textContent = 'Auto-detect unavailable — using the default list.';
      return;
    }
    sel.innerHTML =
      '<option value="Whole screen">Whole screen (everything)</option>' +
      data.sections.map(s =>
        '<option value="' + s.replace(/"/g,'&quot;') + '">' +
        s.replace(/</g,'&lt;') + '</option>').join('') +
      '<option value="__custom__">Custom area… (type below)</option>';
    sel.value = 'Whole screen';
    _sectionCustom.style.display = 'none';
    status.textContent = 'Detected ' + data.sections.length +
      ' sections from the design — pick one or keep "Whole screen".';
  } catch (e) {
    status.textContent = 'Auto-detect failed — using the default list.';
  }
}

document.getElementById('go').addEventListener('click', async () => {
  const err = document.getElementById('err');
  const results = document.getElementById('results');
  err.style.display = 'none';
  results.style.display = 'none';
  document.getElementById('go').disabled = true;
  document.getElementById('spin').style.display = 'block';

  const fd = new FormData();
  fd.append('figma_url', document.getElementById('figma').value.trim());
  fd.append('section', currentSection());
  fd.append('build', files.build);
  if (files.design) fd.append('design', files.design);

  try {
    const resp = await fetch('/compare', { method:'POST', body:fd });
    const data = await resp.json();
    document.getElementById('spin').style.display = 'none';
    if (!resp.ok) {
      err.textContent = data.error || 'Something went wrong.';
      err.style.display = 'block';
      refreshButton();
      return;
    }
    render(data);
  } catch (e) {
    document.getElementById('spin').style.display = 'none';
    err.textContent = 'Request failed: ' + e;
    err.style.display = 'block';
  }
  refreshButton();
});

function esc(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

let _mismatches = [];
let _filter = 'all';

function diffSentence(x) {
  return esc(x.property) + ' should be ' + esc(x.design_value) +
    ' in the design, but the build shows ' + esc(x.build_value) + '.';
}

function drawCards() {
  const list = _filter === 'all'
    ? _mismatches
    : _mismatches.filter(x => x.severity === _filter);

  document.getElementById('rows').innerHTML = _mismatches.length === 0
    ? '<div class="acc low"><div class="acc-head"><span class="acc-title">No mismatches — the build matches the design.</span></div></div>'
    : (list.length === 0
        ? '<div style="color:var(--muted);font-size:13px;padding:8px 2px">No ' + _filter + '-severity issues.</div>'
        : list.map((x, i) =>
      '<div class="acc ' + x.severity + '" data-i="' + _mismatches.indexOf(x) + '">' +
        '<div class="acc-head">' +
          '<span class="badge ' + x.severity + '">' +
            (_mismatches.indexOf(x) + 1) + '. ' + x.severity.toUpperCase() + '</span>' +
          '<span class="acc-title">' + esc(x.element) +
            ' <small>— ' + esc(x.property) + '</small></span>' +
          '<span class="chev">▶</span>' +
        '</div>' +
        '<div class="acc-body">' +
          '<div class="what">' + diffSentence(x) + '</div>' +
          '<div class="cmp">' +
            '<div class="expected"><h4>Design (expected)</h4><div class="val">' +
              esc(x.design_value) + '</div></div>' +
            '<div class="actual"><h4>Build (actual)</h4><div class="val">' +
              esc(x.build_value) + '</div></div>' +
          '</div>' +
          '<div class="fix"><b>How to fix:</b> ' + esc(x.fix_hint) + '</div>' +
        '</div>' +
      '</div>').join(''));
}

function setFilter(f) {
  _filter = f;
  document.querySelectorAll('.filter').forEach(b =>
    b.setAttribute('data-on', b.dataset.f === f ? '1' : '0'));
  drawCards();
}

document.getElementById('rows').addEventListener('click', e => {
  const head = e.target.closest('.acc-head');
  if (head && head.parentElement.classList.contains('acc'))
    head.parentElement.classList.toggle('open');
});
document.getElementById('bar').addEventListener('click', e => {
  const b = e.target.closest('.filter');
  if (b && b.dataset.f) setFilter(b.dataset.f);
});

function render(d) {
  const m = d.mismatches, ok = d.matches;
  _mismatches = m;
  _lastData = d;
  _filter = 'all';
  const c = { high:0, medium:0, low:0 };
  m.forEach(x => c[x.severity] = (c[x.severity]||0)+1);

  const fp = (cls,f,label,n) =>
    '<button class="filter ' + cls + '" data-f="' + f + '" data-on="' +
    (f==='all'?'1':'0') + '">' + label + ' (' + n + ')</button>';
  document.getElementById('bar').innerHTML =
    fp('all','all','All issues', m.length) +
    fp('high','high','High', c.high) +
    fp('med','medium','Medium', c.medium) +
    fp('low','low','Low', c.low) +
    '<span class="filter ok">✓ ' + ok.length + ' matching</span>';

  const pass = c.high === 0;
  const note = m.length === 0
    ? 'Pixel-perfect — no deviations found.'
    : (pass
        ? c.medium + ' medium · ' + c.low + ' low — no blocking issues.'
        : c.high + ' high · ' + c.medium + ' medium · ' + c.low +
          ' low. Click a card for details and the fix.');
  document.getElementById('verdict').innerHTML =
    '<span class="verdict-badge ' + (pass ? 'pass">UI PASS' : 'fail">UI FAIL') +
    '</span> &nbsp;<span style="color:var(--muted)">' +
    esc(d.focus || 'Whole screen') + ' · ' + note + '</span>';

  drawCards();

  document.getElementById('matches').innerHTML = ok.length
    ? '<h3>✓ Matches design (' + ok.length + ')</h3>' +
      ok.slice(0,20).map(x =>
        '<div>' + esc(x.element) + ' — ' + esc(x.property) + '</div>').join('') +
      (ok.length > 20 ? '<div>… and ' + (ok.length-20) + ' more</div>' : '')
    : '';

  document.getElementById('meta').textContent =
    d.usage.engine + ' · ' + d.frame_name +
    (d.element_count ? ' · ' + d.element_count + ' design elements' : '') +
    ' · tokens in=' + d.usage.input_tokens + ' out=' + d.usage.output_tokens;

  document.getElementById('results').style.display = 'block';
  drawAnnotation();
}

let _lastData = null;
const SEV_RGB = { high:'#dc2626', medium:'#d97706', low:'#6b7280' };

function drawAnnotation() {
  const wrap = document.getElementById('annotWrap');
  const canvas = document.getElementById('annot');
  if (!files.build || !_lastData) { wrap.style.display = 'none'; return; }

  const img = new Image();
  img.onload = () => {
    // Cap very large screenshots so the canvas stays manageable.
    const maxW = 1600;
    const scale = img.naturalWidth > maxW ? maxW / img.naturalWidth : 1;
    const W = Math.round(img.naturalWidth * scale);
    const H = Math.round(img.naturalHeight * scale);
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, W, H);

    _lastData.mismatches.forEach((x, i) => {
      const b = x.box;
      if (!b) return;
      const rx = b.x * W, ry = b.y * H, rw = b.w * W, rh = b.h * H;
      const col = SEV_RGB[x.severity] || '#dc2626';

      ctx.lineWidth = Math.max(2, W / 500);
      ctx.strokeStyle = col;
      ctx.strokeRect(rx, ry, rw, rh);

      // numbered tag at the top-left of the box
      const n = String(i + 1);
      ctx.font = 'bold ' + Math.max(13, W/90) + 'px Segoe UI, sans-serif';
      const padX = 6, th = Math.max(18, W/55);
      const label = n + '. ' + (x.property || x.element || '');
      const tw = ctx.measureText(label).width + padX * 2;
      let ly = ry - th;
      if (ly < 0) ly = ry;            // keep on-canvas
      ctx.fillStyle = col;
      ctx.fillRect(rx, ly, Math.min(tw, W - rx), th);
      ctx.fillStyle = '#fff';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, rx + padX, ly + th / 2);
    });

    wrap.style.display = 'block';
  };
  img.src = URL.createObjectURL(files.build);
}

function buildMarkdown(d) {
  const NL = String.fromCharCode(10);
  const ts = new Date().toISOString().slice(0, 16).replace('T', ' ');
  const groups = { high: [], medium: [], low: [] };
  d.mismatches.forEach((x, i) => (groups[x.severity] || groups.low).push([i + 1, x]));

  const high = (groups.high || []).length;
  const status = high === 0 ? 'PASS' : 'FAIL';

  const L = [];
  L.push('# UI Fidelity Fix List — ' + (d.frame_name || 'Design vs Build'));
  L.push('');
  L.push('**Status: ' + status + '**  ·  Section: ' + (d.focus || 'Whole screen'));
  L.push('');
  L.push('_Generated ' + ts + ' · ' + d.usage.engine + '_');
  L.push('');
  L.push('Apply the changes below so the build matches the Figma design. '
       + 'Each item: what is wrong, expected vs actual, and the fix.');
  L.push('');

  ['high', 'medium', 'low'].forEach(sev => {
    const g = groups[sev];
    if (!g.length) return;
    L.push('## ' + sev[0].toUpperCase() + sev.slice(1) + ' priority ('
         + g.length + ')');
    L.push('');
    g.forEach(([n, x]) => {
      L.push('- [ ] **' + x.element + ' — ' + x.property + '** (#' + n + ')');
      L.push('  - Expected (design): `' + x.design_value + '`');
      L.push('  - Actual (build): `' + x.build_value + '`');
      L.push('  - Fix: ' + x.fix_hint);
      L.push('');
    });
  });

  if (d.matches && d.matches.length) {
    L.push('## Already matches design');
    L.push('');
    d.matches.forEach(x => L.push('- ' + x.element + ' — ' + x.property));
    L.push('');
  }
  return L.join(NL);
}

function downloadBlob(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

document.getElementById('btnMd').addEventListener('click', async () => {
  if (!_lastData) return;
  const md = buildMarkdown(_lastData);
  downloadBlob(new Blob([md], { type: 'text/markdown' }), 'ui-fix-list.md');
  try {
    await navigator.clipboard.writeText(md);
    const c = document.getElementById('copied');
    c.textContent = 'Downloaded + copied to clipboard — paste into Copilot.';
    setTimeout(() => (c.textContent = ''), 4000);
  } catch (e) { /* clipboard may be blocked; the file still downloaded */ }
});

document.getElementById('btnImg').addEventListener('click', () => {
  const canvas = document.getElementById('annot');
  if (!canvas.width) return;
  canvas.toBlob(b => downloadBlob(b, 'annotated-build.png'), 'image/png');
});
</script>
</body>
</html>"""


def _env_status() -> tuple[bool, str]:
    if os.environ.get("GEMINI_API_KEY"):
        engine = "Engine: Google Gemini (free). Ready."
    elif os.environ.get("ANTHROPIC_API_KEY"):
        engine = "Engine: Anthropic Claude. Ready."
    else:
        return False, (
            "No model key set. Add GEMINI_API_KEY (free) or ANTHROPIC_API_KEY "
            "to .env and restart this app."
        )
    return True, engine


AI_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How the AI works — UI Fidelity Checker</title>
<style>
  :root { --bg:#f4f6f9; --panel:#fff; --line:#dfe3e8; --text:#1f2937;
          --muted:#6b7280; --brand:#1d4ed8; --brand-dark:#1e3a8a; --ok:#059669; }
  *{box-sizing:border-box} body{margin:0;font:16px/1.65 "Segoe UI",system-ui,sans-serif;
    background:var(--bg);color:var(--text)}
  .wrap{max-width:920px;margin:0 auto;padding:0 32px}
  header{background:var(--brand-dark);color:#fff;padding:34px 0}
  header h1{margin:0;font-size:28px;font-weight:700}
  header p{margin:8px 0 0;color:#c7d2fe}
  header a{color:#c7d2fe;font-size:14px;font-weight:600;text-decoration:none}
  main{padding:36px 0 80px}
  h2{font-size:21px;margin:34px 0 10px;border-bottom:1px solid var(--line);
     padding-bottom:8px}
  h2:first-child{margin-top:0}
  p{margin:10px 0}
  .tag{display:inline-block;background:#eef2ff;color:var(--brand-dark);
       font-weight:700;font-size:13px;padding:5px 12px;border-radius:999px;
       margin-right:8px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
        padding:22px 26px;margin:16px 0;box-shadow:0 1px 3px rgba(16,24,40,.05)}
  table{border-collapse:collapse;width:100%;margin:14px 0;font-size:15px}
  th,td{border:1px solid var(--line);padding:10px 12px;text-align:left;
        vertical-align:top}
  th{background:#f3f4f6;font-weight:600}
  code{background:#eef2ff;padding:1px 6px;border-radius:4px;font-size:14px}
  ol.flow{counter-reset:s;list-style:none;padding:0}
  ol.flow li{position:relative;padding:10px 0 10px 44px;margin:6px 0}
  ol.flow li:before{counter-increment:s;content:counter(s);position:absolute;
    left:0;top:8px;width:28px;height:28px;border-radius:50%;background:var(--brand);
    color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;
    font-size:14px}
  .yes{color:var(--ok);font-weight:700} .no{color:#b91c1c;font-weight:700}
  .muted{color:var(--muted);font-size:14px}
</style>
</head>
<body>
<header><div class="wrap" style="display:flex;justify-content:space-between;align-items:center;gap:20px">
  <div><h1>How the AI works</h1><p>The AI technology behind UI Fidelity Checker</p></div>
  <a href="/">← Back to the tool</a>
</div></header>
<main><div class="wrap">

  <h2>In one line</h2>
  <p>
    <span class="tag">Generative AI</span>
    <span class="tag">Multimodal vision LLM</span>
    <span class="tag">Structured output</span>
  </p>
  <p>This is a <b>generative-AI application</b> built on a <b>multimodal
  vision Large Language Model</b>. It looks at two images and generates a
  structured, machine-readable report. It is a focused <b>AI workflow</b>,
  <i>not</i> an autonomous agent.</p>

  <h2>Generative AI vs. Agentic AI — which is this?</h2>
  <div class="card">
  <table>
    <tr><th>Aspect</th><th>This tool</th></tr>
    <tr><td>Generative AI?</td><td><span class="yes">Yes.</span> A vision LLM
      generates the findings (what differs, severity, fix, location) from the
      design and build images.</td></tr>
    <tr><td>Agentic AI?</td><td><span class="no">No.</span> There is no
      autonomous agent loop — no self-directed planning, no tool-calling, no
      acting on the environment, no memory. The model is called, returns a
      structured answer, and the program does the rest deterministically.</td></tr>
    <tr><td>Best description</td><td>A <b>prompt-engineered, structured-output
      generative-AI pipeline</b> (a "workflow"), not an agent.</td></tr>
  </table>
  </div>
  <p class="muted">Why this matters: agentic systems decide their own steps and
  can take actions. This tool's steps are fixed in code; the AI only does the
  perception + judgement, and only ever returns text/JSON.</p>

  <h2>Models used</h2>
  <table>
    <tr><th>Backend</th><th>Model</th><th>Role</th><th>Cost</th></tr>
    <tr><td>Google Gemini <i>(default)</i></td><td><code>gemini-2.5-flash</code>
      and fallbacks</td><td>Vision + reasoning + JSON output</td>
      <td>Free tier</td></tr>
    <tr><td>Anthropic Claude <i>(optional)</i></td><td>Claude (vision-capable)
      </td><td>Same role, higher-precision localisation</td><td>Paid</td></tr>
  </table>
  <p>The backend is <b>pluggable</b>: whichever API key is configured is used.
  If a free Gemini model is busy, the tool automatically retries and falls
  back across several Gemini models.</p>

  <h2>AI techniques in play</h2>
  <ul>
    <li><b>Multimodal prompting</b> — two images (design + build) plus a
      written brief are sent to the model together.</li>
    <li><b>Role / system prompting</b> — the model is instructed to act as a
      senior UI-fidelity reviewer with explicit comparison rules.</li>
    <li><b>Structured outputs</b> — the response is constrained to a strict
      JSON schema (findings, severity, expected/actual, fix, bounding box) so
      it is reliably machine-usable, not free text.</li>
    <li><b>Deterministic decoding</b> — temperature 0 for repeatable results.</li>
    <li><b>Scoped prompting</b> — an optional instruction restricts the model
      to one section of the screen.</li>
    <li><b>Vision grounding</b> — the model returns normalised coordinates so
      the app can draw boxes on the screenshot.</li>
  </ul>

  <h2>What it deliberately does <i>not</i> use</h2>
  <p class="muted">No model training or fine-tuning · no RAG / vector database ·
  no agent framework or tool-calling loop · no autonomous decision-making ·
  no persistent memory. It is a single, well-prompted pipeline.</p>

  <h2>The pipeline (at most two model calls)</h2>
  <ol class="flow">
    <li><b>Section detection (optional, generative):</b> the design image is
      sent to the model, which returns the list of UI sections it sees — used
      to populate the scope dropdown.</li>
    <li><b>Comparison (generative):</b> design image + build image + the chosen
      scope are sent with the reviewer system prompt; the model returns JSON
      findings.</li>
    <li><b>Deterministic post-processing (plain code, no AI):</b> sort by
      severity, compute the PASS/FAIL verdict, draw the annotated screenshot,
      and build the Markdown fix list.</li>
  </ol>

  <h2>Honest limitations</h2>
  <p class="muted">Outputs are model judgements, not measurements — values and
  box positions are estimates and can be imprecise (more so on the free Gemini
  tier than on Claude). It is a fast assistant for catching drift, not a
  pixel-exact measurement tool.</p>

</div></main>
</body>
</html>"""


@app.get("/")
def index():
    ok, msg = _env_status()
    return render_template_string(PAGE, env_ok=ok, env_msg=msg)


@app.get("/ai")
def ai_info():
    return render_template_string(AI_PAGE)


@app.post("/sections")
def sections():
    f = request.files.get("design") or request.files.get("build")
    if not f or not f.filename:
        return jsonify(error="An image is required."), 400
    try:
        secs = detect_sections(f.read(), media_type_for(f.filename))
    except (DiffError, ValueError) as e:
        return jsonify(error=str(e)), 400
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    return jsonify(sections=secs)


@app.post("/compare")
def compare():
    figma_url = (request.form.get("figma_url") or "").strip()
    focus = (request.form.get("section") or "").strip() or None
    build = request.files.get("build")
    design = request.files.get("design")

    if not build or not build.filename:
        return jsonify(error="A build screenshot is required."), 400
    if not design and not figma_url:
        return jsonify(
            error="Provide a design image (recommended) or a Figma link."
        ), 400

    try:
        build_mt = media_type_for(build.filename)
        build_bytes = build.read()
        if design and design.filename:
            design_mt = media_type_for(design.filename)
            result = diff_images(
                design.read(), design_mt, build_bytes, build_mt, focus
            )
        else:
            result = diff(figma_url, build_bytes, build_mt, focus)
    except (DiffError, ValueError) as e:
        return jsonify(error=str(e)), 400
    except RuntimeError as e:
        return jsonify(error=str(e)), 502
    except Exception as e:  # never leak an HTML 500 to the frontend
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
