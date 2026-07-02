// ════════════════════════════════════════════════════════════
//  Search — filters, run matching, SSE progress, render/sort/save/freeze,
//  per-row actions, extras picker
// ════════════════════════════════════════════════════════════
// The search tab's core: loads filter dropdowns, runs candidate-vs-job matching
// (streamed via SSE with a one-shot fallback), renders/sorts/freezes the result
// table, and the per-row save/pin/dismiss/extras-picker actions.
import { state, _ACTIONS, app } from "./state.js";
import { esc, gradeClass, storeJob, getStoredJob } from "./util.js";
import api from "./api.js";
import { exportResults, exportResultsXlsx } from "./export.js";

//  Filter chip toggles (single-select per group)
// ════════════════════════════════════════════════════════════
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const group = chip.dataset.group;
    document.querySelectorAll(`.chip[data-group="${group}"]`).forEach(c => c.classList.remove('on'));
    chip.classList.add('on');
  });
});

function getChipVal(group) {
  const el = document.querySelector(`.chip.on[data-group="${group}"]`);
  return el ? el.dataset.val : '';
}

// ════════════════════════════════════════════════════════════
//  Load filter dropdowns from API
// ════════════════════════════════════════════════════════════
// _filterOpts moved to state.filterOpts (state.js).

async function loadFilters() {
  try {
    const data = await api.get('/api/filters');
    const states    = data.data.states     || [];
    const occGroups = data.data.occ_groups || [];
    const portals   = data.data.portals    || [];

    // Cache for AI filter assist
    state.filterOpts = {states, occ_groups: occGroups, portals};

    // Search filters
    populateSelect('filterState',    states,    'All states');
    populateSelect('filterOccGroup', occGroups, 'Occupational group');
    populateSelect('filterPortal',   portals,   'All portals', 'ams');

    // Radar scope filters — separate block so errors above can't kill these
    populateSelect('rfSector',  occGroups, 'All sectors');
    populateSelect('rfStateF',  states,    'All states');
    populateSelect('rfPortalF', portals,   'All portals');

    setDbStatus(true);
  } catch(e) {
    setDbStatus(false, e.message);
  }
}

function populateSelect(id, vals, placeholder, pinnedFirst) {
  const sel = document.getElementById(id);
  if (!sel) return;
  sel.innerHTML = `<option value="">${placeholder}</option>`;
  vals.forEach((v, i) => {
    const o = document.createElement('option');
    o.value = v; o.textContent = v;
    if (pinnedFirst && v === pinnedFirst) o.style.fontWeight = '700';
    sel.appendChild(o);
    // Separator after pinned item
    if (pinnedFirst && v === pinnedFirst && vals[i + 1] && vals[i + 1] !== pinnedFirst) {
      const sep = document.createElement('option');
      sep.disabled = true; sep.textContent = '──────────';
      sel.appendChild(sep);
    }
  });
}

function setDbStatus(ok, msg) {
  document.getElementById('dbDot').className   = 'db-dot' + (ok ? '' : ' error');
  document.getElementById('dbStatus').textContent = ok ? 'Connected' : `DB error: ${msg}`;
}

// Action registry for the run-row/results-filter controls in the search-tab
// markup (candidate.js claimed its own slice of this block already).
Object.assign(_ACTIONS, {
  // run row
  'export-results':          ()      => exportResults(state.lastResults),
  'export-results-xlsx':     ()      => exportResultsXlsx(state.lastResults),
  'save-all':                ()      => saveAll(),
  'clear-results':           ()      => clearResults(),
  'save-candidate':          ()      => saveCandidate(document.getElementById('btnSaveCandidate')),
  // results filter + sortable headers
  'rescore-frozen-results':  ()      => rescoreFrozenResults(),
  'toggle-freeze':           ()      => toggleFreeze(),
  'toggle-show-weak':        ()      => toggleShowWeak(),
  'sort-by':                 (el)    => sortBy(el.dataset.sort),
});


// ════════════════════════════════════════════════════════════
//  Run matching
// ════════════════════════════════════════════════════════════
document.getElementById('btnRun').addEventListener('click', runMatching);
document.getElementById('btnFindMore').addEventListener('click', findMoreJobs);

// ════════════════════════════════════════════════════════════
//  Per-row actions — dismiss (×) and freeze/pin (❄) a single result
// ════════════════════════════════════════════════════════════

// Remove a single job from the results view so the list stays clean. Dismissed
// jobs are remembered, so a later re-run won't bring them back.
function dismissJob(jobId) {
  const id = String(jobId);
  state.dismissedJobIds.add(id);
  state.pinnedJobIds.delete(id);   // a dismissed job can't also be frozen
  const tr = document.getElementById('row-' + jobId);
  if (tr) {
    tr.style.transition = 'opacity .2s, transform .2s';
    tr.style.opacity = '0';
    tr.style.transform = 'translateX(14px)';
  }
  setTimeout(() => {
    state.lastResults = state.lastResults.filter(j => String(j.job_id) !== id);
    renderResults(state.lastResults);
  }, 200);
}

// Weak (C-grade) matches are hidden by default — they match too weakly to be
// useful. This toggle reveals them. Frozen C rows always stay visible.
let _showWeakC = false;
function toggleShowWeak() {
  _showWeakC = document.getElementById('showCChk').checked;
  document.getElementById('showCToggle').classList.toggle('on', _showWeakC);
  if (state.lastResults.length) renderResults(state.lastResults);
}

