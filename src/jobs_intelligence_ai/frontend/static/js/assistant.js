// ════════════════════════════════════════════════════════════
//  Candidate assistant (docked main-page chat)
// ════════════════════════════════════════════════════════════
// The docked chat that discusses the active candidate: highlight matching jobs
// by a free-text criterion, analyze fit against the current results, score a
// pasted job URL, and merge structured profile updates the assistant proposes
// back into the candidate card.
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";
import api from "./api.js";

// ════════════════════════════════════════════════════════════
//  Candidate assistant (docked main-page chat)
// ════════════════════════════════════════════════════════════
let _candAsstStarted = false;   // greeting shown yet?
let _candAsstBusy    = false;
let _candAsstMode    = '';      // '' = normal chat; 'highlight' = next msg is a highlight criterion
const _CAND_ASST_LIST_FIELDS = ['skills', 'top_skills', 'strengths', 'certifications'];

// Highlight state — a natural-language criterion + the job_ids that matched it.
// Sticky: re-applied automatically after a re-run so new offers are evaluated too.

function candAsstToggleMenu(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('candAsstMenu');
  const btn  = document.getElementById('candAsstToolsBtn');
  const open = menu.classList.toggle('open');
  btn.classList.toggle('on', open);
}
function _closeCandAsstMenu() {
  document.getElementById('candAsstMenu')?.classList.remove('open');
  document.getElementById('candAsstToolsBtn')?.classList.remove('on');
}
document.addEventListener('click', e => {
  if (!e.target.closest?.('.cand-asst-tools')) _closeCandAsstMenu();
});

// Start the highlight flow: arm highlight mode and ask what to highlight.
function candAsstStartHighlight() {
  _closeCandAsstMenu();
  if (document.getElementById('candAsst').classList.contains('collapsed')) candAsstToggle();
  _candAsstStarted = true;
  _candAsstMode = 'highlight';
  candAsstAppendAi("What would you like to highlight? Describe it in plain language — for example:", {
    chips: ['Travel benefits', 'Remote-friendly', 'High salary', 'No German required'],
  });
  document.getElementById('candAsstMsg').focus();
}

function candAsstClearHighlight() {
  _closeCandAsstMenu();
  state.highlightCriterion = '';
  state.highlightedJobIds  = new Set();
  document.getElementById('candAsstClearHlBtn').style.display = 'none';
  if (state.lastResults.length) app.renderResults(state.lastResults);
}

// Overall analysis: how the candidate stacks up against the CURRENT matched jobs —
// strengths, recurring gaps, and what to work on. Reads the on-screen result set.
async function candAsstAnalyzeFit() {
  _closeCandAsstMenu();
  if (document.getElementById('candAsst').classList.contains('collapsed')) candAsstToggle();
  _candAsstStarted = true;

  if (!state.lastResults.length) {
    candAsstAppendAi('Run matching first so there are jobs to analyze the candidate against.');
    return;
  }
  const text = state.lastMatchText || app.buildCandidateText();
  if (!text) { candAsstAppendAi('Add a candidate profile first, then run matching.'); return; }

  const thread = document.getElementById('candAsstThread');
  const typing = document.createElement('div');
  typing.className = 'chat-msg ai'; typing.id = 'candAsstTyping';
  typing.innerHTML = '<div class="chat-typing">Analyzing the candidate against the matched jobs…</div>';
  thread.appendChild(typing); candAsstScroll();

  const jobs = state.lastResults.slice(0, 30).map(j => ({
    title: j.title, company: j.company, grade: j.grade, score_pct: j.score_pct,
    city: j.city, state: j.state, skills: j.skills, skills_en: j.skills_en,
    summary: j.summary, description: (j.description || '').slice(0, 300),
  }));

  try {
    const data = await api.post('/api/match/analyze', { candidate_text: text, jobs });
    document.getElementById('candAsstTyping')?.remove();
    candAsstAppendAi(data.text || 'No analysis returned.');
  } catch(e) {
    document.getElementById('candAsstTyping')?.remove();
    candAsstAppendAi('Network error: ' + e.message);
  }
}

