// ════════════════════════════════════════════════════════════
//  Search — filters, run matching, SSE progress, render/sort/save,
//  per-row actions, extras picker
// ════════════════════════════════════════════════════════════
// The search tab's core: loads filter dropdowns, runs candidate-vs-job matching
// (streamed via SSE with a one-shot fallback), renders/sorts the result table,
// and the per-row save/dismiss/extras-picker actions.
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
    const states     = data.data.states     || [];
    const occGroups  = data.data.occ_groups || [];
    const portals    = data.data.portals    || [];
    const workTimes  = data.data.work_time             || [];
    const empRels    = data.data.employment_relationship || [];
    const educations = data.data.education             || [];
    const nace       = data.data.nace                  || [];

    // Cache for AI filter assist
    state.filterOpts = {states, occ_groups: occGroups, portals};
    _naceRows = nace;

    // Search filters
    populateSelect('filterState',    states,    'All states');
    populateSelect('filterOccGroup', occGroups, 'Occupational group');
    populateSelect('filterPortal',   portals,   'All portals', 'ams');
    populateSelect('filterWorkTime',               workTimes,  'Work time (any)');
    populateSelect('filterEmploymentRelationship', empRels,    'Employment type (any)');
    populateSelect('filterEducation',              educations, 'Education (any)');
    _populateNace1();

    // Radar scope filters — separate block so errors above can't kill these
    populateSelect('rfSector',  occGroups, 'All sectors');
    populateSelect('rfStateF',  states,    'All states');
    populateSelect('rfPortalF', portals,   'All portals');

    setDbStatus(true);
  } catch(e) {
    setDbStatus(false, e.message);
  }
}

// ════════════════════════════════════════════════════════════
//  NACE cascading dropdowns (Company Criteria) — mirrors
//  services.search.utils.nace_levels() so both sides agree on how a raw
//  code splits into 3 levels (AT: dot-separated, SK: plain digit string).
// ════════════════════════════════════════════════════════════
let _naceRows = [];   // [[code, text], ...] from /api/filters

function naceLevels(code) {
  if (!code) return [null, null, null];
  code = String(code).trim();
  if (code.includes('.')) {
    const parts = code.split('.');
    return [parts[0] || null, parts.length >= 2 ? parts.slice(0, 2).join('.') : null,
            parts.length >= 3 ? code : null];
  }
  return [code.slice(0, 2) || null, code.length >= 3 ? code.slice(0, 3) : null,
          code.length >= 5 ? code : null];
}

function _populateNace1() {
  const sel = document.getElementById('filterNace1');
  if (!sel) return;
  const seen = new Map();
  _naceRows.forEach(([code, text]) => {
    const [lvl1] = naceLevels(code);
    if (lvl1 && !seen.has(lvl1)) seen.set(lvl1, text);
  });
  sel.innerHTML = '<option value="">Any</option>' +
    [...seen.keys()].sort().map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
}

function _lockNaceField(wrapId, selId, placeholder) {
  document.getElementById(wrapId)?.classList.add('locked');
  const sel = document.getElementById(selId);
  if (sel) { sel.disabled = true; sel.innerHTML = `<option value="">${placeholder}</option>`; }
}

function onNace1Change() {
  const v = document.getElementById('filterNace1').value;
  const wrap2 = document.getElementById('filterNace2Wrap');
  const sel2  = document.getElementById('filterNace2');
  _lockNaceField('filterNace3Wrap', 'filterNace3', 'Select NACE 2 first');
  if (!v) { _lockNaceField('filterNace2Wrap', 'filterNace2', 'Select NACE 1 first'); return; }
  const seen = new Map();
  _naceRows.forEach(([code, text]) => {
    const [lvl1, lvl2] = naceLevels(code);
    if (lvl1 === v && lvl2 && !seen.has(lvl2)) seen.set(lvl2, text);
  });
  wrap2.classList.remove('locked');
  sel2.disabled = false;
  sel2.innerHTML = '<option value="">Any</option>' +
    [...seen.keys()].sort().map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
}

