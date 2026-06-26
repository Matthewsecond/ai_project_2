// ════════════════════════════════════════════════════════════
//  Saved jobs panel — candidate-centric dashboard + table
// ════════════════════════════════════════════════════════════
// The Saved tab: Match Insights dashboard (per-candidate analysis cards) and
// the candidate table (DB-persisted + session-local rows, column chooser,
// per-column filters, inline edits), plus the interview-notes chat docked
// in the dashboard.
import { state, _ACTIONS, app } from "./state.js";
import { esc } from "./util.js";
import api from "./api.js";
import { exportSaved, generateSavedReport } from "./export.js";

//  Saved jobs panel
// ════════════════════════════════════════════════════════════
// ── Match Insights dashboard state ───────────────────────────────────────────
let _miCandidates = [];   // [{name, initials, matches, gradeA, createdBy, createdAt, hasProfile}]
let _miIdx        = 0;
let _miD          = null; // current candidate insights payload
const _miCache    = {};   // candidate name → insights payload
let _savedSource  = 'db';   // 'db' (persisted) | 'local' (session, not yet saved)
let _savedKind    = 'real'; // 'real' (CV candidates) | 'template' (guided builder)
let _savedDbLoaded = false;  // has the user explicitly pulled from MySQL this session?
let _localCandidates = [];  // session candidate profiles not yet pushed to MySQL

// A template candidate is one built in the guided builder (is_template flag).
function _isTemplate(c){ return !!c.isTemplate; }

// Remember a candidate built/parsed in this session so it can be reviewed and
// saved from the Saved-tab "Local" view. Keyed by name; later edits overwrite.
function _trackLocalCandidate(profile){
  if (!profile) return;
  const name = (profile.name || '').trim();
  if (!name || name === 'Unassigned') return;
  const entry = { ...profile, name };
  const i = _localCandidates.findIndex(c => c.name === name);
  if (i >= 0) _localCandidates[i] = entry; else _localCandidates.push(entry);
  _refreshLocalCount();
}

// Local candidates still worth showing = those not already persisted in the DB.
function _localCandidatesForView(){
  const dbNames = new Set(_miCandidates.map(c => c.name));
  return _localCandidates
    .filter(p => !dbNames.has((p.name || '').trim()))
    .map(_localToRow);
}

// Shape a session profile like a /api/saved/candidates row so the table renders
// it uniformly. _local/_profile flag it for the "Save to database" action.
function _localToRow(p){
  const skillSrc = (Array.isArray(p.top_skills) && p.top_skills.length) ? p.top_skills : p.skills;
  const skills = Array.isArray(skillSrc) ? skillSrc.join(', ') : (skillSrc || '');
  const name = p.name || '';
  return {
    name, initials: app._initials(name || '?'),
    status: p.status || 'New', title: p.title || '', summary: p.summary || '',
    email: p.email || '', phone: p.phone || '', linkedin: p.linkedin || '',
    location: p.location || '', languages: p.languages || '', skills,
    experience: (p.years_experience ? `${p.years_experience} years` : (p.experience_years || '')),
    salary: p.salary_expectation || '',
    availability: p.availability || '', source: '', matches: 0, gradeA: 0,
    // AI-analysed fields (LinkedIn imports)
    seniority: p.seniority || '', industry: p.industry || '',
    roleCategory: p.role_category || '', educationLevel: p.education_level || '',
    estSalary: _fmtEstSalary(p), aiSummary: p.ai_summary || '',
    isTemplate: (p.source || '').toLowerCase() === 'template',
    createdBy: '', createdAt: '', lastSaved: '', hasProfile: true,
    _local: true, _profile: p,
  };
}

// "€3,000–4,200/mo" from a profile's AI salary estimate, or '' if absent.
function _fmtEstSalary(p){
  const lo = p.estimated_salary_min, hi = p.estimated_salary_max;
  if (!lo || !hi) return '';
  return `€${(+lo).toLocaleString()}–${(+hi).toLocaleString()}/mo`;
}

// The candidate list backing the table for the active source AND kind.
function _svActiveList(){
  const base = _savedSource === 'local' ? _localCandidatesForView() : _miCandidates;
  const wantTemplate = _savedKind === 'template';
  return base.filter(c => _isTemplate(c) === wantTemplate);
}

function _refreshLocalCount(){
  const el = document.getElementById('svLocalCount');
  if (!el) return;
  // Count only the local candidates of the kind currently in view.
  const wantTemplate = _savedKind === 'template';
  const n = _localCandidatesForView().filter(c => _isTemplate(c) === wantTemplate).length;
  el.textContent = n ? String(n) : '';
}

