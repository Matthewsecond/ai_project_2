// ════════════════════════════════════════════════════════════
//  Interview scorecard — generate questions, record answers, score them
//  State lives in `state.interview` and is persisted into the saved job's
//  extras.interview so it restores when the candidate/job is reopened.
// ════════════════════════════════════════════════════════════
// Driven from the job-detail modal's description toolbar (modal.js calls these
// via app.*) and the description toolbar's two desc-toggle-* actions, which live
// here because they're really interview/CV-questions and outreach generation,
// not modal-shell concerns.
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";
import api from "./api.js";

// ════════════════════════════════════════════════════════════
//  Interview scorecard — generate questions, record answers, score them
//  State lives in `state.interview` and is persisted into the saved job's
//  extras.interview so it restores when the candidate/job is reopened.
// ════════════════════════════════════════════════════════════
let _aspectsBusy = false;
// Recruiter (scoring) vs candidate (coaching) lens over the same Q&A. Frontend-only.
let _ivPerspective = 'recruiter';
// Ephemeral AI follow-up suggestions awaiting Add/dismiss, keyed by parent question id.
// Not persisted — a suggestion only becomes durable once Added as a real question.
let _ivPendingFollowup = {};

function _interviewReset() {
  state.interview = { questions: [], answers: {}, overall: null, aspects: [], aspectsSummary: '', aspectsBaseline: null, frozen: false, opportunities: null };
  _aspectsBusy = false;
  _ivPendingFollowup = {};
}

// True when at least one answer has been recorded — gates the extras checkbox.
function _ivHasAnswers() {
  return Object.values(state.interview.answers || {}).some(a => (a.answer || '').trim());
}

// Load a previously-saved interview for the job now open in the modal (if any).
function _interviewRestore(jobId) {
  // Same job_id can be saved under more than one candidate — prefer the row for the
  // candidate currently open in the modal, else fall back to the first match.
  const cand = (typeof getCandidateName === 'function') ? app.getCandidateName() : null;
  const matches = (state.savedJobs || []).filter(j => String(j.job_id) === String(jobId));
  const saved = (cand && matches.find(j => j.candidate_name === cand)) || matches[0];
  const iv = saved && saved.extras && saved.extras.interview;
  if (iv && typeof iv === 'object') {
    state.interview = {
      questions: Array.isArray(iv.questions) ? iv.questions : [],
      answers:   (iv.answers && typeof iv.answers === 'object') ? iv.answers : {},
      overall:   iv.overall || null,
      aspects:   Array.isArray(iv.aspects) ? iv.aspects : [],
      aspectsSummary: iv.aspectsSummary || '',
      aspectsBaseline: (iv.aspectsBaseline && typeof iv.aspectsBaseline === 'object') ? iv.aspectsBaseline : null,
      frozen:    !!iv.frozen,
      opportunities: (iv.opportunities && typeof iv.opportunities === 'object') ? iv.opportunities : null,
    };
  }
}

// Job context sent to the interview endpoints.
function _ivJob() {
  const j = state.modalJob || {};
  return { title: j.title, company: j.company,
           salary: j.salary || '',
           location: [j.city, j.state].filter(Boolean).join(', '),
           skills: j.skills_en || j.skills,
           description: (j.description || j.description_snippet || '') };
}

// Compact "interview so far" digest for cross-answer context: the answered questions
// other than the ones in excludeIds. Mirrors the records builder used by
// summarizeInterview/refreshAspects, minus the excluded ids.
function _ivOtherRecords(excludeIds) {
  const skip = new Set((excludeIds || []).map(String));
  return (state.interview.questions || [])
    .filter(q => !skip.has(String(q.id)))
    .map(q => ({ question: q.question, ...(state.interview.answers[q.id] || {}) }))
    .filter(r => _ivAnswerComplete(r))   // only finished answers are established context
    .map(r => ({ question: r.question, answer: r.answer, score: r.score }));
}

// The candidate's CV text for the interview. Prefer a raw parsed/pasted CV
// (`state.lastParsedText`), but fall back to text rebuilt from the loaded profile via
// app.buildCandidateText() — a candidate reloaded from the database has a structured
// profile but no raw CV text, so without this the panel wrongly says "No CV".
function _ivCvText() {
  const raw = (state.lastParsedText || '').trim();
  if (raw) return raw;
  try { return (app.buildCandidateText() || '').trim(); } catch (_) { return ''; }
}

// Interview content follows the page-wide "AI lang" setting (state.jobChatLang), NOT
// the description's display language (state.modalLang defaults to DE for the source
// posting). So selecting EN at the top of the page yields English questions.
function _ivLang() {
  return (typeof state.jobChatLang !== 'undefined' && state.jobChatLang) ? state.jobChatLang : 'en';
}

// The recruiter's structured profile / AI summary, fed to the helper as prior analysis.
function _ivProfile() {
  const p = state.currentCandidateProfile;
  if (!p || typeof p !== 'object') return null;
  const slim = {};
  ['name','title','seniority','experience_years','years_experience','location','languages',
   'industry','role_category','education','education_level','salary_expectation','availability',
   'top_skills','skills','ai_summary','summary'].forEach(k => {
    const v = p[k];
    if (v != null && v !== '' && !(Array.isArray(v) && !v.length)) slim[k] = v;
  });
  return Object.keys(slim).length ? slim : null;
}

