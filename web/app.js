// CatchLength console: replays recorded agent runs (samples/<id>/run.json) and shows the benchmark.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const nf1 = new Intl.NumberFormat('en', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const cm = (v) => (v == null ? '<span class="muted">–</span>' : `${nf1.format(v)}<span class="unit">cm</span>`);
  const NS = 'http://www.w3.org/2000/svg';
  const STEP = { inspect_clip: 'Plan', calibrate: 'Calibrate', segment: 'Segment', find_missed: 'Check the count', rescue: 'Rescue',
    measure: 'Measure', classify: 'Species', apply_rules: 'Rules', request_review: 'Hand to officer', submit_report: 'File report', sign_off: 'Officer sign-off' };
  const RULE_TEXT = { no_minimum: 'No gazetted minimum size', pass: 'Above legal minimum', below_minimum: 'Below legal minimum',
    no_rule_in_pack: 'No rule in the pack', info: '' };
  let samples = [], run = null, dir = '', selected = null, timer = null;

  // ---- views ------------------------------------------------------------------------------------------------
  function show(view) {
    for (const v of ['run', 'benchmark', 'about']) $(`#view-${v}`).hidden = v !== view;
    document.querySelectorAll('.rail a[data-view]').forEach((a) => {
      if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (view === 'benchmark') benchmark();
  }
  window.addEventListener('hashchange', () => show(location.hash.slice(1) || 'run'));

  // ---- data ---------------------------------------------------------------------------------------------------
  async function init() {
    samples = await (await fetch('samples/index.json')).json();
    const seg = $('#samples');
    seg.innerHTML = samples.map((s, i) => `<button type="button" role="radio" aria-checked="${i === 0}" data-i="${i}">${esc(s.label)}</button>`).join('');
    seg.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) load(+b.dataset.i); });
    $('#run-btn').addEventListener('click', live);
    show(location.hash.slice(1) || 'run');
    await load(0);
  }

  async function load(i) {
    clearTimeout(timer);
    document.querySelectorAll('#samples button').forEach((b) => b.setAttribute('aria-checked', String(+b.dataset.i === i)));
    dir = `samples/${samples[i].id}/`;
    run = await (await fetch(dir + 'run.json')).json();
    const sim = run.simulated;
    $('#notice').hidden = !sim;
    if (sim) $('#notice').textContent = sim.note;
    $('#frame-img').src = dir + 'frame.jpg';
    $('#frame-img').alt = `Best frame of ${run.source}: fish on a dark sheet with printed marker tiles`;
    const [w, h] = run.size;
    $('#overlay').setAttribute('viewBox', `0 0 ${w} ${h}`);
    $('#frame-sub').textContent = `frame ${run.best_frame} · ${run.tiles.length} marker ${run.tiles.length === 1 ? 'tile' : 'tiles'}`;
    render(run.log.length);
  }

  // ---- live run on the server, streamed turn by turn; falls back to the recording ---------------------------------
  async function live() {
    const btn = $('#run-btn');
    const id = samples[+document.querySelector('#samples [aria-checked="true"]').dataset.i].id;
    let res;
    try { res = await fetch('api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sample: id }) }); }
    catch { return replay(); }
    if (!res.ok || !(res.headers.get('content-type') || '').includes('event-stream')) return replay();
    btn.disabled = true; btn.textContent = 'Running live…';
    const turns = [];
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '', fail = null, doneDir = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let k;
      while ((k = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, k); buf = buf.slice(k + 2);
        const ev = /event: (\w+)/.exec(block)?.[1], data = JSON.parse(/data: (.*)/s.exec(block)?.[1] || '{}');
        if (ev === 'turn') { turns.push(data); timeline(turns, true); $('#finding').innerHTML = `<span class="muted">Live: turn ${turns.length}…</span>`; }
        if (ev === 'error') fail = data.message;
        if (ev === 'done') doneDir = data.dir;
      }
    }
    btn.disabled = false; btn.textContent = 'Run again';
    if (fail || !doneDir) { $('#notice').hidden = false; $('#notice').textContent = `Live run unavailable: ${fail || 'no result'} Showing the recorded run.`; return replay(); }
    dir = doneDir;
    run = await (await fetch(dir + 'run.json')).json();
    $('#frame-img').src = dir + 'frame.jpg?' + Date.now();
    $('#notice').hidden = !run.simulated;
    render(run.log.length);
  }

  // ---- replay: the recorded log arrives turn by turn ------------------------------------------------------------
  function replay() {
    clearTimeout(timer);
    const btn = $('#run-btn');
    btn.disabled = true; btn.textContent = 'Running…';
    let k = 0;
    render(0);
    const tick = () => {
      k += 1;
      render(k, true);
      if (k < run.log.length) timer = setTimeout(tick, 650);
      else { btn.disabled = false; btn.textContent = 'Run again'; }
    };
    timer = setTimeout(tick, 300);
  }

  function render(upto, animate = false) {
    const log = run.log.slice(0, upto);
    const done = upto >= run.log.length;
    const seen = new Set(log.map((l) => l.tool));
    // fish appear when SAM found them; rescued ones (ids >= 1000) when the rescue landed
    const visible = run.fish.filter((f) => (seen.has('segment') && +f.id < 1000) || (seen.has('rescue') && +f.id >= 1000));
    timeline(log, animate);
    overlay(visible, seen.has('measure'));
    ledger(seen.has('measure') ? visible : [], seen);
    const r = run.receipt?.fish;
    const status = { awaiting_signoff: 'waiting for the officer to sign off', needs_review: 'handed to the officer',
      needs_refilm: 'clip refused, re-film needed', signed_off: 'signed off', running: 'unfinished' }[run.status] || run.status;
    $('#finding').innerHTML = done && r
      ? `<b>${r.accepted} of ${r.detected} fish measured</b>, ${r.flagged ? `${r.flagged} handed to the officer` : 'none flagged'} · <span class="muted">${esc(status)}</span>`
      : upto ? `<span class="muted">Turn ${upto} of ${run.log.length}…</span>` : 'Replay the recorded run turn by turn.';
    $('#tl-sub').textContent = `${upto} of ${run.log.length} turns · $${(run.cost?.usd ?? 0).toFixed(3)}`;
    lf(done ? run.report?.lf_1cm : null);
    receipt(done ? run.receipt : null);
  }

  function say(tool, r) {
    if (!r) return '';
    if (r.refused) return `<b>Refused:</b> ${esc(r.feedback)}${r.escalated ? ` <b>${esc(r.escalated)}</b>` : ''}`;
    switch (tool) {
      case 'inspect_clip': return `Usable. Expects <b>${r.expected_count}</b> fish; best frame ${r.best_frame}; ${r.issues?.length ? esc(r.issues.join('; ')) : 'no problems seen'}.`;
      case 'calibrate': return `${r.tiles.length} marker tiles found; corner error <b>${r.corner_error_px} px</b> (limit 1.5).`;
      case 'segment': return `SAM 3.1 found <b>${r.found}</b>; the plan expected ${r.expected}. ${esc(r.note.charAt(0).toUpperCase() + r.note.slice(1))}.`;
      case 'find_missed': return `Spark counts ${r.count}: ${r.missed_boxes.length} without an outline${r.merged_ids.length ? `, outline ${esc(r.merged_ids.join(', '))} wraps two fish` : ''}.`;
      case 'rescue': return `Boxes and negative points sent back to SAM: kept ${r.accepted.map(esc).join(', ') || 'none'}${r.rejected.length ? `, rejected ${r.rejected.length}` : ''}. Now <b>${r.count_now}</b> fish.`;
      case 'measure': return `<b>${r.measured}</b> measured two ways, ${r.flagged.length} flagged. ${r.cross_frame ? esc(r.cross_frame.note.charAt(0).toUpperCase() + r.cross_frame.note.slice(1)) : ''}.`;
      case 'classify': { const c = {}; Object.values(r.species).forEach((s) => (c[s] = (c[s] || 0) + 1)); return Object.entries(c).map(([s, n]) => `${n} × ${esc(s)}`).join(', ') + '.'; }
      case 'apply_rules': return 'Every fish checked against the cited rule pack.';
      case 'request_review': return `Queued for the officer (${r.queued}).`;
      case 'submit_report': return `Filed: <b>${r.measured}</b> fish, waiting for ${esc(r.waiting_for)}.`;
      default: return '';
    }
  }

  function timeline(log, animate) {
    $('#timeline').innerHTML = log.map((l, i) => {
      const r = l.result || {};
      const pill = r.escalated ? '<span class="pill warn">escalated</span>' : r.refused ? '<span class="pill no">refused</span>'
        : l.tool === 'measure' && r.flagged?.length ? `<span class="pill warn">${r.flagged.length} flagged</span>`
        : l.tool === 'segment' && r.found !== r.expected ? '<span class="pill warn">count off</span>' : '<span class="pill ok">passed</span>';
      return `<li class="${animate && i === log.length - 1 ? 'arrive' : ''}"><span class="tool">${esc(STEP[l.tool] || l.tool)}</span>${pill}<span class="say">${say(l.tool, r)}</span></li>`;
    }).join('') || '<li><span class="say">No turns yet.</span></li>';
    const tl = $('#timeline'); tl.scrollTop = animate ? tl.scrollHeight : 0;  // follow a replay; a finished run reads from the top
  }

  function overlay(fish, measured) {
    const svg = $('#overlay');
    svg.innerHTML = '';
    for (const f of fish) {
      const flagged = measured && f.status === 'needs_review';
      const p = document.createElementNS(NS, 'polygon');
      p.setAttribute('points', f.outline.map((q) => q.join(',')).join(' '));
      p.setAttribute('class', `fish${flagged ? ' flagged' : ''}${selected === f.id ? ' on' : ''}`);
      p.addEventListener('click', () => pick(f.id));
      svg.appendChild(p);
      const [x0, y0] = f.box;
      const t = document.createElementNS(NS, 'text');
      const fs = Math.round(run.size[0] / 40);  // label size follows the frame, so it reads at any resolution
      t.setAttribute('x', x0); t.setAttribute('y', Math.max(fs, y0 - fs / 3)); t.setAttribute('class', 'lbl'); t.setAttribute('font-size', fs); t.textContent = f.id;
      svg.appendChild(t);
      if (measured && selected === f.id && f.points) {
        const [a, b] = [f.points.snout, f.points.fork];
        const line = document.createElementNS(NS, 'line');
        Object.entries({ x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: 'fl' }).forEach(([k, v]) => line.setAttribute(k, v));
        svg.appendChild(line);
        for (const q of [a, b]) { const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', q[0]); c.setAttribute('cy', q[1]); c.setAttribute('r', 9); c.setAttribute('class', 'pt'); svg.appendChild(c); }
      }
    }
  }

  function ledger(fish, seen) {
    const body = $('#ledger tbody');
    $('#fish-sub').textContent = fish.length ? `${fish.length} fish · fork length is snout tip to tail fork, on the sheet's plane` : '';
    if (!fish.length) { body.innerHTML = `<tr><td colspan="7" class="empty">${seen.has('segment') ? 'Measuring…' : 'Run the agent to see each fish.'}</td></tr>`; return; }
    body.innerHTML = fish.map((f) => {
      const fr = Object.values(f.frames_mm || {});
      const spread = fr.length && f.axis_cm != null ? (Math.max(...fr, f.axis_cm * 10) - Math.min(...fr, f.axis_cm * 10)) / 10 : null;
      const rule = (f.rules || []).find((x) => x.result !== 'info');
      const st = f.status === 'measured' ? '<span class="pill ok">accepted</span>' : f.status === 'needs_review' ? '<span class="pill warn">to officer</span>' : '<span class="pill n">found</span>';
      return `<tr data-id="${esc(f.id)}" class="${selected === f.id ? 'on' : ''}" tabindex="0">
        <td>${esc(f.id)}</td><td>${f.species ? esc(f.species) : '<span class="muted">–</span>'}</td>
        <td class="num">${cm(f.fork_cm)}</td><td class="num">${cm(f.axis_cm)}</td>
        <td class="num">${spread == null ? '<span class="muted">–</span>' : `±${nf1.format(spread / 2)}<span class="unit">cm</span>`}</td>
        <td>${st}${f.why ? `<span class="why">${esc(f.why)}</span>` : ''}</td>
        <td class="rule">${rule ? `${esc(RULE_TEXT[rule.result] ?? rule.result)} <span class="muted">[${esc(rule.rule || '–')}]</span>` : '<span class="muted">–</span>'}</td></tr>`;
    }).join('');
    body.querySelectorAll('tr[data-id]').forEach((tr) => {
      tr.addEventListener('click', () => pick(tr.dataset.id));
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(tr.dataset.id); } });
    });
  }

  function pick(id) {
    selected = selected === id ? null : id;
    render(run.log.length);
  }

  // ---- small charts --------------------------------------------------------------------------------------------
  function svgEl(w, h, label) {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', `0 0 ${w} ${h}`); s.setAttribute('role', 'img'); s.setAttribute('aria-label', label);
    return s;
  }
  const add = (p, tag, attrs, txt) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); if (txt != null) n.textContent = txt; p.appendChild(n); return n; };
  const niceMax = (v) => { const step = v <= 5 ? 1 : v <= 10 ? 2 : 5; return Math.ceil((v + 0.001) / step) * step; };

  function lf(bins) {
    const el = $('#lf');
    el.className = 'chart';
    if (!bins || !Object.keys(bins).length) { el.innerHTML = '<p class="empty">Appears when the report is filed.</p>'; return; }
    const ks = Object.keys(bins).map(Number), lo = Math.min(...ks), hi = Math.max(...ks);
    const xs = []; for (let k = lo; k <= hi; k++) xs.push(k);
    const W = 520, H = 200, L = 28, B = 22, top = niceMax(Math.max(...Object.values(bins)));
    const bw = (W - L) / xs.length;
    const s = svgEl(W, H, `Length frequency: ${Object.values(bins).reduce((a, b) => a + b, 0)} fish in 1 cm classes from ${lo} to ${hi} cm`);
    for (let t = 0; t <= top; t += top <= 5 ? 1 : 2) {
      const y = H - B - (t / top) * (H - B - 8);
      add(s, 'line', { x1: L, x2: W, y1: y, y2: y, class: 'grid-line' });
      add(s, 'text', { x: L - 8, y: y + 4, 'text-anchor': 'end', class: 'axis' }, t);
    }
    xs.forEach((k, i) => {
      const n = bins[k] || 0, hgt = (n / top) * (H - B - 8);
      if (n) add(s, 'rect', { x: L + i * bw + 2, y: H - B - hgt, width: Math.max(2, bw - 4), height: hgt, class: 'bar' });
      if (xs.length <= 12 || i % Math.ceil(xs.length / 10) === 0) add(s, 'text', { x: L + i * bw + bw / 2, y: H - 4, 'text-anchor': 'middle', class: 'axis' }, k);
    });
    const all = xs.flatMap((k) => Array(bins[k] || 0).fill(k)), n = all.length;
    const med = n % 2 ? all[(n - 1) / 2] : (all[n / 2 - 1] + all[n / 2]) / 2;
    const p = document.createElement('p');
    p.className = 'sub lf-sum';
    p.textContent = `${n} accepted fish · ${lo} to ${hi + 1} cm · median class ${med} cm`;
    el.replaceChildren(s, p);
  }

  function receipt(rc) {
    const el = $('#receipt');
    if (!rc) { el.innerHTML = '<dt>Status</dt><dd class="muted">Appears when the report is filed.</dd>'; return; }
    const rows = [
      ['Clip SHA-256', rc.clip_sha256 ? rc.clip_sha256.slice(0, 16) + '…' : '– (simulated, no clip file)'],
      ['Finished', rc.finished_utc.replace('T', ' ').replace('+00:00', ' UTC')],
      ['Models', rc.models.join(', ')],
      ['Calibration', `${rc.calibration.tiles.length} tiles, corner error ${rc.calibration.corner_error_px?.toFixed(2)} px`],
      ['Fish', `${rc.fish.detected} found, ${rc.fish.accepted} accepted, ${rc.fish.flagged} flagged`],
      ['Rescued by SAM', rc.rescued.length ? rc.rescued.join(', ') : 'none'],
      ['Frames checked', [rc.frames.best, ...rc.frames.checked].join(', ')],
      ['Cost', `$${rc.cost_usd.toFixed(3)}`],
      ['Code', rc.git_commit || 'uncommitted'],
      ['CSV SHA-256', rc.csv_sha256.slice(0, 16) + '…'],
    ];
    el.innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  }

  // ---- benchmark ------------------------------------------------------------------------------------------------
  async function benchmark() {
    const body = $('#bm-body');
    let bm = null;
    try { const r = await fetch('benchmark.json'); if (r.ok) bm = await r.json(); } catch { /* not published yet */ }
    if (!bm) {
      $('#bm-finding').innerHTML = 'No field benchmark yet. <span class="muted">Fish are tape-measured at Peliyagoda on Sun 1 Nov; the agent never sees those numbers.</span>';
      body.innerHTML = `<article class="card"><header class="card-h"><h2>What will be measured</h2></header>
        <dl class="kv"><dt>Length</dt><dd>Mean and median error against the tape, 90th percentile, share within 2 cm, bias and limits of agreement. Error among accepted fish is shown apart from all fish.</dd>
        <dt>Count</dt><dd>Clips where the agent's count equals the fish on the sheet.</dd>
        <dt>Species</dt><dd>Accuracy over three species from a closed list, "unknown" allowed.</dd>
        <dt>Pass marks</dt><dd>Mean error 2.0 cm or less on 40 or more fish; exact count on 90% of clean clips; species right 90% of the time.</dd></dl></article>`;
      return;
    }
    const L = bm.length_accepted_only, A = bm.length;
    $('#bm-finding').innerHTML = `<b>Mean error ${nf1.format(L.mae)} cm</b> on ${L.n} accepted fish · ${bm.flagged} handed to the officer · <span class="muted">${bm.n_measured} fish measured in all</span>`;
    body.innerHTML = `<article class="card"><div class="kpis">
      <div class="kpi"><div class="v">${nf1.format(L.mae)}<span class="unit">cm</span></div><div class="l">mean error, accepted fish</div></div>
      <div class="kpi"><div class="v">${Math.round(L.within_2cm * 100)}<span class="unit">%</span></div><div class="l">within 2 cm of the tape</div></div>
      <div class="kpi"><div class="v">${bm.count.exact_rate == null ? '–' : Math.round(bm.count.exact_rate * 100)}<span class="unit">%</span></div><div class="l">clips counted exactly</div></div>
      <div class="kpi"><div class="v">${bm.species.accuracy == null ? '–' : Math.round(bm.species.accuracy * 100)}<span class="unit">%</span></div><div class="l">species right</div></div></div>
      <div class="chart" id="scatter"></div><p class="sub">Each dot is one fish: tape on the x axis, agent on the y axis. Dashed line = perfect agreement. Hollow dots were handed to the officer. All fish: mean error ${nf1.format(A.mae)} cm.</p></article>`;
    scatter($('#scatter'), bm.pairs.filter((p) => p.agent_cm != null));
  }

  function scatter(el, pairs) {
    const W = 640, H = 420, L = 40, B = 30, vals = pairs.flatMap((p) => [p.tape_cm, p.agent_cm]);
    const lo = Math.floor(Math.min(...vals) / 5) * 5, hi = Math.ceil(Math.max(...vals) / 5) * 5;
    const x = (v) => L + ((v - lo) / (hi - lo)) * (W - L - 8), y = (v) => H - B - ((v - lo) / (hi - lo)) * (H - B - 8);
    const s = svgEl(W, H, `Agent against tape for ${pairs.length} fish, ${lo} to ${hi} cm`);
    for (let t = lo; t <= hi; t += 5) {
      add(s, 'line', { x1: L, x2: W - 8, y1: y(t), y2: y(t), class: 'grid-line' });
      add(s, 'text', { x: L - 8, y: y(t) + 4, 'text-anchor': 'end', class: 'axis' }, t);
      add(s, 'text', { x: x(t), y: H - 8, 'text-anchor': 'middle', class: 'axis' }, t);
    }
    add(s, 'line', { x1: x(lo), y1: y(lo), x2: x(hi), y2: y(hi), class: 'ideal' });
    for (const p of pairs) add(s, 'circle', { cx: x(p.tape_cm), cy: y(p.agent_cm), r: 5, class: `dot${p.status === 'needs_review' ? ' flagged' : ''}` });
    el.replaceChildren(s);
  }

  init();
})();
