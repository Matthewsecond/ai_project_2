// ════════════════════════════════════════════════════════════
//  Guided candidate builder
// ════════════════════════════════════════════════════════════
// The "build a target candidate" chat — assembles a structured draft (sector,
// roles, skills, levels, languages, certs, salary, availability, notes) via a
// turn-based chat with quick-reply chips, then hands the draft to
// buildCandidateText() (candidate.js) for matching, or saves it as a reusable
// template candidate.
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";
import api from "./api.js";

const GB_LEVELS = ['Entry (0–2 yrs)', 'Mid (3–5 yrs)', 'Senior (6–10 yrs)', 'Expert / Lead (10+ yrs)'];
// The 14 sectors (mirror of core/categories.SECTORS labels) for the manual picker.
const GB_SECTORS = ['Healthcare & Care', 'Beauty & Personal Care', 'Education & Childcare',
  'Hospitality & Gastronomy', 'IT & Software', 'Construction & Trades', 'Logistics & Transport',
  'Retail & Sales', 'Office / Finance & Legal', 'Production & Manufacturing', 'Cleaning & Facility',
  'Security', 'Technical & Engineering', 'Management & Business'];
const GB_FIELDS = [
  { key:'sector',     label:'Sector',         type:'opts', opts:() => GB_SECTORS },
  { key:'roles',      label:'Target role',    type:'free', ph:'role + Enter' },
  { key:'skills',     label:'Key skills',     type:'free', ph:'skill + Enter' },
  { key:'levels',     label:'Seniority',      type:'opts', opts:() => GB_LEVELS },
  { key:'states',     label:'States',         type:'opts', opts:() => state.filterOpts.states },
  { key:'languages',  label:'Languages',      type:'free', ph:'e.g. German C1 + Enter' },
  { key:'certs',      label:'Certifications', type:'free', ph:'cert + Enter' },
  { key:'salary',     label:'Salary',         type:'text', ph:'e.g. €2,200+ or 4500–5500' },
  { key:'availability',label:'Availability',  type:'text', ph:'e.g. immediate or 2026-09' },
  { key:'notes',      label:'Notes',          type:'area', ph:'Industry preference, other context…', full:true },
];
const GB_LIST = ['sector','roles','skills','levels','states','languages','certs'];

let gbHistory   = [];   // {role:'ai'|'user', text, updates?, q?}
let gbUserEdits = [];   // manual edits since last send
let gbLastOffer = null; // options offered last turn: {kind, values} — for "choose all"
let gbLastField = '';   // draft field the last question targeted — for answer routing
let gbSel       = new Set(); // multi-select state for the current data-option chips
let gbReady     = false;
let gbBusy      = false;

// Broad sector starters shown under the opening question (single-click).
const GB_STARTERS = ['IT', 'Healthcare & care', 'Logistics & warehouse',
  'Retail & sales', 'Office & admin', 'Skilled trades', 'Hospitality'];

function gbInit() {
  if (gbReady) return;
  gbReady = true;
  gbRenderFields();
  gbHistory.push({ role:'ai',
    text:"Hi — I'll help you build a target candidate. Which role(s) are you hiring for?",
    chips: GB_STARTERS.map(s => ({ label: s, value: s })), chipsMulti: false });
  gbRenderThread();
}