// Freeze / unfreeze a single result. Frozen rows are pinned to the top and are
// kept (with their current score) when you re-run matching to pull in more jobs.
function togglePinJob(jobId) {
  const id = String(jobId);
  if (state.pinnedJobIds.has(id)) state.pinnedJobIds.delete(id);
  else state.pinnedJobIds.add(id);
  renderResults(state.lastResults);
}

// ════════════════════════════════════════════════════════════
//  Freeze results — keep the job set fixed and only re-score it
// ════════════════════════════════════════════════════════════

function _runLabelFor() {
  if (state.resultsFrozen && state.lastResults.length) return 'Re-score results';
  return 'Run matching';
}

function toggleFreeze() {
  state.resultsFrozen = document.getElementById('freezeChk').checked;
  document.getElementById('freezeToggle').classList.toggle('on', state.resultsFrozen);
  document.getElementById('resultsTbody')?.classList.toggle('all-frozen', state.resultsFrozen);
  document.getElementById('runLabel').textContent = _runLabelFor();
  // When frozen, offer a second action: search for more jobs to add to the locked set.
  const moreBtn = document.getElementById('btnFindMore');
  if (moreBtn) moreBtn.style.display = (state.resultsFrozen && state.lastResults.length) ? '' : 'none';
  const st = document.getElementById('statusText');
  if (st && state.resultsFrozen && state.lastResults.length) {
    st.textContent = `❄ Frozen — ${state.lastResults.length} jobs locked. Re-score them against a changed candidate, or find more jobs to add.`;
  }
  _updateStaleNotice();
}

// Show a warning when a FROZEN result set no longer matches the current candidate
// (e.g. you froze, then edited the CV). The data to detect this already exists:
// `state.scoredAgainstText` is what the scores correspond to. Cheap, prevents acting on
// stale scores. Hidden whenever not frozen, no results, or the text still matches.
function _updateStaleNotice() {
  const el = document.getElementById('staleScoreNotice');
  if (!el) return;
  let cur = '';
  try { cur = (app.buildCandidateText() || '').trim(); } catch (_) {}
  const stale = state.resultsFrozen && state.lastResults.length && cur &&
                cur !== (state.scoredAgainstText || '').trim();
  el.style.display = stale ? 'flex' : 'none';
}

// Re-evaluate staleness whenever the candidate input changes (any field in the input area).
document.addEventListener('input', e => {
  if (e.target.closest && e.target.closest('.input-area')) _updateStaleNotice();
});

function _captureRowRects() {
  const m = {};
  document.querySelectorAll('#resultsTbody tr[id^="row-"]').forEach(tr => {
    m[tr.id] = tr.getBoundingClientRect().top;
  });
  return m;
}

// FLIP slide + score-delta badge after a re-score, so the reshuffle is visible.
function _animateRescore(prevRects, prevScore) {
  document.querySelectorAll('#resultsTbody tr[id^="row-"]').forEach(tr => {
    const oldTop = prevRects[tr.id];
    if (oldTop != null) {
      const dy = oldTop - tr.getBoundingClientRect().top;
      if (Math.abs(dy) > 1) {
        tr.style.transition = 'none';
        tr.style.transform  = `translateY(${dy}px)`;
        requestAnimationFrame(() => {
          tr.style.transition = 'transform .6s cubic-bezier(.22,.61,.36,1)';
          tr.style.transform  = '';
        });
      }
    }
    const jid = tr.id.replace('row-', '');
    const job = state.lastResults.find(j => String(j.job_id) === jid);
    if (!job) return;
    const before = prevScore[job.job_id];
    if (before == null) return;
    const diff = Math.round((job.score - before) * 100);
    if (diff !== 0) {
      tr.classList.add('row-rescored');
      setTimeout(() => tr.classList.remove('row-rescored'), 1700);
      const pct = tr.querySelector('.pct');
      if (pct) {
        const b = document.createElement('span');
        b.className   = 'score-delta ' + (diff > 0 ? 'up' : 'down');
        b.textContent = (diff > 0 ? '▲+' : '▼') + Math.abs(diff);
        pct.insertAdjacentElement('afterend', b);
      }
    }
  });
}

