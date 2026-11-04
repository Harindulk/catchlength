// CatchLength console: runs the agent live when the server is there, otherwise replays recorded runs
// (samples/<id>/run.json), and shows the benchmark against the tape.
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const nf1 = new Intl.NumberFormat('en', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cm = (v) => (v == null ? '<span class="muted">–</span>' : `${nf1.format(v)}<span class="unit">cm</span>`);
  const cap = (t) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : '');
  const NS = 'http://www.w3.org/2000/svg';
  const COMMON = { 'Katsuwonus pelamis': 'Skipjack', 'Euthynnus affinis': 'Kawakawa', 'Rastrelliger kanagurta': 'Indian mackerel', 'Auxis thazard': 'Frigate tuna', 'Auxis rochei': 'Bullet tuna', unknown: 'Unknown' };
  const STAGES = [['inspect_clip', 'Plan'], ['calibrate', 'Calibrate'], ['segment', 'Segment'], ['find_missed', 'Check count'],
    ['rescue', 'Rescue'], ['measure', 'Measure'], ['classify', 'Species'], ['apply_rules', 'Rules'], ['submit_report', 'File']];
  const NAME = Object.fromEntries(STAGES.concat([['request_review', 'Hand to officer'], ['sign_off', 'Officer sign-off']]));
  const RULE_SHORT = { no_minimum: 'No minimum found', pass: 'Above minimum', below_minimum: 'Below minimum', no_rule_in_pack: 'No rule in pack' };
  const CHECK = '<svg class="tick" viewBox="0 0 16 16" aria-label="passed" role="img"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  let samples = [], run = null, dir = '', selected = null, timer = null;
  const decisions = {};
  // Officer screen in the port's languages. si/ta are draft wording: needs a native speaker's check before field use.
  const T = {
    en: { ok: 'Sign off report', back: 'Send back', note: 'Note for the agent (optional)',
      filed: (a, f) => `<b>Report filed.</b> ${a} fish accepted${f ? `, ${f} need your look first` : ''}. Sign off, or send it back with a note.` },
    si: { ok: 'වාර්තාව අනුමත කරන්න', back: 'ආපසු යවන්න', note: 'නියෝජිතයාට සටහනක් (අවශ්‍ය නම්)',
      filed: (a, f) => `<b>වාර්තාව ගොනු කරන ලදී.</b> මාළු ${a}ක් පිළිගන්නා ලදී${f ? `, මාළු ${f}ක් ඔබ මුලින් පරීක්ෂා කළ යුතුය` : ''}. අනුමත කරන්න, නැතහොත් සටහනක් සමඟ ආපසු යවන්න.` },
    ta: { ok: 'அறிக்கையை அங்கீகரி', back: 'திருப்பி அனுப்பு', note: 'முகவருக்குக் குறிப்பு (விருப்பத்தேர்வு)',
      filed: (a, f) => `<b>அறிக்கை தாக்கல் செய்யப்பட்டது.</b> ${a} மீன்கள் ஏற்கப்பட்டன${f ? `, ${f} மீன்களை முதலில் நீங்கள் பார்க்க வேண்டும்` : ''}. அங்கீகரிக்கவும், அல்லது குறிப்புடன் திருப்பி அனுப்பவும்.` },
  };
  const LOCAL = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const RUN_LABEL = LOCAL ? 'Run the agent' : 'Replay recorded run';
  let lang = 'en';  // officer decisions per run folder: { approve, note, at, saved }

  // ---- views ------------------------------------------------------------------------------------------------
  // a run replayed from the response cache cost nothing this time; say that instead of a bare $0.000
  const spend = (r, usd) => (r.cost && r.cost.calls && r.cost.cached === r.cost.calls ? `${r.cost.calls} model calls, replayed` : `$${usd.toFixed(3)}`);

  function show(view) {
    for (const v of ['run', 'benchmark', 'about']) $(`#view-${v}`).hidden = v !== view;
    document.querySelectorAll('.rail a[data-view]').forEach((a) => {
      if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    if (view === 'benchmark') benchmark();
  }
  window.addEventListener('hashchange', () => show(location.hash.slice(1) || 'run'));

  const getJson = async (url) => { const r = await fetch(url, { cache: 'no-cache' }); if (!r.ok) throw new Error(`${r.status} ${url}`); return r.json(); };

  // a file that did not load: say which, and offer to try again, instead of leaving the cards blank
  function fail(msg, retry) {
    const n = $('#notice');
    n.hidden = false;
    n.innerHTML = `${esc(msg)} <button type="button" class="secondary">Retry</button>`;
    n.querySelector('button').addEventListener('click', retry);
  }

  async function init() {
    $('#samples').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) load(+b.dataset.i); });
    $('#run-btn').textContent = RUN_LABEL;
    $('#run-btn').addEventListener('click', live);
    $('#signoff').addEventListener('submit', (e) => { e.preventDefault(); decide(true); });
    $('#sendback-btn').addEventListener('click', () => decide(false));
    $('#signoff-lang').addEventListener('change', (e) => { lang = e.target.value; signoff(true); });
    show(location.hash.slice(1) || 'run');
    await loadIndex();
  }

  async function loadIndex() {
    try { samples = await getJson('samples/index.json'); }
    catch { return fail('The sample list (samples/index.json) did not load.', loadIndex); }
    const seg = $('#samples');
    seg.hidden = samples.length < 2;
    seg.innerHTML = samples.map((s, i) => `<button type="button" role="radio" aria-checked="${i === 0}" data-i="${i}">${esc(s.label)}</button>`).join('');
    await load(0);
  }

  async function load(i) {
    clearTimeout(timer);
    if (document.body.classList.contains('running')) { busy(false); $('#run-btn').textContent = RUN_LABEL; }  // a replay cut short by a tab switch must not leave the button stuck
    $('#notice').hidden = true;
    const d = `samples/${samples[i].id}/`;
    try { run = await getJson(d + 'run.json'); }
    catch { return fail(`The sample "${samples[i].label}" did not load (${d}run.json).`, () => load(i)); }
    dir = d;
    document.querySelectorAll('#samples button').forEach((b) => b.setAttribute('aria-checked', String(+b.dataset.i === i)));
    selected = null;
    $('#sample-line').innerHTML = run.simulated
      ? `<span class="pill warn">Simulated</span> Museum reference fish at known lengths, scripted model stand-ins. Not a field result.`
      : run.synthetic
        ? `<span class="pill warn">Synthetic scene</span> ${esc(run.synthetic.tests)} Real Muse Spark 1.3 + SAM 3.1; museum fish at known lengths.`
        : `<span class="pill n">Field clip</span> ${esc(run.source)}`;
    $('#frame-img').src = dir + 'frame.jpg';
    $('#frame-img').alt = `Best frame of ${run.source}: fish on a dark sheet next to printed marker tiles`;
    const [w, h] = run.size;
    $('#overlay').setAttribute('viewBox', `0 0 ${w} ${h}`);
    $('#frame-sub').textContent = `frame ${run.best_frame} · ${run.tiles.length} marker ${run.tiles.length === 1 ? 'tile' : 'tiles'}`;
    render(run.log.length);
  }

  // ---- a live run on the server, streamed turn by turn; falls back to the recording -----------------------------
  async function live() {
    if (!run) return;  // nothing loaded yet: the notice above says why
    const id = samples[+(document.querySelector('#samples [aria-checked="true"]')?.dataset.i ?? 0)].id;
    let res;
    const recorded = () => { note(run.simulated ? 'Replaying the scripted stand-in run (no model calls).' : 'Replaying this run as it was recorded on Muse Spark 1.3 and SAM 3.1. Live runs need the local server (see the README).'); return replay(); };
    try { res = await fetch('api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sample: id }) }); }
    catch { return recorded(); }
    if (!res.ok || !(res.headers.get('content-type') || '').includes('event-stream')) return recorded();
    busy(true, 'Running live…');
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
        if (ev === 'turn') { turns.push(data); timeline(turns, true); stages(turns, false); verdict(null, `Live · turn ${turns.length}`); }
        if (ev === 'error') fail = data.message;
        if (ev === 'done') doneDir = data.dir;
      }
    }
    busy(false);
    if (fail || !doneDir) { note(`Live run unavailable: ${fail || 'no result came back.'} Showing the recorded run instead.`); return replay(); }
    try { run = await getJson(doneDir + 'run.json'); }
    catch { note('The live run finished but its result did not load. Showing the recorded run instead.'); return replay(); }
    dir = doneDir;
    $('#frame-img').src = dir + 'frame.jpg?' + Date.now();
    render(run.log.length);
  }

  // ---- replay: the recorded log arrives turn by turn ------------------------------------------------------------
  function replay() {
    clearTimeout(timer);
    busy(true, 'Replaying…');
    let k = 0;
    render(0);
    const tick = () => {
      k += 1;
      render(k, true);
      if (k < run.log.length) timer = setTimeout(tick, 650);
      else busy(false);
    };
    timer = setTimeout(tick, 300);
  }

  function busy(on, label) {
    const btn = $('#run-btn');
    btn.disabled = on;
    btn.textContent = on ? label : (LOCAL ? 'Run again' : 'Replay again');
    document.body.classList.toggle('running', on);
  }

  function note(text) { const n = $('#notice'); n.hidden = !text; n.textContent = text || ''; }

  // ---- render ---------------------------------------------------------------------------------------------------
  function render(upto, animate = false) {
    const log = run.log.slice(0, upto);
    const done = upto >= run.log.length;
    const seen = new Set(log.map((l) => l.tool));
    const visible = run.fish.filter((f) => (seen.has('segment') && +f.id < 1000) || (seen.has('rescue') && +f.id >= 1000));
    timeline(log, animate);
    stages(log, done);
    overlay(visible, seen.has('measure'));
    const calRefused = [...log].reverse().find((l) => l.tool === 'calibrate')?.result?.refused;
    ledger(seen.has('measure') ? visible : [], calRefused ? 'No lengths filed: calibration refused.' : seen.has('segment') ? 'Measuring…' : 'Each fish appears here once it has been measured.');
    verdict(done ? run : null, upto ? `Turn ${upto} of ${run.log.length}` : 'Ready');
    const usd = done ? run.cost?.usd ?? 0 : log[log.length - 1]?.usd ?? 0;  // the spend so far, as the run builds it
    $('#tl-sub').textContent = `${upto} of ${run.log.length} turns · ${spend(run, usd)}`;
    checks(log);
    lf(done ? run.report?.lf_1cm || {} : null);
    receipt(done ? run.receipt : null);
    cited(done ? run : null);
    signoff(done);
  }

  function signoff(done) {
    const box = $('#signoff'), d = decisions[dir];
    const waiting = done && run.status === 'awaiting_signoff';
    box.hidden = !waiting && !d;
    $('#run-btn').className = waiting && !d ? 'secondary' : 'primary';  // once filed, signing off is the main job
    if (box.hidden) return;
    box.classList.toggle('done', !!d && d.approve);
    box.classList.toggle('back', !!d && !d.approve);
    box.querySelector('.signoff-actions').hidden = !!d;
    const f = run.receipt.fish;
    $('#signoff-text').innerHTML = d
      ? `${d.approve ? '<b>Signed off</b>' : '<b>Sent back to the agent</b>'} at ${esc(d.at)}${d.note ? `: “${esc(d.note)}”` : ''}${d.saved ? '' : ' <span class="muted">(recorded run: not saved)</span>'}`
      : T[lang].filed(f.accepted, f.flagged);
    $('#signoff-text').lang = d ? 'en' : lang;
    $('#signoff-btn').textContent = T[lang].ok;
    $('#sendback-btn').textContent = T[lang].back;
    $('#signoff-note').placeholder = T[lang].note;
    $('#signoff-lang-note').hidden = lang === 'en';
  }

  async function decide(approve) {
    const note = $('#signoff-note').value.trim();
    const at = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    let saved = false;
    if (dir.startsWith('live/')) {
      try {
        const r = await fetch('api/signoff', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sample: dir.split('/')[1], approve, note }) });
        saved = r.ok;
      } catch { /* shown as not saved */ }
    }
    decisions[dir] = { approve, note, at, saved };
    render(run.log.length);
  }

  function verdict(r, progress) {
    const el = $('#verdict');
    const fig = (v, l, cls = '') => `<div class="${cls}"><dd>${v}</dd><dt>${esc(l)}</dt></div>`;
    if (!r || !r.receipt) {
      el.innerHTML = fig('<span class="muted">–</span>', 'fish found') + fig('<span class="muted">–</span>', 'accepted')
        + fig('<span class="muted">–</span>', 'to the officer') + fig(`<span class="muted small">${esc(progress)}</span>`, 'status', 'status');
      return;
    }
    const f = r.receipt.fish, d = decisions[dir];
    const status = d ? (d.approve ? 'Signed off' : 'Sent back') : { awaiting_signoff: 'Waiting for sign-off', needs_review: 'With the officer', needs_refilm: 'Clip refused',
      signed_off: 'Signed off', sent_back: 'Sent back', running: 'Unfinished' }[r.status] || r.status;
    el.innerHTML = fig(f.detected, 'fish found') + fig(`${f.accepted}<span class="of"> of ${f.detected}</span>`, 'accepted')
      + fig(f.flagged, 'to the officer', f.flagged ? 'warn' : '') + fig(`<span class="small">${esc(status)}</span>`, `${r.log.length} turns · ${spend(r, r.cost.usd)}`, 'status');
  }

  // The checks the tools ran, read from the log and the fish: limit, result, and whether it fired.
  function checks(log) {
    const R = (t) => [...log].reverse().find((l) => l.tool === t)?.result;
    const rows = [];
    const cal = R('calibrate');
    if (cal) rows.push(cal.refused ? ['no', 'Marker tiles', 'flat, corners within 1.5 px', 'none found: refused to measure']
      : ['ok', 'Marker tiles', 'corners within 1.5 px', `${cal.tiles.length} tiles, ${nf2.format(cal.corner_error_px)} px`]);
    const seg = R('segment');
    if (seg) rows.push(seg.found === seg.expected ? ['ok', 'Fish count', 'SAM matches the plan', `${seg.found} of ${seg.expected}`]
      : ['warn', 'Fish count', 'SAM matches the plan', `SAM ${seg.found}, plan ${seg.expected}${R('find_missed') ? `; Spark recounted ${R('find_missed').count}` : ''}`]);
    const resc = R('rescue');
    if (resc) rows.push(['warn', 'Rescue', 'box + negative point to SAM', `kept ${resc.accepted.length}, rejected ${resc.rejected.length}`]);
    if (R('measure')) {
      const fish = run.fish.filter((f) => f.snap_mm), worst = fish.reduce((a, f) => Math.max(a, ...Object.values(f.snap_mm)), 0);
      const over = fish.filter((f) => Math.max(...Object.values(f.snap_mm)) > 10).map((f) => f.id);
      if (fish.length) rows.push([over.length ? 'warn' : 'ok', 'Spark points on SAM outline', 'within 10 mm', over.length ? `fish ${over.join(', ')} off by ${nf1.format(worst)} mm: to officer` : `all ${fish.length}, worst ${nf1.format(worst)} mm`]);
      const tl = run.fish.filter((f) => /total length/.test(f.why || '')).map((f) => f.id);
      rows.push([tl.length ? 'warn' : 'ok', 'Outline vs species length', 'within 3% (frigate, bullet)', tl.length ? `fish ${tl.join(', ')}: to officer` : 'all within']);
      const multi = Object.keys(R('measure').cross_frame?.frames || {}).length;
      rows.push(multi ? ['ok', 'Same fish, other frames', 'drift under 1 cm', `${multi} more frames`] : ['todo', 'Same fish, other frames', 'drift under 1 cm', 'single still: not run']);
    }
    const sp = R('classify');
    if (sp) { const u = Object.values(sp.species).filter((s) => s === 'unknown').length; rows.push([u ? 'warn' : 'ok', 'Species', 'closed list, else unknown', u ? `${u} unknown` : 'all named; officer confirms']); }
    const bad = log.filter((l) => l.tool === 'submit_report' && l.result?.refused);
    if (bad.length) rows.push(['warn', 'Report check', 'counts explained, citations real', `refused ${bad.length}×, then fixed${/rules that don't exist/.test(bad[0].result.feedback) ? ' (a made-up citation)' : ''}`]);
    const q = run.reviews?.length ?? 0;
    if (log.some((l) => l.tool === 'submit_report' && l.result?.filed)) rows.push([q ? 'warn' : 'ok', 'Officer queue', 'anything unproven', q ? `${q} item${q > 1 ? 's' : ''} for the officer` : 'nothing queued']);
    const icon = { ok: CHECK, warn: '!', no: '×', todo: '–' };
    $('#checks').innerHTML = rows.length ? rows.map(([s, n, lim, res]) => `<li class="ck ${s}"><span class="ic" aria-label="${{ ok: 'passed', warn: 'fired', no: 'refused', todo: 'not run' }[s]}">${icon[s]}</span><span class="n">${esc(n)}<span class="lim">${esc(lim)}</span></span><span class="r">${esc(res)}</span></li>`).join('')
      : '<li class="ck idle"><span class="n muted">Checks appear as the agent runs.</span></li>';
  }

  function stageState(log, tool) {
    const hits = log.filter((l) => l.tool === tool);
    if (!hits.length) return 'todo';
    const r = hits[hits.length - 1].result || {};
    if (r.escalated) return 'esc';
    if (r.refused) return 'no';
    if ((tool === 'segment' && r.found !== r.expected) || (tool === 'measure' && r.flagged?.length)) return 'warn';
    return 'ok';
  }

  function stages(log, done) {
    const last = log[log.length - 1]?.tool;
    $('#stages').innerHTML = STAGES.map(([t, name]) => {
      const st = stageState(log, t);
      const cur = !done && t === last ? ' current' : '';
      const label = { todo: 'not reached', ok: 'passed', warn: 'needs a look', no: 'refused', esc: 'escalated' }[st];
      return `<li class="st ${st}${cur}"><span class="mark" aria-hidden="true"></span><span class="nm">${name}</span><span class="vh">${label}</span></li>`;
    }).join('');
  }

  function say(tool, r) {
    if (!r) return '';
    if (r.refused) return `<b>Refused.</b> ${esc(r.feedback)}${r.escalated ? ` <b>${esc(r.escalated)}</b>` : ''}`;
    switch (tool) {
      case 'inspect_clip': return `${r.usable === false ? '<b>Spark called it unusable</b>, so the officer will see why; the checks decide.' : 'Usable.'} Expects <b>${r.expected_count}</b> fish; best frame ${r.best_frame}${r.issues?.length ? `; ${esc(r.issues.join('; '))}` : ''}.`;
      case 'calibrate': return `${r.tiles.length} marker tiles; corner error <b>${r.corner_error_px} px</b> of 1.5 allowed.`;
      case 'segment': return `SAM 3.1 found <b>${r.found}</b>, the plan expected ${r.expected}.`;
      case 'find_missed': return `Spark counts ${r.count}: ${r.missed_boxes.length} without an outline${r.merged_ids.length ? `; outline ${esc(r.merged_ids.join(', '))} wraps two fish` : ''}.`;
      case 'rescue': return `Boxes and negative points back to SAM: kept ${r.accepted.map(esc).join(', ') || 'none'}${r.rejected.length ? `, rejected ${r.rejected.length}` : ''}. Now <b>${r.count_now}</b> fish.`;
      case 'measure': return `<b>${r.measured}</b> measured two ways, ${r.flagged.length} flagged. ${r.cross_frame ? esc(cap(r.cross_frame.note)) + '.' : ''}`;
      case 'classify': { const c = {}; Object.values(r.species).forEach((s) => (c[s] = (c[s] || 0) + 1)); return Object.entries(c).map(([s, n]) => `${n} × <i>${esc(s)}</i>`).join(', ') + '.'; }
      case 'apply_rules': return 'Each fish checked against the cited rule pack.';
      case 'request_review': return `Queued for the officer (${r.queued}).`;
      case 'submit_report': return `Filed <b>${r.measured}</b> fish; waiting for ${esc(r.waiting_for)}.`;
      default: return '';
    }
  }

  function timeline(log, animate) {
    $('#timeline').innerHTML = log.map((l, i) => {
      const r = l.result || {};
      const tag = r.escalated ? '<span class="pill warn">escalated</span>' : r.refused ? '<span class="pill no">refused</span>'
        : l.tool === 'measure' && r.flagged?.length ? `<span class="pill warn">${r.flagged.length} flagged</span>`
        : l.tool === 'segment' && r.found !== r.expected ? '<span class="pill warn">count off</span>' : CHECK;
      const last = i === log.length - 1;
      return `<li class="${animate && last ? 'arrive' : ''}${last && document.body.classList.contains('running') ? ' now' : ''}">
        <span class="tool">${esc(NAME[l.tool] || l.tool)}</span><span class="tag">${tag}</span>
        <span class="say">${say(l.tool, r)}</span>${l.ms != null ? `<span class="ms">${l.ms} ms</span>` : ''}</li>`;
    }).join('') || '<li class="idle"><span class="say">Press Run to watch the agent work through the clip.</span></li>';
    const tl = $('#timeline'); tl.scrollTop = animate ? tl.scrollHeight : 0;
  }

  function overlay(fish, measured) {
    const svg = $('#overlay');
    svg.innerHTML = '';
    const fs = Math.round(run.size[0] / 42);  // label size follows the frame, so it reads at any resolution
    for (const f of fish) {
      const flagged = measured && f.status === 'needs_review';
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', `fishg${selected === f.id ? ' on' : ''}${selected && selected !== f.id ? ' dim' : ''}`);
      const p = document.createElementNS(NS, 'polygon');
      p.setAttribute('points', f.outline.map((q) => q.join(',')).join(' '));
      p.setAttribute('class', `fish${flagged ? ' flagged' : ''}`);
      g.appendChild(p);
      if (measured && f.points) {  // the measurement itself: snout to fork, on every fish
        const [a, b] = [f.points.snout, f.points.fork];
        const line = document.createElementNS(NS, 'line');
        Object.entries({ x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: 'fl' }).forEach(([k, v]) => line.setAttribute(k, v));
        g.appendChild(line);
        for (const q of [a, b]) { const c = document.createElementNS(NS, 'circle'); c.setAttribute('cx', q[0]); c.setAttribute('cy', q[1]); c.setAttribute('r', fs / 4); c.setAttribute('class', 'pt'); g.appendChild(c); }
      }
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', f.box[0]); t.setAttribute('y', Math.max(fs, f.box[1] - fs / 3)); t.setAttribute('class', 'lbl'); t.setAttribute('font-size', fs); t.textContent = f.id;
      g.appendChild(t);
      g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button'); g.setAttribute('data-id', f.id);
      g.setAttribute('aria-label', `Fish ${f.id}${measured ? `, ${f.status === 'measured' ? 'accepted' : 'to the officer'}` : ''}`);
      g.setAttribute('aria-pressed', String(selected === f.id));
      g.addEventListener('click', () => pick(f.id));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(f.id, '.fishg'); } });
      svg.appendChild(g);
    }
    const s = run.fish.find((f) => f.id === selected);
    $('#frame-cap').innerHTML = s && measured
      ? `<b>Fish ${esc(s.id)}</b> · fork length ${cm(s.fork_cm)} · outline ${cm(s.axis_cm)}${snapText(s) ? ` · ${snapText(s)}` : ''} · ${esc(s.species || 'species pending')} · ${s.status === 'measured' ? 'accepted' : esc(s.why || 'with the officer')}`
      : measured ? '<span class="muted">Dashed lines run from snout tip to tail fork. Pick a fish for its numbers.</span>' : '';
  }

  // how far Spark's two points sat from SAM's outline, against the run's own limit
  function snapText(f) {
    if (!f.snap_mm || f.snap_mm.fork == null) return '';
    return `Spark's snout point ${nf1.format(f.snap_mm.snout)} mm and fork point ${nf1.format(f.snap_mm.fork)} mm from SAM's outline (limit ${run.receipt?.thresholds?.snap_mm ?? 10} mm)`;
  }

  function ledger(fish, emptyMsg) {
    const body = $('#ledger tbody');
    $('#fish-sub').textContent = fish.length ? `${fish.length} fish · fork length is snout tip to tail fork, measured on the sheet's plane` : '';
    if (!fish.length) { body.innerHTML = `<tr class="idle"><td colspan="7" class="empty">${esc(emptyMsg)}</td></tr>`; return; }
    body.innerHTML = fish.map((f) => {
      const fr = Object.values(f.frames_mm || {});
      const spread = fr.length && f.axis_cm != null ? (Math.max(...fr, f.axis_cm * 10) - Math.min(...fr, f.axis_cm * 10)) / 10 : null;
      const rule = (f.rules || []).find((x) => x.result !== 'info');
      const st = f.status === 'measured' ? '<span class="pill ok">accepted</span>' : f.status === 'needs_review' ? '<span class="pill warn">to officer</span>' : '<span class="pill n">found</span>';
      return `<tr data-id="${esc(f.id)}" class="${selected === f.id ? 'on' : ''}" tabindex="0" aria-selected="${selected === f.id}">
        <td class="id">${esc(f.id)}</td><td>${f.species ? (COMMON[f.species] ? `${COMMON[f.species]} <i class="lat">${esc(f.species)}</i>` : `<i>${esc(f.species)}</i>`) : '<span class="muted">–</span>'}</td>
        <td class="num strong">${cm(f.fork_cm)}</td><td class="num">${cm(f.axis_cm)}</td>
        <td class="num">${spread == null ? '<span class="muted">–</span>' : `±${nf1.format(spread / 2)}<span class="unit">cm</span>`}</td>
        <td>${st}${f.why ? `<span class="why">${esc(f.why)}</span>` : ''}${selected === f.id && snapText(f) ? `<span class="why detail">${snapText(f)}</span>` : ''}</td>
        <td class="rule">${rule ? `${esc(RULE_SHORT[rule.result] || rule.result)}` : '<span class="muted">–</span>'}</td></tr>`;
    }).join('');
    body.querySelectorAll('tr[data-id]').forEach((tr) => {
      tr.addEventListener('click', () => pick(tr.dataset.id));
      tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(tr.dataset.id, 'tr'); } });
    });
  }

  function cited(r) {
    const el = $('#cited');
    const rules = r?.rules_cited ? Object.values(r.rules_cited) : [];
    if (!rules.length) { el.innerHTML = ''; return; }
    el.innerHTML = `<h3>Rules cited</h3><ul>${rules.map((x) => `<li><sup>${esc(x.id)}</sup>
      <span class="q">“${esc(x.quote)}”</span> <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source_title)}</a>
      ${x.status === 'reported' ? '<span class="muted">· from a secondary source, not yet checked against the gazette text</span>' : ''}</li>`).join('')}</ul>`;
  }

  function pick(id, refocus) {
    selected = selected === id ? null : id;
    render(run.log.length);
    if (refocus) document.querySelector(`${refocus}[data-id="${CSS.escape(id)}"]`)?.focus();  // the render rebuilt the row or outline the keyboard was on
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
    if (!bins) { el.innerHTML = '<p class="empty">Appears when the report is filed.</p>'; return; }
    if (!Object.keys(bins).length) { el.innerHTML = '<p class="empty">No accepted fish, so nothing to bin.</p>'; return; }
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
      ['Clip SHA-256', rc.clip_sha256 ? rc.clip_sha256.slice(0, 16) + '…' : (run.synthetic ? '– (synthetic scene, a still image, no clip file)' : '– (simulated, no clip file)')],
      ['Finished', rc.finished_utc.replace('T', ' ').replace('+00:00', ' UTC')],
      ['Models', rc.models.join(', ')],
      ['Calibration', rc.calibration.tiles.length ? `${rc.calibration.tiles.length} tiles, corner error ${nf2.format(rc.calibration.corner_error_px)} px` : 'refused: no marker tile found, no lengths filed'],
      ['Fish', `${rc.fish.detected} found, ${rc.fish.accepted} accepted, ${rc.fish.flagged} flagged`],
      ['Rescued by SAM', rc.rescued.length ? rc.rescued.join(', ') : 'none'],
      ['Frames checked', rc.frames.checked.length ? [rc.frames.best, ...rc.frames.checked].join(', ') : `frame ${rc.frames.best} only (a single still, so no cross-frame check)`],
      ['Cost', run.cost && run.cost.calls && run.cost.cached === run.cost.calls ? `$${rc.cost_usd.toFixed(3)} (all ${run.cost.calls} model calls replayed from the cache of the recorded run)` : `$${rc.cost_usd.toFixed(3)}`],
      ['Code', rc.freeze_tag ? (rc.frozen ? `${rc.freeze_tag}: code and thresholds match the freeze` : `${rc.describe} (code or thresholds changed since ${rc.freeze_tag})`) : rc.git_commit || 'uncommitted'],
      ['CSV SHA-256', rc.csv_sha256.slice(0, 16) + '…'],
    ];
    el.innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')
      + (run.seller ? `<dt>Seller's copy</dt><dd><a href="receipt.html?s=${encodeURIComponent(dir.split('/')[1])}">Size receipt to share</a> <span class="muted">(length and estimated weight)</span></dd>` : '');
  }

  // ---- benchmark ------------------------------------------------------------------------------------------------
  async function benchmark() {
    const body = $('#bm-body');
    const get = async (f) => { try { const r = await fetch(f, { cache: 'no-cache' }); return r.ok ? r.json() : null; } catch { return null; } };
    const bm = await get('benchmark.json');
    const plan = `<article class="card"><header class="card-h"><h2>What the tape benchmark measures</h2><span class="sub">pass marks set before the shoot</span></header>
        <dl class="kv"><dt>Bias first</dt><dd>The bar is NARA's own photo-board method: 0.05 cm from the measuring board on 22 frigate tuna whose lengths spread only about 1.3 cm (IOTC-2025-WPM16-10rev1). The headline is the uncorrected mean difference and the 95% limits of agreement on every fish. A second mark is the bias on the 10 held-out fish (tags 4, 8 … 40) after a correction fitted only on the other fish: under 0.5 cm either way.</dd>
        <dt>Length</dt><dd>Mean error as a share of fish length, the share within 1 cm, and limits of agreement, accepted fish shown apart from all fish. 2.0 cm on 40 or more fish is the floor below which we stop, not a mark of accuracy: on a 27 cm tuna it is 7%.</dd>
        <dt>Count</dt><dd>The agent's count equals the fish on the sheet in 90% of clean clips.</dd>
        <dt>Species</dt><dd>Right 90% of the time, from a closed list of five coastal species, "unknown" allowed.</dd>
        <dt>Worst fish</dt><dd>The fish with the largest errors are listed by name, with what the agent did about them.</dd></dl></article>`;
    if (!bm) {
      const g = await get('geometry_budget.json');
      $('#bm-finding').innerHTML = 'No tape benchmark yet. <span class="muted">Fish are tape-measured on Wed 4 Nov; the agent never sees those numbers.</span>';
      const pc = await get('public_check.json');
      body.innerHTML = (g ? `<article class="card"><header class="card-h"><h2>What the camera and tiles add on their own</h2><span class="pill n">Simulated</span></header>
        <div class="kpis">
          <div class="kpi"><div class="v">${nf2.format(g.mae_cm)}<span class="unit">cm</span></div><div class="l">mean error</div></div>
          <div class="kpi"><div class="v">${nf2.format(g.p90_cm)}<span class="unit">cm</span></div><div class="l">90th percentile</div></div>
          <div class="kpi"><div class="v">${nf2.format(g.worst_cm)}<span class="unit">cm</span></div><div class="l">worst fish</div></div>
          <div class="kpi"><div class="v">${g.n_fish}</div><div class="l">fish in ${g.n_scenes} scenes</div></div></div>
        <p class="sub">Museum reference fish pasted at known lengths, blurred, noised and compressed like a 1080p phone frame from about 1 m, then measured through the marker tiles with each fish's true outline. This is the floor the geometry sets; it says nothing yet about SAM 3.1's outlines or Muse Spark's points. Bias ${nf2.format(g.bias_cm)} cm.</p></article>` : '') + (pc ? `<article class="card"><header class="card-h"><h2>Stress test on public footage</h2><span class="pill n">Real fish, no tiles</span></header>
        <div class="kpis">
          <div class="kpi"><div class="v">${pc.frames.filter((f) => f.lengths === 0).length}<span class="unit">of ${pc.frames.length}</span></div><div class="l">frames refused: no tiles, no lengths filed</div></div>
          <div class="kpi"><div class="v">${pc.frames.reduce((n, f) => n + f.by_eye, 0)}</div><div class="l">real fish in view, all outlined by SAM 3.1</div></div>
          <div class="kpi"><div class="v">${pc.frames.reduce((n, f) => n + Math.max(0, f.sam - f.by_eye), 0)}</div><div class="l">printed fish pictures SAM also outlined</div></div></div>
        <p class="sub">Four frames of a Spanish mackerel and a black sea bass on a measuring board, from FWC's "How to Measure a Fish" (<a href="https://youtu.be/2Va-ANxdQhM" rel="noopener">CC BY</a>). It tests behaviour, not length: no tiles for scale, no tape reading. Spark called the sea bass "unknown" but the spotted mackerel a kawakawa at 0.85-0.88, a look-alike outside its five species, which is why species stays officer-confirmed. Cost $${pc.cost_usd.toFixed(2)}.</p></article>` : '') + plan;
      return;
    }
    const L = bm.length_accepted_only, A = bm.length, P = bm.pass_marks;
    const mark = (ok, label) => `<span class="pill ${ok ? 'ok' : 'no'}">${label} ${ok ? 'met' : 'missed'}</span>`;
    const H = bm.held_out.held_out_corrected, NB = bm.nara_bar, sgn = (v) => (v > 0 ? '+' : '') + nf2.format(v);
    const worst = bm.pairs.filter((p) => p.agent_cm != null).sort((a, b) => Math.abs(b.agent_cm - b.tape_cm) - Math.abs(a.agent_cm - a.tape_cm)).slice(0, 3);
    const tl = await get('benchmark_tl.json');
    $('#bm-finding').innerHTML = `<b>Mean difference from the tape ${sgn(L.bias)} cm</b>, 95% of fish between ${sgn(L.loa95[0])} and ${sgn(L.loa95[1])} cm · n = ${L.n} accepted fish, ${bm.flagged} to the officer · <span class="muted">uncorrected, every fish counted</span>`;
    body.innerHTML = `<article class="card"><div class="marks">${H.n >= 5 ? mark(NB.met, 'Held-out bias under 0.5 cm') : `<span class="pill n">Held-out set: ${H.n} fish, too few to judge</span>`} ${!P.length && L.mae != null && L.mae <= 2 ? `<span class="pill n">Stop floor needs 40 fish (mean error ${nf1.format(L.mae)} cm is under 2)</span>` : mark(P.length, 'Stop floor (2 cm, 40 fish)')} ${mark(P.count, 'Count')}</div><div class="kpis">
      <div class="kpi"><div class="v">${sgn(L.bias)}<span class="unit">cm</span></div><div class="l">mean difference, fork length</div></div>
      <div class="kpi"><div class="v">${sgn(L.loa95[0])} to ${sgn(L.loa95[1])}<span class="unit">cm</span></div><div class="l">95% limits of agreement</div></div>
      <div class="kpi"><div class="v">${nf1.format(L.mae_pct)}<span class="unit">%</span></div><div class="l">mean error as share of length</div></div>
      <div class="kpi"><div class="v">${Math.round(L.within_1cm * 100)}<span class="unit">%</span></div><div class="l">within 1 cm of the tape</div></div>
      <div class="kpi"><div class="v">${bm.count.exact_rate == null ? '–' : Math.round(bm.count.exact_rate * 100)}<span class="unit">%</span></div><div class="l">clips counted exactly</div></div>
</div>${tl && tl.n ? `<p class="sub"><b>Total length</b> (what NARA measures): the outline against the taped total length, ${tl.n} fish, mean difference ${sgn(tl.mean_diff_cm)} cm, 95% between ${sgn(tl.loa95[0])} and ${sgn(tl.loa95[1])} cm, ${Math.round(tl.within_1cm * 100)}% within 1 cm.</p>` : ''}<p class="sub">A small pilot: store-bought fish, one session, not a port trial. NARA validated its photo method with the same comparison on 22 fish (IOTC-2025-WPM16-10rev1). Species is not scored here: it stays an officer-confirmed field.</p>
      <div class="chart" id="scatter"></div><p class="sub">Each dot is one fish: tape on the x axis, agent on the y axis. Dashed line = perfect agreement. Hollow dots were handed to the officer. Accepted fish: mean error ${nf1.format(L.mae)} cm, bias ${nf1.format(L.bias)} cm before correction, 95% of errors between ${nf1.format(L.loa95[0])} and ${nf1.format(L.loa95[1])} cm. All fish: mean error ${nf1.format(A.mae)} cm.</p></article>
      <div class="grid two">
      <article class="card"><header class="card-h"><h2>Largest errors</h2><span class="sub">shown, never dropped</span></header>
        <div class="table-wrap"><table class="ledger"><thead><tr><th scope="col">Fish</th><th scope="col" class="num">Tape</th><th scope="col" class="num">Agent</th><th scope="col" class="num">Error</th><th scope="col">Agent's call</th></tr></thead><tbody>
        ${worst.map((p) => `<tr><td>${esc(p.key)}</td><td class="num">${cm(p.tape_cm)}</td><td class="num">${cm(p.agent_cm)}</td><td class="num">${cm(p.agent_cm - p.tape_cm)}</td><td>${p.status === 'needs_review' ? '<span class="pill warn">handed to officer</span>' : '<span class="pill n">accepted</span>'}</td></tr>`).join('')}
        </tbody></table></div></article>
      <article class="card"><header class="card-h"><h2>Counts per clip</h2><span class="sub">${bm.unmatched.length} fish without a tag</span></header>
        <div class="table-wrap"><table class="ledger"><thead><tr><th scope="col">Clip</th><th scope="col" class="num">Agent</th><th scope="col" class="num">Tape sheet</th><th scope="col">Exact</th></tr></thead><tbody>
        ${bm.count.clips.map((c) => `<tr><td>${esc(c.clip)}</td><td class="num">${c.detected}</td><td class="num">${c.on_tape ?? '–'}</td><td>${c.on_tape == null ? '<span class="muted">–</span>' : c.exact ? '<span class="pill ok">yes</span>' : '<span class="pill no">no</span>'}</td></tr>`).join('')}
        </tbody></table></div></article></div>` + plan;
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