// ── Live candidate assessment (aspects) ──────────────────────
function _renderAspects() {
  const el = document.getElementById('interviewAspects');
  const list = state.interview.aspects || [];
  if (!list.length && !_aspectsBusy) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = ''; el.className = 'iv-aspects';
  const rows = list.map(a => {
    const st  = ['strong','mixed','weak','unknown'].includes(a.status) ? a.status : 'unknown';
    const pct = a.score == null ? 0 : a.score;
    const col = st === 'strong' ? '#1a7a2e' : st === 'weak' ? '#c0392b' : st === 'mixed' ? '#b87800' : '#bbb';
    // Movement-since-baseline badge (▲/▼); tooltip adds the latest answer's step change.
    let deltaHtml = '';
    if (a.delta != null && a.delta !== 0) {
      const up = a.delta > 0;
      let tip = `Baseline ${a.score - a.delta}% → now ${a.score}%`;
      if (a.step != null && a.step !== 0) tip += ` · this answer ${a.step > 0 ? '+' : ''}${a.step}`;
      deltaHtml = `<span class="iv-aspect-delta ${up ? 'up' : 'down'}" title="${esc(tip)}">${up ? '▲ +' : '▼ '}${a.delta}</span>`;
    }
    return `<div class="iv-aspect">
      <div class="iv-aspect-main">
        <div class="iv-aspect-name">${esc(a.aspect)}</div>
        ${a.note ? `<div class="iv-aspect-note">${esc(a.note)}</div>` : ''}
        <div class="iv-aspect-bar"><span style="width:${pct}%;background:${col}"></span></div>
      </div>
      <div class="iv-aspect-right">
        <span class="iv-aspect-score ${st}">${a.score == null ? '—' : a.score + '%'}</span>
        ${deltaHtml}
      </div>
    </div>`;
  }).join('');
  el.innerHTML = `<div class="iv-aspects-head">
      <span class="iv-aspects-title">Candidate assessment</span>
      ${_aspectsBusy ? '<span class="iv-aspects-busy">updating…</span>' : ''}
    </div>${rows || ''}`;
}

// Ask the helper to (re)assess the candidate across aspects given the answers so
// far. Called once when the interview opens and again after each scored answer.
async function refreshAspects() {
  if (_aspectsBusy) return;
  _aspectsBusy = true;
  _renderAspects();
  const records = (state.interview.questions || [])
    .map(q => ({ question: q.question, ...(state.interview.answers[q.id] || {}) }))
    .filter(r => _ivAnswerComplete(r));   // only finished answers count as evidence
  try {
    const data = await api.post('/api/interview/assess', { job: _ivJob(), cv_text: _ivCvText(), profile: _ivProfile(),
                             records, prior_aspects: state.interview.aspects || [], lang: _ivLang() });
    if (data.ok && Array.isArray(data.aspects)) {
      // Movement badges: cumulative vs the BASELINE (first assessment, established once
      // and kept for the whole interview) as the visible delta; per-answer step for the
      // tooltip. Matched by aspect name (kept stable via prior_aspects).
      const prior = {};
      (state.interview.aspects || []).forEach(a => { if (a.score != null) prior[a.aspect] = a.score; });
      if (!state.interview.aspectsBaseline) {
        const base = {};
        data.aspects.forEach(a => { if (a.score != null) base[a.aspect] = a.score; });
        state.interview.aspectsBaseline = base;
      }
      const base = state.interview.aspectsBaseline || {};
      data.aspects.forEach(a => {
        a.delta = (a.score != null && base[a.aspect] != null) ? a.score - base[a.aspect] : null;
        a.step  = (a.score != null && prior[a.aspect] != null) ? a.score - prior[a.aspect] : null;
      });
      state.interview.aspects = data.aspects;
      state.interview.aspectsSummary = data.summary || '';
    }
  } catch (_) { /* leave prior aspects in place */ }
  finally {
    _aspectsBusy = false;
    _renderAspects();
    // Only persist (which auto-saves the job) once the recruiter has actually
    // recorded an answer — opening the panel for the baseline read shouldn't add
    // the job to the pipeline on its own.
    if (_ivHasAnswers()) _persistInterview();
  }
}

function _ivScoreClass(s) { return s >= 70 ? 'high' : s >= 45 ? 'mid' : 'low'; }

// A turn counts as a finished answer (feeds summary/assessment, enables follow-ups)
// when the model marked it complete — or, for legacy answers with no flag, when scored.
function _ivAnswerComplete(a) {
  if (!a) return false;
  if (a.complete === true) return true;
  if (a.complete === false) return false;
  return a.score != null;
}

function _ivResultHtml(a) {
  if (a == null) return '';
  // In-progress: the model judged this turn a clarifying/partial reply, not a
  // complete answer — show guidance, no score (so it never reads as a low grade).
  if (a.complete === false) {
    const label = a.status === 'clarifying' ? 'clarifying' : (a.status === 'partial' ? 'partial' : 'in progress');
    return `<div class="iv-progress">
        <span class="iv-progress-pill">◷ In progress · ${esc(label)}</span>
        ${a.needs ? `<div class="iv-progress-note">↳ ${esc(a.needs)}</div>` : ''}
      </div>`;
  }
  if (a.score == null) return '';
  const chips = [
    ...(a.strengths || []).map(s => `<span class="iv-chip ok">✓ ${esc(s)}</span>`),
    ...(a.concerns  || []).map(s => `<span class="iv-chip warn">⚠ ${esc(s)}</span>`),
    ...(a.signals   || []).map(s => `<span class="iv-chip sig">${esc(s)}</span>`),
  ].join('');
  return `<div class="iv-score-row">
      <span class="iv-score ${_ivScoreClass(a.score)}">${a.score}%</span>
      <span class="iv-verdict">${esc(a.verdict || '')}</span>
    </div>${chips ? `<div class="iv-chips">${chips}</div>` : ''}`;
}