// Start the URL-match flow: arm url mode and ask for a posting URL.
function candAsstStartUrlMatch() {
  _closeCandAsstMenu();
  if (document.getElementById('candAsst').classList.contains('collapsed')) candAsstToggle();
  _candAsstStarted = true;
  _candAsstMode = 'url';
  candAsstAppendAi("Paste a job posting URL and I'll score it against the current candidate profile. " +
                   "Only postings already in the database are supported for now — live scraping is coming soon.");
  document.getElementById('candAsstMsg').focus();
}

// Grade ONE job — looked up by its posting URL — against the current candidate.
async function matchJobUrl(url) {
  url = (url || '').trim();
  if (!url) { _candAsstMode = ''; return; }

  const profileText = app.buildCandidateText();
  if (!profileText) {
    candAsstAppendAi('Add a candidate profile first, then paste a job URL to score it.');
    _candAsstMode = '';
    return;
  }

  const thread = document.getElementById('candAsstThread');
  const typing = document.createElement('div');
  typing.className = 'chat-msg ai'; typing.id = 'candAsstTyping';
  typing.innerHTML = '<div class="chat-typing">Scoring that posting…</div>';
  thread.appendChild(typing); candAsstScroll();

  try {
    const data = await api.post('/api/match/url', { candidate_text: profileText, url });
    document.getElementById('candAsstTyping')?.remove();
    if (!data.in_db)   { candAsstAppendAi(data.message || "That URL isn't in the database yet."); return; }
    const j   = data.job;
    const loc = [j.city, j.state].filter(Boolean).join(', ');
    candAsstAppendUrlResult(
      `${j.title} @ ${j.company}${loc ? ' · ' + loc : ''} — graded ${j.grade} (${j.score_pct}).` +
      (j.match_reason ? ' ' + j.match_reason : ''),
      j
    );
  } catch(e) {
    document.getElementById('candAsstTyping')?.remove();
    candAsstAppendAi('Network error: ' + e.message);
  } finally {
    _candAsstMode = '';
  }
}

// AI bubble for a URL match, with an "Add to results" button that injects the
// graded job into the on-screen offers table. Built directly (not via
// candAsstAppendAi) so the button can carry the job object via a closure.
function candAsstAppendUrlResult(text, job) {
  const el = document.createElement('div');
  el.className = 'chat-msg ai';
  const already = state.lastResults.some(r => String(r.job_id) === String(job.job_id));
  el.innerHTML =
    `<div class="chat-bubble">${esc(text)}</div>` +
    `<div class="cand-asst-update">
       <button type="button" class="cand-asst-rerun"${already ? ' disabled' : ''}>
         ${already ? '✓ Already in results' : '➕ Add to results'}
       </button>
     </div>`;
  if (!already) {
    el.querySelector('button').addEventListener('click', ev => addUrlJobToResults(job, ev.currentTarget));
  }
  document.getElementById('candAsstThread').appendChild(el);
  candAsstScroll();
}

// Inject a single URL-matched job into the results table (dedupe by job_id), then
// re-rank by score so it lands where it belongs among the existing offers. The job
// is pinned so it's visible even when it's a weak (C) match (which the table hides
// by default) and sticks across re-runs — it was added deliberately.
function addUrlJobToResults(job, btn) {
  const id = String(job.job_id);
  if (!state.lastResults.some(r => String(r.job_id) === id)) {
    state.lastResults.push(job);
    state.lastResults.sort((a, b) => (b.score || 0) - (a.score || 0));
  }
  state.dismissedJobIds.delete(id);   // a re-added job must not stay hidden by a prior dismiss
  state.pinnedJobIds.add(id);         // pin: keeps weak matches visible and sticks across re-runs
  app.renderResults(state.lastResults);
  if (btn) { btn.disabled = true; btn.textContent = '✓ Added to results'; }
}