async function rescoreFrozenResults() {
  const btn = document.getElementById('btnRun');
  const text = app.buildCandidateText();
  if (!text) { alert('Please enter a candidate profile.'); return; }
  if (!state.lastResults.length) return;
  // Nothing changed since the current scores — re-scoring identical input just churns
  // (the grader jitters a little each call). Skip it and tell the user.
  if (text.trim() === (state.scoredAgainstText || '').trim()) {
    document.getElementById('resultsStatus').innerHTML =
      '<span style="color:#b45309;font-weight:600">Candidate unchanged — nothing to re-score. Edit the profile, then re-score.</span>';
    return;
  }

  btn.disabled = true;
  document.getElementById('runLabel').textContent = 'Re-scoring…';
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Re-scoring the frozen results against the updated candidate…</span>';

  const prevScore = {};
  state.lastResults.forEach(j => { prevScore[j.job_id] = j.score; });
  const prevRects = _captureRowRects();

  const jobs = state.lastResults.map(j => ({
    job_id: j.job_id, title: j.title, company: j.company, city: j.city, state: j.state,
    skills: j.skills, skills_en: j.skills_en, summary: j.summary,
    description: (j.description || '').slice(0, 400), occ_group: j.occ_group,
  }));

  try {
    const data = await api.post('/api/match/rescore', { candidate_text: text, jobs });
    const map = {};
    (data.jobs || []).forEach(u => { map[u.job_id] = u; });
    state.lastResults.forEach(j => {
      if (state.pinnedJobIds.has(String(j.job_id))) return;   // frozen row keeps its score
      const u = map[j.job_id];
      if (u) {
        j.score = u.score; j.score_pct = u.score_pct; j.grade = u.grade;
        if (u.match_reason) j.match_reason = u.match_reason;
      }
    });
    state.scoredAgainstText = text;           // scores now correspond to this candidate text
    renderResults(state.lastResults);          // re-sorts into the new order
    _animateRescore(prevRects, prevScore);
    _updateStaleNotice();                // scores fresh again — hide the warning
  } catch(e) {
    document.getElementById('resultsStatus').innerHTML =
      `<span>Error re-scoring: ${esc(e.message)}</span>`;
  } finally {
    btn.disabled = false;
    document.getElementById('runLabel').textContent = _runLabelFor();
  }
}