function _renderInterviewOverall() {
  const el = document.getElementById('interviewOverall');
  const answered = Object.values(state.interview.answers).filter(a => _ivAnswerComplete(a)).length;
  if (!answered) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = '';
  const ov = state.interview.overall;
  el.className = ov ? 'iv-overall' : '';
  el.innerHTML = `
    <div class="iv-overall-row">
      <button class="desc-action-btn" data-action="summarize-interview">${ov ? 'Re-summarize' : 'Summarize interview'}</button>
      ${ov ? `<span class="iv-score ${_ivScoreClass(ov.score)}">${ov.score}%</span>
              <span class="iv-reco">${esc(ov.recommendation || '')}</span>` : ''}
    </div>
    ${ov && ov.summary ? `<div class="iv-summary">${esc(ov.summary)}</div>` : ''}`;
}

// ── Candidate lens: model answers + improvement opportunities ──
// Reveal the model answer for one question (gated: only after it has an answer).
// Cached on the answer object so it persists with the saved interview.
async function revealModelAnswer(id) {
  const q = (state.interview.questions || []).find(x => String(x.id) === String(id));
  if (!q) return;
  const a = state.interview.answers[id] || {};
  if (!(a.answer || '').trim()) return;   // gated
  const btn = document.getElementById('ivModelBtn-' + id);
  if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }
  try {
    const data = await api.post('/api/interview/model_answer', { question: q.question, note: q.note || '', job: _ivJob(),
                             cv_text: _ivCvText(), profile: _ivProfile(), lang: _ivLang() });
    if (data.ok) {
      a.modelAnswer = data.model_answer || '';
      a.modelCovers = Array.isArray(data.covers) ? data.covers : [];
      state.interview.answers[id] = a;
      if (_ivHasAnswers()) _persistInterview();
    } else if (btn) {
      btn.disabled = false; btn.textContent = '★ Reveal model answer';
      alert(data.error || 'Could not load the model answer.');
      return;
    }
  } catch (_) {
    if (btn) { btn.disabled = false; btn.textContent = '★ Reveal model answer'; }
    return;
  }
  _renderInterview();
}

