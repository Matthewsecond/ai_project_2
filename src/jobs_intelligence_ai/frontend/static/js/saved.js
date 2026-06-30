// ════════════════════════════════════════════════════════════
//  Saved tab — the database view (Candidates / Jobs / Companies / Contacts)
// ════════════════════════════════════════════════════════════
// A simple switcher over the four saved collections. Everything you save goes
// straight to the database; this tab just reads it back. Each collection renders
// the same sortable grid (click a header to sort, per-row Remove). No session/
// local staging, no dashboard — those were removed in the simplification.
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";

let _savedCollection = 'candidates';   // candidates | jobs | companies | contacts
let _collRows = [];
let _collSort = { key: null, dir: 1 };

// Each collection: the GET endpoint + the response key, the columns to show
// (label + value getter), the empty-state text, and how to build the DELETE URL
// for a row (candidates delete by name; the rest by saved-row id).
const SAVED_COLLECTIONS = {
  candidates: {
    url: '/api/saved/candidates', listKey: 'candidates', empty: 'No saved candidates yet.',
    cols: [
      { key:'name',      label:'Name',      get:r => r.name },
      { key:'title',     label:'Title',     get:r => r.title },
      { key:'seniority', label:'Seniority', get:r => r.seniority },
      { key:'location',  label:'Location',  get:r => r.location },
      { key:'status',    label:'Status',    get:r => r.status },
      { key:'matches',   label:'Matches',   get:r => r.matches },
      { key:'email',     label:'Email',     get:r => r.email },
      { key:'lastSaved', label:'Last saved',get:r => r.lastSaved },
    ],
    delId: r => r.name,
    delUrl: id => '/api/saved/candidate/' + encodeURIComponent(id),
  },
  jobs: {
    url: '/api/saved', listKey: 'jobs', empty: 'No saved jobs yet — save matches from a search.',
    cols: [
      { key:'title',           label:'Title',     get:r => r.title },
      { key:'company',         label:'Company',   get:r => r.company },
      { key:'location',        label:'Location',  get:r => r.location },
      { key:'candidate_name',  label:'Candidate', get:r => r.candidate_name },
      { key:'pipeline_status', label:'Status',    get:r => r.pipeline_status },
      { key:'notes',           label:'Notes',     get:r => r.notes },
    ],
    delId: r => r.job_id,
    delUrl: id => '/api/saved/' + encodeURIComponent(id),
  },
  companies: {
    url: '/api/saved/companies', listKey: 'companies', empty: 'No saved companies yet — save a target company from a search.',
    cols: [
      { key:'name',     label:'Company',  get:r => r.name || ('#' + r.target_company_id) },
      { key:'industry', label:'Industry', get:r => r.industry },
      { key:'location', label:'Location', get:r => r.location || r.city },
      { key:'notes',    label:'Notes',    get:r => r.notes },
      { key:'savedAt',  label:'Saved',    get:r => r.savedAt },
    ],
    delId: r => r.id,
    delUrl: id => '/api/saved/companies/' + encodeURIComponent(id),
  },
  contacts: {
    url: '/api/saved/contacts', listKey: 'contacts', empty: 'No saved contacts yet — save a contact from a search.',
    cols: [
      { key:'name',    label:'Name',    get:r => r.name || ('#' + r.contact_id) },
      { key:'title',   label:'Title',   get:r => r.title || r.position },
      { key:'company', label:'Company', get:r => r.company },
      { key:'email',   label:'Email',   get:r => r.email },
      { key:'notes',   label:'Notes',   get:r => r.notes },
      { key:'savedAt', label:'Saved',   get:r => r.savedAt },
    ],
    delId: r => r.id,
    delUrl: id => '/api/saved/contacts/' + encodeURIComponent(id),
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
  loadCollection(kind);
}

async function loadCollection(kind){
  const spec   = SAVED_COLLECTIONS[kind]; if (!spec) return;
  const status = document.getElementById('savedLoadStatus');
  if (status) status.textContent = 'Loading…';
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
  body.innerHTML = rows.map(r =>
    '<tr>' + spec.cols.map(c => `<td>${esc((c.get(r) ?? '').toString())}</td>`).join('') +
    `<td><button class="sv-row-del" data-action="delete-saved-row" data-id="${esc((spec.delId(r) ?? '').toString())}">Remove</button></td></tr>`
  ).join('');
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

// Saving now writes straight to the database, so session staging is gone. Kept
// as a no-op so the candidate/guided callers don't need to change.
function _trackLocalCandidate(){ /* intentionally empty */ }

Object.assign(_ACTIONS, {
  'set-saved-collection': (el) => setSavedCollection(el.dataset.collection),
  'sort-collection':      (el) => sortCollection(el.dataset.key),
  'delete-saved-row':     (el) => deleteSavedRow(el.dataset.id),
});

Object.assign(app, { openSavedTab, _trackLocalCandidate, loadSaved });