function gbRenderFields() {
  const wrap = document.getElementById('gbFields');
  if (!wrap) return;
  wrap.innerHTML = '';
  GB_FIELDS.forEach(f => {
    const cell = document.createElement('div');
    cell.className = 'gb-field' + (f.full ? ' full' : '');
    const lbl = `<label>${f.label}</label>`;
    if (f.type === 'free' || f.type === 'opts') {
      const chips = (state.gbDraft[f.key] || []).map((v, i) =>
        `<span class="gb-chip">${esc(v)}<span class="x" data-action="gb-remove-item" data-key="${f.key}" data-i="${i}">×</span></span>`).join('');
      let entry;
      if (f.type === 'free') {
        entry = `<input type="text" placeholder="${f.ph}" data-gbfree="${f.key}"
          data-keydown-action="gb-add-item-enter" data-key="${f.key}">`;
      } else {
        const opts = (f.opts() || []).filter(o => !(state.gbDraft[f.key] || []).includes(o));
        entry = `<select data-change-action="gb-add-item-select" data-key="${f.key}">
          <option value="">+ add…</option>${opts.map(o => `<option>${esc(o)}</option>`).join('')}</select>`;
      }
      cell.innerHTML = `${lbl}<div class="gb-chips" id="gbc-${f.key}">${chips}${entry}</div>`;
    } else if (f.type === 'area') {
      cell.innerHTML = `${lbl}<textarea class="gb-text" id="gbt-${f.key}" placeholder="${f.ph}"
        data-input-action="gb-set-scalar" data-key="${f.key}">${esc(state.gbDraft[f.key] || '')}</textarea>`;
    } else {
      cell.innerHTML = `${lbl}<input type="text" class="gb-text" id="gbt-${f.key}" placeholder="${f.ph}"
        value="${esc(state.gbDraft[f.key] || '')}" data-input-action="gb-set-scalar" data-key="${f.key}">`;
    }
    wrap.appendChild(cell);
  });
}

function gbAddItem(key, val) {
  val = (val || '').trim();
  if (!val) return;
  if (!state.gbDraft[key].includes(val)) {
    state.gbDraft[key].push(val);
    gbRecordEdit(`added "${val}" to ${gbLabel(key)}`);
    gbRenderFields();
  }
}
function gbRemoveItem(key, idx) {
  const removed = state.gbDraft[key][idx];
  state.gbDraft[key].splice(idx, 1);
  gbRecordEdit(`removed "${removed}" from ${gbLabel(key)}`);
  gbRenderFields();
}
let _gbScalarTimer = {};
function gbSetScalar(key, val) {
  state.gbDraft[key] = val;
  clearTimeout(_gbScalarTimer[key]);
  _gbScalarTimer[key] = setTimeout(() => {
    if (val.trim()) gbRecordEdit(`set ${gbLabel(key)} to "${val.trim()}"`);
  }, 700);
}
function gbLabel(key) {
  if (key === 'name') return 'Template name';
  return (GB_FIELDS.find(f => f.key === key) || {}).label || key;
}
function gbRecordEdit(text) { gbUserEdits.push(text); }

// Action registry for the guided-builder dynamic fields + quick-reply chips.
Object.assign(_ACTIONS, {
  'gb-remove-item':     (el)    => gbRemoveItem(el.dataset.key, +el.dataset.i),
  'gb-add-item-enter':  (el, e) => { if (e.key === 'Enter') { e.preventDefault(); gbAddItem(el.dataset.key, el.value); el.value = ''; } },
  'gb-add-item-select': (el)    => { if (el.value) { gbAddItem(el.dataset.key, el.value); el.value = ''; } },
  'gb-set-scalar':      (el)    => gbSetScalar(el.dataset.key, el.value),
  'gb-quick':           (el)    => gbQuick(el.dataset.v),
  'gb-toggle':          (el)    => gbToggle(el.dataset.v),
  'gb-done':            ()      => gbDone(),
});