const _MI_SPARK = '<svg viewBox="0 0 24 24"><path d="M12 2l2.2 5.8L20 10l-5.8 2.2L12 18l-2.2-5.8L4 10l5.8-2.2L12 2z"/></svg>';
function _miEl(h){ const t=document.createElement('template'); t.innerHTML=h.trim(); return t.content.firstChild; }
function _miSparkPath(vals,W,H,pad){
  const mn=Math.min(...vals), mx=Math.max(...vals);
  const xs=i=>pad+i*(W-2*pad)/(vals.length-1), ys=v=>H-pad-((v-mn)/((mx-mn)||1))*(H-2*pad);
  return { line:vals.map((v,i)=>`${i?'L':'M'}${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).join(' '),
           area:`M${xs(0)} ${H-pad} `+vals.map((v,i)=>`L${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).join(' ')+` L${xs(vals.length-1)} ${H-pad} Z`,
           lastX:xs(vals.length-1), lastY:ys(vals[vals.length-1]) };
}

// Explicit "Load from database" — drops cached insights and re-pulls everything
// the API now persists in MySQL (candidates, profiles, saved jobs) from any
// previous session, then re-renders the dashboard.
// Open the Saved tab WITHOUT touching the database. The DB is only ever pulled
// on the explicit "Load from database" action, so opening the tab is predictable:
// it shows this session's ("Local") candidates until the user asks for more.
function openSavedTab(){
  if (!_savedDbLoaded){
    state.savedView = 'table';
    setSavedSource('local');   // also flips the toggle's active state
  }
  _applySavedView();
}

async function reloadSavedFromDb() {
  _savedDbLoaded = true;
  Object.keys(_miCache).forEach(k => delete _miCache[k]);   // _miCache is const
  const btn    = document.getElementById('savedReloadBtn');
  const status = document.getElementById('savedLoadStatus');
  if (btn)    btn.disabled = true;
  if (status) status.textContent = 'Loading…';
  try {
    await loadSaved();
    setSavedSource('db');       // show what was just pulled from the database
    if (status) {
      const n = _miCandidates.length;
      const j = state.savedJobs.length;
      status.textContent = n
        ? `Loaded ${n} candidate${n!==1?'s':''} · ${j} saved job${j!==1?'s':''}`
        : 'Nothing saved in the database yet';
    }
  } catch (e) {
    if (status) status.textContent = 'Load failed: ' + (e.message || e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadSaved() {
  const empty = document.getElementById('savedEmpty');
  try {
    // Keep the legacy state.savedJobs array + badge in sync (used by Excel export etc.)
    const sres = await fetch('/api/saved');
    const sdata = await sres.json();
    if (sdata.ok) { state.savedJobs = sdata.jobs; app.updateSavedBadge(); }

    const res  = await fetch('/api/saved/candidates');
    const data = await res.json();
    _miCandidates = (data.ok && data.candidates) ? data.candidates : [];
    if (_miIdx >= _miCandidates.length) _miIdx = 0;
    // Before any explicit DB load: if session candidates exist, land on
    // Table · Local so they're visible and one click from being saved.
    if (!_savedDbLoaded && !_miCandidates.length && _localCandidatesForView().length){
      state.savedView = 'table';
      setSavedSource('local');
    }
    _applySavedView();
  } catch(e) {
    document.getElementById('csBar').style.display = 'none';
    document.getElementById('savedDashBody').style.display = 'none';
    document.getElementById('savedTableWrap').style.display = 'none';
    empty.style.display = '';
    empty.innerHTML = `<div class="error-box" style="margin:0">Error: ${esc(e.message)}</div>`;
  }
}

// Switch between the insights dashboard and the candidate table view.
function setSavedView(v){ state.savedView = v; _applySavedView(); }

// Action registry for the SAVED tab static markup — view/kind/source toggles,
// save-all, column chooser, reload, Excel/PDF export, interview-notes panel.
Object.assign(_ACTIONS, {
  'set-saved-view':            (el)    => setSavedView(el.dataset.view),
  'set-saved-kind':            (el)    => setSavedKind(el.dataset.kind),
  'set-saved-source':          (el)    => setSavedSource(el.dataset.source),
  'save-all-local-candidates': ()      => saveAllLocalCandidates(),
  'toggle-col-chooser':        (el, e) => toggleColChooser(e),
  'reload-saved-from-db':      ()      => reloadSavedFromDb(),
  'reload-saved-from-db-link': (el, e) => { e.preventDefault(); reloadSavedFromDb(); },
  'export-saved':              ()      => exportSaved(state.savedJobs),
  'generate-saved-report':     ()      => generateSavedReport(_miCandidates[_miIdx]),
  'ic-toggle':                 ()      => _icToggle(),
  'ic-toggle-body':            ()      => _icToggleBody(),
  'ic-send':                   ()      => _icSend(),
});

// "Save all to database" only applies to a non-empty Local table.
function _updateSaveAllBtn(){
  const b = document.getElementById('svSaveAllBtn');
  if (b) b.style.display =
    (state.savedView==='table' && _savedSource==='local' && _svActiveList().length) ? '' : 'none';
}

// Switch the table's data source between persisted (db) and session (local).
function setSavedSource(src){
  _savedSource = src;
  document.getElementById('svSrcDb').classList.toggle('active', src==='db');
  document.getElementById('svSrcLocal').classList.toggle('active', src==='local');
  _svClosePops();
  _refreshLocalCount();
  _updateSaveAllBtn();
  renderCandTable();
}

// Switch the table between real (CV) candidates and template candidates.
function setSavedKind(kind){
  _savedKind = kind;
  document.getElementById('svKindReal').classList.toggle('active', kind==='real');
  document.getElementById('svKindTpl').classList.toggle('active', kind==='template');
  _svClosePops();
  _refreshLocalCount();
  _updateSaveAllBtn();
  renderCandTable();
}

// Show the panels for the active view, given the current candidate lists.
function _applySavedView(){
  const bar     = document.getElementById('csBar');
  const body    = document.getElementById('savedDashBody');
  const table   = document.getElementById('savedTableWrap');
  const empty   = document.getElementById('savedEmpty');
  const colsBtn  = document.getElementById('svColsBtn');
  const srcTog   = document.getElementById('svSourceToggle');
  const kindTog  = document.getElementById('svKindToggle');
  const saveAll  = document.getElementById('svSaveAllBtn');
  document.getElementById('svTabDash').classList.toggle('active', state.savedView==='dash');
  document.getElementById('svTabTable').classList.toggle('active', state.savedView==='table');
  _refreshLocalCount();

  const hasDb    = _miCandidates.length > 0;
  const hasLocal = _localCandidatesForView().length > 0;

  // ── Dashboard view: always insights over persisted (db) candidates ──────────
  if (state.savedView !== 'table'){
    srcTog.style.display='none'; kindTog.style.display='none'; colsBtn.style.display='none';
    saveAll.style.display='none'; _svClosePops();
    if (!hasDb){
      bar.style.display='none'; body.style.display='none'; table.style.display='none';
      empty.style.display=''; return;
    }
    empty.style.display='none'; table.style.display='none';
    bar.style.display=''; body.style.display='';
    _miBuildSwitcher(); _miGo(_miIdx);
    return;
  }

  // ── Table view: db / local switch ───────────────────────────────────────────
  bar.style.display='none'; body.style.display='none';
  if (!hasDb && !hasLocal){
    table.style.display='none'; colsBtn.style.display='none';
    srcTog.style.display='none'; kindTog.style.display='none'; saveAll.style.display='none';
    _svClosePops();
    empty.style.display=''; return;
  }
  empty.style.display='none'; table.style.display='';
  colsBtn.style.display=''; srcTog.style.display=''; kindTog.style.display='';
  // "Save all to database" only makes sense for the Local source with rows present.
  saveAll.style.display = (_savedSource==='local' && _svActiveList().length) ? '' : 'none';
  renderCandTable();
}

// ── Candidate table: columns, filters, column chooser ───────────────────────
const SV_STATUS_OPTIONS = ['New','Screening','Interviewing','Offer','Hired','Rejected','On hold'];
// type: cand | status | num | email | link | text | date.  def = visible by default.
// edit:true → inline-editable for DB candidates; field = the DB column to PATCH.
const SV_COLUMNS = [
  { key:'name',        label:'Candidate',    type:'cand',   def:true,  always:true },
  { key:'status',      label:'Status',       type:'status', def:true  },
  { key:'title',       label:'Title',        type:'text',   def:true,  edit:true, field:'title' },
  { key:'seniority',   label:'Seniority',    type:'text',   def:true  },
  { key:'location',    label:'Location',     type:'text',   def:true,  edit:true, field:'location' },
  { key:'matches',     label:'Matches',      type:'num',    def:true  },
  { key:'gradeA',      label:'A-grade',      type:'num',    def:true  },
  { key:'email',       label:'Email',        type:'email',  def:true,  edit:true, field:'email' },
  { key:'linkedin',    label:'LinkedIn',     type:'link',   def:true,  edit:true, field:'linkedin' },
  { key:'createdBy',   label:'Created by',   type:'text',   def:true  },
  { key:'lastSaved',   label:'Last saved',   type:'date',   def:true  },
  { key:'phone',       label:'Phone',        type:'text',   def:false, edit:true, field:'phone' },
  { key:'experience',  label:'Experience',   type:'text',   def:false, edit:true, field:'experience_years' },
  { key:'industry',    label:'Industry',     type:'text',   def:false },
  { key:'roleCategory',label:'Role',         type:'text',   def:false },
  { key:'educationLevel',label:'Education',  type:'text',   def:false },
  { key:'languages',   label:'Languages',    type:'text',   def:false, edit:true, field:'languages' },
  { key:'skills',      label:'Skills',       type:'text',   def:false, edit:true, field:'skills' },
  { key:'salary',      label:'Salary exp.',  type:'text',   def:false, edit:true, field:'salary_expectation' },
  { key:'estSalary',   label:'Est. salary',  type:'text',   def:false },
  { key:'availability',label:'Availability', type:'text',   def:false, edit:true, field:'availability' },
  { key:'aiSummary',   label:'AI summary',   type:'text',   def:false },
  { key:'summary',     label:'Summary',      type:'text',   def:false, edit:true, field:'summary' },
  { key:'source',      label:'Source',       type:'text',   def:false },
  { key:'createdAt',   label:'Created',      type:'date',   def:false },
];
let _svVisible = null;   // Set of visible column keys
let _svFilters = {};     // key → filter string (status: exact, else contains)

function _svLoadPrefs(){
  try {
    const cols = JSON.parse(localStorage.getItem('jia_sv_cols') || 'null');
    _svVisible = new Set(Array.isArray(cols) && cols.length
      ? cols : SV_COLUMNS.filter(c=>c.def).map(c=>c.key));
    _svFilters = JSON.parse(localStorage.getItem('jia_sv_filters') || '{}') || {};
  } catch(e){
    _svVisible = new Set(SV_COLUMNS.filter(c=>c.def).map(c=>c.key));
    _svFilters = {};
  }
  _svVisible.add('name');   // candidate column is always on
}
function _svSavePrefs(){
  localStorage.setItem('jia_sv_cols', JSON.stringify([...SV_COLUMNS.map(c=>c.key).filter(k=>_svVisible.has(k))]));
  localStorage.setItem('jia_sv_filters', JSON.stringify(_svFilters));
}
function _svVisibleCols(){ return SV_COLUMNS.filter(c => _svVisible.has(c.key)); }

// Apply the active per-column filters to the candidate list.
function _svFilterRows(){
  const list   = _svActiveList();
  const active = Object.entries(_svFilters).filter(([k,v]) => v !== '' && v != null);
  if (!active.length) return list.map((c,i)=>({c,i}));
  return list.map((c,i)=>({c,i})).filter(({c}) =>
    active.every(([k,v]) => {
      const col = SV_COLUMNS.find(x=>x.key===k);
      const cell = (c[k] ?? '').toString();
      if (col && col.type==='status') return cell === v;
      return cell.toLowerCase().includes(String(v).toLowerCase());
    }));
}

function renderCandTable(){
  if (_svVisible === null) _svLoadPrefs();
  const head = document.getElementById('savedTableHead');
  const tb   = document.getElementById('savedTableBody');
  const cols = _svVisibleCols();

  // The actions column sits right after Status (or after the name column when
  // Status is hidden) instead of being stranded at the far right of the table.
  const statusIdx = cols.findIndex(col => col.key==='status');
  const actIdx = (statusIdx >= 0 ? statusIdx : 0) + 1;

  // Header: each label is a button that opens that column's filter.
  const ths = cols.map(col => {
    const th = document.createElement('th');
    if (col.type==='num') th.className = 'sv-c-center';
    const filtered = _svFilters[col.key] != null && _svFilters[col.key] !== '';
    const btn = _miEl(`<button class="sv-th ${filtered?'filtered':''}" type="button">
        <span>${esc(col.label)}</span><span class="sv-fdot"></span><span class="sv-caret">▼</span></button>`);
    btn.addEventListener('click', (e)=>openColFilter(col.key, e.currentTarget));
    th.appendChild(btn);
    return th;
  });
  ths.splice(actIdx, 0, _miEl('<th class="sv-actions-h">Actions</th>'));
  head.innerHTML = '';
  ths.forEach(th => head.appendChild(th));

  // Body
  const rows = _svFilterRows();
  tb.innerHTML = '';
  document.getElementById('savedTableEmpty').style.display = rows.length ? 'none' : '';
  rows.forEach(({c, i}) => {
    const tr  = document.createElement('tr');
    const tds = cols.map(col => _svCell(col, c, i));
    tds.splice(actIdx, 0, _svActionsCell(c, tr));
    tds.forEach(td => tr.appendChild(td));
    // Arm a DB row's "Save changes" button as soon as any editable cell changes.
    const saveBtn = tr.querySelector('.sv-save-changes');
    if (saveBtn){
      tr.querySelectorAll('.sv-edit').forEach(inp =>
        inp.addEventListener('input', ()=>{ saveBtn.disabled=false; saveBtn.classList.add('dirty'); }));
    }
    tb.appendChild(tr);
  });
  const total = _svActiveList().length;
  const noun  = _savedKind==='template' ? 'template' : 'candidate';
  document.getElementById('savedLoadStatus').textContent =
    `${rows.length} of ${total} ${_savedSource==='local'?'local ':''}${noun}${total!==1?'s':''}`;
}

// Build the actions cell: Open / Save changes / Erase for DB rows; Save to
// database / Remove for local (session) rows.
function _svActionsCell(c, tr){
  const act = document.createElement('td');
  act.className = 'sv-actions';
  if (c._local){
    act.innerHTML = `<button class="sv-link sv-save" type="button">Save to database</button>
                     <button class="sv-link sv-danger" type="button">Remove</button>`;
    const [saveBtn, rmBtn] = act.querySelectorAll('button');
    saveBtn.addEventListener('click', ()=>saveLocalCandidate(c, saveBtn));
    rmBtn.addEventListener('click', ()=>removeLocalCandidate(c));
  } else {
    act.innerHTML = `<button class="sv-link" type="button">Open</button>
                     <button class="sv-link sv-save-changes" type="button" disabled title="Save edited fields, then recalculate insights">Save changes</button>
                     <button class="sv-link sv-danger" type="button">Erase</button>`;
    const [openBtn, saveBtn, eraseBtn] = act.querySelectorAll('button');
    openBtn.addEventListener('click', ()=>loadCandidateFromTable(c));
    saveBtn.addEventListener('click', ()=>saveCandidateEdits(c, tr, saveBtn));
    eraseBtn.addEventListener('click', ()=>eraseCandidateFromTable(c));
  }
  return act;
}

// Build one <td> for a column/candidate.
function _svCell(col, c, i){
  const td = document.createElement('td');
  const v = c[col.key];
  // Inline-editable field for a DB candidate → render an input the recruiter can
  // tweak; the row's "Save changes" button persists it. (Local rows stay static.)
  if (col.edit && !c._local){
    const inp = document.createElement('input');
    inp.className = 'sv-edit';
    inp.value = (v == null) ? '' : v;
    inp.dataset.field = col.field;
    inp.dataset.key   = col.key;
    if (col.key === 'email') inp.type = 'email';
    if (col.key === 'skills') inp.placeholder = 'comma, separated, skills';
    td.appendChild(inp);
    return td;
  }
  switch (col.type){
    case 'cand':
      td.innerHTML = `<div class="sv-cand"><span class="sv-av">${esc(c.initials)}</span>
        <b>${esc(c.name)}</b>${c.hasProfile?'':'<span class="sv-noprof">no CV</span>'}</div>`;
      break;
    case 'status': {
      const sel = document.createElement('select');
      sel.className = 'sv-status-sel sv-st-' + (v||'New').replace(/\s+/g,'-');
      SV_STATUS_OPTIONS.forEach(o=>{
        const op=document.createElement('option'); op.value=o; op.textContent=o;
        if (o===(v||'New')) op.selected=true; sel.appendChild(op);
      });
      if (c._local){
        sel.addEventListener('change', ()=>{
          c._profile.status = sel.value;
          sel.className = 'sv-status-sel sv-st-' + sel.value.replace(/\s+/g,'-');
        });
      } else {
        sel.addEventListener('change', ()=>updateCandidateStatus(c, sel.value, sel));
      }
      td.appendChild(sel);
      break;
    }
    case 'num':
      td.className = 'sv-c-center';
      td.innerHTML = (col.key==='gradeA' && v) ? `<span class="sv-badge-a">${v}</span>` : (v ?? 0);
      break;
    case 'email':
      td.innerHTML = v ? `<a class="sv-cell-link" href="mailto:${esc(v)}">${esc(v)}</a>` : '<span class="sv-muted">—</span>';
      break;
    case 'link':
      td.innerHTML = v ? `<a class="sv-li" href="${esc(v)}" target="_blank" rel="noopener">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="#0a66c2"><path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14zM8.34 17V10.4H6.2V17h2.14zM7.27 9.5a1.24 1.24 0 1 0 0-2.48 1.24 1.24 0 0 0 0 2.48zM18 17v-3.62c0-1.93-1.03-2.83-2.4-2.83-1.11 0-1.6.61-1.88 1.04v-.89H11.6c.03.6 0 6.3 0 6.3h2.13v-3.52c0-.19.01-.38.07-.52.15-.38.5-.77 1.08-.77.76 0 1.07.58 1.07 1.43V17H18z"/></svg>
          Profile</a>` : '<span class="sv-muted">—</span>';
      break;
    case 'date':
      td.textContent = (v||'').slice(0,10) || '—';
      break;
    default:
      td.textContent = (v==null || v==='') ? '—' : v;
      if ((v||'').length > 60){ td.title = v; td.textContent = v.slice(0,57)+'…'; }
  }
  return td;
}

// PATCH a candidate's status; revert the dropdown on failure.
async function updateCandidateStatus(c, status, sel){
  if (!c) return;
  const prev = c.status;
  try {
    const data = await api.patch('/api/saved/candidate/' + encodeURIComponent(c.name), { status });
    c.status = status;
    sel.className = 'sv-status-sel sv-st-' + status.replace(/\s+/g,'-');
  } catch(e){
    alert('Could not update status: ' + (e.message||e));
    sel.value = prev; c.status = prev;
  }
}

// Persist all edited fields of one DB candidate row, then drop the cached
// insights so the dashboard recalculates from the updated profile.
async function saveCandidateEdits(c, tr, btn){
  const inputs = [...tr.querySelectorAll('.sv-edit')];
  const fields = {};
  inputs.forEach(inp => { fields[inp.dataset.field] = inp.value; });
  if (!Object.keys(fields).length) return;
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    const data = await api.patch('/api/saved/candidate/' + encodeURIComponent(c.name), fields);
    // Reflect new values on the row object and invalidate cached insights so the
    // next time this candidate's dashboard opens it recomputes from the edits.
    inputs.forEach(inp => { c[inp.dataset.key] = inp.value; });
    delete _miCache[c.name];
    btn.classList.remove('dirty');
    btn.textContent = '✓ Saved';
    setTimeout(()=>{ btn.textContent = orig; btn.disabled = true; }, 1600);
  } catch(e){
    alert('Could not save changes: ' + (e.message || e));
    btn.disabled = false; btn.textContent = orig;
  }
}

// ── Column chooser ───────────────────────────────────────────────────────────
function toggleColChooser(ev){
  ev.stopPropagation();
  const pop = document.getElementById('svColChooser');
  if (pop.style.display !== 'none'){ pop.style.display='none'; return; }
  if (_svVisible === null) _svLoadPrefs();
  _svClosePops();
  pop.innerHTML = '<h4>Show columns</h4>' + SV_COLUMNS.map(col => `
    <label class="sv-ck">
      <input type="checkbox" data-k="${col.key}" ${_svVisible.has(col.key)?'checked':''} ${col.always?'disabled':''}>
      ${esc(col.label)}
    </label>`).join('');
  pop.querySelectorAll('input[type=checkbox]').forEach(cb=>{
    cb.addEventListener('change', ()=>{
      if (cb.checked) _svVisible.add(cb.dataset.k); else _svVisible.delete(cb.dataset.k);
      _svSavePrefs(); renderCandTable();
    });
  });
  pop.style.display = '';
}

// ── Per-column filter popover ────────────────────────────────────────────────
function openColFilter(key, anchor){
  const pop = document.getElementById('svFilterPop');
  const col = SV_COLUMNS.find(c=>c.key===key);
  if (pop.style.display !== 'none' && pop.dataset.k === key){ pop.style.display='none'; return; }
  _svClosePops();
  pop.dataset.k = key;
  const cur = _svFilters[key] || '';
  let inner = `<div style="font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px">Filter · ${esc(col.label)}</div>`;
  if (col.type === 'status'){
    inner += `<select id="svFilterInput"><option value="">All statuses</option>` +
      SV_STATUS_OPTIONS.map(o=>`<option value="${o}" ${cur===o?'selected':''}>${o}</option>`).join('') + `</select>`;
  } else {
    inner += `<input id="svFilterInput" type="text" placeholder="contains…" value="${esc(cur)}">`;
  }
  inner += `<div class="sv-filter-row">
      <button class="sv-link" type="button" id="svFilterClear">Clear</button>
      <button class="sv-link" type="button" id="svFilterClose">Done</button></div>`;
  pop.innerHTML = inner;

  // position under the clicked header
  const wrap = document.getElementById('savedTableWrap').getBoundingClientRect();
  const a = anchor.getBoundingClientRect();
  pop.style.left = Math.min(a.left - wrap.left, wrap.width - 220) + 'px';
  pop.style.top  = (a.bottom - wrap.top + 6) + 'px';
  pop.style.display = '';

  const input = document.getElementById('svFilterInput');
  input.focus();
  const apply = ()=>{
    const val = input.value;
    if (val === '' ) delete _svFilters[key]; else _svFilters[key] = val;
    _svSavePrefs(); renderCandTable();
  };
  input.addEventListener('input', apply);
  input.addEventListener('change', apply);
  document.getElementById('svFilterClear').addEventListener('click', ()=>{
    delete _svFilters[key]; _svSavePrefs(); pop.style.display='none'; renderCandTable();
  });
  document.getElementById('svFilterClose').addEventListener('click', ()=>{ pop.style.display='none'; });
}

function _svClosePops(){
  const a=document.getElementById('svColChooser'), b=document.getElementById('svFilterPop');
  if (a) a.style.display='none';
  if (b){ b.style.display='none'; b.dataset.k=''; }
}
// Close popovers when clicking outside them.
document.addEventListener('click', (e)=>{
  if (e.target.closest('#svColChooser') || e.target.closest('#svFilterPop') ||
      e.target.closest('#svColsBtn') || e.target.closest('.sv-th')) return;
  _svClosePops();
});

// Open a candidate from the table → switch to the dashboard view for them.
function loadCandidateFromTable(c){
  const idx = _miCandidates.findIndex(x => x.name === c.name);
  if (idx < 0) return;
  _miIdx = idx;
  setSavedView('dash');
}

// GDPR erasure from the table — removes the candidate and all their saved jobs.
async function eraseCandidateFromTable(c){
  if (!c) return;
  if (!confirm(`Erase "${c.name}" and all ${c.matches} saved job(s)?\n\nThis permanently deletes the candidate from the database and cannot be undone.`)) return;
  try {
    const data = await api.del('/api/saved/candidate/' + encodeURIComponent(c.name));
    delete _miCache[c.name];
    await reloadSavedFromDb();
  } catch(e){
    alert('Could not erase: ' + (e.message || e));
  }
}

// Persist a session ("local") candidate to the MySQL candidate table.
async function saveLocalCandidate(row, btn){
  const profile = row._profile;
  const name = profile && (profile.name || '').trim();
  if (!name){ alert('Give the candidate a name before saving.'); return; }
  btn.disabled = true; const orig = btn.textContent; btn.textContent = 'Saving…';
  try {
    const data = await api.post('/api/saved/candidate', { profile });
    // Persisted — drop it from the Local list. Only fold the fresh DB list in if
    // the user is already viewing the database; otherwise leave the Database side
    // untouched until they load it explicitly (keeps the tab predictable).
    _localCandidates = _localCandidates.filter(c => (c.name||'').trim() !== name);
    if (_savedDbLoaded && data.candidates) {
      _miCandidates = data.candidates;
      if (_miIdx >= _miCandidates.length) _miIdx = 0;
    }
    _refreshLocalCount();
    const status = document.getElementById('savedLoadStatus');
    if (_savedSource === 'local' && !_localCandidatesForView().length){
      if (_savedDbLoaded && _miCandidates.length) setSavedSource('db');
      else _applySavedView();   // nothing left locally → empty state
    } else {
      renderCandTable();
    }
    if (status) status.textContent = `Saved “${name}” to the database`;
  } catch(e){
    alert('Could not save candidate: ' + (e.message || e));
    btn.disabled = false; btn.textContent = orig;
  }
}

// Bulk-save every local candidate in the current view to the database.
async function saveAllLocalCandidates(){
  const rows = _svActiveList().filter(c => c._local);
  if (!rows.length) return;
  const noun = _savedKind==='template' ? 'template' : 'candidate';
  if (!confirm(`Save all ${rows.length} local ${noun}${rows.length!==1?'s':''} to the database?`)) return;
  const btn = document.getElementById('svSaveAllBtn');
  const orig = btn ? btn.textContent : '';
  if (btn){ btn.disabled = true; btn.textContent = 'Saving…'; }
  let ok = 0, fail = 0;
  for (const row of rows){
    const profile = row._profile;
    const name = profile && (profile.name || '').trim();
    if (!name){ fail++; continue; }
    try {
      const data = await api.post('/api/saved/candidate', { profile });
      _localCandidates = _localCandidates.filter(c => (c.name||'').trim() !== name);
      if (_savedDbLoaded && data.candidates) _miCandidates = data.candidates;
      ok++;
    } catch(e){ fail++; }
  }
  if (btn){ btn.disabled = false; btn.textContent = orig; }
  if (_miIdx >= _miCandidates.length) _miIdx = 0;
  _refreshLocalCount();
  // Drop back to the Database view when nothing local is left and the DB is loaded.
  if (_savedSource==='local' && !_svActiveList().length && _savedDbLoaded && _miCandidates.length)
    setSavedSource('db');
  else
    _applySavedView();
  const status = document.getElementById('savedLoadStatus');
  if (status) status.textContent = `Saved ${ok} to the database${fail?` · ${fail} failed`:''}`;
}

// Drop a session candidate from the Local view (does not touch the database).
function removeLocalCandidate(row){
  const name = row._profile && (row._profile.name || '').trim();
  if (!name) return;
  if (!confirm(`Remove local candidate "${name}" from this session?\n\nThis only clears it from the Local list — nothing in the database changes.`)) return;
  _localCandidates = _localCandidates.filter(c => (c.name||'').trim() !== name);
  _refreshLocalCount();
  if (!_localCandidatesForView().length && _miCandidates.length) setSavedSource('db');
  else if (!_localCandidatesForView().length) _applySavedView();
  else renderCandTable();
}

function _miBuildSwitcher(){
  const list=document.getElementById('csList');
  list.innerHTML='';
  _miCandidates.forEach((c,i)=>{
    const chip=_miEl(`<button class="cs-chip ${i===_miIdx?'active':''}" data-i="${i}">
      <span class="cs-av">${esc(c.initials)}</span>
      <span class="cs-nm">${esc(c.name)}<small>${c.matches} matches · ${c.gradeA} A-grade</small></span>
    </button>`);
    chip.addEventListener('click',()=>_miGo(i));
    list.appendChild(chip);
  });
  document.getElementById('csCount').textContent=`${_miIdx+1} / ${_miCandidates.length}`;
}

async function _miGo(i){
  if (!_miCandidates.length) return;
  _miIdx=(i+_miCandidates.length)%_miCandidates.length;
  document.querySelectorAll('#csList .cs-chip').forEach(ch=>ch.classList.toggle('active', +ch.dataset.i===_miIdx));
  document.getElementById('csCount').textContent=`${_miIdx+1} / ${_miCandidates.length}`;
  const name=_miCandidates[_miIdx].name;
  _miD=null;
  _miShowLoading(name);
  try {
    let payload=_miCache[name];
    if (!payload) {
      const data = await api.get('/api/saved/insights?candidate='+encodeURIComponent(name));
      payload=data.insights; _miCache[name]=payload;
    }
    _miD=payload;
    _miRender();
    _icOnCandidateSwitch();
  } catch(e){
    document.getElementById('grid1').innerHTML=`<div class="error-box" style="margin:0">Could not build insights: ${esc(e.message)}</div>`;
    document.getElementById('grid2').innerHTML='';
  }
}

function _miShowLoading(name){
  document.getElementById('candHeader').innerHTML=`<div style="padding:6px 2px;color:#9ca3af">Computing insights for ${esc(name)}…</div>`;
  document.getElementById('briefing').innerHTML='';
  document.getElementById('kpiStrip').innerHTML='';
  document.getElementById('grid1').innerHTML='';
  document.getElementById('grid2').innerHTML='';
}

function _miRefreshCurrent(){
  // Drop cache for the active candidate and re-pull (after a save/remove).
  if (_miCandidates[_miIdx]) delete _miCache[_miCandidates[_miIdx].name];
  loadSaved();
}

function _miRender(){
  _miRenderHeader(); _miRenderBriefing(); _miRenderKpis(); _miRenderCards();
}

// ── Interview chat ──────────────────────────────────────────────────────────
let _icHistory = {};   // keyed by candidate name → [{role,content,overrides?}]

function _icToggle(){
  const panel = document.getElementById('icPanel');
  const btn   = document.getElementById('icOpenBtn');
  const isOpen = panel.classList.contains('open');
  if (isOpen) {
    panel.classList.remove('open','body-open');
  } else {
    panel.classList.add('open','body-open');
    _icRenderThread();
    setTimeout(()=>document.getElementById('icInput').focus(), 50);
  }
  btn.setAttribute('title', isOpen ? 'Open interview notes' : 'Close interview notes');
}

function _icToggleBody(){
  const panel = document.getElementById('icPanel');
  panel.classList.toggle('body-open');
  if (panel.classList.contains('body-open'))
    setTimeout(()=>document.getElementById('icInput').focus(), 50);
}

function _icCandKey(){
  return (_miCandidates[_miIdx] || {}).name || '';
}

function _icRenderThread(){
  const key    = _icCandKey();
  const thread = document.getElementById('icThread');
  const empty  = document.getElementById('icEmpty');
  const msgs   = _icHistory[key] || [];
  // remove old messages (keep the empty placeholder node)
  Array.from(thread.children).forEach(n => { if (n !== empty) n.remove(); });
  if (!msgs.length) { empty.style.display=''; return; }
  empty.style.display='none';
  msgs.forEach(m => {
    const el = document.createElement('div');
    el.className = `ic-msg ${m.role==='hr'?'hr':'ai'}`;
    let inner = `<div class="ic-bubble">${esc(m.content)}</div>`;
    if (m.role==='ai' && m.overrides && Object.keys(m.overrides).length) {
      const tags = Object.entries(m.overrides).map(([k,v]) => {
        const label = {salary_expectation:'Salary',location:'Location',skills:'Skills',
          availability:'Available',title:'Role',languages:'Languages',experience_years:'Exp'}[k] || k;
        const val = Array.isArray(v) ? v.join(', ') : String(v);
        return `<span class="ic-tag">${esc(label)}: ${esc(val.length>30?val.slice(0,28)+'…':val)}</span>`;
      }).join('');
      inner += `<div class="ic-tags">${tags}</div>`;
    }
    el.innerHTML = inner;
    thread.appendChild(el);
  });
  thread.scrollTop = thread.scrollHeight;
}

// Clear interview notes when switching candidates
function _icOnCandidateSwitch(){
  const panel = document.getElementById('icPanel');
  // keep panel open if it was open, but re-render for the new candidate
  if (panel.classList.contains('open')) _icRenderThread();
  // update the "has notes" dot on the open button
  const key = _icCandKey();
  const btn = document.getElementById('icOpenBtn');
  if (btn) btn.classList.toggle('has-notes', !!(_icHistory[key]||[]).length);
}

async function _icSend(){
  const cand = _icCandKey();
  if (!cand) return;
  const input = document.getElementById('icInput');
  const msg   = (input.value || '').trim();
  if (!msg) return;

  const send = document.getElementById('icSend');
  input.value = '';
  send.disabled = true;

  // Append HR message immediately
  if (!_icHistory[cand]) _icHistory[cand] = [];
  _icHistory[cand].push({ role:'hr', content: msg });
  _icRenderThread();

  // Show typing indicator
  const thread = document.getElementById('icThread');
  const typing = document.createElement('div');
  typing.className = 'ic-typing'; typing.textContent = 'Updating profile…';
  thread.appendChild(typing); thread.scrollTop = thread.scrollHeight;

  try {
    const data = await api.post('/api/saved/observation', { candidate: cand, message: msg });
    typing.remove();

    _icHistory[cand].push({ role:'ai', content: data.reply, overrides: data.overrides || {} });

    // Patch the live insights data and re-render in place — no full reload
    if (data.insights) {
      _miD = data.insights;
      _miCache[cand] = data.insights;
      _miRender();
    }
  } catch(e) {
    typing.remove();
    _icHistory[cand].push({ role:'ai', content: `Error: ${e.message}`, overrides:{} });
  }

  _icRenderThread();
  // update dot indicator
  const btn = document.getElementById('icOpenBtn');
  if (btn) btn.classList.add('has-notes');
  send.disabled = false;
  input.focus();
}

// Wire Enter key in interview input
document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById('icInput');
  if (inp) inp.addEventListener('keydown', e => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); _icSend(); } });
});