function _renderOpportunities() {
  const el = document.getElementById('interviewOpportunities');
  if (!el) return;
  if (_ivPerspective !== 'candidate') { el.style.display = 'none'; return; }
  const answered = Object.values(state.interview.answers).filter(a => (a.answer || '').trim()).length;
  if (!answered) { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = '';
  el.className = 'iv-candidate-only iv-overall';
  const opp = state.interview.opportunities;
  const head = `<div class="iv-overall-row">
      <button class="desc-action-btn" data-action="load-opportunities">${opp ? '↻ Refresh opportunities' : '✨ Show my biggest opportunities'}</button>
    </div>`;
  let body = '';
  if (opp) {
    const items = (opp.items || []).map(o => {
      const cls = o.impact === 'high' ? 'high' : o.impact === 'low' ? 'low' : 'mid';
      return `<div class="iv-opp">
          <div class="iv-opp-head">
            <span class="iv-opp-impact ${cls}">${esc(o.impact || 'medium')}</span>
            <span class="iv-opp-title">${esc(o.title)}</span>
          </div>
          ${o.rationale ? `<div class="iv-opp-why">${esc(o.rationale)}</div>` : ''}
          ${o.action ? `<div class="iv-opp-action">→ ${esc(o.action)}</div>` : ''}
        </div>`;
    }).join('');
    body = (opp.summary ? `<div class="iv-summary">${esc(opp.summary)}</div>` : '')
         + (items ? `<div class="iv-opps">${items}</div>` : '');
  }
  el.innerHTML = head + body;
}

async function loadOpportunities() {
  const records = (state.interview.questions || [])
    .map(q => ({ question: q.question, ...(state.interview.answers[q.id] || {}) }))
    .filter(r => (r.answer || '').trim())
    .map(r => ({ question: r.question, answer: r.answer, score: r.score }));
  const el = document.getElementById('interviewOpportunities');
  if (el) el.innerHTML = '<div class="iv-overall-row"><span class="iv-aspects-busy">analyzing…</span></div>';
  try {
    const data = await api.post('/api/interview/opportunities', { records, job: _ivJob(), cv_text: _ivCvText(),
                             profile: _ivProfile(), lang: _ivLang() });
    if (data.ok) {
      state.interview.opportunities = { items: data.opportunities || [], summary: data.summary || '' };
      if (_ivHasAnswers()) _persistInterview();
    } else {
      alert(data.error || 'Could not analyze opportunities.');
    }
  } catch (_) { /* leave prior opportunities in place */ }
  _renderOpportunities();
}

function _renderInterview() {
  const wrap = document.getElementById('interviewScorecard');
  const qs = state.interview.questions || [];
  // Index follow-ups by their parent so each renders nested under it.
  const byParent = {};
  qs.forEach(q => { if (q.followupTo != null) (byParent[q.followupTo] = byParent[q.followupTo] || []).push(q); });
  const top = qs.filter(q => q.followupTo == null);
  wrap.innerHTML = top.map(q => _ivRenderNode(q, byParent)).join('');
  _applyIvPerspective();
  _renderInterviewControls();
  _renderAspects();
  _renderInterviewOverall();
  _renderOpportunities();
}

// Recruiter (scoring) vs candidate (coaching) lens. CSS on the wrapper hides the
// blocks that don't belong to the active lens; this just syncs the class + buttons.
function _applyIvPerspective() {
  const w = document.getElementById('modalDescCvQuestionsWrap');
  if (w) {
    w.classList.toggle('iv-persp-candidate', _ivPerspective === 'candidate');
    w.classList.toggle('iv-persp-recruiter', _ivPerspective !== 'candidate');
  }
  const rb = document.getElementById('ivPerspRecruiter');
  const cb = document.getElementById('ivPerspCandidate');
  if (rb) rb.classList.toggle('active', _ivPerspective !== 'candidate');
  if (cb) cb.classList.toggle('active', _ivPerspective === 'candidate');
}

function setIvPerspective(p) {
  _ivPerspective = (p === 'candidate') ? 'candidate' : 'recruiter';
  _renderInterview();
}

// Action registry for the interview scorecard dynamic markup — editable
// questions, per-answer analyze/score/reveal/follow-up controls, summary +
// opportunities buttons. Question ids are numeric (coerced with +).
Object.assign(_ACTIONS, {
  'iv-edit-question':        (el) => _ivEditQuestion(+el.dataset.id, el.value),
  'persist-interview':       ()   => _persistInterview(),
  'remove-interview-question': (el) => removeInterviewQuestion(+el.dataset.id),
  'suggest-followup':        (el) => suggestFollowup(+el.dataset.id),
  'analyze-interview-answer':(el) => analyzeInterviewAnswer(+el.dataset.id, el.dataset.asis === '1'),
  'reveal-model-answer':     (el) => revealModelAnswer(+el.dataset.id),
  'iv-on-input':             (el) => _ivOnInput(+el.dataset.id, el.value),
  'add-followup':            (el) => addFollowup(+el.dataset.parentId),
  'dismiss-followup':        (el) => dismissFollowup(+el.dataset.parentId),
  'summarize-interview':     ()   => summarizeInterview(),
  'load-opportunities':      ()   => loadOpportunities(),
});

// Render one question and (recursively) its follow-ups nested beneath it.
function _ivRenderNode(item, byParent) {
  const a = state.interview.answers[item.id] || {};
  const scored = a.score != null;
  const isFollowup = item.followupTo != null;
  const editable = !!item.custom;   // manual, imported and follow-up questions are editable
  // Custom/imported/follow-up questions render with an editable input; AI gap
  // questions stay read-only. Every question can be removed (✕).
  const badge = isFollowup
    ? `<span class="iv-q-num followup" title="Follow-up">↳</span>`
    : `<span class="iv-q-num${editable ? ' custom' : ''}">${item.id}</span>`;
  const textPart = editable
    ? `<input class="iv-q-edit" value="${esc(item.question)}" placeholder="Type your question…"
              data-input-action="iv-edit-question" data-id="${item.id}" data-change-action="persist-interview">`
    : `<div class="iv-q-text">${esc(item.question)}${item.note ? `<span class="iv-q-note">${esc(item.note)}</span>` : ''}</div>`;
  const head = `${badge}${textPart}<button class="iv-q-del" title="Remove this question" data-action="remove-interview-question" data-id="${item.id}">✕</button>`;

  const hasAnswer = (a.answer || '').trim();
  const complete = _ivAnswerComplete(a);
  // Follow-up only makes sense once there's a complete answer; before that it's still
  // a conversation. Once a thread is exhausted, show the "enough context" marker.
  let fuBtn = '';
  if (a.followupExhausted) {
    fuBtn = `<span class="iv-followup-done" title="${esc(a.followupReason || 'No further follow-up needed')}">✓ Enough context</span>`;
  } else if (complete) {
    fuBtn = `<button class="desc-action-btn iv-followup-btn" data-action="suggest-followup" data-id="${item.id}">💡 Suggest follow-up</button>`;
  }
  // While the exchange is still open (answer present but not complete), offer the
  // manual override to score it as-is.
  const scoreNowBtn = (hasAnswer && !complete)
    ? `<button class="desc-action-btn iv-score-now" data-action="analyze-interview-answer" data-id="${item.id}" data-asis="1" title="Score the answer as it stands, even mid-exchange">⏎ Score now</button>`
    : '';

  const pend = _ivPendingFollowup[item.id];
  const suggestHtml = pend ? _ivSuggestHtml(item.id, pend.question, pend.note) : '';
  const childHtml = (byParent[item.id] || []).map(c => _ivRenderNode(c, byParent)).join('');

  // Candidate lens: model answer is GATED — locked until they've answered, then a
  // reveal button, then the coaching itself (cached on the answer so it persists).
  let modelInner;
  if (!hasAnswer) {
    modelInner = `<div class="iv-model-locked">🔒 Answer first to unlock the model answer</div>`;
  } else if (a.modelAnswer) {
    const covers = (a.modelCovers || []).map(c => `<li>${esc(c)}</li>`).join('');
    modelInner = `<div class="iv-model">
        <div class="iv-model-head">★ What a strong answer covers</div>
        <div class="iv-model-body">${esc(a.modelAnswer)}</div>
        ${covers ? `<ul class="iv-model-covers">${covers}</ul>` : ''}
      </div>`;
  } else {
    modelInner = `<button class="desc-action-btn" id="ivModelBtn-${item.id}" data-action="reveal-model-answer" data-id="${item.id}">★ Reveal model answer</button>`;
  }
  const modelHtml = `<div class="iv-candidate-only iv-model-wrap">${modelInner}</div>`;

  return `<div class="iv-q${isFollowup ? ' followup' : ''}" data-qid="${item.id}">
      <div class="iv-q-head">${head}</div>
      <textarea class="iv-answer" rows="2" placeholder="What the candidate said — capture the back-and-forth too (their clarifying questions, your replies, their answer)…"
                data-input-action="iv-on-input" data-id="${item.id}">${esc(a.answer || '')}</textarea>
      <div class="iv-q-actions">
        <button class="desc-action-btn iv-analyze" data-action="analyze-interview-answer" data-id="${item.id}">${scored ? 'Re-analyze' : 'Analyze'}</button>
        ${scoreNowBtn}
        ${fuBtn}
      </div>
      <div class="iv-result" id="ivResult-${item.id}">${_ivResultHtml(a)}</div>
      ${modelHtml}
      <div class="iv-suggest-wrap" id="ivSuggest-${item.id}">${suggestHtml}</div>
      ${childHtml ? `<div class="iv-q-children">${childHtml}</div>` : ''}
    </div>`;
}

function _ivSuggestHtml(parentId, question, note) {
  return `<div class="iv-suggest">
      <div class="iv-suggest-text">${esc(question)}</div>
      ${note ? `<div class="iv-q-note">${esc(note)}</div>` : ''}
      <div class="iv-suggest-actions">
        <button class="desc-action-btn" data-action="add-followup" data-parent-id="${parentId}">➕ Add</button>
        <button class="desc-action-btn" data-action="dismiss-followup" data-parent-id="${parentId}">✕</button>
      </div>
    </div>`;
}

// Controls row — shown whenever the interview panel is open. Add/Import are always
// available; Freeze/New/Analyze-all depend on the current question/answer state.
function _renderInterviewControls() {
  const row = document.getElementById('interviewControls');
  row.style.display = 'flex';
  const hasQ = !!(state.interview.questions && state.interview.questions.length);
  const frozen = !!state.interview.frozen;
  const fb = document.getElementById('ivFreezeBtn');
  const rb = document.getElementById('ivRegenBtn');
  const ab = document.getElementById('ivAnalyzeAllBtn');
  const note = document.getElementById('ivFrozenNote');
  fb.style.display = hasQ ? '' : 'none';
  fb.textContent = frozen ? '🔓 Unfreeze' : '🔒 Freeze questions';
  fb.classList.toggle('active', frozen);
  rb.style.display = (hasQ && !frozen) ? '' : 'none';
  ab.style.display = _ivHasUnscored() ? '' : 'none';
  note.style.display = (hasQ && frozen) ? '' : 'none';
}

// Freeze locks the question set and saves it immediately, so it survives closing
// the window and never regenerates. Unfreeze re-enables regeneration.
async function toggleFreezeInterview() {
  if (!state.interview.questions || !state.interview.questions.length) return;
  state.interview.frozen = !state.interview.frozen;
  _renderInterviewControls();
  await _persistInterview();   // persist now (saving the job) so the questions stick
}

// Discard the current questions and generate a fresh set (only when not frozen).
async function regenerateInterview() {
  if (state.interview.frozen) return;
  if (_ivHasAnswers() &&
      !confirm('Replace the current questions and clear the recorded answers for this interview?')) return;
  state.interview.questions = [];
  state.interview.answers = {};
  state.interview.aspects = [];
  state.interview.aspectsSummary = '';
  state.interview.overall = null;
  state.descCvQuestionsShown = false;   // force descToggleCvQuestions to re-open + regenerate
  await descToggleCvQuestions();
}

function _ivOnInput(id, val) {
  (state.interview.answers[id] = state.interview.answers[id] || {}).answer = val;
  _ivSyncFollowupBtn(id);   // show/hide 💡 Suggest follow-up live as the answer changes
}

// Keep the "💡 Suggest follow-up" button in sync with whether an answer exists —
// a targeted DOM tweak (no full re-render, which would eat the Analyze click).
// The exhausted "✓ Enough context" marker is left to the full render in suggestFollowup.
function _ivSyncFollowupBtn(id) {
  const actions = document.querySelector(`.iv-q[data-qid="${id}"] .iv-q-actions`);
  if (!actions) return;
  const a = state.interview.answers[id] || {};
  if (a.followupExhausted) return;
  // No longer exhausted (e.g. answer edited + re-analyzed) → drop any stale marker.
  actions.querySelector('.iv-followup-done')?.remove();
  const btn = actions.querySelector('.iv-followup-btn');
  const want = _ivAnswerComplete(a);   // follow-ups only after a complete answer
  if (want && !btn) {
    actions.insertAdjacentHTML('beforeend',
      `<button class="desc-action-btn iv-followup-btn" data-action="suggest-followup" data-id="${id}">💡 Suggest follow-up</button>`);
  } else if (!want && btn) {
    btn.remove();
  }
}

// Add an interviewer-written question (e.g. something that came up live). Allowed
// even when frozen — freeze only stops AI regeneration, not deliberate edits.
function addInterviewQuestion() {
  state.interview.questions = state.interview.questions || [];
  const ids = state.interview.questions.map(q => q.id).filter(n => typeof n === 'number');
  const nid = (ids.length ? Math.max(...ids) : 0) + 1;
  state.interview.questions.push({ id: nid, question: '', note: 'Added by interviewer', custom: true });
  _renderInterview();
  setTimeout(() => document.querySelector(`.iv-q[data-qid="${nid}"] .iv-q-edit`)?.focus(), 0);
  _persistInterview();
}

function _ivEditQuestion(id, val) {
  const q = (state.interview.questions || []).find(x => x.id === id);
  if (q) q.question = val;
}

function removeInterviewQuestion(id) {
  // Remove this question and every descendant follow-up (and their answers), so
  // deleting a parent never leaves orphaned follow-ups behind.
  const qs = state.interview.questions || [];
  const doomed = new Set([id]);
  let grew = true;
  while (grew) {
    grew = false;
    qs.forEach(q => {
      if (q.followupTo != null && doomed.has(q.followupTo) && !doomed.has(q.id)) { doomed.add(q.id); grew = true; }
    });
  }
  state.interview.questions = qs.filter(q => !doomed.has(q.id));
  doomed.forEach(rid => { delete state.interview.answers[rid]; delete _ivPendingFollowup[rid]; });
  _renderInterview();
  _renderInterviewOverall();
  _persistInterview();
}

// ── AI follow-up suggestions ──────────────────────────────────
// Build the line of questioning (root → … → this node) with answers, so the model
// can judge whether the topic is exhausted or one more probe is warranted.
function _ivThread(id) {
  const byId = {};
  (state.interview.questions || []).forEach(q => { byId[q.id] = q; });
  const chain = [];
  let cur = byId[id];
  while (cur) { chain.unshift(cur); cur = (cur.followupTo != null) ? byId[cur.followupTo] : null; }
  return chain.map(q => {
    const a = state.interview.answers[q.id] || {};
    return { question: q.question, answer: a.answer || '', note: q.note || '' };
  });
}

// Ids in the root→node chain — excluded from the cross-answer digest so the current
// thread isn't duplicated in the prompt.
function _ivThreadIds(id) {
  const byId = {};
  (state.interview.questions || []).forEach(q => { byId[q.id] = q; });
  const ids = [];
  let cur = byId[id];
  while (cur) { ids.push(cur.id); cur = (cur.followupTo != null) ? byId[cur.followupTo] : null; }
  return ids;
}

async function suggestFollowup(id) {
  const item = (state.interview.questions || []).find(q => q.id === id);
  if (!item) return;
  const a = state.interview.answers[id] || {};
  if (!(a.answer || '').trim()) return;
  const btn = document.querySelector(`.iv-q[data-qid="${id}"] .iv-followup-btn`);
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const data = await api.post('/api/interview/followup', { thread: _ivThread(id), job: _ivJob(), cv_text: _ivCvText(),
                             profile: _ivProfile(), lang: _ivLang(),
                             others: _ivOtherRecords(_ivThreadIds(id)) });
    if (data.exhausted) {
      // Persist the "done" state so the marker survives reopening.
      state.interview.answers[id] = { ...a, followupExhausted: true, followupReason: data.reason || '' };
      _persistInterview();
      _renderInterview();
    } else {
      _ivPendingFollowup[id] = { question: data.question, note: data.note || '' };
      _renderInterview();   // shows the suggestion chip under this answer
    }
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = '💡 Suggest follow-up'; }
    alert('Follow-up failed: ' + e.message);
  }
}