function gbRenderThread() {
  const t = document.getElementById('gbThread');
  if (!t) return;
  t.innerHTML = gbHistory.map((m, i) => {
    if (m.role === 'user') return `<div class="gb-msg user">${esc(m.text)}</div>`;
    const updates = (m.updates && m.updates.length)
      ? `<div class="gb-msg-updates">${m.updates.map(u => `<span class="u">${esc(u)}</span>`).join('')}</div>` : '';
    const main = `<div class="gb-msg ai">${esc(m.text)}${updates}</div>`;
    const q = m.q ? `<div class="gb-msg q">${esc(m.q)}</div>` : '';
    // Quick-reply chips — only on the most recent message.
    let chips = '';
    if (i === gbHistory.length - 1 && m.chips && m.chips.length) {
      if (m.chipsMulti) {
        // Multi-select toggles + green Done. A meta chip (label ending in "?",
        // e.g. "What are the options?") stays single-click and is never selected.
        const btns = m.chips.map(c => {
          if (/\?\s*$/.test(c.label))
            return `<button type="button" class="gb-quick-chip" data-action="gb-quick" data-v="${esc(c.value)}">${esc(c.label)}</button>`;
          return `<button type="button" class="gb-quick-chip${gbSel.has(c.value) ? ' sel' : ''}" `
            + `data-action="gb-toggle" data-v="${esc(c.value)}">${esc(c.label)}</button>`;
        }).join('');
        const done = `<button type="button" class="gb-quick-done" data-action="gb-done"`
          + `${gbSel.size ? '' : ' disabled'}>Done${gbSel.size ? ' (' + gbSel.size + ')' : ''}</button>`;
        chips = `<div class="gb-quick">${btns}${done}</div>`;
      } else {
        // Suggestions / starters: single-click send.
        chips = `<div class="gb-quick">${m.chips.map(c =>
          `<button type="button" class="gb-quick-chip" data-action="gb-quick" data-v="${esc(c.value)}">${esc(c.label)}</button>`).join('')}</div>`;
      }
    }
    return main + q + chips;
  }).join('');
  if (gbBusy) t.innerHTML += `<div class="gb-typing">assistant is typing…</div>`;
  t.scrollTop = t.scrollHeight;
}

async function gbSend() {
  const inp = document.getElementById('gbMsg');
  const msg = inp.value.trim();
  if (!msg || gbBusy) return;
  inp.value = '';
  gbSel = new Set();   // clear any multi-select from the previous turn
  // The assistant's last question — so "what are the options?" stays on-topic.
  const prevQ = [...gbHistory].reverse().find(m => m.role === 'ai' && m.q);
  const lastQuestion = prevQ ? prevQ.q : '';
  gbHistory.push({ role:'user', text:msg });
  const edits = gbUserEdits.slice();
  gbUserEdits = [];
  gbBusy = true;
  document.getElementById('gbSendBtn').disabled = true;
  gbRenderThread();

  try {
    const data = await api.post('/api/guided/chat', { message: msg, draft: state.gbDraft, user_edits: edits, last_offer: gbLastOffer, lang: state.jobChatLang, last_question: lastQuestion, last_field: gbLastField });
    const changed = gbApplyDraft(data.draft, data.field_updates);
    const chips = gbBuildChips(data.options, data.suggestions, !!data.next_question);
    // Both data-option chips (sector/role/region) and free-text suggestions
    // (skills, seniority…) are multi-select + Done, so several can be picked.
    const chipsMulti = chips.length > 0;
    gbHistory.push({ role:'ai', text:data.reply, updates:changed,
                     q:data.next_question || '', chips, chipsMulti });
    // Remember the field the question targets, so the next answer is filed there.
    gbLastField = data.answer_field || '';
    // Remember what we offered so a multi-pick "Done" resolves to the right field —
    // facet picks by their facet, free-text suggestions by their answer_field
    // (excluding any "…?" meta chip, which must never be filed as an answer).
    gbLastOffer = (data.options && data.options.length && data.facet)
      ? { kind: data.facet, values: data.options.map(o => o.value) }
      : (data.suggestions && data.suggestions.length && data.answer_field)
        ? { kind: data.answer_field, values: data.suggestions.filter(s => !/\?\s*$/.test(s)) }
        : null;
  } catch(e) {
    gbHistory.push({ role:'ai', text:'Sorry — something went wrong (' + e.message + '). Try again.' });
  } finally {
    gbBusy = false;
    document.getElementById('gbSendBtn').disabled = false;
    gbRenderThread();
  }
}

// Build quick-reply chips shown under a question. Two sources:
//  • options    — real data-backed picks (role families / regions) with counts;
//                 carry the canonical German `value` (sent on click / stored).
//  • suggestions — short model-proposed answers for open questions (skills,
//                 seniority, salary…), incl. a "What are the options?" chip;
//                 the label is also the value sent on click.
// Chips show only when there's a question to answer.
function gbBuildChips(options, suggestions, hasQuestion) {
  if (!hasQuestion) return [];
  if (options && options.length)
    return options.slice(0, 5).map(o => ({ label: `${o.label} (${o.n})`, value: o.value }));
  return (suggestions || []).slice(0, 5).map(s => ({ label: s, value: s }));
}