// Evaluate the criterion against the on-screen offers and tint the matches.
async function applyHighlight(criterion) {
  criterion = (criterion || '').trim();
  if (!criterion) { _candAsstMode = ''; return; }
  if (!state.lastResults.length) {
    candAsstAppendAi('Run matching first so there are offers to highlight.');
    _candAsstMode = '';
    return;
  }
  const thread = document.getElementById('candAsstThread');
  const typing = document.createElement('div');
  typing.className = 'chat-msg ai'; typing.id = 'candAsstTyping';
  typing.innerHTML = '<div class="chat-typing">Scanning the offers…</div>';
  thread.appendChild(typing); candAsstScroll();

  try {
    const ids = await _fetchHighlightIds(criterion, state.lastResults);
    document.getElementById('candAsstTyping')?.remove();
    state.highlightCriterion = criterion;
    state.highlightedJobIds  = new Set((ids || []).map(String));
    document.getElementById('candAsstClearHlBtn').style.display =
      state.highlightedJobIds.size ? '' : 'none';
    app.renderResults(state.lastResults);
    const n = state.highlightedJobIds.size;
    candAsstAppendAi(n
      ? `Highlighted ${n} offer${n !== 1 ? 's' : ''} matching “${criterion}” in amber. They stay highlighted when you re-run (and combine with frozen rows). Use the Actions button → Clear highlight to remove.`
      : `No offers on screen match “${criterion}”. Try different wording, or run matching for more results first.`);
  } catch(e) {
    document.getElementById('candAsstTyping')?.remove();
    candAsstAppendAi('Could not evaluate that highlight: ' + e.message);
  } finally {
    _candAsstMode = '';
  }
}

async function _fetchHighlightIds(criterion, results) {
  const jobs = results.map(j => ({
    job_id: j.job_id, title: j.title, company: j.company, city: j.city, state: j.state,
    salary: j.salary, skills: j.skills, skills_en: j.skills_en,
    summary: j.summary, description: (j.description || '').slice(0, 700),
  }));
  const data = await api.post('/api/match/highlight', { criterion, jobs });
  return data.job_ids || [];
}

// Re-apply the active highlight after a fresh re-run, so new offers get evaluated
// and frozen rows keep their highlight. Best-effort.
async function reapplyHighlight() {
  if (!state.highlightCriterion || !state.lastResults.length) return;
  try {
    const ids = await _fetchHighlightIds(state.highlightCriterion, state.lastResults);
    state.highlightedJobIds = new Set((ids || []).map(String));
    document.getElementById('candAsstClearHlBtn').style.display =
      state.highlightedJobIds.size ? '' : 'none';
    app.renderResults(state.lastResults);
  } catch(e) { /* keep prior highlights on failure */ }
}

function candAsstToggle() {
  const panel = document.getElementById('candAsst');
  panel.classList.toggle('collapsed');
  if (!panel.classList.contains('collapsed')) candAsstEnsureGreeting();
}

function candAsstEnsureGreeting() {
  if (_candAsstStarted) return;
  _candAsstStarted = true;
  const p = state.currentCandidateProfile;
  const hasCand = !!(p && (p.name || (p.skills || []).length || (p.top_skills || []).length));
  candAsstAppendAi(hasCand
    ? "I'm here to help with this candidate. Tell me a detail to add to their CV — e.g. “add a forklift licence, available from July” — or ask me anything about the matched offers."
    : "Load a candidate above (upload or paste a CV), then I can refine their CV and talk you through the matched offers. You can also just ask me questions here.");
}

function candAsstScroll() {
  const t = document.getElementById('candAsstThread');
  if (t) t.scrollTop = t.scrollHeight;
}