async function runMatching() {
  const btn = document.getElementById('btnRun');
  // Fresh run → reset the manual "Save candidate" button + status indicator.
  const scBtn = document.getElementById('btnSaveCandidate');
  if (scBtn) { scBtn.textContent = '＋ Save candidate'; scBtn.classList.remove('saved', 'dup'); scBtn.disabled = false; }
  const scStatus = document.getElementById('candSaveStatus');
  if (scStatus) scStatus.style.display = 'none';

  // Frozen: don't run a fresh search — re-score the locked job set in place.
  if (state.resultsFrozen && state.lastResults.length) return rescoreFrozenResults();

  // LinkedIn mode: scrape the profile(s) first, then match on the scraped text.
  if (state.activeMode === 'linkedin') {
    btn.disabled = true;
    const ok = await app.ensureLinkedInScraped();
    if (!ok) {
      btn.disabled = false;
      document.getElementById('runLabel').textContent = 'Run matching';
      return;
    }
  }

  const text = app.buildCandidateText();
  if (!text) {
    btn.disabled = false;
    document.getElementById('runLabel').textContent = 'Run matching';
    alert('Please enter a candidate profile.');
    return;
  }
  state.lastMatchText = text;   // remember who we searched with, for per-job fit chat

  const filters  = {};
  const stateF   = document.getElementById('filterState').value;
  const occGroup = document.getElementById('filterOccGroup').value;
  const portal   = document.getElementById('filterPortal').value;
  const city     = document.getElementById('filterCity').value.trim();
  const keyword  = document.getElementById('filterKeyword').value.trim();
  if (stateF)   filters.state     = stateF;
  if (occGroup) filters.occ_group = occGroup;
  if (portal)   filters.portal    = portal;
  if (city)     filters.city      = city;
  if (keyword)  filters.keyword   = keyword;

  const topN = parseInt(document.getElementById('topNSelect').value);

  const tbody = document.getElementById('resultsTbody');
  // Keep any frozen (pinned) rows visible while the new search runs; show the
  // loading spinner beneath them instead of blanking the whole table.
  const pinnedNow = state.lastResults.filter(j => state.pinnedJobIds.has(String(j.job_id)));
  if (pinnedNow.length) {
    renderResults(pinnedNow);
    const loader = document.createElement('tr');
    loader.id = 'matchingLoaderRow';
    loader.innerHTML = `<td colspan="8" class="no-results">
      <div class="spinner" style="margin:0 auto 10px"></div>
      Finding more matches… (frozen results kept above)
    </td>`;
    tbody.appendChild(loader);
  } else {
    tbody.innerHTML = `<tr><td colspan="8" class="no-results">
      <div class="spinner" style="margin:0 auto 10px"></div>
      Running AI matching against live database…
    </td></tr>`;
  }
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Running AI matching — embedding candidate profile and searching vector store…</span>';

  btn.disabled = true;
  document.getElementById('runLabel').textContent = 'Matching…';

  // Apply the final job set: keep individually-frozen (pinned) jobs across the
  // re-run, fresh results fill the rest, drop dismissed, de-dupe against pinned.
  // Shared by the streaming path and the /api/match fallback.
  const applyFinalJobs = (jobs) => {
    const pinned    = state.lastResults.filter(j => state.pinnedJobIds.has(String(j.job_id)));
    const pinnedIds = new Set(pinned.map(j => String(j.job_id)));
    const fresh     = (jobs || []).filter(j =>
      !state.dismissedJobIds.has(String(j.job_id)) && !pinnedIds.has(String(j.job_id)));
    state.lastResults = [...pinned, ...fresh];
    state.scoredAgainstText = text;   // these scores correspond to this candidate text
    renderResults(state.lastResults);
  };

  try {
    let finalJobs = null;
    try {
      finalJobs = await streamMatching(text, filters, topN);
    } catch (streamErr) {
      // Streaming unavailable/failed — fall back to the one-shot endpoint.
      console.warn('Match stream failed, falling back to /api/match:', streamErr);
      const data = await api.post('/api/match', { candidate_text: text, filters, top_n: topN });
      finalJobs = data.jobs || [];
    }
    applyFinalJobs(finalJobs);
    // Auto-save the candidate to the database (unless the user turned it off).
    if (document.getElementById('autosaveCandidate')?.checked) saveCandidate();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:20px">
      <div class="error-box">Error: ${esc(e.message)}</div>
    </td></tr>`;
    document.getElementById('resultsStatus').innerHTML = '<span>Error — check Flask console.</span>';
  } finally {
    btn.disabled = false;
    document.getElementById('runLabel').textContent = 'Run matching';
  }
}

// Persist the current candidate profile to the database (saved_candidates). Drives
// both the auto-save on run-matching and the manual "Save candidate" button. Safely
// no-ops when there's no structured profile / name to save.
async function saveCandidate(btn) {
  const profile = state.currentCandidateProfile;
  const name    = (profile && profile.name) || app.getCandidateName();
  if (!profile || !name || name === 'Unassigned') {
    // Only surface this for an explicit click — the silent auto-save path (no btn)
    // just skips quietly until a profile is parsed.
    if (btn) _setCandSaveStatus('Add a candidate profile first', 'dup');
    return;
  }
  try {
    const data    = await api.post('/api/saved/candidate', { profile: { ...profile, name } });
    const already = data.added === false || data.already_saved;
    _setCandSaveStatus(
      already ? `● ${name} already saved${data.owner ? ' by ' + data.owner : ''}` : '✓ Candidate saved',
      already ? 'dup' : 'ok');
    if (btn) {
      btn.textContent = already ? 'Already saved' : '✓ Candidate saved';
      btn.classList.remove('dup', 'saved');
      btn.classList.add(already ? 'dup' : 'saved');
      btn.disabled = true;
    }
  } catch(e) {
    if (btn) btn.textContent = 'Save failed';
    else console.warn('Auto-save candidate failed:', e);
  }
}

// Green "saved" / red "already saved" indicator next to the Run-matching row.
function _setCandSaveStatus(msg, kind) {
  const el = document.getElementById('candSaveStatus');
  if (!el) return;
  el.textContent = msg;
  el.className   = 'cand-save-status ' + kind;   // kind: 'ok' | 'dup'
  el.style.display = '';
}

// Frozen-set action: search again with WIDER retrieval and append any jobs not
// already shown, keeping the frozen rows. Warns when nothing new turns up.
async function findMoreJobs() {
  const text = state.lastMatchText || app.buildCandidateText();
  if (!text) { alert('Please enter a candidate profile.'); return; }

  const moreBtn = document.getElementById('btnFindMore');
  const runBtn  = document.getElementById('btnRun');
  const prevIds = new Set(state.lastResults.map(j => String(j.job_id)));

  const filters  = {};
  const stateF   = document.getElementById('filterState').value;
  const occGroup = document.getElementById('filterOccGroup').value;
  const portal   = document.getElementById('filterPortal').value;
  const city     = document.getElementById('filterCity').value.trim();
  const keyword  = document.getElementById('filterKeyword').value.trim();
  if (stateF)   filters.state     = stateF;
  if (occGroup) filters.occ_group = occGroup;
  if (portal)   filters.portal    = portal;
  if (city)     filters.city      = city;
  if (keyword)  filters.keyword   = keyword;

  if (moreBtn) moreBtn.disabled = true;
  if (runBtn)  runBtn.disabled  = true;
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Looking for more matching jobs…</span>';

  try {
    let fresh = null;
    try {
      // top_n 0 = no display cap; max_results 50 = widen Stage-1 retrieval to the cap.
      fresh = await streamMatching(text, filters, 0, 50);
    } catch (streamErr) {
      const data = await api.post('/api/match', { candidate_text: text, filters, max_results: 50 });
      fresh = data.jobs || [];
    }
    // We only care about strong matches: add new A/B jobs, ignore C. The warning
    // fires when the wider search surfaced no new A or B job beyond the current set.
    const newAB = (fresh || []).filter(j =>
      (j.grade === 'A' || j.grade === 'B') &&
      !prevIds.has(String(j.job_id)) && !state.dismissedJobIds.has(String(j.job_id)));
    if (newAB.length) {
      state.lastResults = [...state.lastResults, ...newAB];   // frozen rows stay; new ones sort in by score
      renderResults(state.lastResults);
      document.getElementById('resultsStatus').innerHTML =
        `<span style="color:#1648a8;font-weight:600">➕ Added ${newAB.length} new A/B job${newAB.length !== 1 ? 's' : ''} to the frozen set.</span>`;
    } else {
      document.getElementById('resultsStatus').innerHTML =
        '<span style="color:#b45309;font-weight:600">⚠ No new A and B jobs were added — the search found nothing stronger beyond the current set.</span>';
    }
  } catch(e) {
    document.getElementById('resultsStatus').innerHTML =
      `<span>Error finding more: ${esc(e.message)}</span>`;
  } finally {
    if (moreBtn) moreBtn.disabled = false;
    if (runBtn)  runBtn.disabled  = false;
  }
}

// ════════════════════════════════════════════════════════════
//  Streaming match (SSE) + live progress meter
// ════════════════════════════════════════════════════════════
// Consumes /api/match/stream, showing a "Searching…" meter while the server
// retrieves + grades, and resolves with the final ranked job array. Throws if the
// stream can't be read or the server emits an error event — so runMatching() can
// fall back to /api/match.

// Signature kept (cycle, added) for call-site compatibility; only total/done drive
// the copy now that retrieval is a single pass, not a convergence loop.
function renderMatchProgress(cycle, total, added, done) {
  const pct = done ? 100 : 70;
  const label = done
    ? `Found ${total} job${total === 1 ? '' : 's'}`
    : (total > 0 ? `Searching… · ${total} job${total === 1 ? '' : 's'}` : 'Searching…');
  document.getElementById('resultsStatus').innerHTML = `
    <div class="match-progress${done ? ' done' : ''}">
      <div class="match-progress-bar"><div class="match-progress-fill" style="width:${pct}%"></div></div>
      <span class="match-progress-text">${esc(label)}</span>
    </div>`;
}

async function streamMatching(text, filters, topN, maxResults) {
  const res = await api.raw('/api/match/stream', {
    method: 'POST',
    body: { candidate_text: text, filters, top_n: topN,
            ...(maxResults ? { max_results: maxResults } : {}) },
  });
  if (!res.ok || !res.body) throw new Error(`stream HTTP ${res.status}`);

  renderMatchProgress(0, 0, null, false);

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalJobs = null;

  // Parse the SSE byte stream: events are separated by a blank line, payload
  // lives on `data:` lines.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep;
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = rawEvent.split('\n').find(l => l.startsWith('data:'));
      if (!dataLine) continue;
      let ev;
      try { ev = JSON.parse(dataLine.slice(5).trim()); } catch { continue; }

      if (ev.event === 'cycle') {
        renderMatchProgress(ev.cycle, ev.total, ev.added, false);
      } else if (ev.event === 'done') {
        finalJobs = ev.jobs || [];
        renderMatchProgress(ev.cycles, ev.total, null, true);
      } else if (ev.event === 'error') {
        throw new Error(ev.error || 'stream error');
      }
    }
  }

  if (finalJobs === null) throw new Error('stream ended without a result');
  return finalJobs;
}

// ════════════════════════════════════════════════════════════
//  Render results
// ════════════════════════════════════════════════════════════

function renderResults(jobs) {
  const notDismissed = jobs.filter(j => !state.dismissedJobIds.has(String(j.job_id)));
  // Weak (C) matches are hidden unless the toggle is on — but a frozen C row stays.
  const visible = notDismissed.filter(j =>
    _showWeakC || (j.grade || 'C') !== 'C' || state.pinnedJobIds.has(String(j.job_id)));
  const hiddenC = notDismissed.length - visible.length;
  const sorted = [...visible].sort((a, b) => {
    // Pinned ("frozen") results always rank first, so they stick when re-running.
    const ap = state.pinnedJobIds.has(String(a.job_id)) ? 1 : 0;
    const bp = state.pinnedJobIds.has(String(b.job_id)) ? 1 : 0;
    if (ap !== bp) return bp - ap;
    let av, bv;
    if (state.sortCol === 'score') {
      av = a.score; bv = b.score;
    } else if (state.sortCol === 'location') {
      av = [a.city, a.state].filter(Boolean).join(', ').toLowerCase();
      bv = [b.city, b.state].filter(Boolean).join(', ').toLowerCase();
    } else {
      av = (a[state.sortCol] || '').toString().toLowerCase();
      bv = (b[state.sortCol] || '').toString().toLowerCase();
    }
    return state.sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
  });

  const savedIds = new Set(state.savedJobs.map(j => j.job_id));
  const tbody    = document.getElementById('resultsTbody');
  // Whole-set freeze: tint every row blue so it's clear the entire set is locked.
  tbody.classList.toggle('all-frozen', state.resultsFrozen);

  if (!sorted.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="no-results">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      No jobs found — try broadening filters.
    </td></tr>`;
    document.getElementById('resultsStatus').innerHTML = '<span>No results.</span>';
    return;
  }

  tbody.innerHTML = '';
  sorted.forEach((job, i) => {
    const g      = job.grade || 'C';
    const loc    = [job.city, job.state].filter(Boolean).join(', ') || '—';
    const isSaved = savedIds.has(job.job_id);
    const isPinned = state.pinnedJobIds.has(String(job.job_id));
    const sid    = storeJob({ ...job, _batch: 'search' });
    const tr     = document.createElement('tr');
    tr.id = `row-${job.job_id}`;
    if (isPinned) tr.classList.add('row-pinned');
    tr.innerHTML = `
      <td>
        <span class="grade ${gradeClass(g)}">${g}</span><span class="pct">${job.score_pct || ''}</span>
      </td>
      <td style="cursor:pointer" data-action="open-job-modal" data-sid="${sid}" title="Click to see details">
        <div class="job-title-main" style="color:#1a56c4">${esc(job.title)}</div>
        ${job.match_reason ? `<div class="match-reason">${esc(job.match_reason)}</div>` : ''}
      </td>
      <td>${job.company ? `<span class="company-link" data-company="${esc(job.company)}">${esc(job.company)}</span>` : '—'}<span class="job-contacts" id="jc-${job.job_id}"></span></td>
      <td>${esc(loc)}</td>
      <td>${esc(job.salary || '—')}</td>
      <td>${job.portal ? `<span class="tag tag-portal">${esc(job.portal)}</span>` : '—'}</td>
      <td>${job.posted ? `<span class="tag tag-posted">${esc(String(job.posted).substring(0,10))}</span>` : '—'}</td>
      <td style="display:flex;gap:5px;align-items:center">
        <button class="save-btn${isSaved ? ' saved' : ''}" id="save-${job.job_id}"
          data-action="toggle-save" data-job-id="${job.job_id}">${isSaved ? '✓ Saved' : '+ Save'}</button>
        <button class="row-pin${isPinned ? ' on' : ''}" id="pin-${job.job_id}"
          data-action="toggle-pin-job" data-job-id="${job.job_id}"
          title="${isPinned ? 'Frozen — kept when you re-run for more results' : 'Freeze this result — keep it when you re-run for more'}">❄</button>
        <button class="extras-picker-btn visible" id="extras-pick-${job.job_id}"
          data-action="open-extras-picker" data-job-id="${job.job_id}" data-sid="${sid}"
          title="Save with extras">+ extras</button>
        ${job.url ? `<a href="${esc(job.url)}" target="_blank" class="link-btn" title="Open posting">
          <svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
        </a>` : ''}
        <button class="row-x" data-action="dismiss-job" data-job-id="${job.job_id}"
          title="Remove from view">×</button>
      </td>`;
    tr.style.opacity   = '0';
    tr.style.transform = 'translateY(6px)';
    tr.style.transition = 'opacity .25s, transform .25s';
    tbody.appendChild(tr);
    setTimeout(() => { tr.style.opacity = '1'; tr.style.transform = 'none'; }, 30 + i * 25);
  });

  const nA = visible.filter(j => j.grade === 'A').length;
  const nB = visible.filter(j => j.grade === 'B').length;
  const nC = visible.filter(j => j.grade === 'C').length;
  const nPin = visible.filter(j => state.pinnedJobIds.has(String(j.job_id))).length;
  document.getElementById('resultsStatus').innerHTML =
    `<span style="color:#1a7a2e;font-weight:500">✓</span>&nbsp; ${visible.length} matches found — ${nA} strong (A) · ${nB} good (B)` +
    (_showWeakC ? ` · ${nC} weak (C)` : (hiddenC ? ` · <span style="color:#9aa3b2">${hiddenC} weak (C) hidden</span>` : '')) +
    (nPin ? ` · <span style="color:#1648a8;font-weight:600">❄ ${nPin} frozen</span>` : '');

  _loadJobContacts(sorted);
}