// Click a quick-reply chip → send its value as the user's next message.
function gbQuick(value) {
  if (gbBusy || !value) return;
  const inp = document.getElementById('gbMsg');
  inp.value = value;
  gbSend();
}

// Multi-select: toggle a data-option chip on/off, then submit the lot with Done.
function gbToggle(value) {
  if (gbBusy || !value) return;
  if (gbSel.has(value)) gbSel.delete(value); else gbSel.add(value);
  gbRenderThread();
}
function gbDone() {
  if (gbBusy || !gbSel.size) return;
  const vals = [...gbSel];
  gbSel = new Set();
  document.getElementById('gbMsg').value = vals.join(', ');
  gbSend();
}

// Replace draft, re-render, flash changed fields. Returns human labels of changes.
function gbApplyDraft(newDraft, fieldUpdates) {
  const changedKeys = Object.keys(fieldUpdates || {}).filter(k => k in state.gbDraft);
  state.gbDraft = { ...state.gbDraft, ...newDraft };
  gbRenderFields();
  const labels = [];
  changedKeys.forEach(k => {
    labels.push(gbLabel(k));
    const el = document.getElementById('gbc-' + k) || document.getElementById('gbt-' + k);
    if (el) { el.classList.add('flash'); setTimeout(() => el.classList.remove('flash'), 1400); }
  });
  return labels;
}

// Build the candidate profile object (Match Insights shape) from the draft.
function gbProfileFromDraft() {
  const d = state.gbDraft;
  const j = (a) => (a || []).filter(Boolean).join(', ');
  return {
    name: d.name || document.getElementById('candidateName').value.trim() || 'Template candidate',
    title: j(d.roles),
    skills: (d.skills || []).filter(Boolean),
    languages: j(d.languages),
    salary_expectation: d.salary || '',
    location: j(d.states),
    availability: d.availability || '',
    source: 'template',   // marks this as a template candidate (vs a real CV one)
  };
}

async function gbSaveTemplate() {
  const ab = state.lastResults.filter(j => j.grade !== 'C');
  if (!ab.length) { alert('Run matching first — then save the matched A/B roles as a template candidate.'); return; }

  // Name the template candidate (draft name → prompt fallback).
  let name = (state.gbDraft.name || '').trim();
  if (!name) name = (prompt('Name this template candidate:', gbProfileFromDraft().title || 'Template candidate') || '').trim();
  if (!name) return;
  state.gbDraft.name = name;

  // Wire the profile so saved jobs carry the template profile for Match Insights.
  state.currentCandidateProfile = { ...gbProfileFromDraft(), name };
  app._trackLocalCandidate(state.currentCandidateProfile);
  document.getElementById('candidateName').value = name;

  const btn = document.getElementById('gbSaveTemplateBtn');
  btn.disabled = true; const orig = btn.textContent; btn.textContent = 'Saving…';
  try {
    await app.saveAll();   // saves A/B roles under app.getCandidateName() with the profile
    btn.textContent = '✓ Saved to pipeline';
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2000);
  } catch(e) {
    btn.textContent = 'Error — retry'; btn.disabled = false;
  }
}


// Action registry for the guided-builder send box + save-template button
// (split out of the search-tab's mixed registry block since these route here).
Object.assign(_ACTIONS, {
  'gb-send-enter':           (el, e) => { if (e.key === 'Enter') { e.preventDefault(); gbSend(); } },
  'gb-send':                 ()      => gbSend(),
  'gb-save-template':        ()      => gbSaveTemplate(),
});

// Cross-module export — registered on app so the page module's mode-tab/workflow
// listeners and candidate.js's setWorkflow() can call into this module.
Object.assign(app, { gbInit });