function candAsstAppendUser(text) {
  const el = document.createElement('div');
  el.className = 'chat-msg user';
  el.innerHTML = `<div class="chat-bubble">${esc(text)}</div>`;
  document.getElementById('candAsstThread').appendChild(el);
  candAsstScroll();
}

function candAsstAppendAi(text, opts) {
  opts = opts || {};
  const el = document.createElement('div');
  el.className = 'chat-msg ai';
  let html = `<div class="chat-bubble">${esc(text)}</div>`;
  if (opts.cvNote) {
    html += `<div class="cand-asst-update">
      <span class="cand-asst-update-label">✓ Added to CV</span>
      <span class="cand-asst-update-note">${esc(opts.cvNote)}</span>
      <button type="button" class="cand-asst-rerun" data-action="cand-asst-rerun">Re-run matching</button>
    </div>`;
  }
  // A suggested search direction (e.g. "logistics roles") — one click folds it into the
  // matching text and re-runs, widening/re-aiming the search without editing the CV.
  if (opts.searchSuggestion) {
    html += `<div class="cand-asst-update">
      <span class="cand-asst-update-label">🔎 Widen the search</span>
      <span class="cand-asst-update-note">${esc(opts.searchSuggestion)}</span>
      <button type="button" class="cand-asst-rerun" data-action="cand-asst-search"
        data-suggestion="${esc(opts.searchSuggestion)}">Search these roles →</button>
    </div>`;
  }
  if (Array.isArray(opts.chips) && opts.chips.length) {
    html += `<div class="cand-asst-chips">` +
      opts.chips.map(c => `<button type="button" class="cand-asst-chip" data-action="cand-asst-chip">${esc(c)}</button>`).join('') +
      `</div>`;
  }
  el.innerHTML = html;
  document.getElementById('candAsstThread').appendChild(el);
  candAsstScroll();
}
// Candidate-assistant dynamic chips (rerun / re-aimed search / quick-reply chip).
Object.assign(_ACTIONS, {
  'cand-asst-rerun':  (el) => candAsstRerun(el),
  'cand-asst-search': (el) => candAsstSearch(el),
  'cand-asst-chip':   (el) => candAsstChip(el),
});