// Action registry for the dynamically-built results rows — clickable title
// (open modal), save / pin / extras-picker / dismiss buttons. The button
// handlers keep the original stopPropagation so a row-level click can't fire.
Object.assign(_ACTIONS, {
  'open-job-modal':    (el)    => app.openJobModal(el.dataset.sid),
  'toggle-save':       (el)    => toggleSave(el, el.dataset.jobId),
  'toggle-pin-job':    (el, e) => { e.stopPropagation(); togglePinJob(el.dataset.jobId); },
  'open-extras-picker':(el, e) => { e.stopPropagation(); openExtrasPicker(el.dataset.jobId, el.dataset.sid, el); },
  'dismiss-job':       (el, e) => { e.stopPropagation(); dismissJob(el.dataset.jobId); },
});

// ════════════════════════════════════════════════════════════
//  Per-job contacts (shown in the result row → panel to save them)
// ════════════════════════════════════════════════════════════
let _jobContacts = {};   // job_id (string) → [ {contact_id, name, email, phone, linkedin} ]

// After results render, batch-fetch the contacts for the shown jobs and drop a
// small indicator into each row's company cell (name if one, "N contacts" if more).
async function _loadJobContacts(jobs) {
  const ids = jobs.map(j => j.job_id).filter(Boolean);
  if (!ids.length) return;
  try {
    const data = await api.post('/api/jobs/contacts', { job_ids: ids });
    _jobContacts = (data && data.contacts) || {};
  } catch(e) { return; }
  Object.entries(_jobContacts).forEach(([jid, cts]) => {
    const el = document.getElementById('jc-' + jid);
    if (!el || !cts.length) return;
    const label = cts.length === 1 ? `👤 ${esc(cts[0].name || 'Contact')}` : `👤 ${cts.length} contacts`;
    el.innerHTML = `<span class="job-contact-chip" data-action="open-job-contacts" data-job-id="${esc(jid)}" title="View & save contact${cts.length !== 1 ? 's' : ''}">${label}</span>`;
  });
}

