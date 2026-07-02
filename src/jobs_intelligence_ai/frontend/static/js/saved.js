// ════════════════════════════════════════════════════════════
//  Saved tab — the database view (Candidates / Jobs / Companies / Contacts)
// ════════════════════════════════════════════════════════════
// A simple switcher over the four saved collections. Everything you save goes
// straight to the database; this tab just reads it back. Each collection renders
// the same sortable grid (click a header to sort, per-row Remove). No session/
// local staging, no dashboard — those were removed in the simplification.
import { state, _ACTIONS, app } from "./state.js";
import { esc, storeJob } from "./util.js";

let _savedCollection = 'candidates';   // candidates | jobs | companies | contacts
let _collRows = [];
let _collSort = { key: null, dir: 1 };
let _editKey  = null;                   // row currently in inline-edit mode (its delId), or null

const _CAND_STATUS = ['New', 'Contacted', 'Interviewing', 'Placed', 'Rejected'];
const _SENIORITY   = ['', 'Junior', 'Mid', 'Senior', 'Lead', 'Executive'];

// Saved-job sales pipeline: canonical codes in the DB, labels in the UI (i18n-ready).
// Distinct from the candidate *hiring* pipeline above.
const _JOB_PIPELINE = [
  ['new',           'New'],
  ['in_progress',   'In Progress'],
  ['proposal_sent', 'Proposal Sent'],
  ['won',           'Won'],
  ['lost',          'Lost'],
];
const _JOB_PIPELINE_LABEL = Object.fromEntries(_JOB_PIPELINE);

// The status cell is always a live dropdown — changing it PATCHes immediately,
// no row Edit mode needed. Unknown legacy values stay selectable verbatim.
function _statusSelect(r){
  const code = (r.pipeline_status || 'new').toString();
  const opts = _JOB_PIPELINE_LABEL[code] ? _JOB_PIPELINE : [[code, code], ..._JOB_PIPELINE];
  return `<select class="sv-status-select sv-status-${esc(code)}" data-change-action="set-job-status"`
    + ` data-id="${esc(String(r.job_id))}">`
    + opts.map(([c, l]) => `<option value="${esc(c)}"${c === code ? ' selected' : ''}>${esc(l)}</option>`).join('')
    + `</select>`;
}

async function setJobStatus(el){
  const id = el.dataset.id, code = el.value;
  el.disabled = true;
  try {
    const res  = await fetch('/api/saved/' + encodeURIComponent(id), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_status: code }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || ('HTTP ' + res.status));
    const row = _collRows.find(r => String(r.job_id) === id);
    if (row) row.pipeline_status = code;
    el.className = 'sv-status-select sv-status-' + code;
    el.disabled = false;
  } catch(e){
    el.disabled = false;
    alert('Status update failed: ' + (e.message || e));
    loadCollection(_savedCollection);   // reload so the select reflects the real DB state
  }
}