function _miRenderHeader(){
  const D=_miD, h=document.getElementById('candHeader');
  h.innerHTML='';
  h.appendChild(_miEl(`<div class="cand-profile-top">
    <div class="cand-profile-avatar">${esc(D.initials)}</div>
    <div class="cand-profile-body">
      <div class="cand-profile-name">${esc(D.name)}</div>
      <div class="cand-profile-sub">${esc(D.title)} · ${D.years} yrs · ${esc(D.location)} · ${esc(D.langs)}</div>
      <div class="cand-profile-skills">${(D.skills||[]).map(s=>`<span class="cand-profile-skill">${esc(s)}</span>`).join('')}</div>
    </div>
    <div class="cand-meta-inline">
      <div><b>Asks</b> ${esc(D.asks)}</div>
      <div><b>Available</b> ${esc(D.available)}</div>
      <div><b>Prefers</b> ${esc(D.prefers)}</div>
    </div>
  </div>`));
}

function _miRenderBriefing(){
  const D=_miD, b=document.getElementById('briefing');
  b.innerHTML='';
  b.appendChild(_miEl(`<div class="brief-head">
    <span class="brief-icon">${_MI_SPARK}</span>
    <span class="brief-title">Match briefing</span>
    <span class="brief-meta"><span class="dot"></span> Synthesised from the panels below</span>
  </div>`));
  b.appendChild(_miEl(`<div class="brief-text">${(D.briefing||[]).map(p=>`<p>${p}</p>`).join('')}</div>`));
  b.appendChild(_miEl(`<div class="brief-actions">${(D.actions||[]).map((a,i)=>`<div class="brief-action"><span class="num">${i+1}</span><span>${a}</span></div>`).join('')}</div>`));
}