// Open the contacts panel for one job — each contact gets a Save button that
// reuses the save-contact action (→ saved_contacts).
function openJobContacts(jobId) {
  const cts  = _jobContacts[String(jobId)] || [];
  const body = document.getElementById('jcModalBody');
  document.getElementById('jcModalSub').textContent = `${cts.length} contact${cts.length !== 1 ? 's' : ''} for this job`;
  body.innerHTML = cts.length
    ? `<div class="co-contact-list">` + cts.map(ct => {
        const meta = [ct.email, ct.phone].filter(Boolean).join('  ·  ');
        return `<div class="co-contact-row">
          <div class="co-contact-info">
            <div class="co-contact-name">${esc(ct.name || 'Unknown')}</div>
            ${meta ? `<div class="co-contact-meta">${esc(meta)}</div>` : ''}
          </div>
          <button class="co-save-btn co-contact-save" data-action="save-contact"
            data-ctid="${esc(String(ct.contact_id))}" data-ctname="${esc(ct.name || '')}"
            data-ctemail="${esc(ct.email || '')}" data-ctphone="${esc(ct.phone || '')}"
            data-ctlinkedin="${esc(ct.linkedin || '')}">Save</button>
        </div>`;
      }).join('') + `</div>`
    : `<div class="co-no-data" style="padding:20px">No contacts for this job.</div>`;
  document.getElementById('jcModal').classList.remove('hidden');
}