// Each collection: the GET endpoint + the response key, the columns to show (label +
// value getter; `edit` marks a column as inline-editable, 'select' with `opts` for a
// dropdown), the empty-state text, and how to build the DELETE / PATCH URLs for a row
// (candidates key off the name; the rest off the saved-row id). A row's edited column
// keys are sent verbatim as the PATCH body — the backend enforces the field allow-list.
const SAVED_COLLECTIONS = {
  candidates: {
    url: '/api/saved/candidates', listKey: 'candidates', empty: 'No saved candidates yet.',
    cols: [
      // The name opens the candidate detail modal (see candidate.js openCandidateDetail).
      { key:'name',      label:'Name',      get:r => r.name,
        render:r => `<a class="cand-name-link" data-action="open-candidate" data-name="${esc(r.name)}">${esc(r.name)}</a>` },
      { key:'title',     label:'Title',     get:r => r.title,     edit:true },
      { key:'seniority', label:'Seniority', get:r => r.seniority, edit:'select', opts:_SENIORITY },
      { key:'location',  label:'Location',  get:r => r.location,  edit:true },
      { key:'status',    label:'Status',    get:r => r.status,    edit:'select', opts:_CAND_STATUS },
      { key:'matches',   label:'Matches',   get:r => r.matches },
      { key:'createdBy', label:'Saved by',  get:r => r.createdBy },
      { key:'lastSaved', label:'Last saved',get:r => r.lastSaved },
    ],
    delId: r => r.name,
    delUrl: id => '/api/saved/candidate/' + encodeURIComponent(id),
    patchUrl: r => '/api/saved/candidate/' + encodeURIComponent(r.name),
  },
  jobs: {
    url: '/api/saved', listKey: 'jobs', empty: 'No saved jobs yet — save matches from a search.',
    cols: [
      // Title opens the full job detail modal (reuses search's openJobModal).
      { key:'title',           label:'Title',     get:r => r.title,           edit:true, detail:true },
      { key:'company',         label:'Company',   get:r => r.company,         edit:true },
      { key:'location',        label:'Location',  get:r => r.location,        edit:true },
      { key:'candidate_name',  label:'Candidate', get:r => r.candidate_name },
      // Always a live dropdown (see _statusSelect) — no Edit mode needed to change it.
      { key:'pipeline_status', label:'Status',
        get:r => _JOB_PIPELINE_LABEL[r.pipeline_status] || r.pipeline_status,
        render:r => _statusSelect(r) },
      { key:'notes',           label:'Notes',     get:r => r.notes,           edit:true },
    ],
    delId: r => r.job_id,
    delUrl: id => '/api/saved/' + encodeURIComponent(id),
    patchUrl: r => '/api/saved/' + encodeURIComponent(r.job_id),
  },
  companies: {
    url: '/api/saved/companies', listKey: 'companies', empty: 'No saved companies yet — save a target company from a search.',
    cols: [
      // Company name opens the full company panel (reuses openCompanyPanel).
      { key:'name',     label:'Company',  get:r => r.name || ('#' + r.target_company_id), edit:true, detail:true },
      { key:'industry', label:'Industry', get:r => r.industry, edit:true },
      { key:'location', label:'Location', get:r => r.location || r.city, edit:true },
      { key:'notes',    label:'Notes',    get:r => r.notes, edit:true },
      { key:'savedAt',  label:'Saved',    get:r => r.savedAt },
    ],
    delId: r => r.id,
    delUrl: id => '/api/saved/companies/' + encodeURIComponent(id),
    patchUrl: r => '/api/saved/companies/' + encodeURIComponent(r.id),
  },
  contacts: {
    url: '/api/saved/contacts', listKey: 'contacts', empty: 'No saved contacts yet — save a contact from a search.',
    cols: [
      // Name opens the contact detail modal (openContactDetail, below).
      { key:'name',    label:'Name',    get:r => r.name || ('#' + r.contact_id), edit:true, detail:true },
      { key:'title',   label:'Title',   get:r => r.title || r.position, edit:true },
      { key:'company', label:'Company', get:r => r.company, edit:true },
      { key:'email',   label:'Email',   get:r => r.email, edit:true },
      { key:'notes',   label:'Notes',   get:r => r.notes, edit:true },
      { key:'savedAt', label:'Saved',   get:r => r.savedAt },
    ],
    delId: r => r.id,
    delUrl: id => '/api/saved/contacts/' + encodeURIComponent(id),
    patchUrl: r => '/api/saved/contacts/' + encodeURIComponent(r.id),
  },
};

// Tab activation (boot.js) → show the active collection.
function openSavedTab(){ setSavedCollection(_savedCollection); }

function setSavedCollection(kind){
  if (!SAVED_COLLECTIONS[kind]) kind = 'candidates';
  _savedCollection = kind;
  document.querySelectorAll('#svCollectionToggle .sv-tab').forEach(b =>
    b.classList.toggle('active', b.dataset.collection === kind));
  _collSort = { key: null, dir: 1 };
  _editKey  = null;
  loadCollection(kind);
}

async function loadCollection(kind){
  const spec   = SAVED_COLLECTIONS[kind]; if (!spec) return;
  const status = document.getElementById('savedLoadStatus');
  if (status) status.textContent = 'Loading…';
  _editKey = null;
  try {
    const res  = await fetch(spec.url);
    const data = await res.json();
    _collRows  = (data.ok && data[spec.listKey]) ? data[spec.listKey] : [];
    if (status) status.textContent = `${_collRows.length} saved ${kind}`;
  } catch(e){
    _collRows = [];
    if (status) status.textContent = 'Load failed: ' + (e.message || e);
  }
  renderCollection();
}

