// ════════════════════════════════════════════════════════════
//  Candidate — input modes, CV upload/parse, profile card, LinkedIn, examples
// ════════════════════════════════════════════════════════════
// Owns the single-candidate input surface: mode tabs (CV/LinkedIn/guided/template),
// the single<->multiple workflow toggle, CV drop zone + parsing, the profile card,
// LinkedIn scraping, example candidates, company info panel, and buildCandidateText()
// (the text every other module matches/chats against).
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";
import api from "./api.js";
import { updateMapStats } from "./map.js";

//  Input mode tabs
// ════════════════════════════════════════════════════════════
document.querySelectorAll('.mode-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const prevMode = state.activeMode;
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.input-zone').forEach(z => z.classList.remove('active'));
    tab.classList.add('active');
    state.activeMode = tab.dataset.mode;
    // Switching to a DIFFERENT input source: the shown candidate was derived from the
    // previous source, so clear the stale identity (name tag, profile card, dup warning)
    // — but keep each zone's typed text so nothing the user entered is lost.
    if (prevMode !== state.activeMode) _resetCandidateOnModeSwitch();
    document.getElementById('zone-' + state.activeMode).classList.add('active');
    const guided = state.activeMode === 'guided';
    if (guided) app.gbInit();
    const stBtn = document.getElementById('gbSaveTemplateBtn');
    if (stBtn) stBtn.style.display = guided ? 'inline-flex' : 'none';
    document.getElementById('runLabel').textContent = guided ? 'Find roles' : 'Run matching';
    _applyChrome();   // run row / candidate bar visibility (workflow + mode aware)
    // Re-evaluate the "already in DB" warning against the new mode's source.
    if (state.activeMode === 'linkedin')   checkLinkedInDuplicate();
    else if (state.activeMode === 'cv')    checkCandidateDuplicate(document.getElementById('candidateName')?.value || '');
    else                             _showDupWarn(null);
  });
});

// ════════════════════════════════════════════════════════════
//  Single ↔ Multiple candidate workflow
// ════════════════════════════════════════════════════════════
let _currentWorkflow = 'single';

// Single source of truth for the single-candidate chrome (run row + candidate bar),
// driven by both the workflow toggle and the input-mode tabs so they never conflict.
function _applyChrome() {
  const multiple = _currentWorkflow === 'multiple';
  const runRow = document.querySelector('.run-row');
  if (runRow) runRow.style.display = multiple ? 'none' : '';
  const cbar = document.querySelector('.candidate-bar');
  if (cbar) cbar.style.display = (multiple || state.activeMode === 'guided') ? 'none' : '';
}

// Switch between the single-candidate workflow (CV / LinkedIn / template tabs) and
// the multiple-candidates workflow (cluster a pool into segments).
function setWorkflow(wf) {
  _currentWorkflow = wf;
  if (wf === 'multiple') { state.mcDrilledFrom = false; app._setBackToSegments(false); }
  document.querySelectorAll('.wf-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.workflow === wf));
  const tabs = document.querySelector('.mode-tabs');
  const methodLabel = document.getElementById('methodLabel');

  if (wf === 'multiple') {
    if (tabs) tabs.style.display = 'none';
    if (methodLabel) methodLabel.style.display = 'none';
    document.querySelectorAll('.input-zone').forEach(z => z.classList.remove('active'));
    document.getElementById('zone-multiple').classList.add('active');
    state.activeMode = 'multiple';
  } else {
    if (tabs) tabs.style.display = '';
    if (methodLabel) methodLabel.style.display = '';
    document.getElementById('zone-multiple').classList.remove('active');
    // Re-activate the current single input mode (default: CV).
    const mode = (state.activeMode === 'multiple') ? 'cv' : state.activeMode;
    const tab  = document.querySelector('.mode-tab[data-mode="' + mode + '"]')
              || document.querySelector('.mode-tab[data-mode="cv"]');
    document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.input-zone').forEach(z => z.classList.remove('active'));
    tab.classList.add('active');
    state.activeMode = tab.dataset.mode;
    document.getElementById('zone-' + state.activeMode).classList.add('active');
    if (state.activeMode === 'guided') app.gbInit();
  }
  _applyChrome();
}

// ════════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════════

//  CV drop zone
// ════════════════════════════════════════════════════════════
const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', ()  => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) processFile(file);
});
document.getElementById('cvFileInput').addEventListener('change', e => {
  if (e.target.files[0]) processFile(e.target.files[0]);
});

async function processFile(file) {
  document.getElementById('dropText').innerHTML = `Reading <strong>${esc(file.name)}</strong>…`;
  const isPdf = file.name.toLowerCase().endsWith('.pdf');
  if (isPdf) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res  = await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Extraction failed');
      document.getElementById('cvPasteText').value = data.text;
      _setCvLoaded(file.name);
      parseCandidate(data.text);
    } catch(e) {
      document.getElementById('dropText').innerHTML =
        `<span style="color:#ef4444">${esc(file.name)} — extraction failed, paste text below</span>`;
    }
  } else {
    const reader = new FileReader();
    reader.onload = e => {
      const text = e.target.result.substring(0, 5000);
      document.getElementById('cvPasteText').value = text;
      _setCvLoaded(file.name);
      parseCandidate(text);
    };
    reader.onerror = () => {
      document.getElementById('dropText').innerHTML = `${esc(file.name)} — paste text below instead`;
    };
    reader.readAsText(file);
  }
}

// ── AI Candidate profile ──────────────────────────────────────
let _parseProfileTimer = null;

function setCandidateName(name) {
  // Keep the hidden input in sync for job-saving (reads candidateName.value)
  const inp = document.getElementById('candidateName');
  if (inp) inp.value = name || '';
  // Update candidate bar tag
  const tag     = document.getElementById('candNameTag');
  const display = document.getElementById('candNameDisplay');
  const editRow = document.getElementById('candEditRow');
  const hint    = document.getElementById('candHint');
  if (name) {
    if (display) display.textContent = name;
    if (tag)     tag.style.display    = '';
    if (editRow) editRow.style.display = 'none';
    if (hint)    hint.style.display    = 'none';
  } else {
    if (tag)     tag.style.display    = 'none';
    if (editRow) editRow.style.display = 'none';
    if (hint)    hint.style.display    = '';
  }
}

function startEditCandidateName() {
  document.getElementById('candNameTag').style.display    = 'none';
  document.getElementById('candEditRow').style.display    = '';
  document.getElementById('candHint').style.display       = 'none';
  const inp = document.getElementById('candidateName');
  if (inp) { inp.focus(); inp.select(); }
}

// Warn (red banner) when the candidate being added already exists in the DB, and
// offer a "Load from database" button to reload their profile + saved jobs instead
// of re-parsing a CV / re-scraping a LinkedIn profile.
let _dupCheckSeq      = 0;
let _dupCandidateName = '';   // name backing the banner's Load-from-database button

// Render (or hide) the duplicate banner from a lookup result (or null to hide).
function _showDupWarn(cand){
  const warn = document.getElementById('candDupWarn');
  if (!warn) return;
  _dupCandidateName = cand ? (cand.name || '') : '';
  if (!cand){ warn.style.display='none'; warn.innerHTML=''; return; }
  const kind = cand.isTemplate ? 'template' : 'candidate';
  const jobs = cand.matches ? ` · ${cand.matches} saved job${cand.matches!==1?'s':''}` : '';
  warn.innerHTML =
    `<span class="cdw-ico">!</span>` +
    `<span><b>${esc(cand.name)}</b> is already in the database as a ${kind} — ` +
    `status <span class="cdw-status">${esc(cand.status)}</span>${jobs}</span>` +
    `<span class="cdw-actions">` +
      `<button type="button" class="cdw-load" data-action="load-candidate-from-db" ` +
      `title="Load the saved profile and the jobs already stored for this candidate — no new search">` +
      `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 15v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>` +
      `Load saved records</button>` +
      `<button type="button" class="cdw-refresh" data-action="refresh-candidate-from-db" ` +
      `title="Re-run matching against the live database to find new/updated jobs, then refresh this candidate's record and saved jobs">` +
      `<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6"/></svg>` +
      `Refresh from database</button>` +
    `</span>`;
  warn.style.display = '';
}

// CV mode: look the candidate up by NAME.
async function checkCandidateDuplicate(name){
  if (!document.getElementById('candDupWarn')) return;
  name = (name || '').trim();
  if (!name || name.toLowerCase() === 'unassigned'){ _showDupWarn(null); return; }
  const seq = ++_dupCheckSeq;
  try {
    const data = await api.get('/api/saved/lookup?name=' + encodeURIComponent(name));
    if (seq !== _dupCheckSeq) return;   // a newer check superseded this one
    _showDupWarn(data.exists ? data.candidate : null);
  } catch(e){
    if (seq === _dupCheckSeq) _showDupWarn(null);
  }
}