Object.assign(_ACTIONS, {
  'open-job-contacts': (el)    => openJobContacts(el.dataset.jobId),
  'jc-modal-close':    ()      => document.getElementById('jcModal').classList.add('hidden'),
  'jc-modal-backdrop': (el, e) => { if (e.target === el) document.getElementById('jcModal').classList.add('hidden'); },
});

// ════════════════════════════════════════════════════════════
//  Sort
// ════════════════════════════════════════════════════════════
function sortBy(col) {
  if (state.sortCol === col) state.sortAsc = !state.sortAsc;
  else { state.sortCol = col; state.sortAsc = col !== 'score'; }
  if (state.lastResults.length) renderResults(state.lastResults);
}

// ════════════════════════════════════════════════════════════
//  Save / unsave
// ════════════════════════════════════════════════════════════
async function toggleSave(btn, jobId) {
  if (btn.classList.contains('saved')) return;
  const job = state.lastResults.find(j => j.job_id == jobId);
  if (!job) return;
  const jobWithCandidate = { ...job, candidate_name: app.getCandidateName() };
  try {
    const data = await api.post('/api/saved', { job: jobWithCandidate, candidate_profile: state.currentCandidateProfile || null });
    if (data.ok) {
      btn.textContent = '✓ Saved';
      btn.classList.add('saved');
      state.savedJobs = data.jobs;
      updateSavedBadge();
    }
  } catch(e) { alert('Save failed: ' + e.message); }
}

async function saveAll() {
  for (const job of state.lastResults.filter(j => j.grade !== 'C')) {
    const btn = document.getElementById(`save-${job.job_id}`);
    if (btn && !btn.classList.contains('saved')) await toggleSave(btn, job.job_id);
  }
}

function updateSavedBadge() {
  const n  = state.savedJobs.length;
  const nb = document.getElementById('savedBadgeNav');
  if (nb) { nb.style.display = n ? 'inline' : 'none'; nb.textContent = n; }
}

// ════════════════════════════════════════════════════════════
//  Extras picker popup (results table)
// ════════════════════════════════════════════════════════════
let _epJobId = null;   // job_id currently open in picker
let _epSid   = null;   // store key
let _epSel   = {};     // { salary: true, quality: false, … }

const _EP_OPTS = [
  { key: 'salary',    label: 'Salary',       needsCv: false },
  { key: 'quality',   label: 'Quality',      needsCv: false },
  { key: 'strength',  label: 'Strength',     needsCv: true  },
  { key: 'compact',   label: 'Description',  needsCv: false },
  { key: 'questions', label: 'Questions',    needsCv: true  },
  { key: 'outreach',  label: 'Outreach',     needsCv: false },
];

function openExtrasPicker(jobId, sid, anchor) {
  const popup = document.getElementById('extrasPickerPopup');
  // Toggle off if same job
  if (popup.style.display !== 'none' && _epJobId === jobId) {
    closeExtrasPicker(); return;
  }
  _epJobId = jobId; _epSid = sid; _epSel = {};

  const hasCv = !!state.lastParsedText;
  document.getElementById('extrasPickerOptions').innerHTML = _EP_OPTS.map(o => {
    const dis = o.needsCv && !hasCv ? 'disabled title="Upload a CV first"' : '';
    return `<button class="extras-picker-opt" id="epopt-${o.key}" ${dis}
      data-action="toggle-ep-opt" data-key="${o.key}">${o.label}</button>`;
  }).join('');
  document.getElementById('extrasPickerSaveBtn').disabled = true;
  document.getElementById('extrasPickerSaveBtn').textContent = 'Save job + selected extras';

  // Position below the anchor
  popup.style.display = 'block';
  const r  = anchor.getBoundingClientRect();
  const pw = popup.offsetWidth;
  const ph = popup.offsetHeight;
  let top  = r.bottom + 6;
  let left = r.left;
  if (left + pw > window.innerWidth - 8)  left = window.innerWidth - pw - 8;
  if (top  + ph > window.innerHeight - 8) top  = r.top - ph - 6;
  popup.style.top  = top  + 'px';
  popup.style.left = left + 'px';

  setTimeout(() => document.addEventListener('click', _epDismiss, { capture: true }), 0);
}

function _epDismiss(e) {
  const popup  = document.getElementById('extrasPickerPopup');
  const anchor = document.getElementById(`extras-pick-${_epJobId}`);
  if (popup?.contains(e.target) || anchor?.contains(e.target)) return;
  closeExtrasPicker();
}

