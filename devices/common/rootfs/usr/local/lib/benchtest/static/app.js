// pedal.benchtest's page. It draws what GET /api/state says and asks for runs; every rule (the
// order, the setup, the lamps, the pass bars) is the service's, so this file decides nothing.
//
// Hooks a browser test can rely on:
//   blocks      g.module#module-<id>[data-component] with data-lamp (pass|fail|none), data-prev
//               (pass|fail|''), data-transition (none|pass-to-fail|fail-to-pass), data-selected
//   test rows   li.test#test-<id>[data-test] with the same lamp attributes and data-status
//   lamps       .lamp with lamp-pass|lamp-fail and lamp-muted (previous) | lamp-bright (current),
//               data-lamp-role (previous|current) and data-state (pass|fail)
//   results     div.result[data-test-result] with data-status; li[data-component][data-check-ok]
//   detail      #detail[data-component]; li.detail-failure[data-test][data-check]
//   run         body[data-run-status][data-run-id]; #setup, #setup-done, #setup-skip
//   fake        #fake-controls, select[data-fake-test], input[data-fake-check], button[data-fake-set]
(() => {
  'use strict';

  const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
  const $ = (id) => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  let state = null;
  let built = false;
  let selected = null;
  let allowLeave = false;
  let pendingLeave = null;
  let timer = null;

  // Logical positions, as on the module map: outside on the left, the audio side, the digital
  // side, outside on the right. Cables are straight and coloured by kind.
  const LAYOUT = {
    interface:    {x: 16, y: 74, w: 150, h: 280},
    guitar_input: {x: 230, y: 80, w: 180, h: 66},
    output_left:  {x: 230, y: 180, w: 180, h: 66},
    output_right: {x: 230, y: 280, w: 180, h: 66},
    codec:        {x: 460, y: 72, w: 150, h: 282},
    codec_wires:  {x: 622, y: 110, w: 170, h: 60, pill: true},
    core:         {x: 800, y: 80, w: 170, h: 120},
    uart_wires:   {x: 800, y: 213, w: 170, h: 58, pill: true},
    pico:         {x: 800, y: 284, w: 170, h: 70},
    mains:        {x: 1086, y: 90, w: 140, h: 66},
    probe:        {x: 1086, y: 286, w: 140, h: 66},
  };
  const CABLES = [
    {k: 'audio', outside: true, d: [[166, 113], [230, 113]]},
    {k: 'audio', outside: true, d: [[166, 213], [230, 213]]},
    {k: 'audio', outside: true, d: [[166, 313], [230, 313]]},
    {k: 'audio', d: [[410, 113], [460, 113]]},
    {k: 'audio', d: [[410, 213], [460, 213]]},
    {k: 'audio', d: [[410, 313], [460, 313]]},
    {k: 'digital', d: [[610, 140], [800, 140]]},
    {k: 'digital', d: [[885, 200], [885, 284]]},
    {k: 'power', outside: true, d: [[1086, 123], [970, 123]]},
    {k: 'service', outside: true, d: [[1086, 319], [970, 319]]},
  ];
  const STATUS_WORDS = {
    queued: 'waiting its turn', waiting_setup: 'waiting for the cables', running: 'running…',
    pass: 'passed', fail: 'failed', not_run: 'not run', skipped: 'skipped', stopped: 'stopped',
  };
  const GROUPS = [
    {id: 'health', title: 'Health — no cables'},
    {id: 'noise', title: 'Noise — the engine muted while it listens'},
    {id: 'further', title: 'Go further', collapsed: true},
  ];

  // ------------------------------------------------------------------------------------ the API

  async function api(method, path, body) {
    const opts = {method, headers: {'Authorization': 'Bearer ' + token, 'X-Benchtest-Client': 'browser'}};
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const response = await fetch(path, opts);
    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (!response.ok) {
      const err = new Error((data && data.error) || ('HTTP ' + response.status));
      err.status = response.status;
      throw err;
    }
    return data;
  }

  function say(text) {
    const m = $('message');
    m.textContent = text || '';
    m.hidden = !text;
  }

  async function poll() {
    clearTimeout(timer);
    let next = 1000;
    try {
      state = await api('GET', '/api/state');
      if (!built) build();
      render();
      if (state.run && ['running', 'waiting_setup'].includes(state.run.status)) next = 400;
      if ($('message').dataset.kind === 'connection') { say(''); delete $('message').dataset.kind; }
    } catch (err) {
      next = 2000;
      $('message').dataset.kind = 'connection';
      say(err.status === 401
        ? 'This page\'s key is not the service\'s: run scripts/benchtest on your computer to open a fresh page.'
        : 'The service on the pedal is not answering. If it has stopped, run scripts/benchtest on your computer to start it again.');
    }
    timer = setTimeout(poll, next);
  }

  // --------------------------------------------------------------------------------- building

  function el(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function html(tag, attrs, parent, text) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) {
      if (k === 'class') e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }

  function build() {
    built = true;
    document.body.dataset.fake = String(!!state.fake);
    $('fake-badge').hidden = !state.fake;
    buildDiagram();
    buildTests();
    if (state.fake) buildFake();
  }

  function buildDiagram() {
    const z = $('zones');
    el('rect', {x: 198, y: 42, width: 432, height: 336, class: 'zoneA'}, z);
    el('rect', {x: 630, y: 42, width: 424, height: 336, class: 'zoneD'}, z);
    el('rect', {x: 196, y: 40, width: 860, height: 340, rx: 14, class: 'caseline'}, z);
    el('text', {x: 200, y: 32, class: 'caselabel'}, z, 'The case');
    el('text', {x: 210, y: 62, class: 'zlabel'}, z, 'AUDIO SIDE');
    el('text', {x: 642, y: 62, class: 'zlabel'}, z, 'DIGITAL SIDE');
    el('text', {x: 16, y: 62, class: 'zlabel'}, z, 'OUTSIDE');
    el('text', {x: 1086, y: 62, class: 'zlabel'}, z, 'OUTSIDE');
    const cables = $('cables');
    for (const c of CABLES) {
      const g = el('g', {class: 'cable k-' + c.k + (c.outside ? ' outside' : '')}, cables);
      const d = 'M' + c.d.map((p) => p.join(' ')).join(' L');
      el('path', {d, class: 'halo'}, g);
      el('path', {d, class: 'line'}, g);
    }
    const modules = $('modules');
    for (const comp of state.components) {
      const p = LAYOUT[comp.id];
      if (!p) continue;
      const g = el('g', {
        class: 'module ' + comp.kind, id: 'module-' + comp.id, 'data-component': comp.id,
        'data-lamp': 'none', 'data-prev': '', 'data-transition': 'none', 'data-selected': 'false',
        tabindex: '0', role: 'button', 'aria-label': comp.name + ': ' + comp.job,
      }, modules);
      el('rect', {x: p.x, y: p.y, width: p.w, height: p.h, rx: p.pill ? 22 : 8, class: 'box'}, g);
      const cx = p.x + p.w / 2;
      const top = p.pill ? p.y + 18 : p.y + 22;
      el('text', {x: cx, y: top, 'text-anchor': 'middle', class: 't'}, g, comp.name);
      el('text', {x: cx, y: top + 14, 'text-anchor': 'middle', class: 's'}, g, comp.line);
      if (comp.id === 'codec') {
        el('text', {x: cx, y: p.y + p.h - 14, 'text-anchor': 'middle', class: 'mini'}, g, 'the audio star');
      }
      el('g', {class: 'lamps', 'data-lamps-for': comp.id}, g);
      g.addEventListener('click', () => clickModule(comp.id));
      g.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); clickModule(comp.id); }
      });
    }
  }

  function buildTests() {
    const holder = $('test-groups');
    for (const group of GROUPS) {
      const tests = state.tests.filter((t) => t.group === group.id);
      if (!tests.length) continue;
      let box;
      if (group.collapsed) {
        box = html('details', {id: 'group-' + group.id, class: 'group'}, holder);
        html('summary', {}, box, group.title);
      } else {
        box = html('section', {id: 'group-' + group.id, class: 'group'}, holder);
        html('h3', {}, box, group.title);
      }
      const list = html('ol', {}, box);
      for (const t of tests) {
        const li = html('li', {class: 'test', id: 'test-' + t.id, 'data-test': t.id, 'data-status': '',
          'data-lamp': 'none', 'data-prev': '', 'data-transition': 'none',
          'data-offered': String(t.offered)}, list);
        const head = html('label', {class: 'test-head'}, li);
        html('span', {class: 'lamps', 'data-lamps-for': t.id}, head);
        const box2 = html('input', {type: 'checkbox', class: 'test-pick', 'data-test': t.id}, head);
        box2.checked = !!t.default;
        html('span', {class: 'test-name'}, head, t.name);
        html('span', {class: 'test-line'}, head, t.line);
        html('span', {class: 'test-status'}, head, '');
        const result = html('div', {class: 'result', 'data-test-result': t.id, 'data-status': ''}, li);
        result.hidden = true;
        html('p', {class: 'result-summary'}, result);
        html('p', {class: 'result-evidence'}, result);
        html('p', {class: 'result-next'}, result);
        html('ul', {class: 'result-checks'}, result);
      }
    }
  }

  function buildFake() {
    $('fake-controls').hidden = false;
    const rows = $('fake-rows');
    for (const t of state.tests) {
      const tr = html('tr', {'data-fake-row': t.id}, rows);
      html('td', {}, tr, t.name);
      const td = html('td', {}, tr);
      const select = html('select', {'data-fake-test': t.id, 'aria-label': 'next outcome of ' + t.name}, td);
      const options = [['pass', 'pass'], ['fail', 'fail'], ['not_run', 'not run']];
      if (t.id === 'noise_input') options.splice(2, 0, ['hum', 'mains hum']);
      for (const [value, label] of options) html('option', {value}, select, label);
      const td2 = html('td', {}, tr);
      const component = html('select', {'data-fake-component': t.id, 'aria-label': 'the block it fails'}, td2);
      html('option', {value: ''}, component, '(its usual block)');
      for (const c of t.components) html('option', {value: c}, component, nameOf(c));
      const td3 = html('td', {}, tr);
      html('input', {type: 'text', 'data-fake-check': t.id, placeholder: 'the check that failed (optional)'}, td3);
      const td4 = html('td', {}, tr);
      const set = html('button', {type: 'button', class: 'quiet', 'data-fake-set': t.id}, td4, 'Set next');
      html('td', {class: 'note', 'data-fake-queue': t.id}, tr, '');
      set.addEventListener('click', () => setFake(t.id));
    }
  }

  async function setFake(testId) {
    const value = document.querySelector('[data-fake-test="' + testId + '"]').value;
    const component = document.querySelector('[data-fake-component="' + testId + '"]').value;
    const checkText = document.querySelector('[data-fake-check="' + testId + '"]').value.trim();
    const outcome = {test: testId};
    if (value === 'hum') outcome.hum = true;
    else if (value === 'not_run') outcome.status = 'not_run';
    else outcome.ok = value === 'pass';
    if (value === 'fail') {
      if (component) outcome.component = component;
      if (checkText) outcome.check = checkText;
    }
    try {
      await api('POST', '/api/fake/next', outcome);
      poll();
    } catch (err) {
      say('The fake outcome was not set: ' + err.message);
    }
  }

  // -------------------------------------------------------------------------------- rendering

  function nameOf(componentId) {
    const c = state && state.components.find((x) => x.id === componentId);
    return c ? c.name : componentId;
  }

  function testOf(testId) {
    return state.tests.find((t) => t.id === testId) || {name: testId};
  }

  function lampKey(l) {
    return (l.previous || '') + '>' + (l.current || '');
  }

  function setLampAttrs(node, l) {
    node.dataset.lamp = l.current || 'none';
    node.dataset.prev = l.previous || '';
    node.dataset.transition = l.previous ? l.previous + '-to-' + l.current : 'none';
  }

  function lampList(l) {
    const out = [];
    if (l.previous) out.push({role: 'previous', state: l.previous, tone: 'muted'});
    if (l.current) out.push({role: 'current', state: l.current, tone: 'bright'});
    return out;
  }

  function drawSvgLamps(g, comp, l) {
    if (g.dataset.key === lampKey(l)) return;
    g.dataset.key = lampKey(l);
    g.textContent = '';
    const p = LAYOUT[comp];
    const lamps = lampList(l);
    lamps.forEach((lamp, i) => {
      const cx = p.x + p.w / 2 + (lamps.length === 2 ? (i === 0 ? -9 : 9) : 0);
      const cy = p.pill ? p.y + 45 : p.y + 52;
      el('circle', {cx, cy, r: 6.5, class: 'lamp lamp-' + lamp.state + ' lamp-' + lamp.tone,
        'data-lamp-role': lamp.role, 'data-state': lamp.state}, g)
        .appendChild(el('title', {}, null, (lamp.role === 'previous' ? 'the run before: ' : 'the latest run: ') +
          (lamp.state === 'pass' ? 'passed' : 'failed')));
    });
  }

  function drawHtmlLamps(span, l) {
    if (span.dataset.key === lampKey(l)) return;
    span.dataset.key = lampKey(l);
    span.textContent = '';
    for (const lamp of lampList(l)) {
      html('span', {class: 'lamp lamp-' + lamp.state + ' lamp-' + lamp.tone, 'data-lamp-role': lamp.role,
        'data-state': lamp.state, title: (lamp.role === 'previous' ? 'the run before: ' : 'the latest run: ') +
          (lamp.state === 'pass' ? 'passed' : 'failed')}, span);
    }
  }

  function render() {
    const run = state.run;
    const running = !!run && ['running', 'waiting_setup'].includes(run.status);
    document.body.dataset.runStatus = run ? run.status : 'idle';
    document.body.dataset.runId = run ? run.id : '';

    const h = state.helper;
    $('helper-status').textContent = !h.needed ? '' : (h.present
      ? 'scripts/benchtest is running on your computer'
      : 'scripts/benchtest is not running on your computer: the noise tests and the probe need it');

    const inRun = new Set(running ? run.tests.map((t) => t.test) : []);
    for (const comp of state.components) {
      const g = $('module-' + comp.id);
      if (!g) continue;
      const l = state.lamps.components[comp.id];
      setLampAttrs(g, l);
      drawSvgLamps(g.querySelector('[data-lamps-for]'), comp.id, l);
      g.classList.toggle('sel', selected === comp.id);
      g.dataset.selected = String(selected === comp.id);
      g.classList.toggle('in-run', running && comp.tests.some((t) => inRun.has(t)));
    }

    const slots = {};
    if (run) for (const slot of run.tests) slots[slot.test] = slot;
    for (const t of state.tests) {
      const li = $('test-' + t.id);
      li.dataset.offered = String(t.offered);
      const l = state.lamps.tests[t.id];
      setLampAttrs(li, l);
      drawHtmlLamps(li.querySelector('.lamps'), l);
      const slot = slots[t.id];
      li.dataset.status = slot ? slot.status : '';
      li.classList.toggle('in-run', running && !!slot);
      li.querySelector('.test-status').textContent = slot ? (STATUS_WORDS[slot.status] || slot.status) : '';
      const pick = li.querySelector('.test-pick');
      pick.disabled = running || !t.offered;
      if (!t.offered) pick.checked = false;
      renderResult(li.querySelector('.result'), slot && slot.result ? slot.result : null,
        slot && slot.result ? 'run' : 'history', state.results[t.id]);
    }

    $('test-button').disabled = running;
    $('forget-button').disabled = running;
    $('cancel-button').hidden = !running;
    $('run-status').textContent = runWords(run);

    const setup = $('setup');
    if (run && run.status === 'waiting_setup' && run.waiting) {
      setup.hidden = false;
      $('setup-title').textContent = 'Before “' + run.waiting.name + '”:';
      const steps = $('setup-steps');
      const key = run.id + ':' + run.waiting.test;
      if (steps.dataset.key !== key) {
        steps.dataset.key = key;
        steps.textContent = '';
        for (const s of run.waiting.steps) html('p', {}, steps, s);
      }
      setup.dataset.test = run.waiting.test;
    } else {
      setup.hidden = true;
      setup.dataset.test = '';
    }

    renderDetail();
    if (state.fake && state.fake_bench) {
      for (const t of state.tests) {
        const cell = document.querySelector('[data-fake-queue="' + t.id + '"]');
        const queue = state.fake_bench.queues[t.id] || [];
        cell.textContent = queue.length ? 'next: ' + queue.map(outcomeWords).join(', then ') : 'next: pass';
      }
    }
  }

  function outcomeWords(o) {
    if (o.status === 'not_run') return 'not run';
    if (o.hum) return 'mains hum';
    return o.ok ? 'pass' : ('fail' + (o.component ? ' on ' + nameOf(o.component) : '') + (o.check ? ' (' + o.check + ')' : ''));
  }

  function runWords(run) {
    if (!run) return '';
    const done = run.tests.filter((t) => ['pass', 'fail', 'not_run', 'skipped', 'stopped'].includes(t.status)).length;
    const what = run.origin && run.origin.kind === 'component'
      ? 'the benchtests that exercise ' + nameOf(run.origin.component) : run.tests.length + ' benchtest(s)';
    if (run.status === 'running') return 'Running ' + what + ': ' + done + ' of ' + run.tests.length + ' done.';
    if (run.status === 'waiting_setup') return 'Waiting for the cables.';
    const failed = run.tests.filter((t) => t.status === 'fail').length;
    return (run.status === 'stopped' ? 'Stopped. ' : 'Done. ') +
      (failed ? failed + ' of ' + run.tests.length + ' failed.' : 'Nothing failed.');
  }

  function renderResult(box, fromRun, source, fromHistory) {
    const result = fromRun || fromHistory || null;
    if (!result) { box.hidden = true; box.dataset.status = ''; return; }
    const key = (result.run || '') + ':' + result.test + ':' + result.status + ':' + (result.at || '') + ':' + source;
    box.hidden = false;
    box.dataset.status = result.status;
    box.dataset.source = fromRun ? 'run' : 'history';
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    const summary = box.querySelector('.result-summary');
    summary.textContent = '';
    if (!fromRun) html('span', {class: 'label'}, summary, 'Last time: ');
    summary.appendChild(document.createTextNode(result.summary || ''));
    const evidence = box.querySelector('.result-evidence');
    evidence.textContent = result.evidence ? 'Evidence: ' + result.evidence : '';
    evidence.hidden = !result.evidence;
    const next = box.querySelector('.result-next');
    next.textContent = '';
    next.hidden = !result.next;
    if (result.next) {
      html('b', {}, next, 'Next: ');
      next.appendChild(document.createTextNode(result.next));
    }
    const checks = box.querySelector('.result-checks');
    checks.textContent = '';
    for (const c of result.checks || []) {
      const li = html('li', {'data-component': c.component, 'data-check-ok': String(!!c.ok),
        'data-check': c.check || ''}, checks);
      html('b', {}, li, nameOf(c.component) + (c.ok ? ' passed: ' : ' failed: '));
      html('span', {class: 'why'}, li, c.said || c.check || '');
    }
  }

  function renderDetail() {
    const box = $('detail');
    box.dataset.component = selected || '';
    const key = selected ? selected + ':' + JSON.stringify(state.lamps.components[selected]) + ':' +
      JSON.stringify(state.failures[selected] || []) + ':' + JSON.stringify(state.run && state.run.id) : '';
    if (box.dataset.key === key) return;
    box.dataset.key = key;
    box.textContent = '';
    if (!selected) {
      html('p', {class: 'note'}, box, 'Click a block to see its job and run the benchtests that exercise it.');
      return;
    }
    const comp = state.components.find((c) => c.id === selected);
    html('h2', {}, box, comp.name);
    html('p', {class: 'detail-job'}, box, comp.job + '.');
    const runs = new Set(comp.runs);
    if (comp.tests.length) {
      const p = html('p', {}, box, 'Benchtests that exercise it:');
      const ul = html('ul', {id: 'detail-tests'}, box);
      for (const t of comp.tests) {
        const li = html('li', {'data-test': t, 'data-runs-on-click': String(runs.has(t))}, ul, testOf(t).name);
        if (!runs.has(t)) li.appendChild(document.createTextNode(' (only when you tick it)'));
      }
      p.hidden = false;
    }
    const lamp = state.lamps.components[selected];
    const failures = state.failures[selected] || [];
    if (lamp.current === 'fail' && failures.length) {
      html('p', {}, box, 'Failed in the last run that exercised it:');
      const ul = html('ul', {id: 'detail-failures'}, box);
      for (const f of failures) {
        const li = html('li', {class: 'detail-failure', 'data-test': f.test, 'data-check': f.check || ''}, ul);
        html('b', {}, li, testOf(f.test).name + ' failed. ');
        html('span', {class: 'why'}, li, 'The check: ' + (f.check || '?') + '. ' + (f.said || ''));
      }
    } else if (lamp.current === 'pass') {
      html('p', {class: 'detail-pass'}, box, 'Passed in the last run that exercised it.');
    } else {
      html('p', {class: 'note'}, box, 'Not tested yet.');
    }
  }

  // ---------------------------------------------------------------------------------- actions

  async function startRun(body) {
    try {
      const reply = await api('POST', '/api/run', body);
      if (reply && reply.run) state.run = reply.run;
      say('');
      poll();
    } catch (err) {
      say(err.status === 409 ? 'A run is already going: wait for it to finish.' : 'Not started: ' + err.message);
    }
  }

  function clickModule(id) {
    selected = id;
    if (state) render();
    const run = state && state.run;
    if (run && ['running', 'waiting_setup'].includes(run.status)) {
      say('A run is going. Click the block again when it has finished to test it.');
      return;
    }
    startRun({component: id});
  }

  $('test-button').addEventListener('click', () => {
    const picked = [...document.querySelectorAll('.test-pick')].filter((b) => b.checked && !b.disabled)
      .map((b) => b.dataset.test);
    if (!picked.length) { say('Tick at least one benchtest first.'); return; }
    startRun({tests: picked});
  });

  $('cancel-button').addEventListener('click', async () => {
    try { await api('POST', '/api/run/cancel', {}); poll(); } catch (err) { say(err.message); }
  });

  $('forget-button').addEventListener('click', async () => {
    try { await api('POST', '/api/history/forget', {}); say('Previous results forgotten.'); poll(); }
    catch (err) { say('Not forgotten: ' + err.message); }
  });

  async function decide(skip) {
    if (!state || !state.run) return;
    try { await api('POST', '/api/run/continue', {run: state.run.id, skip}); poll(); }
    catch (err) { say(err.message); }
  }
  $('setup-done').addEventListener('click', () => decide(false));
  $('setup-skip').addEventListener('click', () => decide(true));

  // ------------------------------------------------------------------------- stop, and leaving

  function stopService() {
    // fetch with keepalive carries the header and outlives the page; sendBeacon cannot set a
    // header, so it carries the token as ?token=, which /api/shutdown alone accepts.
    const beacon = () => navigator.sendBeacon('/api/shutdown?token=' + encodeURIComponent(token));
    try {
      fetch('/api/shutdown', {method: 'POST', keepalive: true,
        headers: {'Authorization': 'Bearer ' + token, 'X-Benchtest-Client': 'browser'}}).catch(beacon);
    } catch (e) {
      beacon();
    }
  }

  $('stop-button').addEventListener('click', () => {
    allowLeave = true;
    location.assign('/stopped#token=' + encodeURIComponent(token));
  });

  window.addEventListener('beforeunload', (e) => {
    if (allowLeave) return;
    e.preventDefault();
    e.returnValue = '';
  });

  const dialog = $('leave-dialog');
  function askLeave(go) {
    pendingLeave = go;
    if (!dialog.open) dialog.showModal();
  }
  function leave(stop) {
    const go = pendingLeave;
    pendingLeave = null;
    dialog.close();
    if (stop) stopService();
    allowLeave = true;
    if (go) go();
  }
  $('leave-stay').addEventListener('click', () => {
    pendingLeave = null;
    dialog.close();
    history.pushState({benchtest: 'guard'}, '', location.href);
  });
  $('leave-go').addEventListener('click', () => leave(false));
  $('leave-stop').addEventListener('click', () => leave(true));
  dialog.addEventListener('cancel', (e) => { e.preventDefault(); $('leave-stay').click(); });

  // The back button is a navigation the page can see: one guard entry in the history turns it
  // into a popstate, and the page asks its own question instead of the browser's generic one.
  history.replaceState({benchtest: 'base'}, '', location.href);
  history.pushState({benchtest: 'guard'}, '', location.href);
  window.addEventListener('popstate', () => {
    if (allowLeave) return;
    askLeave(() => {
      history.back();
      // A tab opened by scripts/benchtest has nothing to go back to: leaving is then a blank page.
      setTimeout(() => { if (document.visibilityState === 'visible') location.replace('about:blank'); }, 400);
    });
  });
  document.addEventListener('click', (e) => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a || allowLeave || a.target === '_blank' || a.getAttribute('href').startsWith('#')) return;
    e.preventDefault();
    askLeave(() => location.assign(a.href));
  });

  if (!token) {
    say('This page needs the key in its address. Open it with scripts/benchtest on your computer.');
    return;
  }
  poll();
})();