function _miRenderKpis(){
  const D=_miD, strip=document.getElementById('kpiStrip');
  strip.innerHTML='';
  const tot=(D.grades.A+D.grades.B+D.grades.C)||1;
  strip.appendChild(_miEl(`<div class="kpi"><div class="kpi-lbl">Match strength</div>
    <div class="kpi-num">${D.strength}<small>/100</small></div>
    <div class="kpi-mini-bar"><i style="width:${D.grades.A/tot*100}%;background:#1a7a2e"></i><i style="width:${D.grades.B/tot*100}%;background:#e0a92a"></i><i style="width:${D.grades.C/tot*100}%;background:#c9c7bd"></i></div>
    <div class="kpi-sub"><b>${D.grades.A} A</b> · ${D.grades.B} B · ${D.grades.C} C of ${tot}</div></div>`));
  const dir=(D.demandPct>=0?'kpi-up':'kpi-down');
  const sp=_miSparkPath(D.demandSpark&&D.demandSpark.some(v=>v)?D.demandSpark:[0,0,0,0,0,0,0,1],116,30,3);
  strip.appendChild(_miEl(`<div class="kpi"><div class="kpi-lbl">Profile demand</div>
    <div class="kpi-num ${dir}">${D.demandPct>=0?'+':''}${D.demandPct}%</div>
    <svg class="kpi-spark" viewBox="0 0 116 30" width="100%" height="30"><path d="${sp.area}" fill="rgba(26,122,46,.12)"/><path d="${sp.line}" fill="none" stroke="#1a7a2e" stroke-width="1.6"/><circle cx="${sp.lastX}" cy="${sp.lastY}" r="2.4" fill="#1a7a2e"/></svg>
    <div class="kpi-sub">${D.demandNow} new roles/wk · 8-wk trend</div></div>`));
  strip.appendChild(_miEl(`<div class="kpi"><div class="kpi-lbl">Placeability</div>
    <div class="kpi-num">${esc(D.placeText)}</div>
    <div class="kpi-sub" style="margin-top:8px">Similar roles live ~<b>${D.placeabilityDays} days</b></div></div>`));
  strip.appendChild(_miEl(`<div class="kpi"><div class="kpi-lbl">Salary headroom</div>
    <div class="kpi-num">€${(D.salaryCeiling||0).toLocaleString('en-US')}</div>
    <div class="kpi-sub"><b class="kpi-up">+€${(D.salaryHeadroom||0).toLocaleString('en-US')}</b> above ask ceiling</div></div>`));
  const bmSingle = !D.benchmarkTotal || D.benchmarkTotal < 2;
  const bmKpiNum = bmSingle
    ? `<span style="font-size:15px;color:#9ca3af">Only<br>candidate</span>`
    : `${D.benchmarkRank}<small> of ${D.benchmarkTotal}</small>`;
  const bmKpiSub = bmSingle
    ? 'No peers to compare yet'
    : (D.benchmarkRank===1 ? 'Strongest in pipeline' : `Rank ${D.benchmarkRank} of ${D.benchmarkTotal} candidates`);
  strip.appendChild(_miEl(`<div class="kpi"><div class="kpi-lbl">Pipeline rank</div>
    <div class="kpi-num">${bmKpiNum}</div>
    <div class="kpi-sub" style="margin-top:8px">${bmKpiSub}</div></div>`));
}