function onNace2Change() {
  const v1 = document.getElementById('filterNace1').value;
  const v2 = document.getElementById('filterNace2').value;
  const wrap3 = document.getElementById('filterNace3Wrap');
  const sel3  = document.getElementById('filterNace3');
  if (!v2) { _lockNaceField('filterNace3Wrap', 'filterNace3', 'Select NACE 2 first'); return; }
  const seen = new Map();
  _naceRows.forEach(([code, text]) => {
    const [lvl1, lvl2, lvl3] = naceLevels(code);
    if (lvl1 === v1 && lvl2 === v2 && lvl3 && !seen.has(lvl3)) seen.set(lvl3, text);
  });
  wrap3.classList.remove('locked');
  sel3.disabled = false;
  sel3.innerHTML = '<option value="">Any</option>' +
    [...seen.keys()].sort().map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('');
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

// Read the filter-bar controls into a { key: value } object (only non-empty ones),
// shared by runMatching() and runFiltersOnlyStep() so a new filter is one place to add.
function _readFilterInputs() {
  const filters = {};
  const state_    = document.getElementById('filterState').value;
  const occGroup  = document.getElementById('filterOccGroup').value;
  const portal    = document.getElementById('filterPortal').value;
  const city      = document.getElementById('filterCity').value.trim();
  const keyword   = document.getElementById('filterKeyword').value.trim();
  const workTime  = document.getElementById('filterWorkTime').value;
  const empRel    = document.getElementById('filterEmploymentRelationship').value;
  const education = document.getElementById('filterEducation').value;
  if (state_)    filters.state                    = state_;
  if (occGroup)  filters.occ_group                = occGroup;
  if (portal)    filters.portal                   = portal;
  if (city)      filters.city                     = city;
  if (keyword)   filters.keyword                  = keyword;
  if (workTime)  filters.work_time                = workTime;
  if (empRel)    filters.employment_relationship  = empRel;
  if (education) filters.education                = education;

  // Job Status
  const onlineSince   = document.getElementById('filterOnlineSince').value;
  const status        = document.getElementById('filterStatus').value;
  const availableFrom = document.getElementById('filterAvailableFrom').value.trim();
  const scrapingDate  = document.getElementById('filterScrapingDate').value;
  if (onlineSince)   filters.online_since   = onlineSince;
  if (status)        filters.status         = status;
  if (availableFrom) filters.available_from = availableFrom;
  if (scrapingDate)  filters.scraping_date  = scrapingDate;

  // Region
  const postcode = document.getElementById('filterPostcode').value.trim();
  if (postcode) filters.postcode = postcode;

  // Job Criteria
  const jobDescription = document.getElementById('filterJobDescription').value.trim();
  const skills          = document.getElementById('filterSkills').value.trim();
  const salaryRange     = document.getElementById('filterSalary').value;
  if (jobDescription) filters.job_description = jobDescription;
  if (skills)          filters.skills          = skills;
  if (salaryRange) {
    const [lo, hi] = salaryRange.split('-');
    if (lo) filters.salary_min = lo;
    if (hi) filters.salary_max = hi;
  }

  // Company Criteria
  const company = document.getElementById('filterCompany').value.trim();
  const nace1 = document.getElementById('filterNace1').value;
  const nace2 = document.getElementById('filterNace2').value;
  const nace3 = document.getElementById('filterNace3').value;
  const excludeStaffing = document.getElementById('filterExcludeStaffing').checked;
  if (company)         filters.company          = company;
  if (nace1)           filters.nace1            = nace1;
  if (nace2)           filters.nace2            = nace2;
  if (nace3)           filters.nace3            = nace3;
  if (excludeStaffing) filters.exclude_staffing = true;

  return filters;
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
  // Company Criteria — cascading NACE dropdowns
  'nace1-change':            ()      => onNace1Change(),
  'nace2-change':            ()      => onNace2Change(),
  'clear-results':           ()      => clearResults(),
  'run-filters-only-step':   ()      => runFiltersOnlyStep(),
  'save-candidate':          ()      => saveCandidate(document.getElementById('btnSaveCandidate')),
  // results filter + sortable headers
  'toggle-top20':            ()      => toggleTop20(),
  'sort-by':                 (el)    => sortBy(el.dataset.sort),
});


// ════════════════════════════════════════════════════════════
//  Run matching
// ════════════════════════════════════════════════════════════
document.getElementById('btnRun').addEventListener('click', runMatching);