// LinkedIn mode: look the candidate up by the first profile URL in the box, so we
// can warn (and offer a DB reload) BEFORE paying to re-scrape an on-file profile.
async function checkLinkedInDuplicate(){
  if (!document.getElementById('candDupWarn')) return;
  const raw = document.getElementById('liUrls')?.value || '';
  const url = raw.split(/[\n,]+/).map(s => s.trim()).filter(s => /linkedin\.com\//i.test(s))[0] || '';
  if (!url){ _showDupWarn(null); return; }
  const seq = ++_dupCheckSeq;
  try {
    const data = await api.get('/api/saved/lookup?linkedin=' + encodeURIComponent(url));
    if (seq !== _dupCheckSeq) return;
    _showDupWarn(data.exists ? data.candidate : null);
  } catch(e){
    if (seq === _dupCheckSeq) _showDupWarn(null);
  }
}

// Reload a previously-saved candidate (profile + saved jobs) from the DB into the
// search tab — no re-parsing, no re-scraping. Backs the banner's Load button.
async function loadCandidateFromDb(){
  const name = _dupCandidateName;
  if (!name) return;
  const btn = document.querySelector('#candDupWarn .cdw-load');
  const orig = btn ? btn.innerHTML : '';
  if (btn){ btn.disabled = true; btn.innerHTML = 'Loading…'; }
  try {
    const data = await api.get('/api/saved/load?name=' + encodeURIComponent(name));

    if (data.profile){
      _renderCandidateProfile(data.profile);   // re-renders the banner too
      // Seed a matching text from the structured profile so Run matching and the
      // CV-dependent extras (strength, questions) work after a DB load.
      _seedMatchTextFromProfile(data.profile);
    } else {
      setCandidateName(name);
    }
    if (data.jobs && data.jobs.length){
      state.lastResults = data.jobs;
      app.renderResults(state.lastResults);
      updateMapStats(state.lastResults);
      document.getElementById('resultsStatus').innerHTML =
        `<span>Loaded ${data.jobs.length} saved job${data.jobs.length!==1?'s':''} for ${esc(name)} from the database.</span>`;
    }
  } catch(e){
    if (btn){ btn.disabled = false; btn.innerHTML = orig; }
    alert('Could not load from database: ' + (e.message || e));
  }
}

// Put a profile-derived candidate text into the CV box (CV mode) so matching and
// CV-gated extras work for a DB-loaded candidate that has no raw CV text.
function _seedMatchTextFromProfile(profile){
  const txt = _profileToText(profile);
  if (!txt) return;
  _activateCVMode && _activateCVMode();
  const ta = document.getElementById('cvPasteText');
  if (ta && !ta.value.trim()){ ta.value = txt; }
  state.lastParsedText = txt;
}

// "Refresh from database": reload the saved profile, run a FRESH match against the
// live job DB (so new/updated postings show up), then persist the refreshed record
// + the A/B matches back to the database.
async function refreshCandidateFromDb(){
  const name = _dupCandidateName;
  if (!name) return;
  const btn  = document.querySelector('#candDupWarn .cdw-refresh');
  const orig = btn ? btn.innerHTML : '';
  if (btn){ btn.disabled = true; btn.innerHTML = 'Refreshing…'; }
  try {
    const data = await api.get('/api/saved/load?name=' + encodeURIComponent(name));
    if (data.profile){
      _renderCandidateProfile(data.profile);
      _seedMatchTextFromProfile(data.profile);
    } else {
      setCandidateName(name);
    }
    // A refresh is a fresh search — never re-score a frozen set.
    if (state.resultsFrozen){
      const chk = document.getElementById('freezeChk');
      if (chk){ chk.checked = false; app.toggleFreeze(); }
    }
    if (btn) btn.innerHTML = orig;
    await app.runMatching();                 // fresh vector search against the live DB
    if (state.lastResults.length) await app.saveAll();   // upsert profile + save new A/B jobs
    const n = state.lastResults.filter(j => j.grade !== 'C').length;
    document.getElementById('resultsStatus').innerHTML =
      `<span style="color:#1a7a2e;font-weight:500">✓</span>&nbsp; Refreshed ${esc(name)} — ` +
      `${state.lastResults.length} jobs matched, ${n} saved back to the database.</span>`;
  } catch(e){
    if (btn){ btn.disabled = false; btn.innerHTML = orig; }
    alert('Could not refresh from database: ' + (e.message || e));
  }
}

function confirmCandidateName() {
  const editRow = document.getElementById('candEditRow');
  if (!editRow || editRow.style.display === 'none') return;
  const inp  = document.getElementById('candidateName');
  const name = inp ? inp.value.trim() : '';
  setCandidateName(name);
  checkCandidateDuplicate(name);
  // Also update profile card name display
  const pn = document.getElementById('candProfileName');
  if (pn) pn.textContent = name;
  const av = document.getElementById('candProfileAvatar');
  if (av && name) av.textContent = _initials(name);
}

function _initials(name) {
  const p = name.trim().split(/\s+/);
  if (p.length >= 2) return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  return (name[0] || '?').toUpperCase();
}

function _renderCandidateProfile(data) {
  state.currentCandidateProfile = data;
  app._trackLocalCandidate(data);   // make it available in the Saved-tab "Local" view
  checkCandidateDuplicate(data.name || '');   // red banner if already in the DB
  const card    = document.getElementById('candProfileCard');
  const parsing = document.getElementById('candParsing');
  const content = document.getElementById('candProfileContent');

  setCandidateName(data.name || '');

  // Avatar
  const av = document.getElementById('candProfileAvatar');
  if (av) av.textContent = data.name ? _initials(data.name) : '?';

  // Name
  const pn = document.getElementById('candProfileName');
  if (pn) pn.textContent = data.name || 'Candidate';

  // Subtitle: title · seniority · location · experience
  const yrs = data.years_experience ? `${data.years_experience} yrs` : data.experience_years;
  const sub = [data.title, data.seniority, data.location, yrs].filter(Boolean).join(' · ');
  const ps = document.getElementById('candProfileSub');
  if (ps) ps.textContent = sub;

  // Skills chips — prefer the AI-ranked top skills, fall back to raw LinkedIn skills
  const skillList = (Array.isArray(data.top_skills) && data.top_skills.length) ? data.top_skills : (data.skills || []);
  const sk = document.getElementById('candProfileSkills');
  if (sk) sk.innerHTML = skillList.slice(0, 10)
    .map(s => `<span class="cand-profile-skill">${esc(s)}</span>`).join('');

  // Meta row: industry | languages | salary (ask or AI estimate) | availability
  const meta = [];
  const mItem = (label, val) => `<span class="cand-profile-meta-item"><span class="cand-profile-meta-label">${label}</span>${esc(val)}</span>`;
  if (data.industry)            meta.push(mItem('Industry', data.industry));
  if (data.role_category)       meta.push(mItem('Role', data.role_category));
  if (data.languages)           meta.push(mItem('Languages', data.languages));
  if (data.salary_expectation)  meta.push(mItem('Salary', data.salary_expectation));
  else if (data.estimated_salary_min && data.estimated_salary_max)
    meta.push(mItem('Est. salary', `€${data.estimated_salary_min.toLocaleString()}–${data.estimated_salary_max.toLocaleString()}/mo`));
  if (data.management_experience && !/^no\b/i.test(data.management_experience))
    meta.push(mItem('Management', data.management_experience));
  if (data.availability)        meta.push(mItem('Available', data.availability));
  if (Array.isArray(data.certifications) && data.certifications.length)
    meta.push(mItem('Certifications', data.certifications.filter(Boolean).join(', ')));
  const me = document.getElementById('candProfileMeta');
  if (me) me.innerHTML = meta.join('');

  // Summary — prefer the AI recruiter brief over the raw LinkedIn summary
  const sm = document.getElementById('candProfileSummary');
  const summ = data.ai_summary || data.summary || '';
  if (sm) { sm.textContent = summ; sm.style.display = summ ? '' : 'none'; }

  // Strengths (AI) — compact highlight bullets
  const st = document.getElementById('candProfileStrengths');
  if (st) {
    const strengths = Array.isArray(data.strengths) ? data.strengths.filter(Boolean) : [];
    if (strengths.length) {
      st.innerHTML = `<div class="cand-profile-exp-title">Strengths</div>` +
        strengths.slice(0, 5).map(s => `<div class="cps-item">${esc(s)}</div>`).join('');
      st.style.display = '';
    } else { st.innerHTML = ''; st.style.display = 'none'; }
  }

  // Work history (LinkedIn imports) — the candidate's prior employers.
  const ex = document.getElementById('candProfileExp');
  if (ex) {
    const exps = Array.isArray(data.experiences) ? data.experiences.filter(e => e && (e.title || e.company)) : [];
    if (exps.length) {
      const when = e => [e.starts_at, e.ends_at].filter(Boolean).join('–') || (e.starts_at ? `${e.starts_at}–present` : '');
      const nCo = _companiesFromProfile(data).length;
      ex.innerHTML = `<div class="cand-profile-exp-head">
          <span class="cand-profile-exp-title">Experience</span>
          ${nCo ? `<button type="button" class="cpe-save-co" data-action="save-companies" title="Save these employers to the companies table">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-4"/></svg>
            Save companies (${nCo})</button>` : ''}
        </div>` +
        exps.slice(0, 6).map(e => `
          <div class="cand-profile-exp-item">
            <span><span class="cpe-role">${esc(e.title || '—')}</span>${e.company ? ` · <span class="cpe-co">${esc(e.company)}</span>` : ''}</span>
            ${when(e) ? `<span class="cpe-when">${esc(when(e))}</span>` : ''}
          </div>`).join('');
      ex.style.display = '';
    } else {
      ex.innerHTML = ''; ex.style.display = 'none';
    }
  }

  if (parsing) parsing.style.display = 'none';
  if (content) content.style.display = '';
  if (card)    card.classList.add('visible');
}

// Build the company list from a candidate profile: each prior employer from the
// work history (name + URL + role + dates), merged with the current employer's
// extra metadata (industry/size/website). Deduped by LinkedIn URL, else by name.
function _companiesFromProfile(prof){
  if (!prof) return [];
  const out = [], seen = new Map();   // key (url||name) → index in out
  const keyOf = c => (c.linkedin_url || '').trim().toLowerCase() || (c.name || '').trim().toLowerCase();
  (prof.experiences || []).forEach(e => {
    if (!e || !e.company) return;
    const c = { name: e.company, linkedin_url: e.company_url || null,
                title: e.title || null, starts_at: e.starts_at || null, ends_at: e.ends_at || null };
    const k = keyOf(c);
    if (!seen.has(k)) { seen.set(k, out.length); out.push(c); }
  });
  const cc = prof.current_company;
  if (cc && cc.name) {
    const k = keyOf(cc), meta = { industry: cc.industry, size: cc.size, website: cc.website };
    if (seen.has(k)) Object.assign(out[seen.get(k)], meta);
    else out.push({ name: cc.name, linkedin_url: cc.linkedin_url || null, ...meta });
  }
  return out;
}

// Persist the current candidate's employers to the companies table (+ link who
// worked there). Driven by the "Save companies" button in the work-history panel.
async function saveCompanies(btn){
  const prof = state.currentCandidateProfile;
  const name = (prof && prof.name || '').trim() || app.getCandidateName();
  const companies = _companiesFromProfile(prof);
  if (!name) { alert('Give the candidate a name first.'); return; }
  if (!companies.length) { return; }
  const orig = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = 'Saving…';
  try {
    const data = await api.post('/api/saved/companies', { candidate: name, companies, candidate_profile: prof });
    btn.innerHTML = `✓ Saved ${data.saved}`;
    setTimeout(() => { btn.disabled = false; btn.innerHTML = orig; }, 2500);
  } catch(e) {
    btn.disabled = false; btn.innerHTML = orig;
    alert('Could not save companies: ' + (e.message || e));
  }
}

async function parseCandidate(text) {
  if (!text || text === state.lastParsedText) return;
  state.lastParsedText = text;

  const card    = document.getElementById('candProfileCard');
  const parsing = document.getElementById('candParsing');
  const content = document.getElementById('candProfileContent');

  card.classList.add('visible');
  if (parsing) parsing.style.display  = '';
  if (content) content.style.display  = 'none';

  try {
    const data = await api.post('/api/candidate/parse-profile', { text });
    _renderCandidateProfile(data);
  } catch(e) {
    if (parsing) parsing.style.display = 'none';
    card.classList.remove('visible');
    state.lastParsedText = '';
  }
}

function scheduleParsing(text) {
  clearTimeout(_parseProfileTimer);
  if (text.trim().length < 40) return;
  _parseProfileTimer = setTimeout(() => parseCandidate(text.trim()), 1400);
}

// ── LinkedIn URL enrichment (Apify) ───────────────────────────
// Scraping is the first step of "Run matching" in LinkedIn mode (no separate
// button): scrape the profile(s) via the backend Apify actor, render the first
// profile as the active candidate (card + matcher text), then matching proceeds
// on that text. Every imported profile is also tracked as a Local candidate.
let _linkedinText        = '';
let _linkedinScrapedKey  = '';   // URL set last scraped — skip re-scraping the same one

// Ensure the URLs in the box are scraped and _linkedinText is ready to match.
// Returns true on success, false if there were no URLs / the scrape failed
// (a message is shown in #liStatus either way). Caller drives the run button.
async function ensureLinkedInScraped() {
  const raw    = document.getElementById('liUrls').value;
  const urls   = raw.split(/[\n,]+/).map(s => s.trim()).filter(s => /linkedin\.com\//i.test(s));
  const status = document.getElementById('liStatus');
  if (!urls.length) { status.className='li-status err'; status.textContent='Paste at least one LinkedIn profile URL.'; return false; }

  // Reuse the previous scrape when the exact same URL set is already loaded.
  const key = urls.join('\n');
  if (key === _linkedinScrapedKey && _linkedinText) return true;

  document.getElementById('runLabel').textContent = 'Scraping profile…';
  status.className = 'li-status';
  status.innerHTML = `<span class="spinner"></span> Scraping profile${urls.length!==1?'s':''}…`;
  try {
    const data = await api.post('/api/candidate/enrich-linkedin', { urls });
    const profiles = (data.profiles || []).filter(p => p && p.profile);
    if (!profiles.length) throw new Error('No profiles returned');

    // Every imported profile becomes a session ("Local") candidate, ready to save.
    profiles.forEach(p => app._trackLocalCandidate(p.profile));

    // Load the first one as the active candidate (card + matcher text); the rest
    // wait in Saved → Local. Matching then runs on this profile's text.
    _linkedinText       = profiles[0].text || '';
    state.lastParsedText     = _linkedinText;
    _linkedinScrapedKey = key;
    _renderCandidateProfile(profiles[0].profile);

    const n  = profiles.length;
    const nm = esc(profiles[0].profile.name || 'First profile');
    status.className = 'li-status ok';
    status.innerHTML = (n > 1)
      ? `✓ Imported ${n} profiles — “${nm}” matching below; all ${n} added to <a href="#" data-action="goto-saved-local">Saved → Local</a>.`
      : `✓ Imported “${nm}” — matching now…`;
    if (data.requested && data.count < data.requested)
      status.innerHTML += ` <span style="color:#c0392b">(${data.requested - data.count} URL(s) returned no data.)</span>`;
    return true;
  } catch(e) {
    status.className = 'li-status err';
    status.textContent = 'Could not scrape: ' + (e.message || e);
    return false;
  }
}

// Jump to the Saved tab's Local list (where bulk-imported candidates wait to save).
function _gotoSavedLocal() {
  app._activateTab('saved');
  state.savedView = 'table';
  app.setSavedSource('local');
  app._applySavedView();
}

// ── CV loaded chip + preview ──────────────────────────────────
let _cvLoadedName = '';

function _setCvLoaded(name) {
  _cvLoadedName = name;
  document.getElementById('dropText').innerHTML =
    `<div class="cv-loaded-chip" data-action="open-cv-preview">
       <div class="cv-loaded-chip-icon">📄</div>
       <div>
         <div class="cv-loaded-chip-name">✓ ${esc(name)}</div>
         <div class="cv-loaded-chip-hint">Click to preview · ready to match</div>
       </div>
       <button class="cv-loaded-chip-del" data-action="cv-loaded-chip-remove" title="Remove CV">×</button>
     </div>`;
}

// Action registry for the candidate input card — duplicate-warning load/refresh,
// save-companies, LinkedIn import "Saved → Local" link, CV-loaded preview chip.
Object.assign(_ACTIONS, {
  'load-candidate-from-db':    ()      => loadCandidateFromDb(),
  'refresh-candidate-from-db': ()      => refreshCandidateFromDb(),
  'save-companies':            (el)    => saveCompanies(el),
  'goto-saved-local':          (el, e) => { e.preventDefault(); _gotoSavedLocal(); },
  'open-cv-preview':           ()      => openCvPreview(),
  'cv-loaded-chip-remove':     (el, e) => { e.stopPropagation(); clearCandidateProfile(); },
});

function openCvPreview() {
  if (!state.lastParsedText) return;
  document.getElementById('cvPreviewName').textContent = _cvLoadedName || 'CV Preview';
  document.getElementById('cvPreviewBody').textContent  = state.lastParsedText;
  document.getElementById('cvPreviewOverlay').classList.add('cvpo-open');
}

function closeCvPreview() {
  document.getElementById('cvPreviewOverlay').classList.remove('cvpo-open');
}

// ── Company info panel ────────────────────────────────────────

let _coCache = {};   // cache by company name to avoid re-fetching

async function openCompanyPanel(companyName) {
  const modal  = document.getElementById('coModal');
  const body   = document.getElementById('coBody');
  const nameEl = document.getElementById('coPanelName');
  const subEl  = document.getElementById('coPanelSub');

  nameEl.textContent = companyName;
  subEl.textContent  = '';
  body.innerHTML = `<div class="co-loading-wrap"><div class="co-spinner"></div><span>Loading company data…</span></div>`;
  modal.classList.remove('hidden');

  // Use cache if available
  if (_coCache[companyName]) {
    _renderCompanyPanel(_coCache[companyName]);
    return;
  }

  try {
    const data = await api.get('/api/company?name=' + encodeURIComponent(companyName));
    _coCache[companyName] = data;
    _renderCompanyPanel(data);
  } catch(e) {
    body.innerHTML = `<div class="co-no-data" style="padding:30px">Could not load company data: ${esc(e.message)}</div>`;
  }
}

function closeCompanyPanel() {
  document.getElementById('coModal').classList.add('hidden');
}

function _renderCompanyPanel(d) {
  const nameEl = document.getElementById('coPanelName');
  const subEl  = document.getElementById('coPanelSub');
  const body   = document.getElementById('coBody');

  nameEl.textContent = d.company;

  // Sub-header: "12 active jobs · Wien, Niederösterreich"
  const subParts = [];
  if (d.total_jobs) subParts.push(`${d.total_jobs} active job${d.total_jobs !== 1 ? 's' : ''}`);
  if (d.states?.length) subParts.push(d.states.slice(0, 3).join(', ') + (d.states.length > 3 ? ` +${d.states.length - 3}` : ''));
  subEl.textContent = subParts.join('  ·  ');

  const sal  = d.salary_stats || {};
  const avg  = sal.mean ? `€${sal.mean.toLocaleString()}` : '—';
  const rng  = sal.min && sal.max ? `€${sal.min.toLocaleString()} – €${sal.max.toLocaleString()}` : '—';

  if (!d.total_jobs) {
    body.innerHTML = `<div class="co-no-data" style="padding:24px 0">No active jobs found for this company.</div>`;
    return;
  }

  // ── Stats row ──────────────────────────────────────────────
  let html = `<div class="co-stats-row">
    <div class="co-stat"><div class="co-stat-num">${d.total_jobs}</div><div class="co-stat-lbl">Active jobs</div></div>
    <div class="co-stat"><div class="co-stat-num" style="font-size:${avg.length > 9 ? '14px' : '20px'}">${avg}</div><div class="co-stat-lbl">Avg salary</div></div>
    <div class="co-stat"><div class="co-stat-num">${d.states?.length || 0}</div><div class="co-stat-lbl">State${(d.states?.length || 0) !== 1 ? 's' : ''}</div></div>
  </div>`;

  // ── AI Summary ─────────────────────────────────────────────
  if (d.summary) {
    html += `<div class="co-section-hdr">Hiring profile</div>
    <div class="co-summary-box">${esc(d.summary)}</div>`;
  }

  // ── Two-column section: roles + details ─────────────────────
  let leftCol = '';
  let rightCol = '';

  // Left: Top roles
  if (d.top_titles?.length) {
    leftCol += `<div class="co-section-hdr">Top roles</div><div class="co-pill-list">`;
    d.top_titles.forEach(t => {
      leftCol += `<span class="co-pill">${esc(t.title)}<span class="co-pill-count">×${t.count}</span></span>`;
    });
    leftCol += `</div>`;
  }

  // Left: Sectors
  if (d.top_occ?.length) {
    leftCol += `<div class="co-section-hdr">Sectors</div><div class="co-pill-list">`;
    d.top_occ.forEach(o => {
      leftCol += `<span class="co-pill">${esc(o.group)}<span class="co-pill-count">${o.count}</span></span>`;
    });
    leftCol += `</div>`;
  }

  // Right: Salary details
  if (sal.min) {
    rightCol += `<div class="co-section-hdr">Salary range</div>
    <div class="co-salary-block"><span class="co-sal-big">${rng}</span></div>
    <div class="co-sal-details">
      <span class="co-sal-item">Avg <b>€${sal.mean?.toLocaleString()}</b></span>
      <span class="co-sal-item">Median <b>€${sal.median?.toLocaleString()}</b></span>
      <span class="co-sal-item">${sal.count} listed</span>
    </div>`;
  }

  // Right: Locations
  if (d.states?.length) {
    rightCol += `<div class="co-section-hdr">Active in</div><div class="co-pill-list">`;
    d.states.forEach(s => { rightCol += `<span class="co-state-chip">${esc(s)}</span>`; });
    rightCol += `</div>`;
  }

  // Right: Portals + date range
  if (d.portals?.length) {
    rightCol += `<div class="co-section-hdr">Posted on</div><div class="co-pill-list">`;
    d.portals.forEach(p => { rightCol += `<span class="co-pill">${esc(p)}</span>`; });
    rightCol += `</div>`;
  }
  if (d.date_range?.newest) {
    rightCol += `<div class="co-section-hdr" style="margin-top:12px">Latest posting</div>
    <div style="font-size:12px;color:#555"><b>${d.date_range.newest}</b></div>`;
  }

  if (leftCol || rightCol) {
    html += `<div class="co-two-col" style="margin-top:4px">
      <div>${leftCol}</div>
      <div>${rightCol}</div>
    </div>`;
  }

  // ── Recent job listings ─────────────────────────────────────
  if (d.recent_jobs?.length) {
    html += `<div class="co-section-hdr" style="margin-top:18px">Recent postings</div><div class="co-job-list">`;
    d.recent_jobs.forEach(j => {
      const loc  = [j.city, j.state].filter(Boolean).join(', ') || '—';
      const salTag = j.salary ? `<span class="co-job-meta-sal">€${esc(String(j.salary))}</span>` : '';
      const dateTag = j.posted ? `<span>${j.posted}</span>` : '';
      const attrs = j.url ? `href="${esc(j.url)}" target="_blank"` : '';
      html += `<a class="co-job-row" ${attrs}>
        <div class="co-job-row-title">${esc(j.title || '—')}</div>
        <div class="co-job-row-meta">
          <span>📍 ${esc(loc)}</span>
          ${salTag}
          ${j.portal ? `<span>${esc(j.portal)}</span>` : ''}
          ${dateTag}
        </div>
      </a>`;
    });
    html += `</div>`;
  }

  body.innerHTML = html;
}

// Lighter reset used when switching input mode: drops the derived candidate identity
// (name, profile card, dup warning) but PRESERVES each zone's typed text (cvPasteText,
// liUrls, guided fields), unlike clearCandidateProfile() which wipes the inputs.
function _resetCandidateOnModeSwitch() {
  document.getElementById('candProfileCard')?.classList.remove('visible');
  setCandidateName('');
  _showDupWarn(null);
  state.lastParsedText = '';
  _cvLoadedName   = '';
  state.currentCandidateProfile = null;
}

function clearCandidateProfile() {
  document.getElementById('candProfileCard').classList.remove('visible');
  state.mcDrilledFrom = false; app._setBackToSegments(false);   // breaking the candidate breaks the segment link
  setCandidateName('');
  checkCandidateDuplicate('');   // clears the duplicate warning
  state.lastParsedText = '';
  _cvLoadedName   = '';
  state.currentCandidateProfile = null;
  _linkedinText       = '';
  _linkedinScrapedKey = '';
  state.candAsstNotes      = [];   // drop CV details the assistant added for this candidate
  state.dismissedJobIds    = new Set();   // reset per-row dismiss/freeze for the new candidate
  state.pinnedJobIds       = new Set();
  state.highlightCriterion = '';
  state.highlightedJobIds  = new Set();
  ['cvPasteText', 'liUrls'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('dropText').innerHTML =
    'Drop a PDF CV here, or <a href="#" data-action="browse-cv">browse to upload</a> — or paste CV text directly below';
}

document.getElementById('cvPasteText').addEventListener('input', e => scheduleParsing(e.target.value));

// LinkedIn URL box: debounced lookup so we warn (with a DB-reload button) when the
// pasted profile is already on file, before the user pays to re-scrape it.
let _liDupTimer = null;
document.getElementById('liUrls').addEventListener('input', () => {
  clearTimeout(_liDupTimer);
  _liDupTimer = setTimeout(checkLinkedInDuplicate, 500);
});

// ── Example Candidate 1: Anna Bauer (text) ───────────────────
const _EXAMPLE_CANDIDATE = {
  name: 'Anna Bauer',
  text: `Logistics and Warehouse Supervisor with 8 years of experience in Vienna and Lower Austria.

Certified forklift operator (Staplerführerschein, valid until 2027). SAP Warehouse Management certified user (2020). Currently Senior Warehouse Supervisor at MegaLogistics GmbH Wien (2019–present): leading a team of 12 associates across two shifts, introduced SAP WM module reducing stock discrepancies by 23%, responsible for KPI reporting (fill rate, OTIF, pick accuracy). Previously Warehouse Coordinator at AustroPack AG, Niederösterreich (2016–2019): coordinated 2,000+ orders/day pick & pack, trained and onboarded 8 staff.

Key skills: SAP WM, forklift operation, inventory management, team leadership, lean logistics, FIFO/FEFO, MS Excel, KPI reporting.
Languages: German (native), English B2.
Salary expectation: €2,800–3,400 gross/month.
Availability: Immediately. Seeking full-time permanent role in Vienna or Niederösterreich.`,
};

const _EXAMPLE_PROFILE = {
  name: 'Anna Bauer',
  title: 'Logistics & Warehouse Supervisor',
  experience_years: '8 years',
  skills: ['Staplerführerschein','SAP WM','Team Leadership','Inventory Management','KPI Reporting','Lean Logistics','MS Excel','FIFO/FEFO'],
  location: 'Vienna / Niederösterreich',
  languages: 'German (native), English B2',
  salary_expectation: '€2,800–3,400/month',
  availability: 'Immediately',
  summary: 'Experienced logistics supervisor with 8 years in high-volume distribution, certified forklift operator with SAP WM expertise and a track record of reducing stock discrepancies.',
};

// ── Example Candidate 2: Max Weber (PDF) ─────────────────────
const _EXAMPLE_CANDIDATE_2 = {
  name: 'Max Weber',
  text: `Software Developer with 5 years of experience in backend and full-stack development, based in Vienna.

Currently Backend Developer at TechSolutions GmbH Vienna (2022–present): building REST APIs in Python/FastAPI, maintaining PostgreSQL databases, deploying services via Docker and CI/CD pipelines. Previously Junior Developer at WebFactory GmbH (2020–2022): developed React frontends and Node.js services, contributed to agile sprint planning and code reviews. IT Intern at Startup Hub Vienna (2019–2020): built internal tooling with Python and automated reporting workflows.

Education: FH Technikum Wien – BSc Computer Science (2019).
Key skills: Python, FastAPI, JavaScript/TypeScript, React, Node.js, PostgreSQL, Docker, Git, REST APIs, Linux, CI/CD.
Languages: German (native), English C1.
Salary expectation: €3,500–4,500 gross/month.
Availability: 3 months notice. Seeking full-time permanent role in Vienna.`,
};

const _EXAMPLE_PROFILE_2 = {
  name: 'Max Weber',
  title: 'Backend & Full-Stack Developer',
  experience_years: '5 years',
  skills: ['Python','FastAPI','JavaScript/TypeScript','React','Node.js','PostgreSQL','Docker','Git','REST APIs','Linux','CI/CD'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,500–4,500/month',
  availability: '3 months notice',
  education: 'MSc Computer Science, TU Wien',
  summary: 'Full-stack developer with 5 years experience in Python backends and React frontends, comfortable with Docker deployments and agile teams.',
};

// ── Example Candidate 3: Thomas Gruber (finance director, text) ──
const _EXAMPLE_CANDIDATE_3 = {
  name: 'Thomas Gruber',
  text: `Director Group Finance with 15 years of experience in corporate finance, IFRS reporting and investor relations, based in Vorarlberg / Vienna.

Currently Head of Group Finance at Dornbirn Medtech AG (2019–present): responsible for consolidated IFRS financial statements, management reporting to the executive board and supervisory board, investor relations and earnings calls preparation, coordination of annual audit (Big 4). Previously Senior Finance Manager at Zumtobel Group AG, Dornbirn (2014–2019): led a team of 6 finance controllers, implemented SAP S/4HANA group-wide, reduced monthly close cycle from 12 to 7 days. Earlier positions: Finance Controller at Blum GmbH (2011–2014), Audit Senior at Deloitte Wien (2008–2011).

Education: WU Wien – MSc Finance & Accounting (2008). CPA Austria (Steuerberater, 2013).
Key skills: IFRS, Group consolidation, SAP S/4HANA, financial analysis, management reporting, investor relations, earnings calls, budgeting & forecasting, M&A due diligence, team leadership, Big 4 audit background.
Languages: German (native), English C1 (business fluent).
Salary expectation: €80,000–95,000 gross/year.
Availability: 3 months notice. Open to CFO or Director Group Finance roles in Vorarlberg, Vienna, or remote-hybrid.`,
};

const _EXAMPLE_PROFILE_3 = {
  name: 'Thomas Gruber',
  title: 'Director Group Finance',
  experience_years: '15 years',
  skills: ['IFRS','Group Consolidation','SAP S/4HANA','Financial Analysis','Management Reporting','Investor Relations','Budgeting & Forecasting','M&A Due Diligence','Team Leadership','CPA Austria'],
  location: 'Vorarlberg / Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€80,000–95,000/year',
  availability: '3 months notice',
  summary: 'Senior finance director with 15 years across Big 4 audit, controlling and group CFO functions; IFRS and SAP S/4HANA expert with investor relations and M&A experience.',
};

function _activateCVMode() {
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.input-zone').forEach(z => z.classList.remove('active'));
  const cvTab = document.querySelector('.mode-tab[data-mode="cv"]');
  if (cvTab) cvTab.classList.add('active');
  const zone = document.getElementById('zone-cv');
  if (zone) zone.classList.add('active');
  state.activeMode = 'cv';
}

function loadExampleText() {
  _activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = _EXAMPLE_CANDIDATE.text;
  _setCvLoaded('Anna Bauer (example)');
  state.lastParsedText = _EXAMPLE_CANDIDATE.text;
  _renderCandidateProfile(_EXAMPLE_PROFILE);
}

async function loadExamplePdf() {
  const tile = document.getElementById('exPdfTile');
  if (tile) { tile.style.opacity = '0.55'; tile.style.pointerEvents = 'none'; }
  try {
    const res = await api.raw('/api/candidate/example-pdf-2');
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();

    const fd = new FormData();
    fd.append('file', blob, 'Max_Weber_CV.pdf');
    let pdfText = _EXAMPLE_CANDIDATE_2.text;
    try {
      const pr = await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd });
      if (pr.ok) {
        const pj = await pr.json();
        if (pj.text && pj.text.trim().length > 20) pdfText = pj.text;
      }
    } catch(_) {}

    _activateCVMode();
    const paste = document.getElementById('cvPasteText');
    if (paste) paste.value = pdfText;
    _setCvLoaded('Max Weber CV (PDF)');
    state.lastParsedText = pdfText;
    _renderCandidateProfile(_EXAMPLE_PROFILE_2);
  } catch(e) {
    alert('Could not load example CV: ' + e.message);
  } finally {
    if (tile) { tile.style.opacity = '1'; tile.style.pointerEvents = ''; }
  }
}

function loadExample3() {
  _activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = _EXAMPLE_CANDIDATE_3.text;
  _setCvLoaded('Thomas Gruber (example)');
  state.lastParsedText = _EXAMPLE_CANDIDATE_3.text;
  _renderCandidateProfile(_EXAMPLE_PROFILE_3);
}

// ── Example Candidate 4: Sophie Wagner (Data Engineer) ───────
const _EXAMPLE_CANDIDATE_4 = {
  name: 'Sophie Wagner',
  text: `Data Engineer with 5 years of experience in data pipelines, analytics and BI, based in Vienna.

Currently Data Engineer at FinanzGroup Austria (2022–present): building and maintaining ETL pipelines with Apache Airflow and Spark on Azure Databricks, designing star-schema data warehouses in Azure Synapse, delivering Power BI dashboards for the finance and operations departments. Previously Data Analyst at MediaPlus GmbH (2020–2022): built SQL-based reporting in PostgreSQL, automated Excel reporting via Python scripts, introduced Power BI company-wide. Internship at Statistik Austria (2019–2020): assisted with official statistics data processing in R and SAS.

Education: WU Wien – BSc Business Informatics (2019).
Key skills: Python, SQL, Apache Spark, Airflow, Azure Databricks, Azure Synapse, Power BI, Tableau, dbt, PostgreSQL, Git, Docker, statistics.
Languages: German (native), English C1.
Salary expectation: €3,800–4,600 gross/month.
Availability: 2 months notice. Seeking Data Engineer or Senior Analyst roles in Vienna.`,
};
const _EXAMPLE_PROFILE_4 = {
  name: 'Sophie Wagner',
  title: 'Data Engineer',
  experience_years: '5 years',
  skills: ['Python','SQL','Apache Spark','Apache Airflow','Azure Databricks','Power BI','dbt','PostgreSQL','Docker','Statistics'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,800–4,600/month',
  availability: '2 months notice',
  summary: 'Data engineer with 5 years building production pipelines on Azure; strong in Spark, Airflow and Power BI with a business informatics background.',
};

// ── Example Candidate 5: Nina Fuchs (HR Manager) ─────────────
const _EXAMPLE_CANDIDATE_5 = {
  name: 'Nina Fuchs',
  text: `HR Manager with 7 years of experience in full-cycle recruiting, HR operations and people development, based in Vienna.

Currently HR Manager at RetailGroup Austria GmbH (2021–present): responsible for end-to-end recruiting (100+ hires/year across retail and corporate), manage SAP SuccessFactors HRIS, run onboarding and offboarding processes, coordinate annual performance review cycles, advise line managers on Austrian labor law (ABGB, AngG). Previously HR Generalist at BauService AG, Vienna (2019–2021): payroll processing in SAP HR, administering collective bargaining agreements (KV), welfare and health programs. HR Assistant at AMS Wien (2017–2019): candidate counselling, job placement, labor market analysis.

Education: Uni Wien – BSc Psychology (2017). WIFI HR-Fachkraft certificate (2018).
Key skills: Full-cycle recruiting, SAP SuccessFactors, SAP HR, Austrian labor law, onboarding, payroll, performance management, employee relations, KV administration.
Languages: German (native), English B2.
Salary expectation: €3,200–3,900 gross/month.
Availability: 1 month notice. Open to HR Manager or People Partner roles in Vienna.`,
};
const _EXAMPLE_PROFILE_5 = {
  name: 'Nina Fuchs',
  title: 'HR Manager',
  experience_years: '7 years',
  skills: ['Full-cycle Recruiting','SAP SuccessFactors','SAP HR','Austrian Labor Law','Onboarding','Payroll','Performance Management','Employee Relations','KV Administration'],
  location: 'Vienna',
  languages: 'German (native), English B2',
  salary_expectation: '€3,200–3,900/month',
  availability: '1 month notice',
  summary: 'Generalist HR manager with 7 years across retail and public sector; expert in SAP SuccessFactors, Austrian labor law and high-volume recruiting.',
};

// ── Example Candidate 6: Felix Kraus (PR & Marketing Manager) ─
const _EXAMPLE_CANDIDATE_6 = {
  name: 'Felix Kraus',
  text: `PR & Marketing Manager with 6 years of experience in corporate communications, content marketing and brand management, based in Vienna.

Currently PR & Marketing Manager at TravelPlus Austria GmbH (2021–present): managing all external communications (press releases, journalist relationships, crisis PR), running paid and organic social media across LinkedIn, Instagram and TikTok (combined reach 180k), coordinating content calendar and copywriting team of 3, responsible for brand guidelines and visual identity refresh (2023). Previously Content & Social Media Manager at AgencyOne Wien (2019–2021): produced content for 8 B2C clients, managed Google Ads and Meta campaigns (€20k/month budget), grew LinkedIn company pages by an average of 45%. Marketing Coordinator at Eventim Austria (2018–2019): copywriting, event communications, newsletter campaigns (Mailchimp).

Education: FH Wien – BA Media & Communications (2018).
Key skills: PR, content marketing, social media management (LinkedIn, Instagram, TikTok), copywriting, brand strategy, Google Ads, Meta Ads, SEO basics, Adobe Creative Suite, Mailchimp, crisis communications.
Languages: German (native), English C1.
Salary expectation: €3,000–3,800 gross/month.
Availability: Immediately. Seeking PR/Marketing Manager or Head of Communications roles in Vienna.`,
};
const _EXAMPLE_PROFILE_6 = {
  name: 'Felix Kraus',
  title: 'PR & Marketing Manager',
  experience_years: '6 years',
  skills: ['PR & Communications','Content Marketing','Social Media Management','Copywriting','Brand Strategy','Google Ads','Meta Ads','Adobe Creative Suite','SEO','Crisis Communications'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,000–3,800/month',
  availability: 'Immediately',
  summary: 'PR and marketing manager with 6 years in corporate comms and digital; managed 180k social reach and €20k/month ad budgets across B2B and B2C brands.',
};

// ── Example Candidate 7: Stefan Hofer (B2B Sales Manager) ─────
const _EXAMPLE_CANDIDATE_7 = {
  name: 'Stefan Hofer',
  text: `B2B Sales Manager with 10 years of experience in enterprise software and SaaS sales, based in Vienna.

Currently Senior Account Executive at CloudSoft GmbH Austria (2020–present): managing a portfolio of 35 enterprise accounts (€2.4M ARR), consistently exceeding quota 115–130% per year, running full sales cycle from cold outreach to contract close, coordinating with pre-sales and customer success. Previously Account Manager at BusinessSoft AG, Vienna (2016–2020): grew SME segment revenue by 40% over 3 years, introduced Salesforce CRM replacing spreadsheet-based tracking, mentored two junior sales reps. Inside Sales Rep at TeleSolutions Austria (2014–2016): 200+ cold calls/week, exceeded monthly quota 18 out of 24 months.

Education: FH Wiener Neustadt – BA Business Administration (2014).
Key skills: B2B sales, SaaS, enterprise account management, Salesforce CRM, cold calling, pipeline management, contract negotiation, consultative selling, upsell/cross-sell, CRM analytics.
Languages: German (native), English C1.
Salary expectation: €4,500–5,500 gross/month + variable.
Availability: 3 months notice. Open to Sales Manager or Head of Sales roles in Austria.`,
};
const _EXAMPLE_PROFILE_7 = {
  name: 'Stefan Hofer',
  title: 'B2B Sales Manager',
  experience_years: '10 years',
  skills: ['B2B Sales','SaaS','Enterprise Account Management','Salesforce CRM','Pipeline Management','Contract Negotiation','Consultative Selling','Cold Calling','Upsell/Cross-sell'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€4,500–5,500/month + variable',
  availability: '3 months notice',
  summary: 'Enterprise SaaS sales manager with 10 years; consistently 115–130% quota, €2.4M ARR portfolio, Salesforce power user and team mentor.',
};

// ── Example Candidate 8: Julia Reiter (IT Project Manager) ────
const _EXAMPLE_CANDIDATE_8 = {
  name: 'Julia Reiter',
  text: `IT Project Manager and Scrum Master with 8 years of experience managing software delivery and digital transformation projects, based in Vienna.

Currently Senior IT Project Manager at InsureTech Austria AG (2020–present): leading a portfolio of 4 simultaneous software projects (total budget €3.2M), acting as Scrum Master for two agile squads (8–10 devs each), coordinating with C-level stakeholders, managing vendors and third-party integrations, running steering committee meetings and risk registers. Previously IT Project Manager at ConsultCo Wien (2018–2020): delivered ERP implementation (SAP S/4HANA) on time and €120k under budget, managed cross-functional team of 15. Junior PM at Telekom Austria (2016–2018): tracked project milestones, maintained JIRA boards, facilitated retrospectives.

Education: TU Wien – MSc Software Engineering & Internet Computing (2016). PMP certified (2019). PSM I (Professional Scrum Master) certified (2020).
Key skills: IT project management, Scrum / Agile, PMP, PSM I, JIRA, Confluence, SAP S/4HANA delivery, stakeholder management, vendor management, risk management, budgeting, change management.
Languages: German (native), English C1.
Salary expectation: €4,500–5,500 gross/month.
Availability: 2 months notice. Open to IT PM or Programme Manager roles in Vienna.`,
};
const _EXAMPLE_PROFILE_8 = {
  name: 'Julia Reiter',
  title: 'IT Project Manager / Scrum Master',
  experience_years: '8 years',
  skills: ['IT Project Management','Scrum / Agile','PMP','JIRA','Confluence','SAP S/4HANA','Stakeholder Management','Vendor Management','Risk Management','Change Management'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€4,500–5,500/month',
  availability: '2 months notice',
  summary: 'Certified PMP & Scrum Master with 8 years delivering IT projects up to €3.2M; SAP S/4HANA experience and strong agile + stakeholder management track record.',
};

// ── Example Candidate 9: Roman Labuš (Python / data, text) ───
const _EXAMPLE_CANDIDATE_9 = {
  name: 'Roman Labuš',
  text: `Python Developer with ~4 years of experience in web scraping, ETL pipelines and LLM-based data enrichment, based in Bratislava.

Currently Programmer at Acme Recruitment, Bratislava (Aug 2022–present): built and maintained web-scraping solutions for internal competitive-intelligence products (real-estate market, lead research, jobs intelligence). Built automated scrapers in Python with Playwright and Selenium that collect high-value market data, directly generating €100k+ in yearly revenue. Developed ETL pipelines with Apache Airflow and Pandas to load large datasets into SQL databases, integrated Apify to replace manual data collection, and contributed to LLM-based data-enrichment workflows in close collaboration with analysts. Built internal IT tools, project-tracking dashboards and reporting that gave management real-time visibility. Research Intern – Discussion Toxicity Prediction at KInIT (Aug 2023–Jun 2024): trained multilingual models classifying toxic social-media content and built visualizations for end users. Earlier: Copywriter at WebSupport s.r.o. (2016–2022) and Vice President for PR at NGO BEST Bratislava (2021–2022).

Education: Slovak University of Technology, FIIT Bratislava – Information & Communication Technologies (2022–2024); University of Logistics (VŠLG) Bratislava – Informatics in Logistics (2025–present).
Key skills: Python, web scraping (Playwright, Selenium, Apify), ETL, Apache Airflow, Pandas, MySQL/SQL, LLM data enrichment, dashboards, Java (basic).
Languages: Slovak (native), English C1, German B2.
Driving licence: B. Interests: philosophy & business discussion clubs, improv theatre, writing a sci-fi novel ("Mission 77").`,
};
const _EXAMPLE_PROFILE_9 = {
  name: 'Roman Labuš',
  title: 'Python Developer (Web Scraping & Data)',
  experience_years: '4 years',
  skills: ['Python','Web Scraping','Playwright','Selenium','Apify','ETL','Apache Airflow','Pandas','MySQL','LLM Data Enrichment','Dashboards','Java (basic)'],
  location: 'Bratislava',
  languages: 'Slovak (native), English C1, German B2',
  education: 'ICT — FIIT STU Bratislava',
  summary: 'Python developer with ~4 years building production web-scraping and ETL pipelines (Playwright, Selenium, Apify, Airflow) plus LLM-based data enrichment; scrapers generated €100k+ in annual revenue.',
};

// ── Unified example catalogue (Austria) ──────────────────────
const _EXAMPLES_AT = [
  { area:'IT',        areaClass:'it',       name:'Roman Labuš',   desc:'Python · Web Scraping · Airflow · Apify · ETL · LLM', load: ()=>_loadExDirect(9) },
  { area:'IT',        areaClass:'it',       name:'Max Weber',     desc:'Python · FastAPI · React · PostgreSQL · Docker',    badge:'PDF',  load: ()=>loadExamplePdf() },
  { area:'IT',        areaClass:'it',       name:'Julia Reiter',  desc:'IT Project Mgmt · Scrum · PMP · JIRA · SAP S/4HANA', load: ()=>_loadExDirect(8) },
  { area:'Data',      areaClass:'data',     name:'Sophie Wagner', desc:'Python · Spark · Airflow · Azure · Power BI · dbt', load: ()=>_loadExDirect(4) },
  { area:'HR',        areaClass:'hr',       name:'Nina Fuchs',    desc:'Recruiting · SAP SuccessFactors · Labor Law · Payroll', load: ()=>_loadExDirect(5) },
  { area:'PR',        areaClass:'pr',       name:'Felix Kraus',   desc:'PR · Content Marketing · Social Media · Brand Strategy', load: ()=>_loadExDirect(6) },
  { area:'Sales',     areaClass:'sales',    name:'Stefan Hofer',  desc:'B2B Sales · SaaS · Salesforce · Enterprise Accounts', load: ()=>_loadExDirect(7) },
  { area:'Finance',   areaClass:'finance',  name:'Thomas Gruber', desc:'IFRS · Group Consolidation · SAP S/4HANA · M&A',    load: ()=>loadExample3() },
  { area:'Logistics', areaClass:'logistics',name:'Anna Bauer',    desc:'SAP WM · Forklift · Team Leadership · KPI Reporting', load: ()=>loadExampleText() },
];

// ── Slovak example candidates (shown when COUNTRY=sk) ─────────
// Self-contained: each item carries its own parsed text + profile, plus an
// optional PDF endpoint. Bratislava/Košice/Žilina, Slovak languages, Slovak
// market salaries — the SK counterpart to the Austrian set above.
const _SK_EXAMPLES_DATA = [
  { area:'IT', areaClass:'it', name:'Roman Labuš',
    desc:'Python · Web Scraping · Airflow · Apify · ETL · LLM',
    cand:{ name:'Roman Labuš', text:`Python Developer with ~4 years of experience in web scraping, ETL pipelines and LLM-based data enrichment, based in Bratislava.

Currently Programmer at Acme Recruitment, Bratislava (Aug 2022–present): built and maintained web-scraping solutions for internal competitive-intelligence products (real-estate market, lead research, jobs intelligence). Built automated scrapers in Python with Playwright and Selenium that collect high-value market data, directly generating €100k+ in yearly revenue. Developed ETL pipelines with Apache Airflow and Pandas to load large datasets into SQL databases, integrated Apify to replace manual data collection, and contributed to LLM-based data-enrichment workflows in close collaboration with analysts. Built internal IT tools, project-tracking dashboards and reporting that gave management real-time visibility. Research Intern – Discussion Toxicity Prediction at KInIT (Aug 2023–Jun 2024): trained multilingual models classifying toxic social-media content and built visualizations for end users. Earlier: Copywriter at WebSupport s.r.o. (2016–2022) and Vice President for PR at NGO BEST Bratislava (2021–2022).

Education: Slovak University of Technology, FIIT Bratislava – Information & Communication Technologies (2022–2024); University of Logistics (VŠLG) Bratislava – Informatics in Logistics (2025–present).
Key skills: Python, web scraping (Playwright, Selenium, Apify), ETL, Apache Airflow, Pandas, MySQL/SQL, LLM data enrichment, dashboards, Java (basic).
Languages: Slovak (native), English C1, German B2.
Driving licence: B. Interests: philosophy & business discussion clubs, improv theatre, writing a sci-fi novel ("Mission 77").` },
    prof:{ name:'Roman Labuš', title:'Python Developer (Web Scraping & Data)', experience_years:'4 years',
      skills:['Python','Web Scraping','Playwright','Selenium','Apify','ETL','Apache Airflow','Pandas','MySQL','LLM Data Enrichment','Dashboards','Java (basic)'],
      location:'Bratislava', languages:'Slovak (native), English C1, German B2',
      education:'ICT — FIIT STU Bratislava',
      summary:'Python developer with ~4 years building production web-scraping and ETL pipelines (Playwright, Selenium, Apify, Airflow) plus LLM-based data enrichment; scrapers generated €100k+ in annual revenue.' } },

  { area:'IT', areaClass:'it', name:'Marek Novák', badge:'PDF',
    pdf:'/api/candidate/example-pdf-sk', pdfFile:'Marek_Novak_CV.pdf',
    desc:'Python · FastAPI · React · PostgreSQL · Docker',
    cand:{ name:'Marek Novák', text:`Software Developer with 5 years of experience in backend and full-stack development, based in Bratislava.

Currently Backend Developer at TechSolutions s.r.o. Bratislava (2022–present): building REST APIs in Python/FastAPI, maintaining PostgreSQL databases, deploying services via Docker and CI/CD pipelines (GitLab CI). Previously Junior Developer at WebFactory s.r.o. (2020–2022): developed React frontends and Node.js services, contributed to agile sprint planning and code reviews. IT Intern at Startup Hub Bratislava (2019–2020): built internal tooling with Python.

Education: FIIT STU Bratislava – Ing. (MSc) Informatics (2019).
Key skills: Python, FastAPI, JavaScript/TypeScript, React, Node.js, PostgreSQL, Docker, Git, REST APIs, Linux, CI/CD.
Languages: Slovak (native), Czech (fluent), English C1.
Salary expectation: €2,800–3,600 gross/month.
Availability: 2 months notice. Seeking full-time permanent role in Bratislava.` },
    prof:{ name:'Marek Novák', title:'Backend & Full-Stack Developer', experience_years:'5 years',
      skills:['Python','FastAPI','JavaScript/TypeScript','React','Node.js','PostgreSQL','Docker','Git','REST APIs','Linux','CI/CD'],
      location:'Bratislava', languages:'Slovak (native), Czech, English C1',
      salary_expectation:'€2,800–3,600/month', availability:'2 months notice',
      education:'Ing. (MSc) Informatics, FIIT STU Bratislava',
      summary:'Full-stack developer with 5 years in Python backends and React frontends, comfortable with Docker deployments and agile teams.' } },

  { area:'IT', areaClass:'it', name:'Lucia Horváthová',
    desc:'IT Project Mgmt · Scrum · PMP · JIRA · ERP delivery',
    cand:{ name:'Lucia Horváthová', text:`IT Project Manager and Scrum Master with 8 years of experience managing software delivery projects, based in Bratislava.

Currently Senior IT Project Manager at InsureTech Slovakia a.s. (2020–present): leading 4 simultaneous software projects (total budget €2.4M), acting as Scrum Master for two agile squads (8–10 devs each), coordinating with C-level stakeholders and vendors. Previously IT Project Manager at ConsultCo Bratislava (2018–2020): delivered an ERP implementation on time and under budget, managed a cross-functional team of 15. Junior PM at Slovak Telekom (2016–2018): tracked milestones, maintained JIRA boards, facilitated retrospectives.

Education: FEI STU Bratislava – Ing. Software Engineering (2016). PMP certified (2019). PSM I certified (2020).
Key skills: IT project management, Scrum/Agile, PMP, PSM I, JIRA, Confluence, ERP delivery, stakeholder management, vendor management, risk management, budgeting.
Languages: Slovak (native), English C1, German B1.
Salary expectation: €3,000–3,800 gross/month.
Availability: 2 months notice. Open to IT PM or Programme Manager roles in Bratislava.` },
    prof:{ name:'Lucia Horváthová', title:'IT Project Manager / Scrum Master', experience_years:'8 years',
      skills:['IT Project Management','Scrum / Agile','PMP','JIRA','Confluence','ERP Delivery','Stakeholder Management','Vendor Management','Risk Management'],
      location:'Bratislava', languages:'Slovak (native), English C1, German B1',
      salary_expectation:'€3,000–3,800/month', availability:'2 months notice',
      summary:'Certified PMP & Scrum Master with 8 years delivering IT projects up to €2.4M; strong agile and stakeholder management track record.' } },

  { area:'Data', areaClass:'data', name:'Tomáš Kováč',
    desc:'Python · Spark · Airflow · Azure · Power BI · dbt',
    cand:{ name:'Tomáš Kováč', text:`Data Engineer with 5 years of experience in data pipelines, analytics and BI, based in Košice.

Currently Data Engineer at FinGroup Slovakia (2022–present): building ETL pipelines with Apache Airflow and Spark on Azure Databricks, designing star-schema data warehouses in Azure Synapse, delivering Power BI dashboards for finance and operations. Previously Data Analyst at MediaPlus s.r.o. (2020–2022): built SQL reporting in PostgreSQL, automated Excel reporting via Python, rolled out Power BI company-wide. Internship at the Statistical Office of the SR (2019–2020): data processing in R.

Education: TUKE Košice – Ing. Informatics (2019).
Key skills: Python, SQL, Apache Spark, Airflow, Azure Databricks, Azure Synapse, Power BI, dbt, PostgreSQL, Git, Docker, statistics.
Languages: Slovak (native), English C1.
Salary expectation: €2,600–3,400 gross/month.
Availability: 1 month notice. Seeking Data Engineer or Senior Analyst roles in Košice or remote.` },
    prof:{ name:'Tomáš Kováč', title:'Data Engineer', experience_years:'5 years',
      skills:['Python','SQL','Apache Spark','Apache Airflow','Azure Databricks','Power BI','dbt','PostgreSQL','Docker','Statistics'],
      location:'Košice', languages:'Slovak (native), English C1',
      salary_expectation:'€2,600–3,400/month', availability:'1 month notice',
      summary:'Data engineer with 5 years building production pipelines on Azure; strong in Spark, Airflow and Power BI.' } },

  { area:'HR', areaClass:'hr', name:'Zuzana Krajčíová',
    desc:'Recruiting · SuccessFactors · Labour Law · Payroll',
    cand:{ name:'Zuzana Krajčíová', text:`HR Manager with 7 years of experience in full-cycle recruiting, HR operations and people development, based in Bratislava.

Currently HR Manager at RetailGroup Slovakia s.r.o. (2021–present): end-to-end recruiting (100+ hires/year), managing SAP SuccessFactors HRIS, onboarding/offboarding, annual performance reviews, advising line managers on the Slovak Labour Code (Zákonník práce). Previously HR Generalist at BauService a.s. Bratislava (2019–2021): payroll processing, administering collective agreements. HR Assistant at ÚPSVR (labour office) Bratislava (2017–2019): candidate counselling, job placement.

Education: Comenius University Bratislava – Mgr. Psychology (2017).
Key skills: Full-cycle recruiting, SAP SuccessFactors, Slovak Labour Code, onboarding, payroll, performance management, employee relations.
Languages: Slovak (native), English B2.
Salary expectation: €2,200–2,900 gross/month.
Availability: 1 month notice. Open to HR Manager or People Partner roles in Bratislava.` },
    prof:{ name:'Zuzana Krajčíová', title:'HR Manager', experience_years:'7 years',
      skills:['Full-cycle Recruiting','SAP SuccessFactors','Slovak Labour Code','Onboarding','Payroll','Performance Management','Employee Relations'],
      location:'Bratislava', languages:'Slovak (native), English B2',
      salary_expectation:'€2,200–2,900/month', availability:'1 month notice',
      summary:'Generalist HR manager with 7 years across retail and public sector; expert in SAP SuccessFactors and the Slovak Labour Code.' } },

  { area:'PR', areaClass:'pr', name:'Martin Šimko',
    desc:'PR · Content Marketing · Social Media · Brand Strategy',
    cand:{ name:'Martin Šimko', text:`PR & Marketing Manager with 6 years of experience in corporate communications, content marketing and brand management, based in Bratislava.

Currently PR & Marketing Manager at TravelPlus Slovakia s.r.o. (2021–present): managing external communications and press relationships, running paid and organic social media across LinkedIn, Instagram and TikTok (combined reach 150k), coordinating a content team of 3, owning brand guidelines. Previously Content & Social Media Manager at AgencyOne Bratislava (2019–2021): content for 8 B2C clients, Google and Meta campaigns (€15k/month budget). Marketing Coordinator at Eventim Slovakia (2018–2019): copywriting, newsletter campaigns.

Education: Comenius University Bratislava – Mgr. Media & Communications (2018).
Key skills: PR, content marketing, social media (LinkedIn, Instagram, TikTok), copywriting, brand strategy, Google Ads, Meta Ads, SEO basics, Adobe Creative Suite.
Languages: Slovak (native), English C1.
Salary expectation: €1,800–2,400 gross/month.
Availability: Immediately. Seeking PR/Marketing Manager roles in Bratislava.` },
    prof:{ name:'Martin Šimko', title:'PR & Marketing Manager', experience_years:'6 years',
      skills:['PR & Communications','Content Marketing','Social Media Management','Copywriting','Brand Strategy','Google Ads','Meta Ads','Adobe Creative Suite','SEO'],
      location:'Bratislava', languages:'Slovak (native), English C1',
      salary_expectation:'€1,800–2,400/month', availability:'Immediately',
      summary:'PR and marketing manager with 6 years in corporate comms and digital; managed 150k social reach and €15k/month ad budgets.' } },

  { area:'Sales', areaClass:'sales', name:'Peter Varga',
    desc:'B2B Sales · SaaS · Salesforce · Enterprise Accounts',
    cand:{ name:'Peter Varga', text:`B2B Sales Manager with 10 years of experience in enterprise software and SaaS sales, based in Bratislava.

Currently Senior Account Executive at CloudSoft Slovakia s.r.o. (2020–present): managing 35 enterprise accounts (€2.0M ARR), consistently exceeding quota 115–130% per year, running the full sales cycle from outreach to close. Previously Account Manager at BusinessSoft a.s. Bratislava (2016–2020): grew SME revenue by 40% over 3 years, introduced Salesforce CRM, mentored two junior reps. Inside Sales Rep at TeleSolutions Slovakia (2014–2016): 200+ cold calls/week, exceeded quota 18 of 24 months.

Education: University of Economics in Bratislava – Ing. Business Administration (2014).
Key skills: B2B sales, SaaS, enterprise account management, Salesforce CRM, pipeline management, contract negotiation, consultative selling, upsell/cross-sell.
Languages: Slovak (native), English C1, Hungarian B2.
Salary expectation: €2,500–3,200 gross/month + variable.
Availability: 3 months notice. Open to Sales Manager or Head of Sales roles in Slovakia.` },
    prof:{ name:'Peter Varga', title:'B2B Sales Manager', experience_years:'10 years',
      skills:['B2B Sales','SaaS','Enterprise Account Management','Salesforce CRM','Pipeline Management','Contract Negotiation','Consultative Selling','Upsell/Cross-sell'],
      location:'Bratislava', languages:'Slovak (native), English C1, Hungarian B2',
      salary_expectation:'€2,500–3,200/month + variable', availability:'3 months notice',
      summary:'Enterprise SaaS sales manager with 10 years; consistently 115–130% quota, €2.0M ARR portfolio and Salesforce power user.' } },

  { area:'Finance', areaClass:'finance', name:'Eva Tóthová',
    desc:'IFRS · Group Consolidation · SAP S/4HANA · Audit',
    cand:{ name:'Eva Tóthová', text:`Director Group Finance with 15 years of experience in corporate finance, IFRS reporting and controlling, based in Bratislava.

Currently Head of Group Finance at Bratislava Medtech a.s. (2019–present): responsible for consolidated IFRS statements, management reporting to the board, coordination of the annual audit (Big 4). Previously Senior Finance Manager at Industrial Group Slovakia a.s. (2014–2019): led a team of 6 controllers, implemented SAP S/4HANA group-wide, reduced the monthly close from 12 to 7 days. Earlier: Finance Controller (2011–2014) and Audit Senior at Deloitte Bratislava (2008–2011).

Education: University of Economics in Bratislava – Ing. Finance & Accounting (2008). ACCA (2013).
Key skills: IFRS, group consolidation, SAP S/4HANA, financial analysis, management reporting, budgeting & forecasting, M&A due diligence, team leadership, Big 4 audit background.
Languages: Slovak (native), English C1.
Salary expectation: €4,500–6,000 gross/month.
Availability: 3 months notice. Open to CFO or Director Group Finance roles in Bratislava.` },
    prof:{ name:'Eva Tóthová', title:'Director Group Finance', experience_years:'15 years',
      skills:['IFRS','Group Consolidation','SAP S/4HANA','Financial Analysis','Management Reporting','Budgeting & Forecasting','M&A Due Diligence','Team Leadership','ACCA'],
      location:'Bratislava', languages:'Slovak (native), English C1',
      salary_expectation:'€4,500–6,000/month', availability:'3 months notice',
      summary:'Senior finance director with 15 years across Big 4 audit, controlling and group finance; IFRS and SAP S/4HANA expert.' } },

  { area:'Logistics', areaClass:'logistics', name:'Jana Kováčová',
    desc:'SAP WM · Forklift · Team Leadership · KPI Reporting',
    cand:{ name:'Jana Kováčová', text:`Logistics and Warehouse Supervisor with 8 years of experience in high-volume distribution, based in Žilina.

Certified forklift operator (vysokozdvižný vozík, valid until 2027). SAP Warehouse Management certified user (2020). Currently Senior Warehouse Supervisor at MegaLogistics s.r.o. Žilina (2019–present): leading a team of 12 across two shifts, introduced SAP WM reducing stock discrepancies by 23%, responsible for KPI reporting (fill rate, OTIF, pick accuracy). Previously Warehouse Coordinator at SlovPack a.s. (2016–2019): coordinated 2,000+ orders/day pick & pack, trained 8 staff.

Key skills: SAP WM, forklift operation, inventory management, team leadership, lean logistics, FIFO/FEFO, MS Excel, KPI reporting.
Languages: Slovak (native), English B2.
Salary expectation: €1,400–1,900 gross/month.
Availability: Immediately. Seeking full-time permanent role in Žilina region.` },
    prof:{ name:'Jana Kováčová', title:'Logistics & Warehouse Supervisor', experience_years:'8 years',
      skills:['Forklift Licence','SAP WM','Team Leadership','Inventory Management','KPI Reporting','Lean Logistics','MS Excel','FIFO/FEFO'],
      location:'Žilina', languages:'Slovak (native), English B2',
      salary_expectation:'€1,400–1,900/month', availability:'Immediately',
      summary:'Experienced logistics supervisor with 8 years in high-volume distribution; certified forklift operator with SAP WM expertise.' } },
];

// Generic loader for a Slovak example item (PDF download + parse when present,
// otherwise just the bundled text). Mirrors loadExamplePdf / loadExampleText.
async function _loadSkExample(item) {
  _activateCVMode();
  let text = item.cand.text;
  if (item.pdf) {
    try {
      const res = await fetch(item.pdf);
      if (res.ok) {
        const blob = await res.blob();
        const fd = new FormData();
        fd.append('file', blob, item.pdfFile || 'CV.pdf');
        const pr = await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd });
        if (pr.ok) {
          const pj = await pr.json();
          if (pj.text && pj.text.trim().length > 20) text = pj.text;
        }
      }
    } catch(_) {}
  }
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = text;
  _setCvLoaded(item.badge === 'PDF' ? `${item.name} CV (PDF)` : `${item.name} (example)`);
  state.lastParsedText = text;
  _renderCandidateProfile(item.prof);
}

const _EXAMPLES_SK = _SK_EXAMPLES_DATA.map(item => ({
  area: item.area, areaClass: item.areaClass, name: item.name,
  desc: item.desc, badge: item.badge, load: () => _loadSkExample(item),
}));

// Active example set — Slovak when COUNTRY=sk, Austrian otherwise.
const _EXAMPLES = ("{{ country_code }}" === "sk") ? _EXAMPLES_SK : _EXAMPLES_AT;

function _loadExDirect(n) {
  const map = {
    4: [_EXAMPLE_CANDIDATE_4, _EXAMPLE_PROFILE_4, 'Sophie Wagner (example)'],
    5: [_EXAMPLE_CANDIDATE_5, _EXAMPLE_PROFILE_5, 'Nina Fuchs (example)'],
    6: [_EXAMPLE_CANDIDATE_6, _EXAMPLE_PROFILE_6, 'Felix Kraus (example)'],
    7: [_EXAMPLE_CANDIDATE_7, _EXAMPLE_PROFILE_7, 'Stefan Hofer (example)'],
    8: [_EXAMPLE_CANDIDATE_8, _EXAMPLE_PROFILE_8, 'Julia Reiter (example)'],
    9: [_EXAMPLE_CANDIDATE_9, _EXAMPLE_PROFILE_9, 'Roman Labuš (example)'],
  };
  const [cand, prof, label] = map[n];
  _activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = cand.text;
  _setCvLoaded(label);
  state.lastParsedText = cand.text;
  _renderCandidateProfile(prof);
}

function _exToggle() {
  const dd = document.getElementById('exDropdown');
  dd.classList.toggle('open');
}

function _exClose() {
  document.getElementById('exDropdown')?.classList.remove('open');
}

// Build dropdown items once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('exDropdownPanel');
  if (!panel) return;
  _EXAMPLES.forEach((ex, i) => {
    const el = document.createElement('div');
    el.className = 'ex-dropdown-item';
    el.innerHTML = `<span class="ex-area ex-area--${ex.areaClass}">${ex.area}</span>
      <div class="ex-item-body">
        <div class="ex-item-name">${ex.name}${ex.badge ? `<span class="ex-item-badge">${ex.badge}</span>` : ''}</div>
        <div class="ex-item-desc">${ex.desc}</div>
      </div>`;
    el.addEventListener('click', () => { ex.load(); _exClose(); });
    panel.appendChild(el);
  });
  // Close on outside click
  document.addEventListener('click', e => {
    if (!document.getElementById('exDropdown')?.contains(e.target)) _exClose();
  });
});

// ════════════════════════════════════════════════════════════
//  Build candidate text from active mode
// ════════════════════════════════════════════════════════════
function buildCandidateText() {
  let base;
  if (state.activeMode === 'cv') {
    base = document.getElementById('cvPasteText').value.trim();
  } else if (state.activeMode === 'linkedin') {
    base = (_linkedinText || '').trim();
  } else {
    // Guided: assemble from the shared draft object.
    const d = state.gbDraft;
    const parts = [];
    const list = (arr) => (arr || []).filter(Boolean).join(', ');
    if (list(d.roles))      parts.push(`Target role: ${list(d.roles)}`);
    if (list(d.levels))     parts.push(`Experience: ${list(d.levels)}`);
    if (list(d.skills))     parts.push(`Key skills: ${list(d.skills)}`);
    if (list(d.languages))  parts.push(`Languages: ${list(d.languages)}`);
    if (list(d.certs))      parts.push(`Certifications/licenses: ${list(d.certs)}`);
    if (list(d.states))     parts.push(`Location preference: ${list(d.states)}`);
    if (list(d.sector))     parts.push(`Sector: ${list(d.sector)}`);
    if (d.salary)           parts.push(`Salary expectation: ${d.salary}`);
    if (d.availability)     parts.push(`Availability: ${d.availability}`);
    if (d.notes)            parts.push(d.notes);
    base = parts.join('\n');
  }
  // A candidate loaded from the database has a structured profile but no raw CV
  // text — derive matching text from the profile so Run matching still works.
  if (!base && state.currentCandidateProfile) base = _profileToText(state.currentCandidateProfile);
  return _withAsstNotes(base || '');
}

// Reconstruct a plain-text candidate description from a structured profile dict,
// used when matching a DB-loaded candidate that has no raw CV/LinkedIn text.
function _profileToText(p) {
  if (!p) return '';
  const parts = [];
  const list  = (a) => (Array.isArray(a) ? a.filter(Boolean).join(', ') : '');
  if (p.name)               parts.push(p.name);
  if (p.title)              parts.push('Title: ' + p.title);
  if (p.seniority)          parts.push('Seniority: ' + p.seniority);
  const yrs = p.years_experience || p.experience_years;
  if (yrs)                  parts.push('Experience: ' + yrs + (/\d\s*(year|yr)/i.test(String(yrs)) ? '' : ' years'));
  const skills = (Array.isArray(p.top_skills) && p.top_skills.length) ? p.top_skills : (p.skills || []);
  if (list(skills))         parts.push('Skills: ' + list(skills));
  if (list(p.specializations)) parts.push('Specializations: ' + list(p.specializations));
  if (list(p.certifications))  parts.push('Certifications: ' + list(p.certifications));
  if (p.languages)          parts.push('Languages: ' + p.languages);
  if (p.location)           parts.push('Location: ' + p.location);
  if (p.industry)           parts.push('Industry: ' + p.industry);
  if (p.role_category)      parts.push('Role: ' + p.role_category);
  if (p.salary_expectation) parts.push('Salary expectation: ' + p.salary_expectation);
  if (p.availability)       parts.push('Availability: ' + p.availability);
  if (p.ai_summary || p.summary) parts.push(p.ai_summary || p.summary);
  if (Array.isArray(p.experiences) && p.experiences.length) {
    const hist = p.experiences.slice(0, 6)
      .map(e => [e.title, e.company].filter(Boolean).join(' at '))
      .filter(Boolean).join('; ');
    if (hist) parts.push('Experience history: ' + hist);
  }
  return parts.join('\n');
}

// Fold any CV details the candidate assistant added into the matching text,
// regardless of input mode, so a re-run reflects them.
function _withAsstNotes(base) {
  if (!state.candAsstNotes.length) return base;
  const extra = 'Additional details: ' + state.candAsstNotes.join(' ');
  return base ? (base + '\n' + extra) : extra;
}


// Action registry for the candidate-bar / example-dropdown / workflow-toggle /
// CV-zone-browse controls in the search-tab markup — split out of that tab's
// mixed registry block since these route to this module.
Object.assign(_ACTIONS, {
  'start-edit-candidate-name': ()    => startEditCandidateName(),
  'candidate-name-enter':    (el, e) => { if (e.key === 'Enter') confirmCandidateName(); },
  'confirm-candidate-name':  ()      => confirmCandidateName(),
  'ex-toggle':               ()      => _exToggle(),
  'clear-candidate-profile': ()      => clearCandidateProfile(),
  'set-workflow':            (el)    => setWorkflow(el.dataset.workflow),
  // CV zone — browse link (preserve the original preventDefault + stopPropagation)
  'browse-cv':               (el, e) => { e.preventDefault(); e.stopPropagation(); document.getElementById('cvFileInput').click(); },
});

// Cross-module exports — registered on app so search/assistant/guided/saved/modal
// can call into this module without a direct import (avoids circular references).
Object.assign(app, {
  buildCandidateText, setWorkflow, _renderCandidateProfile, ensureLinkedInScraped,
  _initials, openCompanyPanel, closeCompanyPanel, closeCvPreview, clearCandidateProfile,
});