// Fold the assistant's suggested role direction into the matching text (so it sticks
// across future re-runs, like a CV detail) and run a fresh search steered toward it.
function candAsstSearch(btn) {
  const suggestion = (btn.dataset.suggestion || '').trim();
  if (suggestion && !state.candAsstNotes.includes(suggestion)) state.candAsstNotes.push(suggestion);
  btn.disabled = true;
  btn.textContent = 'Searching…';
  document.querySelector('.results-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  app.runMatching();
}

// A quick-reply chip: drop its text into the input and send it.
function candAsstChip(btn) {
  const input = document.getElementById('candAsstMsg');
  input.value = btn.textContent;
  candAsstSend();
}

function candAsstRerun(btn) {
  btn.disabled = true;
  btn.textContent = 'Matching…';
  // Scroll the results into view, then run.
  document.querySelector('.results-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  app.runMatching();
}

// Merge the assistant's structured profile_updates into the candidate card, and
// remember the CV note so a re-run picks the change up. Returns true if applied.
function candAsstApplyUpdates(updates, cvNote) {
  const prof = Object.assign({}, state.currentCandidateProfile || {});
  let changed = false;
  for (const [k, v] of Object.entries(updates || {})) {
    if (v === null || v === undefined || v === '' ||
        (Array.isArray(v) && !v.length)) continue;
    if (_CAND_ASST_LIST_FIELDS.includes(k)) {
      const cur   = Array.isArray(prof[k]) ? prof[k].slice() : [];
      const add   = Array.isArray(v) ? v : [v];
      const lower = new Set(cur.map(x => String(x).toLowerCase()));
      add.forEach(item => {
        const s = String(item).trim();
        if (s && !lower.has(s.toLowerCase())) { cur.push(s); lower.add(s.toLowerCase()); }
      });
      prof[k] = cur; changed = true;
    } else {
      prof[k] = v; changed = true;
    }
  }
  if (!changed) return false;
  app._renderCandidateProfile(prof);   // re-renders the card and updates state.currentCandidateProfile
  const note = (cvNote || '').trim();
  if (note) state.candAsstNotes.push(note);
  return true;
}

async function candAsstSend() {
  if (_candAsstBusy) return;
  const input = document.getElementById('candAsstMsg');
  const text  = input.value.trim();
  if (!text) return;
  _candAsstStarted = true;
  candAsstAppendUser(text);
  input.value = '';

  // Highlight flow: the next message is the criterion to highlight, not a chat turn.
  if (_candAsstMode === 'highlight') { await applyHighlight(text); return; }
  // URL-match flow: the next message is a job posting URL to grade.
  if (_candAsstMode === 'url') { await matchJobUrl(text); return; }

  _candAsstBusy = true;
  const sendBtn = document.getElementById('candAsstSend');
  sendBtn.disabled = true;

  const thread = document.getElementById('candAsstThread');
  const typing = document.createElement('div');
  typing.className = 'chat-msg ai';
  typing.id = 'candAsstTyping';
  typing.innerHTML = '<div class="chat-typing">Thinking…</div>';
  thread.appendChild(typing);
  candAsstScroll();

  // Compact context: the offers currently on screen.
  const jobs = (state.lastResults || []).slice(0, 15).map(j => ({
    title: j.title, company: j.company, city: j.city, state: j.state,
    salary: j.salary, score: j.score, score_pct: j.score_pct,
    grade: j.grade, match_reason: j.match_reason,
  }));

  try {
    const data = await api.post('/api/candidate/assistant', {
      session_id: state.SESSION_ID,
      message:    text,
      profile:    state.currentCandidateProfile || {},
      jobs,
      lang:       'en',
    });
    document.getElementById('candAsstTyping')?.remove();
    let applied = false;
    if (data.profile_updates && Object.keys(data.profile_updates).length) {
      applied = candAsstApplyUpdates(data.profile_updates, data.cv_note);
    }
    candAsstAppendAi(data.reply || 'Done.', {
      cvNote:           applied ? data.cv_note : '',
      searchSuggestion: data.search_suggestion || '',
    });
  } catch(e) {
    document.getElementById('candAsstTyping')?.remove();
    candAsstAppendAi('Network error: ' + e.message);
  } finally {
    _candAsstBusy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

async function candAsstReset() {
  document.getElementById('candAsstThread').innerHTML = '';
  _candAsstStarted = false;
  state.candAsstNotes   = [];
  _candAsstMode    = '';
  try {
    await api.raw('/api/candidate/assistant/reset', { method: 'POST', body: { session_id: state.SESSION_ID } });
  } catch(e) { /* best-effort */ }
  candAsstEnsureGreeting();
}

// Action registry for the candidate-assistant widget — split out of the
// search-tab's mixed registry block since these route to this module.
Object.assign(_ACTIONS, {
  'cand-asst-toggle':        ()      => candAsstToggle(),
  'cand-asst-reset':         (el, e) => { e.stopPropagation(); candAsstReset(); },
  'cand-asst-toggle-menu':   (el, e) => candAsstToggleMenu(e),
  'cand-asst-analyze-fit':   ()      => candAsstAnalyzeFit(),
  'cand-asst-start-highlight': ()    => candAsstStartHighlight(),
  'cand-asst-clear-highlight': ()    => candAsstClearHighlight(),
  'cand-asst-start-url-match': ()    => candAsstStartUrlMatch(),
  'cand-asst-send-enter':    (el, e) => { if (e.key === 'Enter') { e.preventDefault(); candAsstSend(); } },
  'cand-asst-send':          ()      => candAsstSend(),
});

// Cross-module export — registered on app so clustering.js's segment-results
// view can re-apply an active highlight after rendering.
Object.assign(app, { reapplyHighlight });