function _miCard(idx,title,sub,why,span,isNew,ai){
  return _miEl(`<div class="card ${span?'span2':''}">
    <div class="card-head"><span class="card-idx ${isNew?'new':''}">${idx}</span><span class="card-title">${title}</span></div>
    <div class="card-sub">${sub}</div>
    <div class="card-body"></div>
    ${ai?`<div class="ai-read"><span class="spark">${_MI_SPARK}</span><span><b>Read.</b> ${ai}</span></div>`:''}
    <div class="card-why"><b>${isNew?'Stat:':'Why it helps:'}</b> ${why}</div>
  </div>`);
}

function _miFitRadar(){
  const D=_miD;
  const c=_miCard('01','Candidate fit radar','Where the candidate is strong vs. where the match is thin.','A single shape shows the trade-offs at a glance.',false,false,D.radarAI);
  const body=c.querySelector('.card-body');
  const W=300,H=215,cx=W/2,cy=H/2+2,R=76,ax=D.radar,N=ax.length;
  const pt=(i,r)=>{const a=-Math.PI/2+i*2*Math.PI/N;return [cx+Math.cos(a)*r,cy+Math.sin(a)*r];};
  let rings='';[0.25,0.5,0.75,1].forEach(f=>{rings+=`<polygon points="${ax.map((_,i)=>pt(i,R*f).join(',')).join(' ')}" fill="none" stroke="#ece9e0"/>`;});
  let spokes='',labels='';
  ax.forEach((a,i)=>{const[x,y]=pt(i,R);spokes+=`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#ece9e0"/>`;
    const[lx,ly]=pt(i,R+18);const an=Math.abs(lx-cx)<8?'middle':(lx>cx?'start':'end');
    labels+=`<text x="${lx}" y="${ly}" font-size="9.5" fill="#888" text-anchor="${an}" dominant-baseline="middle">${esc(a.axis)}</text>`;});
  const poly=ax.map((a,i)=>pt(i,R*a.v/100).join(',')).join(' ');
  const dots=ax.map((a,i)=>{const[x,y]=pt(i,R*a.v/100);return `<circle cx="${x}" cy="${y}" r="3" fill="#1a3864"/>`;}).join('');
  body.appendChild(_miEl(`<svg viewBox="0 0 ${W} ${H}" width="100%">${rings}${spokes}<polygon points="${poly}" fill="rgba(26,86,196,.16)" stroke="#1a56c4" stroke-width="2"/>${dots}${labels}</svg>`));
  return c;
}
function _miSkillsCoverage(){
  const D=_miD;
  const c=_miCard('02','Skills in demand & gaps','Which skills carry the matches — and what is missing.','Surfaces the most marketable skills and in-demand skills worth coaching toward.',false,false,D.skillsAI);
  const body=c.querySelector('.card-body');
  body.appendChild(_miEl(`<div class="mini-label">Candidate skills · demanded by N of ${D.matches} roles</div>`));
  const bars=_miEl(`<div class="bars"></div>`);
  const mx=Math.max(1,...D.skills2.map(s=>s.n));
  D.skills2.forEach(s=>bars.appendChild(_miEl(`<div class="bar-row"><span class="bar-label">${esc(s.name)}</span><span class="bar-track"><span class="bar-fill" style="width:${s.n/mx*100}%"></span></span><span class="bar-val">${s.n}</span></div>`)));
  body.appendChild(bars);
  if (D.gaps && D.gaps.length){
    body.appendChild(_miEl(`<div class="mini-label" style="margin-top:13px">In-demand skills the candidate is missing</div>`));
    const chips=_miEl(`<div class="gap-chips"></div>`);
    D.gaps.forEach(g=>chips.appendChild(_miEl(`<span class="gap-chip">${esc(g.name)} <b>${g.n}×</b></span>`)));
    body.appendChild(chips);
  }
  return c;
}
function _miSalaryPositioning(){
  const D=_miD;
  const c=_miCard('03','Salary positioning','Is the candidate expectation realistic for these roles?','A “you are here” pay ruler — market range, typical-pay zone, and where the ask falls.',true,false,D.salaryAI);
  const body=c.querySelector('.card-body');
  const m=D.market, b=D.candBand;
  if (!m.median){ body.appendChild(_miEl(`<div class="mini-label">No market salary data for this group.</div>`)); return c; }
  const W=760,H=118,padL=16,padR=16;
  const loV=Math.min(m.p25, b[0])-300, hiV=Math.max(m.p75, b[1])+300;
  const xV=v=>padL+((v-loV)/((hiV-loV)||1))*(W-padL-padR);
  const trackY=58, trackH=22, p25=xV(m.p25), p75=xV(m.p75), med=xV(m.median), bx0=xV(b[0]), bx1=xV(b[1]);
  const candZone=`<rect x="${bx0}" y="34" width="${bx1-bx0}" height="${trackH+30}" rx="6" fill="rgba(26,122,46,.10)"/>
    <line x1="${bx0}" y1="34" x2="${bx0}" y2="${34+trackH+30}" stroke="#1a7a2e" stroke-width="1.5" stroke-dasharray="3 3"/>
    <line x1="${bx1}" y1="34" x2="${bx1}" y2="${34+trackH+30}" stroke="#1a7a2e" stroke-width="1.5" stroke-dasharray="3 3"/>
    <text x="${(bx0+bx1)/2}" y="26" font-size="10.5" font-weight="700" fill="#1a7a2e" text-anchor="middle">${esc(D.name.split(' ')[0])} asks ${esc(D.asks)}</text>`;
  const track=`<rect x="${padL}" y="${trackY}" width="${W-padL-padR}" height="${trackH}" rx="11" fill="#eef1f4" stroke="#e2e6ec"/>
    <rect x="${p25}" y="${trackY}" width="${p75-p25}" height="${trackH}" rx="6" fill="#bcd2ee"/>
    <text x="${(p25+p75)/2}" y="${trackY+15}" font-size="9.5" fill="#3a5a86" text-anchor="middle" font-weight="600">typical pay</text>
    <line x1="${med}" y1="${trackY-7}" x2="${med}" y2="${trackY+trackH+7}" stroke="#1a3864" stroke-width="2.5"/>
    <text x="${med}" y="${trackY+trackH+20}" font-size="9.5" fill="#1a3864" text-anchor="middle" font-weight="600">median €${m.median.toLocaleString('en-US')}</text>`;
  const ticks=`<text x="${xV(loV)}" y="${trackY+trackH+20}" font-size="9" fill="#bbb" text-anchor="start">€${loV.toLocaleString('en-US')}</text>
    <text x="${xV(hiV)}" y="${trackY+trackH+20}" font-size="9" fill="#bbb" text-anchor="end">€${hiV.toLocaleString('en-US')}</text>`;
  body.appendChild(_miEl(`<svg viewBox="0 0 ${W} ${H}" width="100%">${candZone}${track}${ticks}</svg>`));
  body.appendChild(_miEl(`<div class="legend-inline"><span><span class="d" style="background:#bcd2ee"></span>typical market pay (P25–P75)</span><span><span class="d" style="background:rgba(26,122,46,.45)"></span>candidate ask</span><span><span class="d" style="background:#1a3864"></span>market median</span></div>`));
  body.appendChild(_miEl(`<div class="stat-strip"><span><span class="k">Sample</span><span class="v">${D.matches} roles</span></span><span><span class="k">Ask vs market</span><span class="v above">${esc(D.salaryStat.overlap)}</span></span><span><span class="k">Verdict</span><span class="v">${esc(D.salaryStat.verdict)}</span></span></div>`));
  return c;
}
function _miPriorityList(){
  const D=_miD;
  const c=_miCard('04','Priority shortlist','Who to call about first — no chart-reading required.','Sorts matches into plain action tiers; a recruiter just works down the list.',true,false,D.priorityAI);
  const body=c.querySelector('.card-body');
  const deltaTag=(d)=>{ if(d==='in') return `<div class="pri-delta in">in range</div>`; if(d>0) return `<div class="pri-delta up">+€${d} over ask</div>`; return `<div class="pri-delta down">€${Math.abs(d)} under ask</div>`; };
  (D.priority||[]).forEach(t=>{
    const tier=_miEl(`<div class="pri-tier"><div class="pri-tier-head"><span class="pri-dot" style="background:${t.color}"></span>${esc(t.tier)} <span class="cnt">· ${esc(t.note)} · ${t.count} role${t.count>1?'s':''}</span></div></div>`);
    t.roles.forEach(r=>{
      tier.appendChild(_miEl(`<div class="pri-row"><span class="grade grade-${r.g.toLowerCase()}">${esc(r.g)}</span>
        <div class="pri-main"><div class="pri-title">${esc(r.title)} — ${esc(r.co)}</div><div class="pri-sub">${esc(r.loc)} · ${r.match}% match</div></div>
        <div class="pri-pay"><div class="pri-sal">${r.sal?('€'+r.sal.toLocaleString('en-US')):'—'}</div>${deltaTag(r.delta)}</div></div>`));
    });
    if(t.roles.length < t.count) tier.appendChild(_miEl(`<div class="pri-sub" style="text-align:center;padding:5px 0 1px;color:#bbb">+ ${t.count-t.roles.length} more in this tier</div>`));
    body.appendChild(tier);
  });
  return c;
}
function _miDemandTrend(){
  const D=_miD;
  const c=_miCard('05','Demand trend for this profile','Is the market for this candidate heating up or cooling?','Weekly new roles in the candidate occupational group.',true,true,D.demandAI);
  const body=c.querySelector('.card-body');
  const vals=D.demandSpark, avg=D.profileAvg, n=vals.length;
  if (!vals.some(v=>v)){ body.appendChild(_miEl(`<div class="mini-label">No recent posting-date data for this group.</div>`)); return c; }
  const W=720,H=200,padL=34,padR=20,padT=30,padB=30;
  const yMax=Math.max(10,Math.ceil(Math.max(...vals,avg)*1.2/10)*10);
  const slot=(W-padL-padR)/n, cx=i=>padL+slot*i+slot/2, y0=H-padB, yV=v=>padT+(H-padT-padB)*(1-v/yMax);
  let grid='';[Math.round(yMax/3),Math.round(2*yMax/3),yMax].forEach(v=>{const yy=yV(v);grid+=`<line x1="${padL}" y1="${yy}" x2="${W-padR}" y2="${yy}" stroke="#f4f2ec"/><text x="${padL-7}" y="${yy+3}" font-size="9" fill="#cbcabf" text-anchor="end">${v}</text>`;});
  const ay=yV(avg);
  const ref=`<line x1="${padL}" y1="${ay}" x2="${W-padR}" y2="${ay}" stroke="#b9a26a" stroke-width="1.4" stroke-dasharray="5 3"/><text x="${padL+2}" y="${ay-6}" font-size="9.5" fill="#9a8245" font-weight="600">8-wk avg · ~${avg}/wk</text>`;
  let stems='',dots='',labels='';
  vals.forEach((v,i)=>{const recent=i>=n-3,last=i===n-1;
    stems+=`<line x1="${cx(i)}" y1="${y0}" x2="${cx(i)}" y2="${yV(v)}" stroke="${recent?'#bcd0ef':'#e7e5dc'}" stroke-width="7" stroke-linecap="round"/>`;
    dots+=`<circle cx="${cx(i)}" cy="${yV(v)}" r="${last?6.5:5}" fill="${last?'#15407a':(recent?'#1a56c4':'#aeb9c9')}" stroke="#fff" stroke-width="1.5"/>`;
    labels+=`<text x="${cx(i)}" y="${yV(v)-11}" font-size="${last?11:9.5}" font-weight="${recent?700:600}" fill="${recent?'#1a56c4':'#aab'}" text-anchor="middle">${v}</text>`;});
  const wk=vals.slice(0,-1).map((v,i)=>`<text x="${cx(i)}" y="${y0+15}" font-size="8.5" fill="#bbb" text-anchor="middle">w${i+1}</text>`).join('')+`<text x="${cx(n-1)}" y="${y0+15}" font-size="8.5" font-weight="700" fill="#15407a" text-anchor="middle">now</text>`;
  body.appendChild(_miEl(`<svg viewBox="0 0 ${W} ${H}" width="100%"><line x1="${padL}" y1="${y0}" x2="${W-padR}" y2="${y0}" stroke="#e0dfd8"/>${grid}${stems}${ref}${dots}${labels}${wk}</svg>`));
  const vsCls=D.demandVsAvg>=0?'above':'below', vsTxt=(D.demandVsAvg>=0?'+':'')+D.demandVsAvg+'% '+(D.demandVsAvg>=0?'above':'below');
  body.appendChild(_miEl(`<div class="stat-strip"><span><span class="k">8-wk change</span><span class="v ${D.demandPct>=0?'above':'below'}">${D.demandPct>=0?'+':''}${D.demandPct}%</span></span><span><span class="k">Now</span><span class="v">${D.demandNow} roles/wk</span></span><span><span class="k">vs 8-wk avg</span><span class="v ${vsCls}">${vsTxt}</span></span></div>`));
  return c;
}
function _miUpskilling(){
  const D=_miD;
  const c=_miCard('06','Upskilling ROI','What one course unlocks — more matches and higher pay.','Extra group roles and median salary uplift per skill the candidate lacks.',false,true,D.upskillAI);
  const body=c.querySelector('.card-body');
  if (!D.upskill || !D.upskill.length){ body.appendChild(_miEl(`<div class="mini-label">No high-impact skill gaps detected.</div>`)); return c; }
  const maxAdd=Math.max(1,...D.upskill.map(u=>u.add));
  D.upskill.forEach(u=>body.appendChild(_miEl(`<div class="up-row"><div class="up-skill">${esc(u.name)}<small>${esc(u.sub)}</small></div><div class="up-bar-track"><span class="up-bar" style="width:${u.add/maxAdd*100}%"></span></div><div><div class="up-add">+${u.add} roles</div>${u.sal?`<div class="up-sal">+€${u.sal}/mo med.</div>`:''}</div></div>`)));
  return c;
}
function _miTopEmployers(){
  const D=_miD;
  const c=_miCard('07','Top employers to approach','Where the matching roles cluster.','Companies with multiple matching roles — one pitch, several openings.',false,true,D.employersAI);
  const body=c.querySelector('.card-body');
  (D.employers||[]).forEach(e=>body.appendChild(_miEl(`<div class="emp-row"><span class="emp-logo">${esc(e.init)}</span><span class="emp-name">${esc(e.name)}</span><span class="emp-roles">${e.roles} role${e.roles>1?'s':''}</span><span class="emp-sal">${e.sal?('avg €'+e.sal.toLocaleString('en-US')):''}</span></div>`)));
  return c;
}
function _miExpansion(){
  const D=_miD;
  const c=_miCard('08','Pipeline expansion simulator','How to grow a thin shortlist.','Each lever shows how many extra group roles a relaxed filter unlocks.',false,true,D.expansionAI);
  const body=c.querySelector('.card-body');
  if (!D.levers || !D.levers.length){ body.appendChild(_miEl(`<div class="mini-label">No obvious expansion levers from current data.</div>`)); }
  (D.levers||[]).forEach(l=>body.appendChild(_miEl(`<div class="lev-row"><span class="lev-toggle"><i></i></span><span class="lev-name">${esc(l.name)}</span><span class="lev-add">+${l.add}</span></div>`)));
  body.appendChild(_miEl(`<div class="lev-total"><span class="lev-total-num">${esc(D.leverTotal)}</span><span class="lev-total-lbl">potential roles if all levers applied</span></div>`));
  return c;
}
function _miPlaceability(){
  const D=_miD;
  const c=_miCard('09','Placeability & time-on-market','How quickly these roles move.','Derived from how long the saved roles have been live — an outreach deadline.',false,true,D.placeabilityAI);
  const body=c.querySelector('.card-body');
  const fast=D.placeabilityDays && D.placeabilityDays<=20;
  body.appendChild(_miEl(`<div class="pl-head"><span class="pl-big">~${D.placeabilityDays} days</span><span class="pl-pill ${fast?'fast':'norm'}">${fast?'moves fast':'normal pace'}</span></div>`));
  const mx=Math.max(1,...D.placeDist.map(x=>x.n));
  const bars=_miEl(`<div class="bars"></div>`);
  D.placeDist.forEach(x=>bars.appendChild(_miEl(`<div class="bar-row"><span class="bar-label" style="width:54px">${esc(x.d)}</span><span class="bar-track"><span class="bar-fill" style="width:${x.n/mx*100}%;background:#6b7a99"></span></span><span class="bar-val">${x.n}</span></div>`)));
  body.appendChild(bars);
  if (D.placeAroles) body.appendChild(_miEl(`<div class="pl-note"><b>${D.placeAroles} A-role(s)</b> are already 15+ days old — likely to close soon. Prioritise these.</div>`));
  return c;
}
function _miBenchmark(){
  const D=_miD;
  const single = !D.benchmarkTotal || D.benchmarkTotal < 2;
  const sub = single ? 'Add more candidates to enable comparison.' : `How this candidate compares to the rest.`;
  const why = single ? 'Will rank candidates once you have 2 or more in the pipeline.' : 'Ranks match strength against the other saved candidates.';
  const c=_miCard('10','Pipeline benchmark', sub, why, false, true, D.benchmarkAI);
  const body=c.querySelector('.card-body');
  if (single) {
    body.appendChild(_miEl(`<div class="mini-label" style="color:#9ca3af;font-style:italic">Only candidate in the pipeline — no peers to rank against yet.</div>`));
  } else {
    // marker position: rank 1 = rightmost, rank N = leftmost
    const pos = Math.round((1 - (D.benchmarkRank - 1) / (D.benchmarkTotal - 1)) * 100);
    const first = esc(D.name.split(' ')[0]);
    const label = `${first} · ${D.benchmarkRank} of ${D.benchmarkTotal}`;
    body.appendChild(_miEl(`<div class="bm-wrap">
      <div class="bm-track">
        <div class="bm-marker" style="left:${pos}%"></div>
        <div class="bm-flag"   style="left:${pos}%">${label}</div>
      </div>
      <div class="bm-scale"><span>weakest</span><span>median</span><span>strongest</span></div>
      <div class="bm-note">${first} is <b>ranked ${D.benchmarkRank} of ${D.benchmarkTotal}</b> saved candidates by match strength.</div>
    </div>`));
  }
  return c;
}
function _miFreshness(){
  const D=_miD, f=D.fresh;
  const c=_miCard('11','Outreach urgency','Which matches need action now.','Turns posting age &amp; deadlines into a to-do list.',false,true,D.freshAI);
  const body=c.querySelector('.card-body');
  body.appendChild(_miEl(`<div class="fresh-row">
    <div class="fresh-tile alert"><div class="fresh-num">${f.closing}</div><div class="fresh-lbl">closing<br>≤ 7 days</div></div>
    <div class="fresh-tile good"><div class="fresh-num">${f.fresh}</div><div class="fresh-lbl">fresh<br>posted &lt; 7d</div></div>
    <div class="fresh-tile"><div class="fresh-num">${f.stale}</div><div class="fresh-lbl">aging<br>30–60 days</div></div>
    <div class="fresh-tile"><div class="fresh-num">${f.expired}</div><div class="fresh-lbl">deadline<br>passed</div></div>
  </div>`));
  return c;
}
function _miRenderCards(){
  if (!_miD) return;
  const g1=document.getElementById('grid1'); g1.innerHTML='';
  [_miFitRadar(),_miSkillsCoverage(),_miSalaryPositioning(),_miPriorityList()].forEach(c=>g1.appendChild(c));
  const g2=document.getElementById('grid2'); g2.innerHTML='';
  [_miDemandTrend(),_miUpskilling(),_miTopEmployers(),_miExpansion(),_miPlaceability(),_miBenchmark(),_miFreshness()].forEach(c=>g2.appendChild(c));
}