// Accept a suggested follow-up: add it as a nested question under its parent.
// Allowed even when frozen — it's a deliberate action, like Add question.
function addFollowup(parentId) {
  const sug = _ivPendingFollowup[parentId];
  if (!sug) return;
  state.interview.questions = state.interview.questions || [];
  const ids = state.interview.questions.map(q => q.id).filter(n => typeof n === 'number');
  const nid = (ids.length ? Math.max(...ids) : 0) + 1;
  state.interview.questions.push({ id: nid, question: sug.question,
                              note: sug.note || `Follow-up to Q${parentId}`,
                              custom: true, followupTo: parentId });
  delete _ivPendingFollowup[parentId];
  _renderInterview();
  _persistInterview();
  setTimeout(() => document.querySelector(`.iv-q[data-qid="${nid}"] .iv-answer`)?.focus(), 0);
}

function dismissFollowup(parentId) {
  delete _ivPendingFollowup[parentId];
  _renderInterview();
}

// Every question has a COMPLETE answer — used to auto-produce the wrap-up. An open
// (clarifying/partial) exchange doesn't count, so the summary won't fire prematurely.
function _ivAllAnswered() {
  const qs = (state.interview.questions || []).filter(q => (q.question || '').trim());
  return qs.length > 0 && qs.every(q => _ivAnswerComplete(state.interview.answers[q.id]));
}