function closeExtrasPicker() {
  document.getElementById('extrasPickerPopup').style.display = 'none';
  document.removeEventListener('click', _epDismiss, { capture: true });
  _epJobId = null;
}

function toggleEpOpt(key) {
  _epSel[key] = !_epSel[key];
  document.getElementById(`epopt-${key}`)?.classList.toggle('ep-on', !!_epSel[key]);
  document.getElementById('extrasPickerSaveBtn').disabled = !Object.values(_epSel).some(Boolean);
}
_ACTIONS['toggle-ep-opt'] = (el) => toggleEpOpt(el.dataset.key);

async function doSaveWithExtras() {
  const saveBtn = document.getElementById('extrasPickerSaveBtn');
  const job     = getStoredJob(_epSid);
  if (!job) return;

  saveBtn.textContent = 'Fetching…';
  saveBtn.disabled    = true;

  const extras = {};
  await Promise.all([

    _epSel.salary && job.occ_group && api.get(`/api/salary_stats?occ_group=${encodeURIComponent(job.occ_group)}`)
      .then(d => {
        if (!d.count) return;
        const ps  = v => { const n = parseFloat(String(v||'').replace(/[^0-9.]/g,'')); return n > 100 ? n : null; };
        const js  = ps(job.salary);
        const ptb = js ? Math.round((d.salaries.filter(s => s < js).length / d.count) * 100) : null;
        extras.salary = { occ_group: job.occ_group, count: d.count,
          mean: Math.round(d.mean), median: Math.round(d.median),
          job_salary: js, pct_below: ptb, diff_mean: js ? Math.round(js - d.mean) : null };
      }).catch(() => {}),

    _epSel.quality && api.post('/api/quality', { jobs: [job], occ_group: job.occ_group||'', state: job.state||null })
    .then(d => {
      if (!d.jobs?.length) return;
      const q = d.jobs[0];
      extras.quality = { grade: q.quality, score: q.quality_score,
        verdict: q.quality_verdict, fit: q.quality_fit, flags: q.quality_flags };
    }).catch(() => {}),

    _epSel.strength && state.lastParsedText && api.post('/api/candidate_strength', { job: { title: job.title, company: job.company,
        skills: job.skills_en || job.skills,
        description: (job.description || job.description_snippet || '').slice(0,2000) },
        cv_text: state.lastParsedText.slice(0,2000) })
    .then(d => {
      extras.strength = { axes: d.axes, scores: d.scores, reasons: d.reasons, overall: d.overall };
    }).catch(() => {}),

    _epSel.compact && api.post('/api/desc_compact', { description: job.description || job.description_snippet || '', lang: 'en' })
    .then(d => { extras.compact = d.text; }).catch(() => {}),

    _epSel.questions && state.lastParsedText && api.post('/api/desc_cv_questions', { description: job.description || job.description_snippet || '',
        cv_text: state.lastParsedText, lang: 'en' })
    .then(d => { extras.cv_questions = d.text; }).catch(() => {}),

    _epSel.outreach && api.post('/api/desc_outreach', { job: { title: job.title, company: job.company,
        location: [job.city, job.state].filter(Boolean).join(', '),
        salary: job.salary, skills: job.skills_en || job.skills,
        description: (job.description || job.description_snippet || '').slice(0,1500) },
        candidate_name: app.getCandidateName(),
        cv_text: state.lastParsedText ? state.lastParsedText.slice(0,1500) : '', lang: 'en' })
    .then(d => { extras.outreach = d.text; }).catch(() => {}),

  ].filter(Boolean));

  try {
    const data = await api.post('/api/saved', { job: { ...job, candidate_name: app.getCandidateName() }, status: 'New', extras, candidate_profile: state.currentCandidateProfile || null });
    if (data.ok) {
      state.savedJobs = data.jobs;
      updateSavedBadge();
      const sb = document.getElementById(`save-${_epJobId}`);
      if (sb) { sb.textContent = '✓ Saved'; sb.classList.add('saved'); }
      const eb = document.getElementById(`extras-pick-${_epJobId}`);
      if (eb) { eb.textContent = '✓ + extras'; eb.classList.add('saved'); }
      closeExtrasPicker();
    }
  } catch(e) {
    saveBtn.textContent = 'Error — retry';
    saveBtn.disabled = false;
  }
}

function clearResults() {
  state.lastResults = [];
  state.dismissedJobIds = new Set();
  state.pinnedJobIds    = new Set();
  document.getElementById('resultsTbody').innerHTML = `<tr><td colspan="8" class="no-results">
    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/></svg>
    No results yet — run matching to find jobs
  </td></tr>`;
  document.getElementById('resultsStatus').innerHTML =
    '<span>Enter a candidate profile and click Run matching to see results.</span>';
}

async function loadTestData() {
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Loading test fixtures…</span>';
  try {
    const data = await api.get('/api/test/match');
    state.lastResults = data.jobs;
    renderResults(state.lastResults);
  } catch(e) {
    document.getElementById('resultsStatus').innerHTML =
      `<span style="color:#e04040">Test data error: ${esc(e.message)}</span>`;
  }
}


// Cross-module exports — registered on app so candidate/saved/modal/
// assistant/interview can call into this module without a direct import.
Object.assign(app, {
  renderResults, runMatching, saveAll, toggleFreeze, updateSavedBadge,
  doSaveWithExtras, loadFilters,
});