function sortCollection(key){
  if (_collSort.key === key) _collSort.dir *= -1;
  else _collSort = { key, dir: 1 };
  _editKey = null;   // sorting exits any in-progress edit
  renderCollection();
}

function renderCollection(){
  const spec    = SAVED_COLLECTIONS[_savedCollection]; if (!spec) return;
  const head    = document.getElementById('savedCollHead');
  const body    = document.getElementById('savedCollBody');
  const emptyEl = document.getElementById('savedCollEmpty');
  head.innerHTML = spec.cols.map(c => {
    const arrow = _collSort.key === c.key ? (_collSort.dir > 0 ? ' ▲' : ' ▼') : '';
    return `<th data-action="sort-collection" data-key="${c.key}" style="cursor:pointer">${esc(c.label)}${arrow}</th>`;
  }).join('') + '<th></th>';

  let rows = _collRows.slice();
  if (_collSort.key){
    const col = spec.cols.find(c => c.key === _collSort.key);
    rows.sort((a, b) => {
      const av = (col.get(a) ?? '').toString().toLowerCase();
      const bv = (col.get(b) ?? '').toString().toLowerCase();
      return av < bv ? -_collSort.dir : av > bv ? _collSort.dir : 0;
    });
  }
  if (!rows.length){
    body.innerHTML = '';
    emptyEl.textContent = spec.empty;
    emptyEl.style.display = '';
    return;
  }
  emptyEl.style.display = 'none';
  body.innerHTML = rows.map(r => _renderRow(spec, r)).join('');
  // Focus the first editable input when a row enters edit mode.
  if (_editKey !== null) body.querySelector('.sv-cell-input')?.focus();
}

// One <tr> — cells become inputs when this row is the one being edited; the actions
// cell swaps Edit/Remove for Save/Cancel.
function _renderRow(spec, r){
  const key     = (spec.delId(r) ?? '').toString();
  const editing = _editKey !== null && key === _editKey;
  const cells = spec.cols.map(c => {
    if (editing && c.edit) return `<td>${_cellInput(c, (c.get(r) ?? '').toString(), key)}</td>`;
    if (c.render)  return `<td>${c.render(r)}</td>`;
    // A `detail` column becomes a link that opens the item's detail view (like the
    // candidate name link, but dispatched by collection — see openSavedDetail).
    if (c.detail)  return `<td><a class="cand-name-link" data-action="open-saved-detail" `
      + `data-key="${esc(key)}">${esc((c.get(r) ?? '—').toString() || '—')}</a></td>`;
    return `<td>${esc((c.get(r) ?? '').toString())}</td>`;
  }).join('');
  const actions = editing
    ? `<button class="sv-row-save" data-action="save-saved-row"   data-key="${esc(key)}">Save</button>`
      + `<button class="sv-row-edit" data-action="cancel-saved-row">Cancel</button>`
    : `<button class="sv-row-edit" data-action="edit-saved-row"   data-key="${esc(key)}">Edit</button>`
      + `<button class="sv-row-del"  data-action="delete-saved-row" data-id="${esc(key)}">Remove</button>`;
  return `<tr data-rowkey="${esc(key)}">${cells}<td class="sv-actions">${actions}</td></tr>`;
}

// An editable cell: a <select> for enum columns (keeps the current value even if it's
// not one of the presets), else a text <input>. Enter saves, Escape cancels.
function _cellInput(c, val, key){
  const common = `class="sv-cell-input" data-key="${esc(c.key)}" `
    + `data-keydown-action="saved-edit-key" data-rowkey="${esc(key)}"`;
  if (c.edit === 'select'){
    let opts = c.opts || [];
    if (val && !opts.includes(val)) opts = [val, ...opts];
    return `<select ${common}>` +
      opts.map(o => `<option${o === val ? ' selected' : ''}>${esc(o)}</option>`).join('') +
      `</select>`;
  }
  return `<input ${common} value="${esc(val)}">`;
}

function editSavedRow(key){ _editKey = key; renderCollection(); }
function cancelSavedRow(){ _editKey = null; renderCollection(); }