// At least one answered-but-not-yet-scored question — gates the "Analyze all" button.
function _ivHasUnscored() {
  return (state.interview.questions || []).some(q => {
    const a = state.interview.answers[q.id] || {};
    return (a.answer || '').trim() && a.score == null;
  });
}

// ── Show the briefing note the AI is given (transparency) ─────────────────────
// Fetches the exact assembled context from the server so it matches what the model
// sees. Shows the current snapshot: job + CV/profile + every answered question.
async function toggleInterviewContext() {
  const el = document.getElementById('interviewContext');
  const show = el.style.display === 'none' || !el.style.display;
  el.style.display = show ? 'block' : 'none';
  document.getElementById('ivContextBtn')?.classList.toggle('active', show);
  if (!show) return;
  const pre = document.getElementById('ivContextText');
  pre.textContent = 'Loading…';
  try {
    const data = await api.post('/api/interview/context', { job: _ivJob(), cv_text: _ivCvText(),
                             profile: _ivProfile(), others: _ivOtherRecords([]) });
    pre.textContent = data.ok ? (data.context || '(empty)') : ('Error: ' + (data.error || 'failed'));
  } catch (e) { pre.textContent = 'Error: ' + e.message; }
}

// ── Import prepared questions / answers from a document ───────────────────────
function toggleInterviewImport(show) {
  const el = document.getElementById('interviewImport');
  if (!el) return;
  el.style.display = show ? 'block' : 'none';
  if (show) document.getElementById('ivImportText').focus();
  else document.getElementById('ivImportMsg').textContent = '';
}