// ════════════════════════════════════════════════════════════
//  Per-row actions — dismiss (×) a single result
// ════════════════════════════════════════════════════════════

// Remove a single job from the results view so the list stays clean. Dismissed
// jobs are remembered, so a later re-run won't bring them back.
function dismissJob(jobId) {
  const id = String(jobId);
  state.dismissedJobIds.add(id);
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

function toggleTop20() {
  state.top20Only = document.getElementById('top20Chk').checked;
  document.getElementById('top20Chk').closest('label').classList.toggle('on', state.top20Only);
  if (state.lastResults.length) renderResults(state.lastResults);
}

async function runMatching() {
  const btn = document.getElementById('btnRun');
  state.resultsMode = 'ai';
  // Fresh run → reset the manual "Save candidate" button + status indicator.
  const scBtn = document.getElementById('btnSaveCandidate');
  if (scBtn) { scBtn.textContent = '＋ Save candidate'; scBtn.classList.remove('saved', 'dup'); scBtn.disabled = false; }
  const scStatus = document.getElementById('candSaveStatus');
  if (scStatus) scStatus.style.display = 'none';

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

  const filters = _readFilterInputs();

  const topN = parseInt(document.getElementById('topNSelect').value);

  const tbody = document.getElementById('resultsTbody');
  tbody.innerHTML = `<tr><td colspan="8" class="no-results">
    <div class="spinner" style="margin:0 auto 10px"></div>
    Running AI matching against live database…
  </td></tr>`;
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Running AI matching — embedding candidate profile and searching vector store…</span>';

  btn.disabled = true;
  document.getElementById('runLabel').textContent = 'Matching…';

  // Apply the final job set: drop dismissed jobs. Shared by the streaming path
  // and the /api/match fallback.
  const applyFinalJobs = (jobs) => {
    state.lastResults = (jobs || []).filter(j => !state.dismissedJobIds.has(String(j.job_id)));
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

// Step 3 "Job Search with Filters" — a standalone browse by filter criteria only,
// no candidate profile required. Separate pipeline from runMatching(): no vector
// embedding, no grading, so results carry no score/grade (renderResults() and the
// status line both branch on state.resultsMode to render that correctly).
async function runFiltersOnlyStep() {
  state.resultsMode = 'filters';
  state.sortCol = 'created_at';
  state.sortAsc = false;

  const filters = _readFilterInputs();
  const topN    = parseInt(document.getElementById('topNSelect').value);

  const tbody = document.getElementById('resultsTbody');
  tbody.innerHTML = `<tr><td colspan="8" class="no-results">
    <div class="spinner" style="margin:0 auto 10px"></div>
    Searching jobs by filters…
  </td></tr>`;
  document.getElementById('resultsStatus').innerHTML =
    '<div class="spinner"></div><span>Searching the database…</span>';

  try {
    const data = await api.post('/api/search-filters', { filters, top_n: topN });
    state.lastResults = data.jobs || [];
    renderResults(state.lastResults);
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" style="padding:20px">
      <div class="error-box">Error: ${esc(e.message)}</div>
    </td></tr>`;
    document.getElementById('resultsStatus').innerHTML = '<span>Error — check Flask console.</span>';
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
  // Weak (C) matches are excluded entirely — not just hidden behind a toggle.
  // Jobs with no grade at all (filter-only browse — see runFiltersOnlyStep) were
  // never graded, so they're never "weak" and always pass this filter.
  const visible = notDismissed.filter(j => j.grade !== 'C');
  const sorted = [...visible].sort((a, b) => {
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

  // "Top 20 matches only" caps what's rendered, not the underlying set — the
  // status line below still reports the full match/grade counts.
  const displayed = state.top20Only ? sorted.slice(0, 20) : sorted;

  const savedIds = new Set(state.savedJobs.map(j => j.job_id));
  const tbody    = document.getElementById('resultsTbody');

  if (!displayed.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="no-results">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
      No jobs found — try broadening filters.
    </td></tr>`;
    document.getElementById('resultsStatus').innerHTML = '<span>No results.</span>';
    return;
  }

  tbody.innerHTML = '';
  displayed.forEach((job, i) => {
    const hasGrade = job.grade != null;
    const g      = job.grade || 'C';
    const loc    = [job.city, job.state].filter(Boolean).join(', ') || '—';
    const isSaved = savedIds.has(job.job_id);
    const sid    = storeJob({ ...job, _batch: 'search' });
    const tr     = document.createElement('tr');
    tr.id = `row-${job.job_id}`;
    tr.innerHTML = `
      <td>
        ${hasGrade
          ? `<span class="grade ${gradeClass(g)}">${g}</span><span class="pct">${job.score_pct || ''}</span>`
          : '<span class="no-score" title="Filter search — not AI-scored">—</span>'}
      </td>
      <td style="cursor:pointer" data-action="open-job-modal" data-sid="${sid}" title="Click to see details">
        <div class="job-title-main"><span class="job-detail-plus" title="More details">+</span>${esc(job.title)}</div>
        ${job.match_reason ? `<div class="match-reason">${esc(job.match_reason)}</div>` : ''}
      </td>
      <td>${job.company ? `<span class="company-link" data-company="${esc(job.company)}">${esc(job.company)}</span>` : '—'}</td>
      <td>${esc(loc)}</td>
      <td>${esc(job.salary || '—')}</td>
      <td class="job-dates">${job.created_at ? esc(String(job.created_at).substring(0,10)) : '—'}</td>
      <td><span id="jc-${job.job_id}"></span></td>
      <td style="display:flex;gap:4px;align-items:center;padding-left:6px;padding-right:6px">
        ${job.url ? `<a href="${esc(job.url)}" target="_blank" class="icon-btn" title="Open job link">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg>
        </a>` : ''}
        <button class="icon-btn${isSaved ? ' on' : ''}" id="save-${job.job_id}"
          data-action="toggle-save" data-job-id="${job.job_id}" title="${isSaved ? 'Saved' : 'Save job'}">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
        </button>
        <button class="extras-picker-btn visible" id="extras-pick-${job.job_id}"
          data-action="open-extras-picker" data-job-id="${job.job_id}" data-sid="${sid}"
          title="Save with extras">+</button>
        <button class="row-x" data-action="dismiss-job" data-job-id="${job.job_id}"
          title="Remove from view">×</button>
      </td>`;
    tr.style.opacity   = '0';
    tr.style.transform = 'translateY(6px)';
    tr.style.transition = 'opacity .25s, transform .25s';
    tbody.appendChild(tr);
    setTimeout(() => { tr.style.opacity = '1'; tr.style.transform = 'none'; }, 30 + i * 25);
  });

  const gradeSummary = state.resultsMode === 'filters'
    ? `${visible.length} jobs found`
    : (() => {
        const nA = visible.filter(j => j.grade === 'A').length;
        const nB = visible.filter(j => j.grade === 'B').length;
        return `${visible.length} matches found — ${nA} strong (A) · ${nB} good (B)`;
      })();
  document.getElementById('resultsStatus').innerHTML =
    `<span style="color:#1a7a2e;font-weight:500">✓</span>&nbsp; ${gradeSummary}` +
    (state.top20Only && sorted.length > displayed.length ? ` · showing top ${displayed.length}` : '');

  _loadJobContacts(displayed);
}

// Action registry for the dynamically-built results rows — clickable title
// (open modal), save / extras-picker / dismiss buttons. The button handlers
// keep the original stopPropagation so a row-level click can't fire.
Object.assign(_ACTIONS, {
  'open-job-modal':    (el)    => app.openJobModal(el.dataset.sid),
  'toggle-save':       (el)    => toggleSave(el, el.dataset.jobId),
  'open-extras-picker':(el, e) => { e.stopPropagation(); openExtrasPicker(el.dataset.jobId, el.dataset.sid, el); },
  'dismiss-job':       (el, e) => { e.stopPropagation(); dismissJob(el.dataset.jobId); },
  'inline-save-notes-input':   (el) => _inlineSaveNotesInput(el),
  'inline-save-status-change': (el) => _inlineSaveStatusChange(el),
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
  // Iterate every job shown, not just the ones present in the response — the
  // backend only returns entries for jobs that actually have a linked contact,
  // so a job with none would otherwise never get a button at all (previous bug:
  // its cell just stayed empty forever instead of showing a "no contact" state).
  ids.forEach(jid => {
    const el = document.getElementById('jc-' + jid);
    if (!el) return;
    const cts = _jobContacts[String(jid)] || [];
    // Compact icon-button instead of an inline name/email/phone card — keeps the
    // Contact column narrow so the row-action buttons don't need a horizontal
    // scroll to reach. Full details (or "No contacts for this job") are one
    // click away in the contacts modal either way.
    const label = cts.length === 1 ? (cts[0].name || 'Contact')
      : cts.length > 1 ? `${cts.length} contacts` : 'No contact on file';
    el.innerHTML = `<button class="icon-btn job-contact-btn${cts.length ? '' : ' empty'}" data-action="open-job-contacts"
      data-job-id="${esc(String(jid))}" title="${esc(label)}">
      👤${cts.length > 1 ? `<span class="jcb-count">${cts.length}</span>` : ''}
    </button>`;
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
  if (btn.classList.contains('on')) return;
  const job = state.lastResults.find(j => j.job_id == jobId);
  if (!job) return;
  const jobWithCandidate = { ...job, candidate_name: app.getCandidateName() };
  try {
    const data = await api.post('/api/saved', { job: jobWithCandidate, candidate_profile: state.currentCandidateProfile || null });
    if (data.ok) {
      btn.classList.add('on');
      btn.title = 'Saved';
      state.savedJobs = data.jobs;
      updateSavedBadge();
      _revealInlineSaveRow(jobId);
    }
  } catch(e) { alert('Save failed: ' + e.message); }
}

// Clicking Save reveals an inline notes + status row right under that result,
// so a note/pipeline-stage can be added without leaving the Search tab.
const _JOB_STATUS_OPTS = [
  ['new', 'New'], ['in_progress', 'In Progress'], ['proposal_sent', 'Proposal Sent'],
  ['won', 'Won'], ['lost', 'Lost'],
];

function _revealInlineSaveRow(jobId) {
  if (document.getElementById(`inline-save-${jobId}`)) return;   // already shown
  const jobRow = document.getElementById(`row-${jobId}`);
  if (!jobRow) return;
  const tr = document.createElement('tr');
  tr.className = 'inline-save-row';
  tr.id = `inline-save-${jobId}`;
  tr.innerHTML = `<td colspan="8"><div class="inline-save-row-inner">
    <div class="inline-save-notes">
      <div class="field-lbl">Notes</div>
      <input type="text" placeholder="Add a note about this job…" data-job-id="${jobId}" data-input-action="inline-save-notes-input">
    </div>
    <div class="inline-save-status">
      <div class="field-lbl">Status</div>
      <select data-job-id="${jobId}" data-change-action="inline-save-status-change">
        ${_JOB_STATUS_OPTS.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}
      </select>
    </div>
  </div></td>`;
  jobRow.after(tr);
}

let _inlineNotesDebounce = {};
function _inlineSaveNotesInput(el) {
  const jobId = el.dataset.jobId;
  clearTimeout(_inlineNotesDebounce[jobId]);
  _inlineNotesDebounce[jobId] = setTimeout(() => {
    api.patch(`/api/saved/${encodeURIComponent(jobId)}`, { notes: el.value }).catch(() => {});
  }, 500);
}

function _inlineSaveStatusChange(el) {
  const jobId = el.dataset.jobId;
  api.patch(`/api/saved/${encodeURIComponent(jobId)}`, { pipeline_status: el.value }).catch(() => {});
}

async function saveAll() {
  for (const job of state.lastResults.filter(j => j.grade !== 'C')) {
    const btn = document.getElementById(`save-${job.job_id}`);
    if (btn && !btn.classList.contains('on')) await toggleSave(btn, job.job_id);
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
      if (eb) { eb.textContent = '✓'; eb.classList.add('saved'); }
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
  renderResults, runMatching, saveAll, updateSavedBadge,
  doSaveWithExtras, loadFilters,
  // Shared with the Pipeline tab's Jobs sub-tab (saved.js) — same batch-fetch +
  // "#jc-<job_id>" span population used for the Search tab's Contact column.
  loadJobContacts: _loadJobContacts,
});