// Switcher arrows + keyboard
document.addEventListener('DOMContentLoaded',()=>{
  const p=document.getElementById('csPrev'), n=document.getElementById('csNext');
  if (p) p.addEventListener('click',()=>_miGo(_miIdx-1));
  if (n) n.addEventListener('click',()=>_miGo(_miIdx+1));
});
document.addEventListener('keydown',e=>{
  if (!document.getElementById('tab-saved').classList.contains('active')) return;
  if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (e.key==='ArrowLeft') _miGo(_miIdx-1);
  if (e.key==='ArrowRight') _miGo(_miIdx+1);
});

function toggleExtraTab(jobId, key) {
  const pane = document.getElementById(`extras-pane-${key}-${jobId}`);
  const btn  = document.getElementById(`etab-${key}-${jobId}`);
  if (!pane) return;
  const opening = !pane.classList.contains('etab-open');
  // Close all panes for this job first
  document.querySelectorAll(`[id^="extras-pane-"][id$="-${jobId}"]`).forEach(el => {
    el.classList.remove('etab-open');
  });
  document.querySelectorAll(`[id^="etab-"][id$="-${jobId}"]`).forEach(el => {
    el.classList.remove('etab-active');
  });
  if (opening) {
    pane.classList.add('etab-open');
    btn.classList.add('etab-active');
    // Render Plotly radar chart for strength tab
    if (key === 'strength') {
      const chartEl = document.getElementById('extras-chart-' + jobId);
      if (chartEl && chartEl.dataset.axes) {
        try {
          const axes   = JSON.parse(chartEl.dataset.axes);
          const scores = JSON.parse(chartEl.dataset.scores);
          setTimeout(() => Plotly.newPlot(chartEl, [{
            type: 'scatterpolar',
            r: [...scores, scores[0]], theta: [...axes, axes[0]],
            fill: 'toself', fillcolor: 'rgba(26,56,100,0.10)',
            line: { color: '#1a3864', width: 2 },
            hovertemplate: '<b>%{theta}</b><br>%{r}/10<extra></extra>',
          }], {
            polar: {
              radialaxis: { visible: true, range: [0,10], tickvals:[2,4,6,8,10],
                tickfont:{size:8,color:'#bbb'}, gridcolor:'#e8e7e0', linecolor:'#e8e7e0' },
              angularaxis: { tickfont:{size:9,color:'#555'} }, bgcolor:'rgba(0,0,0,0)',
            },
            showlegend:false, margin:{t:20,r:40,b:20,l:40}, paper_bgcolor:'rgba(0,0,0,0)',
          }, { responsive:true, displayModeBar:false }), 60);
        } catch(e) {}
      }
    }
  }
}


// Cross-module exports — registered on app so candidate/clustering/search/
// modal/interview can call into this module without a direct import.
Object.assign(app, {
  openSavedTab, _trackLocalCandidate, setSavedSource, _applySavedView,
  loadSaved, _miRefreshCurrent,
});