// Load a file into the import textarea. Plain text is read in the browser; .docx
// and .pdf are sent to the server extractor (which has no extra dependency for
// docx and reuses pypdf for pdf). The recruiter can edit before parsing.
async function _ivLoadImportFile(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const ta  = document.getElementById('ivImportText');
  const msg = document.getElementById('ivImportMsg');
  const name = (f.name || '').toLowerCase();
  if (name.endsWith('.txt') || name.endsWith('.md') || name.endsWith('.text') ||
      (f.type || '').startsWith('text/')) {
    const r = new FileReader();
    r.onload  = () => { ta.value = r.result || ''; msg.textContent = ''; };
    r.onerror = () => { msg.textContent = 'Could not read that file.'; };
    r.readAsText(f);
    return;
  }
  msg.textContent = 'Extracting ' + f.name + '…';
  try {
    const fd = new FormData();
    fd.append('file', f);
    const res  = await fetch('/api/interview/extract', { method: 'POST', body: fd });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'extract failed');
    ta.value = data.text || '';
    msg.textContent = (data.text || '').trim()
      ? 'Extracted — review the text, then Parse & import.'
      : 'No text found in that file.';
  } catch (e) {
    msg.textContent = 'Could not read that file: ' + e.message;
  }
}

// Parse the pasted/loaded text on the server into Q/A pairs, then append them as
// editable questions with any answers pre-filled (ready to Analyze).
async function importInterviewQuestions() {
  const text = (document.getElementById('ivImportText').value || '').trim();
  const msg  = document.getElementById('ivImportMsg');
  if (!text) { msg.textContent = 'Paste or load some text first.'; return; }
  msg.textContent = 'Parsing…';
  try {
    const data = await api.post('/api/interview/parse', { text });
    if (!Array.isArray(data.questions) || !data.questions.length)
      throw new Error(data.error || 'no questions found');
    state.interview.questions = state.interview.questions || [];
    const ids = state.interview.questions.map(q => q.id).filter(n => typeof n === 'number');
    let next = (ids.length ? Math.max(...ids) : 0) + 1;
    let nq = 0, na = 0;
    data.questions.forEach(q => {
      const qtext = (q.question || '').trim();
      if (!qtext) return;
      const id = next++;
      state.interview.questions.push({ id, question: qtext, note: 'Imported', custom: true });
      const ans = (q.answer || '').trim();
      if (ans) { state.interview.answers[id] = { answer: ans }; na++; }
      nq++;
    });
    _renderInterview();
    _persistInterview();
    toggleInterviewImport(false);
    document.getElementById('ivImportText').value = '';
    const fileEl = document.getElementById('ivImportFile'); if (fileEl) fileEl.value = '';
    if (na) refreshAspects();   // imported answers count as evidence for the assessment
  } catch (e) {
    msg.textContent = 'Import failed: ' + e.message;
  }
}

// Score every answer that has text but no score yet (handy after importing answers).
async function analyzeAllInterview() {
  const btn = document.getElementById('ivAnalyzeAllBtn');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    for (const q of (state.interview.questions || [])) {
      const a = state.interview.answers[q.id] || {};
      if ((a.answer || '').trim() && !_ivAnswerComplete(a)) await analyzeInterviewAnswer(q.id);
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '⚡ Analyze all'; }
    _renderInterviewControls();
  }
}

// Assess one turn. The model decides whether it's a complete answer (→ score) or
// still in progress (→ guidance, no score). `final=true` is the "Score now" override.
async function analyzeInterviewAnswer(id, final = false) {
  const item = (state.interview.questions || []).find(q => q.id === id);
  if (!item) return;
  const row = document.querySelector(`.iv-q[data-qid="${id}"]`);
  const ta  = row?.querySelector('.iv-answer');
  const answer = (ta?.value || '').trim();
  if (!answer) { ta?.focus(); return; }
  const actionBtns = row?.querySelectorAll('.iv-q-actions button') || [];
  actionBtns.forEach(b => b.disabled = true);
  try {
    const data = await api.post('/api/interview/analyze', { question: item.question, answer, note: item.note,
                             job: _ivJob(), cv_text: _ivCvText(), profile: _ivProfile(), lang: _ivLang(),
                             others: _ivOtherRecords([id]), final });
    const _prev = state.interview.answers[id] || {};
    state.interview.answers[id] = { answer, complete: data.complete, status: data.status, needs: data.needs,
                               score: data.score, verdict: data.verdict,
                               strengths: data.strengths, concerns: data.concerns, signals: data.signals,
                               // Keep any revealed model answer — it tracks the QUESTION, not the reply.
                               modelAnswer: _prev.modelAnswer, modelCovers: _prev.modelCovers };
    // Full re-render so the open/scored state and the right action buttons (Score now,
    // 💡 Suggest follow-up) all reflect the new status.
    _renderInterview();
    _persistInterview();
    // Only a COMPLETE answer feeds the assessment and the auto wrap-up — an open
    // exchange (clarifying/partial) must never move the candidate's numbers.
    if (_ivAnswerComplete(state.interview.answers[id])) {
      refreshAspects();
      if (_ivAllAnswered() && !state.interview.overall) summarizeInterview();
    }
  } catch(e) {
    actionBtns.forEach(b => b.disabled = false);
    alert('Analyze failed: ' + e.message);
  }
}

async function summarizeInterview() {
  const records = (state.interview.questions || [])
    .map(q => ({ question: q.question, ...(state.interview.answers[q.id] || {}) }))
    .filter(r => _ivAnswerComplete(r));   // only finished answers feed the wrap-up
  if (!records.length) return;
  const el  = document.getElementById('interviewOverall');
  const btn = el.querySelector('button');
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    const data = await api.post('/api/interview/summarize', { records, job: _ivJob(), cv_text: _ivCvText(), profile: _ivProfile(), lang: _ivLang() });
    state.interview.overall = { score: data.score, recommendation: data.recommendation, summary: data.summary };
    _renderInterviewOverall();
    _persistInterview();
  } catch(e) {
    _renderInterviewOverall();
    alert('Summary failed: ' + e.message);
  }
}

