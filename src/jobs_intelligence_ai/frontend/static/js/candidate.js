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

// Open the Saved tab (the database view of saved candidates / jobs / companies / contacts).
function _gotoSavedLocal() {
  app._activateTab('saved');
}

// Activate the CV input mode (tab + zone) directly, without going through the
// mode-tab click handler — used by DB-load seeding and every example loader.
function _activateCVMode() {
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.input-zone').forEach(z => z.classList.remove('active'));
  const cvTab = document.querySelector('.mode-tab[data-mode="cv"]');
  if (cvTab) cvTab.classList.add('active');
  const zone = document.getElementById('zone-cv');
  if (zone) zone.classList.add('active');
  state.activeMode = 'cv';
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
  // Used by candidate-examples.js to load a bundled example into the CV zone.
  _activateCVMode, _setCvLoaded,
});