// Collect the edited cell values for a row and PATCH them to the collection's endpoint.
async function saveSavedRow(key){
  const spec = SAVED_COLLECTIONS[_savedCollection]; if (!spec) return;
  const row  = _collRows.find(r => (spec.delId(r) ?? '').toString() === key);
  const tr   = [...document.querySelectorAll('#savedCollBody tr')].find(t => t.dataset.rowkey === key);
  if (!row || !tr){ _editKey = null; renderCollection(); return; }

  const body = {};
  tr.querySelectorAll('.sv-cell-input[data-key]').forEach(inp => { body[inp.dataset.key] = inp.value; });
  const saveBtn = tr.querySelector('[data-action="save-saved-row"]');
  if (saveBtn){ saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
  try {
    const res  = await fetch(spec.patchUrl(row), {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || ('HTTP ' + res.status));
    _editKey = null;
    loadCollection(_savedCollection);
    if (_savedCollection === 'jobs') app.loadSaved?.();   // keep the nav badge / export array fresh
  } catch(e){
    if (saveBtn){ saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
    alert('Save failed: ' + (e.message || e));
  }
}

async function deleteSavedRow(id){
  const spec = SAVED_COLLECTIONS[_savedCollection]; if (!spec) return;
  try { await fetch(spec.delUrl(id), { method: 'DELETE' }); }
  catch(e){ /* the reload below reflects the real state regardless */ }
  loadCollection(_savedCollection);
}

// Called from outside the tab (e.g. modal.js after deleting a job): keep the nav
// badge + export array in sync, and refresh the grid if the Saved tab is open.
async function loadSaved(){
  try {
    const res  = await fetch('/api/saved');
    const data = await res.json();
    if (data.ok){ state.savedJobs = data.jobs; app.updateSavedBadge(); }
  } catch(e){ /* badge stays as-is on failure */ }
  if (document.getElementById('tab-saved')?.classList.contains('active'))
    loadCollection(_savedCollection);
}

// ── Detail views (click a title in the grid) ─────────────────────────────────
// Same idea as the candidate name link: clicking a Job / Company / Contact title
// opens a detail view for that row. Jobs and Companies reuse the richer modals the
// search tab already has; Contacts get a small dedicated modal (openContactDetail).
function openSavedDetail(key){
  const spec = SAVED_COLLECTIONS[_savedCollection]; if (!spec) return;
  const row  = _collRows.find(r => (spec.delId(r) ?? '').toString() === key);
  if (!row) return;
  if (_savedCollection === 'jobs')            app.openJobModal(storeJob(row));
  else if (_savedCollection === 'companies')  app.openCompanyPanel(row.name || ('#' + row.target_company_id));
  else if (_savedCollection === 'contacts')   openContactDetail(row);
}

// Contact detail modal — the saved contact's snapshot fields plus the jobs the
// contact is linked to in the market (loaded async from /api/contact/jobs).
async function openContactDetail(r){
  const modal = document.getElementById('ctModal');
  document.getElementById('ctModalName').textContent = r.name || ('Contact #' + r.contact_id);
  document.getElementById('ctModalSub').textContent  =
    [r.title || r.position, r.company].filter(Boolean).join(' · ');

  const links = [];
  if (r.email)    links.push(`<a href="mailto:${esc(r.email)}">${esc(r.email)}</a>`);
  if (r.phone)    links.push(esc(r.phone));
  if (r.linkedin) links.push(`<a href="${esc(r.linkedin)}" target="_blank">LinkedIn ↗</a>`);
  let html = links.length ? `<div class="cd-contact">${links.join('<span class="cd-dot">·</span>')}</div>` : '';

  const facts = [
    ['Title',    r.title || r.position],
    ['Company',  r.company],
    ['Location', r.location || r.city],
    ['Saved',    r.savedAt],
  ].map(([l, v]) => v ? `<span class="cd-fact"><span class="cd-fact-l">${esc(l)}</span> ${esc(String(v))}</span>` : '')
   .filter(Boolean).join('');
  if (facts) html += `<div class="cd-facts">${facts}</div>`;

  if (r.notes) html += `<div class="co-section-hdr">Notes</div><div class="co-summary-box">${esc(r.notes)}</div>`;

  // Linked jobs section — filled in once the fetch below resolves.
  html += `<div class="co-section-hdr" style="margin-top:18px">Jobs `
       +  `<span class="co-contact-count" id="ctJobCount"></span></div>`
       +  `<div id="ctModalJobs"><div class="co-loading-wrap"><div class="co-spinner"></div>`
       +  `<span>Loading jobs…</span></div></div>`;
  document.getElementById('ctModalBody').innerHTML = html;
  modal.classList.remove('hidden');

  const jobsEl = document.getElementById('ctModalJobs');
  const cid    = r.contact_id;
  if (!cid){ jobsEl.innerHTML = `<div class="co-no-data" style="padding:14px 0">No linked jobs.</div>`; return; }
  try {
    const res  = await fetch('/api/contact/jobs?contact_id=' + encodeURIComponent(cid));
    const data = await res.json();
    const jobs = (data.ok && data.jobs) ? data.jobs : [];
    const cnt  = document.getElementById('ctJobCount');
    if (cnt) cnt.textContent = jobs.length;
    if (!jobs.length){
      jobsEl.innerHTML = `<div class="co-no-data" style="padding:14px 0">This contact isn't linked to any active jobs.</div>`;
      return;
    }
    jobsEl.innerHTML = `<div class="co-job-list">` + jobs.map(j => {
      const loc   = [j.city, j.state].filter(Boolean).join(', ') || '—';
      const sal   = j.salary ? `<span class="co-job-meta-sal">€${esc(String(j.salary))}</span>` : '';
      const attrs = j.url ? `href="${esc(j.url)}" target="_blank"` : '';
      return `<a class="co-job-row" ${attrs}>
        <div class="co-job-row-title">${esc(j.title || '—')}</div>
        <div class="co-job-row-meta"><span>${esc(j.company || '')}</span><span>📍 ${esc(loc)}</span>${sal}${j.portal ? `<span>${esc(j.portal)}</span>` : ''}${j.posted ? `<span>${esc(j.posted)}</span>` : ''}</div>
      </a>`;
    }).join('') + `</div>`;
  } catch(e){
    jobsEl.innerHTML = `<div class="co-no-data" style="padding:14px 0">Could not load jobs: ${esc(e.message || e)}</div>`;
  }
}
function closeContactDetail(){ document.getElementById('ctModal').classList.add('hidden'); }

// Saving now writes straight to the database, so session staging is gone. Kept
// as a no-op so the candidate/guided callers don't need to change.
function _trackLocalCandidate(){ /* intentionally empty */ }

Object.assign(_ACTIONS, {
  'set-saved-collection': (el) => setSavedCollection(el.dataset.collection),
  'sort-collection':      (el) => sortCollection(el.dataset.key),
  'edit-saved-row':       (el) => editSavedRow(el.dataset.key),
  'save-saved-row':       (el) => saveSavedRow(el.dataset.key),
  'cancel-saved-row':     ()   => cancelSavedRow(),
  'saved-edit-key':       (el, e) => {
    if (e.key === 'Enter'){ e.preventDefault(); saveSavedRow(el.dataset.rowkey); }
    else if (e.key === 'Escape'){ e.preventDefault(); cancelSavedRow(); }
  },
  'delete-saved-row':     (el) => deleteSavedRow(el.dataset.id),
  'set-job-status':       (el) => setJobStatus(el),
  'open-candidate':       (el) => app.openCandidateDetail(el.dataset.name,
                                     _collRows.find(r => r.name === el.dataset.name)),
  'open-saved-detail':    (el) => openSavedDetail(el.dataset.key),
  'ct-modal-close':       ()   => closeContactDetail(),
  'ct-modal-backdrop':    (el, e) => { if (e.target === el) closeContactDetail(); },
});

// After an edit/delete in the candidate detail modal, refresh the grid if it's the
// active collection (so the row reflects the change without a manual reload).
function refreshSavedIfCandidates(){
  if (_savedCollection === 'candidates') loadCollection('candidates');
}

Object.assign(app, { openSavedTab, _trackLocalCandidate, loadSaved, refreshSavedIfCandidates });