// Persist the interview into the saved job's extras.interview. Auto-saves the job
// to the pipeline on first analyze so the interview survives reopening.
async function _persistInterview() {
  if (!state.modalJob) return;
  const jobId  = state.modalJob.job_id;
  const isSaved = (state.savedJobs || []).some(j => String(j.job_id) === String(jobId));
  try {
    if (isSaved) {
      await api.raw(`/api/saved/${jobId}`, { method: 'PATCH', body: { extras: { interview: state.interview } } });
    } else {
      const status = document.getElementById('modalStatusSel')?.value || 'new';
      const data = await api.post('/api/saved', { job: { ...state.modalJob, candidate_name: app.getCandidateName() },
                                                  status, extras: { interview: state.interview },
                                                  candidate_profile: state.currentCandidateProfile || null });
      if (data.ok) {
        state.savedJobs = data.jobs;
        app.updateSavedBadge();
        const saveBtn = document.getElementById('modalSaveBtn');
        if (saveBtn) { saveBtn.textContent = '✓ Saved'; saveBtn.classList.add('saved'); }
        const tableBtn = document.getElementById(`save-${jobId}`);
        if (tableBtn) { tableBtn.textContent = '✓ Saved'; tableBtn.classList.add('saved'); }
      }
    }
  } catch(e) { /* persistence is best-effort; the in-memory interview stays intact */ }
}

async function descToggleCvQuestions() {
  const btn  = document.getElementById('descCvQuestionsBtn');
  const wrap = document.getElementById('modalDescCvQuestionsWrap');
  const card = document.getElementById('interviewScorecard');
  const msg  = document.getElementById('interviewMsg');
  if (!btn || btn.disabled) return;

  // Toggle closed
  if (state.descCvQuestionsShown) {
    state.descCvQuestionsShown = false;
    btn.textContent = 'Interview';
    btn.classList.remove('active');
    wrap.style.display = 'none';
    return;
  }

  // Opening
  state.descCvQuestionsShown = true;
  btn.classList.add('active');
  btn.textContent = 'Hide';
  wrap.style.display = '';

  // Already have questions (restored from a saved interview, generated, or imported)
  if (state.interview.questions && state.interview.questions.length) {
    msg.style.display = 'none';
    _renderInterview();
    _renderAspects();
    if (_ivCvText() && !(state.interview.aspects && state.interview.aspects.length)) refreshAspects();
    return;
  }

  // No CV → can't auto-generate gap questions, but the recruiter can still Import
  // or Add their own prepared questions.
  if (!_ivCvText()) {
    card.innerHTML = '';
    _renderInterviewControls();   // keeps 📥 Import / ➕ Add available
    document.getElementById('interviewAspects').style.display = 'none';
    document.getElementById('interviewOverall').style.display = 'none';
    msg.style.display = ''; msg.style.fontStyle = 'italic';
    msg.textContent = 'No CV loaded — use 📥 Import or ➕ Add question below, or load a candidate (example, paste, or upload a CV) to auto-generate gap questions and richer analysis.';
    return;
  }
  msg.style.display = 'none';

  // Generate fresh questions
  document.getElementById('interviewOverall').style.display = 'none';
  card.innerHTML = '<div class="iv-loading">Generating interview questions…</div>';
  btn.disabled = true;
  try {
    const data = await api.post('/api/interview/questions', { job: _ivJob(), cv_text: _ivCvText(), profile: _ivProfile(), lang: _ivLang() });
    state.interview.questions = data.questions;
    _renderInterview();
    refreshAspects();   // baseline candidate assessment from CV + profile
  } catch(e) {
    card.innerHTML = '';
    msg.style.display = ''; msg.style.fontStyle = 'italic';
    msg.textContent = 'Could not generate questions: ' + e.message;
  } finally { btn.disabled = false; }
}

async function descToggleOutreach() {
  const btn = document.getElementById('descOutreachBtn');
  if (!btn || btn.disabled) return;

  if (state.descOutreachShown) {
    state.descOutreachShown = false;
    btn.textContent = 'Outreach';
    btn.classList.remove('active');
    document.getElementById('modalDescOutreachWrap').style.display = 'none';
    return;
  }

  if (!state.descOutreach) {
    btn.disabled = true;
    btn.textContent = '…';
    try {
      const candidateName = document.getElementById('candidateName')?.value || '';
      const data = await api.post('/api/desc_outreach', {
        job: {
          title:    state.modalJob.title,
          company:  state.modalJob.company,
          location: [state.modalJob.city, state.modalJob.state].filter(Boolean).join(', '),
          salary:   state.modalJob.salary,
          skills:   state.modalJob.skills_en || state.modalJob.skills,
          description: state.descOriginal.slice(0, 1500),
        },
        candidate_name: candidateName,
        cv_text: state.lastParsedText ? state.lastParsedText.slice(0, 1500) : '',
        lang: state.modalLang,
      });
      state.descOutreach = data.text;
    } catch(e) {
      btn.disabled = false;
      btn.textContent = 'Outreach';
      return;
    }
    btn.disabled = false;
  }

  document.getElementById('modalDescOutreachText').textContent = state.descOutreach;
  document.getElementById('modalDescOutreachWrap').style.display = '';
  state.descOutreachShown = true;
  btn.textContent = 'Hide';
  btn.classList.add('active');
}


// Cross-module exports — registered on app so modal.js's registry (description
// toolbar + interview-scorecard controls) and modal.js's openJobModal (restore
// + reset) can call into this module without a direct import.
Object.assign(app, {
  _ivHasAnswers, _interviewRestore, _interviewReset,
  setIvPerspective, toggleFreezeInterview, regenerateInterview, addInterviewQuestion,
  toggleInterviewImport, analyzeAllInterview, toggleInterviewContext,
  _ivLoadImportFile, importInterviewQuestions,
  descToggleCvQuestions, descToggleOutreach,
});
