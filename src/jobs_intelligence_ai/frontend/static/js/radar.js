// ════════════════════════════════════════════════════════════
//  Radar / Analytics tab — opportunity radar, AI filter assistant,
//  quick finder, per-tab chats, analytics summary builder.
//  Extracted from index.html in 2.6c. Only loadRadar is called from the
//  page module (tab routing); everything else is internal or wired via
//  its own _ACTIONS registrations.
// ════════════════════════════════════════════════════════════
import api from "./api.js";
import { state, _ACTIONS } from "./state.js";
import { esc, mdToHtml } from "./util.js";

// ════════════════════════════════════════════════════════════
//  RADAR TAB
// ════════════════════════════════════════════════════════════

let _radarData        = null;   // cached API response
let _radarLoaded      = false;
let _radarFilterTimer = null;   // debounce handle
let _oppRecs          = [];     // current recommendation texts
let _oppChatHistory   = [];     // multi-turn chat history
let _oppChatBusy      = false;
let _summaryItems     = [];     // saved analytics summary items
let _summaryCounter   = 0;
let _chatAnswers      = [];     // indexed store for chat AI answers (for save button)
let _summaryCardData  = {};     // keyed card data for Add-to-Summary buttons
let _oppsData         = [];     // top opportunities
let _underData        = [];     // underserved segments
let _urgencyData      = [];     // urgency alerts
// Per-tab chat state (shared by triggerTabChat / sendTabChat)
const _tabChats = {
  opps:    { history: [], busy: false, panelId: 'oppsChatPanel',   threadId: 'oppsChatThread',   inputId: 'oppsChatInput',   sendId: 'oppsChatSend'   },
  under:   { history: [], busy: false, panelId: 'underChatPanel',  threadId: 'underChatThread',  inputId: 'underChatInput',  sendId: 'underChatSend'  },
  urgency: { history: [], busy: false, panelId: 'urgencyChatPanel',threadId: 'urgencyChatThread',inputId: 'urgencyChatInput',sendId: 'urgencyChatSend' },
  trend:   { history: [], busy: false, panelId: 'trendChatPanel',  threadId: 'trendChatThread',  inputId: 'trendChatInput',  sendId: 'trendChatSend'  },
};

// AI filter state
let _aiSuggestion    = null;    // pending suggestion (shown in panel, editable)
let _aiFiltersApplied = null;   // what was last applied (for active bar)

// ════════════════════════════════════════════════════════════
//  AI Filter Assistant
// ════════════════════════════════════════════════════════════

// Action registry for the Radar / Analytics static markup (AI filter panel,
// sub-nav, trend tab-chat, quick-finder selects, report + summary chat).
Object.assign(_ACTIONS, {
  'ai-filter-toggle':   ()      => toggleAIFilter(),
  'ai-filter-enter':    (el, e) => { if (e.key === 'Enter') runAIFilterSuggest(); },
  'ai-filter-suggest':  ()      => runAIFilterSuggest(),
  'ai-filter-apply':    ()      => applyAIFilters(),
  'ai-filter-clear':    ()      => clearAIFilters(),
  'radar-sub':          (el)    => radarSub(el, el.dataset.rsub),
  'tab-chat':           (el)    => triggerTabChat(el.dataset.tab, +el.dataset.idx, el.dataset.act),
  'finder-reload':      ()      => loadFinderJobs(),
  'generate-report':    (el)    => generateReport(el.dataset.charts === '1'),
  'summary-chat-quick': (el)    => triggerSummaryChat(el.dataset.msg),
  'summary-chat-send':  ()      => sendSummaryChat(),
  'summary-chat-enter': (el, e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendSummaryChat(); } },
  // radar header + scope filter bar
  'generate-briefing':  ()      => generateBriefing(),
  'radar-refresh':      ()      => loadRadar(true),
  'radar-filter-change': ()     => onRadarFilterChange(),
  'clear-radar-filters': ()     => clearRadarFilters(),
});

function toggleAIFilter() {
  const panel = document.getElementById('raifpPanel');
  const btn   = document.getElementById('raifpToggleBtn');
  const open  = panel.style.display === 'none';
  panel.style.display = open ? '' : 'none';
  btn.classList.toggle('open', open);
  if (open) document.getElementById('raifpQuery').focus();
}

async function runAIFilterSuggest() {
  const query = (document.getElementById('raifpQuery').value || '').trim();
  if (!query) return;

  const btn     = document.getElementById('raifpSuggestBtn');
  const spinner = document.getElementById('raifpSpinner');
  const label   = document.getElementById('raifpSuggestLabel');

  btn.disabled = true;
  spinner.classList.remove('hidden');
  label.textContent = 'Thinking…';
  document.getElementById('raifpResult').style.display = 'none';

  try {
    const data = await api.post('/api/opportunity/filter-assist', {
      query,
      sectors: state.filterOpts.occ_groups || [],
      states:  state.filterOpts.states     || [],
      portals: state.filterOpts.portals    || [],
    });
    _aiSuggestion = data;
    _renderAISuggestion(data);
  } catch(e) {
    _aiSuggestion = null;
    document.getElementById('raifpExplanation').textContent = 'Error: ' + e.message;
    document.getElementById('raifpCountHint').innerHTML = '';
    document.getElementById('raifpCategories').innerHTML = '';
    document.getElementById('raifpResult').style.display = '';
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
    label.textContent = 'Suggest filters';
  }
}

function _renderAISuggestion(s) {
  // Explanation
  document.getElementById('raifpExplanation').textContent = s.explanation || '';

  // Count hint
  const hintEl = document.getElementById('raifpCountHint');
  hintEl.innerHTML = s.count_hint
    ? `<span class="raifp-count-hint">${esc(s.count_hint)}</span>` : '';

  // Chips per category
  let html = '';
  const groups = (s.occ_groups || []).filter(Boolean);
  if (groups.length) {
    html += `<div><div class="raifp-cat-label">Sectors (${groups.length} selected)</div>
      <div class="raifp-chips" id="raifpChipsSectors">`;
    groups.forEach((g, i) => {
      html += `<span class="raifp-chip">
        ${esc(g)}
        <span class="raifp-chip-x" data-action="remove-ai-chip" data-field="occ_groups" data-i="${i}" title="Remove">×</span>
      </span>`;
    });
    html += '</div></div>';
  }

  const selStates = (s.states || []).filter(Boolean);
  if (selStates.length) {
    html += `<div><div class="raifp-cat-label">States</div>
      <div class="raifp-chips">`;
    selStates.forEach((st, i) => {
      html += `<span class="raifp-chip state-chip">
        ${esc(st)}
        <span class="raifp-chip-x" data-action="remove-ai-chip" data-field="states" data-i="${i}" title="Remove">×</span>
      </span>`;
    });
    html += '</div></div>';
  }

  if (s.min_salary) {
    html += `<div><div class="raifp-cat-label">Min salary</div>
      <div class="raifp-chips">
        <span class="raifp-chip salary-chip">€${Number(s.min_salary).toLocaleString('de-AT')}+
          <span class="raifp-chip-x" data-action="remove-ai-salary" title="Remove">×</span>
        </span>
      </div></div>`;
  }

  if (!groups.length && !selStates.length && !s.min_salary) {
    html = '<div style="font-size:12px;color:#aaa;padding:4px 0">No specific filters identified — try rephrasing your query.</div>';
  }

  document.getElementById('raifpCategories').innerHTML = html;
  document.getElementById('raifpResult').style.display = '';
}

function _removeAIChip(type, idx) {
  if (!_aiSuggestion) return;
  _aiSuggestion[type] = (_aiSuggestion[type] || []).filter((_, i) => i !== idx);
  _renderAISuggestion(_aiSuggestion);
}

function _removeAISalary() {
  if (_aiSuggestion) { _aiSuggestion.min_salary = null; _renderAISuggestion(_aiSuggestion); }
}

async function applyAIFilters() {
  if (!_aiSuggestion) return;
  _aiFiltersApplied = JSON.parse(JSON.stringify(_aiSuggestion));  // deep copy

  // Close panel
  document.getElementById('raifpPanel').style.display = 'none';
  document.getElementById('raifpToggleBtn').classList.remove('open');

  // Show active bar
  _renderActiveAIBar();

  // Force reload + generate briefing with AI filters
  _radarLoaded = false;
  await generateBriefing();
}

function _renderActiveAIBar() {
  const bar = document.getElementById('raifpActiveBar');
  if (!_aiFiltersApplied) { bar.style.display = 'none'; return; }

  const groups = (_aiFiltersApplied.occ_groups || []).filter(Boolean);
  const states = (_aiFiltersApplied.states     || []).filter(Boolean);

  if (!groups.length && !states.length && !_aiFiltersApplied.min_salary) {
    bar.style.display = 'none'; return;
  }

  let html = '<span class="raifp-active-label">AI scope:</span>';
  groups.slice(0, 5).forEach((g, i) => {
    html += `<span class="raifp-active-chip">${esc(g)}
      <span class="raifp-active-chip-x" data-action="remove-applied-chip" data-field="occ_groups" data-i="${i}">×</span>
    </span>`;
  });
  if (groups.length > 5) html += `<span class="raifp-active-chip">+${groups.length - 5} more</span>`;
  states.forEach((s, i) => {
    html += `<span class="raifp-active-chip state-chip">${esc(s)}
      <span class="raifp-active-chip-x" data-action="remove-applied-chip" data-field="states" data-i="${i}">×</span>
    </span>`;
  });
  if (_aiFiltersApplied.min_salary) {
    html += `<span class="raifp-active-chip salary-chip">€${Number(_aiFiltersApplied.min_salary).toLocaleString('de-AT')}+</span>`;
  }
  html += '<button class="raifp-clear-btn" style="padding:2px 10px;font-size:11px;margin-left:4px" data-action="ai-filter-clear">Clear AI filters</button>';

  bar.innerHTML = html;
  bar.style.display = '';
}

function _removeAppliedChip(type, idx) {
  if (!_aiFiltersApplied) return;
  _aiFiltersApplied[type] = (_aiFiltersApplied[type] || []).filter((_, i) => i !== idx);
  _renderActiveAIBar();
  _radarLoaded = false;
  generateBriefing();
}

function clearAIFilters() {
  _aiSuggestion    = null;
  _aiFiltersApplied = null;
  document.getElementById('raifpResult').style.display = 'none';
  document.getElementById('raifpQuery').value = '';
  document.getElementById('raifpActiveBar').style.display = 'none';
  _radarLoaded = false;
  loadRadar(true);
}

// ── Filter helpers ──────────────────────────────────────────

function _radarFilterParams() {
  const params = new URLSearchParams();

  // Manual single-select filters
  const sector    = document.getElementById('rfSector')?.value    || '';
  const stateF    = document.getElementById('rfStateF')?.value    || '';
  const portalF   = document.getElementById('rfPortalF')?.value   || '';
  const minSalary = document.getElementById('rfMinSalary')?.value || '';
  if (sector)    params.set('occ_group',  sector);
  if (stateF)    params.set('state',      stateF);
  if (portalF)   params.set('portal',     portalF);
  if (minSalary) params.set('min_salary', minSalary);

  // AI multi-select filters (override manual when applied)
  if (_aiFiltersApplied) {
    (_aiFiltersApplied.occ_groups || []).forEach(g => params.append('occ_groups', g));
    (_aiFiltersApplied.states     || []).forEach(s => params.append('states',     s));
    (_aiFiltersApplied.portals    || []).forEach(p => params.append('portals',    p));
    if (_aiFiltersApplied.min_salary) params.set('min_salary', _aiFiltersApplied.min_salary);
  }

  return params;
}

function _activeFilterCount() {
  return ['rfSector','rfStateF','rfPortalF','rfMinSalary']
    .filter(id => (document.getElementById(id)?.value || '') !== '').length;
}

function onRadarFilterChange() {
  const n = _activeFilterCount();
  const clearBtn = document.getElementById('radarFilterClear');
  const badge    = document.getElementById('radarFilterBadge');
  clearBtn.classList.toggle('hidden', n === 0);
  badge.classList.toggle('hidden', n === 0);
  if (n > 0) badge.textContent = n + ' filter' + (n > 1 ? 's' : '') + ' active';

  // Highlight active selects
  ['rfSector','rfStateF','rfPortalF','rfMinSalary'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active-filter', !!el.value);
  });

  // Auto-refresh stats after 400 ms debounce (no AI call)
  _radarLoaded = false;
  clearTimeout(_radarFilterTimer);
  _radarFilterTimer = setTimeout(() => loadRadar(true), 400);
}

function clearRadarFilters() {
  ['rfSector','rfStateF','rfPortalF','rfMinSalary'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.value = ''; el.classList.remove('active-filter'); }
  });
  document.getElementById('radarFilterClear').classList.add('hidden');
  document.getElementById('radarFilterBadge').classList.add('hidden');
  _radarLoaded = false;
  loadRadar(true);
}


// Sub-nav switching
function radarSub(btn, sub) {
  document.querySelectorAll('.radar-sub-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.radar-subview').forEach(v => v.style.display = 'none');
  btn.classList.add('active');
  document.getElementById('rsub-' + sub).style.display = '';
  if (sub === 'trend'     && _radarData) { renderTrendChart(_radarData.trend || []); renderMomentumChart(_radarData.trend || []); }
  if (sub === 'analytics' && _radarData) renderAnalytics(_radarData);
  if (sub === 'finder')                  loadFinderJobs();
}

// Load stats snapshot (no AI briefing) — fast, called on first tab open / refresh
export async function loadRadar(force = false) {
  if (_radarLoaded && !force) return;
  document.getElementById('rc-total').textContent = '…';

  try {
    const params = _radarFilterParams();
    params.set('briefing', '0');
    const data = await api.get('/api/opportunity?' + params.toString());
    _radarData   = data;
    _radarLoaded = true;

    const ts = new Date().toLocaleTimeString('de-AT', {hour:'2-digit',minute:'2-digit'});
    document.getElementById('radarLastUpdate').textContent = 'Updated ' + ts;

    renderSummaryCards(data.totals);
    populateFinderFilters(data.sectors, data.states, data.portals);

    // Refresh active sub if it depends on data
    const activeSub = document.querySelector('.radar-sub-btn.active')?.dataset?.rsub;
    if (activeSub === 'trend')     { renderTrendChart(data.trend || []); renderMomentumChart(data.trend || []); }
    if (activeSub === 'analytics') renderAnalytics(data);
    if (activeSub === 'finder')    loadFinderJobs();
  } catch(e) {
    document.getElementById('radarOverviewContent').innerHTML =
      `<div class="radar-loading" style="color:#ef4444">Failed to load: ${e.message}</div>`;
  }
}

// AI briefing call — triggered by the button, separate from stats fetch
async function generateBriefing() {
  const btn     = document.getElementById('radarBriefingBtn');
  const spinner = document.getElementById('radarSpinner');
  const label   = document.getElementById('radarBriefingBtnLabel');

  btn.disabled = true;
  spinner.classList.remove('hidden');
  label.textContent = 'Generating…';

  // Show loading state in all AI tabs
  const loadingHtml = '<div class="radar-loading"><span style="display:inline-flex;align-items:center;gap:9px">'
    + '<span style="display:inline-block;width:15px;height:15px;border:2px solid #c4d4f0;border-top-color:#1a3864;border-radius:50%;animation:radar-spin .7s linear infinite"></span>'
    + 'AI is analysing market data…</span></div>';
  document.getElementById('radarOverviewContent').innerHTML  = loadingHtml;
  document.getElementById('radarOppsContent').innerHTML      = loadingHtml;
  document.getElementById('radarUnderContent').innerHTML     = loadingHtml;
  document.getElementById('radarUrgencyContent').innerHTML   = loadingHtml;

  try {
    const params = _radarFilterParams();
    params.set('briefing', '1');
    const data = await api.get('/api/opportunity?' + params.toString());

    _radarData   = data;
    _radarLoaded = true;
    renderSummaryCards(data.totals);
    populateFinderFilters(data.sectors, data.states, data.portals);

    const ts = new Date().toLocaleTimeString('de-AT', {hour:'2-digit',minute:'2-digit'});
    document.getElementById('radarLastUpdate').textContent = 'Updated ' + ts;

    renderBriefing(data.briefing);

    // Also refresh trend charts in case trend tab is active
    renderTrendChart(data.trend || []);
    renderMomentumChart(data.trend || []);
  } catch(e) {
    const errHtml = `<div class="radar-loading" style="color:#ef4444">Briefing failed: ${e.message}</div>`;
    document.getElementById('radarOverviewContent').innerHTML = errHtml;
    document.getElementById('radarOppsContent').innerHTML    = errHtml;
    document.getElementById('radarUnderContent').innerHTML   = errHtml;
    document.getElementById('radarUrgencyContent').innerHTML = errHtml;
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
    label.textContent = '✦ Generate Briefing';
  }
}

function renderSummaryCards(t) {
  const fmt = n => (n == null ? '—' : Number(n).toLocaleString('de-AT'));
  document.getElementById('rc-total').textContent   = fmt(t.total_active);
  document.getElementById('rc-stale30').textContent = fmt(t.stale_30);
  document.getElementById('rc-stale60').textContent = fmt(t.stale_60);
  document.getElementById('rc-urgent').textContent  = fmt(t.urgent_14d);
  document.getElementById('rc-sectors').textContent = fmt(t.sector_count);
  document.getElementById('rc-states').textContent  = fmt(t.state_count);
}

function renderBriefing(b) {
  if (!b || !b.headline) {
    const msg = '<div class="radar-loading" style="color:#aaa">No briefing data available.</div>';
    document.getElementById('radarOverviewContent').innerHTML  = msg;
    document.getElementById('radarOppsContent').innerHTML      = msg;
    document.getElementById('radarUnderContent').innerHTML     = msg;
    document.getElementById('radarUrgencyContent').innerHTML   = msg;
    return;
  }

  // ── Overview: headline + recommendations ──────────────────
  let ovHtml = `<div class="radar-headline">${esc(b.headline)}</div>`;
  if (b.recommendations && b.recommendations.length) {
    _oppRecs = b.recommendations;
    ovHtml += `<div class="radar-section-title">Recommended Focus</div>
      <ul class="radar-rec-list">`;
    _summaryCardData = {};
    b.recommendations.forEach((r, i) => {
      _summaryCardData['rec_' + i] = {type: 'recommendation', label: 'Recommendation ' + (i+1), content: r};
      ovHtml += `<li class="radar-rec-item">
        <div class="radar-rec-item-top">
          <span class="radar-rec-num">${i+1}</span>
          <span>${esc(r)}</span>
        </div>
        <div class="radar-rec-actions">
          <button class="radar-rec-action-btn" data-action="trigger-opp-chat" data-i="${i}" data-act="details">Provide Details</button>
          <button class="radar-rec-action-btn" data-action="trigger-opp-chat" data-i="${i}" data-act="trend">Explain the Trend</button>
          <button class="radar-rec-action-btn" data-action="trigger-opp-chat" data-i="${i}" data-act="data">Show Data</button>
          <button class="add-summary-btn" data-action="add-to-summary-card" data-card="rec_${i}">+ Add to Summary</button>
        </div>
      </li>`;
    });
    ovHtml += '</ul>';
  }
  document.getElementById('radarOverviewContent').innerHTML = ovHtml;
  const _cp = document.getElementById('oppChatPanel');
  if (_cp) _cp.style.display = '';

  // ── Top Opportunities ─────────────────────────────────────
  let opHtml = '';
  if (b.top_opportunities && b.top_opportunities.length) {
    _oppsData = b.top_opportunities;
    opHtml += `<div class="radar-section-title">${b.top_opportunities.length} opportunities identified</div>
      <div class="radar-opp-list">`;
    b.top_opportunities.forEach((o, i) => {
      _summaryCardData['opp_' + i] = {type: 'opportunity', label: o.label, content: o.label + ': ' + o.reason};
      const sig = o.signal === 'strong' ? 'strong' : 'moderate';
      opHtml += `<div class="radar-opp-card ${sig}">
        <div class="radar-opp-card-header">
          <div class="radar-opp-card-label">${esc(o.label)}</div>
          <span class="radar-signal ${sig}">${sig}</span>
        </div>
        <div class="radar-opp-card-reason">${esc(o.reason)}</div>
        <div class="radar-rec-actions" style="margin-top:10px;padding-left:0">
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="opps" data-idx="${i}" data-act="strategy">Sourcing Strategy</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="opps" data-idx="${i}" data-act="salary">Salary Benchmark</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="opps" data-idx="${i}" data-act="signal">Why ${sig}?</button>
          <button class="add-summary-btn" data-action="add-to-summary-card" data-card="opp_${i}">+ Add to Summary</button>
        </div>
      </div>`;
    });
    opHtml += '</div>';
  } else {
    opHtml = '<div class="radar-loading" style="color:#bbb">No top opportunities identified.</div>';
  }
  document.getElementById('radarOppsContent').innerHTML = opHtml;
  const _opCp = document.getElementById('oppsChatPanel');
  if (_opCp && b.top_opportunities && b.top_opportunities.length) _opCp.style.display = '';

  // ── Underserved ───────────────────────────────────────────
  let unHtml = '';
  if (b.underserved && b.underserved.length) {
    _underData = b.underserved;
    unHtml += `<div class="radar-section-title">${b.underserved.length} underserved segments</div>
      <div class="radar-under-list">`;
    b.underserved.forEach((u, i) => {
      _summaryCardData['under_' + i] = {type: 'underserved', label: u.label, content: u.label + ': ' + u.reason};
      unHtml += `<div class="radar-under-card">
        <div class="radar-under-card-header">
          <div class="radar-under-card-label">${esc(u.label)}</div>
        </div>
        <div class="radar-under-card-reason">${esc(u.reason)}</div>
        <div class="radar-rec-actions" style="margin-top:10px;padding-left:0">
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="under" data-idx="${i}" data-act="why">Why Hard to Fill?</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="under" data-idx="${i}" data-act="improve">Improve Inflow</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="under" data-idx="${i}" data-act="compare">Compare to Market</button>
          <button class="add-summary-btn" data-action="add-to-summary-card" data-card="under_${i}">+ Add to Summary</button>
        </div>
      </div>`;
    });
    unHtml += '</div>';
  } else {
    unHtml = '<div class="radar-loading" style="color:#bbb">No underserved markets identified.</div>';
  }
  document.getElementById('radarUnderContent').innerHTML = unHtml;
  const _unCp = document.getElementById('underChatPanel');
  if (_unCp && b.underserved && b.underserved.length) _unCp.style.display = '';

  // ── Urgency Alerts ────────────────────────────────────────
  let urHtml = '';
  if (b.urgency_alerts && b.urgency_alerts.length) {
    _urgencyData = b.urgency_alerts;
    urHtml += `<div class="radar-section-title">${b.urgency_alerts.length} sectors with urgent deadlines</div>
      <div class="radar-urgency-list">`;
    b.urgency_alerts.forEach((u, i) => {
      _summaryCardData['urgency_' + i] = {type: 'urgency', label: u.label, content: u.count + ' urgent roles in ' + u.label + '. ' + (u.note || 'Deadlines within 14 days')};
      urHtml += `<div class="radar-urgency-card" style="flex-direction:column;align-items:stretch;gap:10px">
        <div style="display:flex;align-items:center;gap:14px">
          <div class="radar-urgency-badge">${u.count}</div>
          <div class="radar-urgency-details">
            <div class="radar-urgency-label">${esc(u.label)}</div>
            <div class="radar-urgency-note">${esc(u.note || 'Deadlines within 14 days')}</div>
          </div>
        </div>
        <div class="radar-rec-actions" style="padding-left:0">
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="urgency" data-idx="${i}" data-act="plan">Fast-track Plan</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="urgency" data-idx="${i}" data-act="priority">Who to Prioritize</button>
          <button class="radar-rec-action-btn" data-action="tab-chat" data-tab="urgency" data-idx="${i}" data-act="risk">Risk of Inaction</button>
          <button class="add-summary-btn" data-action="add-to-summary-card" data-card="urgency_${i}">+ Add to Summary</button>
        </div>
      </div>`;
    });
    urHtml += '</div>';
  } else {
    urHtml = '<div class="radar-loading" style="color:#bbb">No urgent deadline alerts.</div>';
  }
  document.getElementById('radarUrgencyContent').innerHTML = urHtml;
  const _urCp = document.getElementById('urgencyChatPanel');
  if (_urCp && b.urgency_alerts && b.urgency_alerts.length) _urCp.style.display = '';

  // ── Volume Trend AI text (chart rendered separately) ──────
  if (b.trend_summary) {
    _summaryCardData['trend_0'] = {type: 'trend', label: 'Volume Trend Insight', content: b.trend_summary};
    document.getElementById('radarTrendAI').innerHTML =
      `<p class="radar-trend-summary">${esc(b.trend_summary)}</p>
       <div style="margin-top:12px"><button class="add-summary-btn" data-action="add-to-summary-card" data-card="trend_0">+ Add to Summary</button></div>`;
    const tBtnRow = document.getElementById('trendBtnRow');
    if (tBtnRow) tBtnRow.style.display = '';
    const tPanel = document.getElementById('trendChatPanel');
    if (tPanel) tPanel.style.display = '';
  }
}

// ── Analytics ──────────────────────────────────────────────

function renderAnalytics(data) {
  renderSectorTable(data.sectors || []);
  renderStateTable(data.states || []);
  renderPortalTable(data.portals || []);
}

function renderTrendChart(trend) {
  const el = document.getElementById('radarTrendChart');
  if (!el) return;
  if (!trend.length) { el.innerHTML = '<div class="radar-loading">No trend data</div>'; return; }
  const labels = trend.map(w => w.week_start || String(w.year_week));
  const vals   = trend.map(w => w.jobs_created);
  // Colour bars by relative volume: darkest = highest week
  const max = Math.max(...vals);
  const colors = vals.map(v => {
    const t = max > 0 ? v / max : 0;
    const r = Math.round(26  + (99  - 26)  * (1 - t));
    const g = Math.round(56  + (184 - 56)  * (1 - t));
    const b2= Math.round(196 + (255 - 196) * (1 - t));
    return `rgb(${r},${g},${b2})`;
  });
  Plotly.newPlot('radarTrendChart', [{
    x: labels, y: vals, type: 'bar',
    marker: {color: colors},
    name: 'Jobs created',
    hovertemplate: '<b>%{x}</b><br>%{y:,} jobs<extra></extra>'
  }], {
    margin: {t: 8, r: 10, b: 45, l: 52},
    plot_bgcolor: '#fff', paper_bgcolor: '#fff',
    font: {family: 'Segoe UI, Arial', size: 11, color: '#888'},
    xaxis: {tickangle: -30, tickfont: {size: 10}, gridcolor: '#f0efe8'},
    yaxis: {tickfont: {size: 10}, gridcolor: '#f0efe8'},
    bargap: 0.25,
  }, {displayModeBar: false, responsive: true});
}

function renderSectorTable(sectors) {
  if (!sectors.length) { document.getElementById('radarSectorTable').innerHTML = '<div class="radar-loading">No data</div>'; return; }
  const maxJobs = Math.max(...sectors.map(s => s.total_jobs || 0));
  let html = `<table class="radar-tbl">
    <thead><tr>
      <th>Sector</th><th>Jobs</th><th class="bar-cell"></th>
      <th>Avg days</th><th>Stale 30d</th><th>Stale 60d</th>
      <th>Urgent</th><th>Avg salary</th>
    </tr></thead><tbody>`;
  for (const s of sectors) {
    const pct = maxJobs ? Math.round((s.total_jobs/maxJobs)*100) : 0;
    const stalePct = s.total_jobs ? Math.round((s.stale_30/s.total_jobs)*100) : 0;
    html += `<tr>
      <td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${esc(s.occ_group)}">${esc(s.occ_group)}</td>
      <td>${(s.total_jobs||0).toLocaleString('de-AT')}</td>
      <td class="bar-cell"><div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div></td>
      <td>${s.avg_days_in_system ?? '—'}</td>
      <td>${s.stale_30||0} <small style="color:#bbb">(${stalePct}%)</small></td>
      <td>${s.stale_60||0}</td>
      <td>${s.urgent_deadline||0}</td>
      <td>${s.avg_salary ? '€'+Math.round(s.avg_salary).toLocaleString('de-AT') : '—'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('radarSectorTable').innerHTML = html;
}

function renderStateTable(states) {
  if (!states.length) { document.getElementById('radarStateTable').innerHTML = '<div class="radar-loading">No data</div>'; return; }
  const maxJobs = Math.max(...states.map(s => s.total_jobs || 0));
  let html = `<table class="radar-tbl">
    <thead><tr><th>State</th><th>Jobs</th><th class="bar-cell"></th><th>Avg days</th><th>Stale 30d</th><th>Urgent</th><th>Avg salary</th></tr></thead><tbody>`;
  for (const s of states) {
    const pct = maxJobs ? Math.round((s.total_jobs/maxJobs)*100) : 0;
    html += `<tr>
      <td>${esc(s.state||'—')}</td>
      <td>${(s.total_jobs||0).toLocaleString('de-AT')}</td>
      <td class="bar-cell"><div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div></td>
      <td>${s.avg_days_in_system ?? '—'}</td>
      <td>${s.stale_30||0}</td>
      <td>${s.urgent_deadline||0}</td>
      <td>${s.avg_salary ? '€'+Math.round(s.avg_salary).toLocaleString('de-AT') : '—'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('radarStateTable').innerHTML = html;
}

function renderPortalTable(portals) {
  if (!portals.length) { document.getElementById('radarPortalTable').innerHTML = '<div class="radar-loading">No data</div>'; return; }
  const maxJobs = Math.max(...portals.map(p => p.total_jobs || 0));
  let html = `<table class="radar-tbl">
    <thead><tr><th>Portal</th><th>Jobs</th><th class="bar-cell"></th><th>Avg days</th><th>Stale 60d</th><th>Avg salary</th></tr></thead><tbody>`;
  for (const p of portals) {
    const pct = maxJobs ? Math.round((p.total_jobs/maxJobs)*100) : 0;
    const stalePct = p.total_jobs ? Math.round((p.stale_60/p.total_jobs)*100) : 0;
    html += `<tr>
      <td>${esc(p.portal||'—')}</td>
      <td>${(p.total_jobs||0).toLocaleString('de-AT')}</td>
      <td class="bar-cell"><div class="mini-bar"><div class="mini-bar-fill stale" style="width:${pct}%"></div></div></td>
      <td>${p.avg_days_in_system ?? '—'}</td>
      <td>${p.stale_60||0} <small style="color:#bbb">(${stalePct}%)</small></td>
      <td>${p.avg_salary ? '€'+Math.round(p.avg_salary).toLocaleString('de-AT') : '—'}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  document.getElementById('radarPortalTable').innerHTML = html;
}

// ── Quick Finder ──────────────────────────────────────────────

function populateFinderFilters(sectors, states, portals) {
  _populateSel('rfOccGroup', sectors.map(s => s.occ_group).filter(Boolean), 'All sectors');
  _populateSel('rfState',    states.map(s => s.state).filter(Boolean),   'All states');
  _populateSel('rfPortal',   portals.map(p => p.portal).filter(Boolean),  'All portals');
}

function _populateSel(id, values, placeholder) {
  const sel = document.getElementById(id);
  const cur = sel.value;
  sel.innerHTML = `<option value="">${placeholder}</option>`;
  for (const v of values) {
    const opt = document.createElement('option');
    opt.value = v; opt.textContent = v;
    if (v === cur) opt.selected = true;
    sel.appendChild(opt);
  }
}

async function loadFinderJobs() {
  const mode      = document.getElementById('rfMode').value;
  const occ_group = document.getElementById('rfOccGroup').value;
  const state     = document.getElementById('rfState').value;
  const portal    = document.getElementById('rfPortal').value;
  const minDays   = document.getElementById('rfMinDays').value;

  document.getElementById('radarFinderList').innerHTML = '<div class="radar-loading">Loading…</div>';
  document.getElementById('rfCount').textContent = '';

  try {
    let url = `/api/opportunity/jobs?mode=${mode}&limit=80`;
    if (occ_group) url += `&occ_group=${encodeURIComponent(occ_group)}`;
    if (state)     url += `&state=${encodeURIComponent(state)}`;
    if (portal)    url += `&portal=${encodeURIComponent(portal)}`;
    if (mode === 'stale') url += `&min_days=${minDays}`;

    const data = await api.get(url);

    document.getElementById('rfCount').textContent = `${data.count} jobs`;
    renderFinderList(data.jobs, mode);
  } catch(e) {
    document.getElementById('radarFinderList').innerHTML =
      `<div class="radar-loading" style="color:#ef4444">Error: ${e.message}</div>`;
  }
}

function renderFinderList(jobs, mode) {
  if (!jobs.length) {
    document.getElementById('radarFinderList').innerHTML =
      '<div class="radar-loading">No jobs found for these filters.</div>';
    return;
  }
  let html = '';
  for (const j of jobs) {
    const daysLabel = mode === 'urgent'
      ? `⏰ ${j.days_until_deadline}d left`
      : `${j.days_in_system}d old`;
    const daysClass = mode === 'urgent' ? 'rfinder-days urgent-days' : 'rfinder-days';
    const salary    = j.salary ? '€'+Math.round(j.salary).toLocaleString('de-AT') : '';
    const linkHtml  = j.url ? `<a class="rfinder-link" href="${esc(j.url)}" target="_blank">↗ Open</a>` : '';
    const deadlineHtml = j.application_deadline
      ? `<span class="rfinder-deadline" title="Deadline">${j.application_deadline.slice(0,10)}</span>` : '';
    html += `<div class="rfinder-row">
      <span class="${daysClass}">${daysLabel}</span>
      <span class="rfinder-title" title="${esc(j.title||'')}">${esc(j.title||'—')}</span>
      <span class="rfinder-company" title="${esc(j.company||'')}">${esc(j.company||'—')}</span>
      <span class="rfinder-state">${esc(j.state||'—')}</span>
      <span class="rfinder-sector" title="${esc(j.occ_group||'')}">${esc(j.occ_group||'—')}</span>
      <span class="rfinder-salary">${salary}</span>
      ${deadlineHtml}
      ${linkHtml}
    </div>`;
  }
  document.getElementById('radarFinderList').innerHTML = html;
}

// ── Tab chat (opps / under / urgency / trend) ────────────────

function triggerTabChat(tab, idx, action) {
  const briefing = (_radarData && _radarData.briefing) || {};
  let msg = '';
  if (tab === 'opps') {
    const o = _oppsData[idx] || {};
    const prompts = {
      strategy: `What's the best sourcing strategy for "${o.label}"? Which channels and approaches work best given it's rated ${o.signal || 'moderate'} signal?`,
      salary:   `How competitive is the salary for "${o.label}" compared to the wider {{ country_demonym }} market? Should we adjust our offer strategy?`,
      signal:   `Break down why "${o.label}" is rated ${o.signal || 'moderate'} signal — which specific data points are driving that rating?`,
    };
    msg = prompts[action] || '';
  } else if (tab === 'under') {
    const u = _underData[idx] || {};
    const prompts = {
      why:     `Why is "${u.label}" underserved and what's the likely root cause — is it salary, location, or a candidate shortage?`,
      improve: `What specific steps can we take to improve candidate inflow for "${u.label}"?`,
      compare: `How does "${u.label}"'s staleness compare to the overall market average, and how severe is the gap?`,
    };
    msg = prompts[action] || '';
  } else if (tab === 'urgency') {
    const u = _urgencyData[idx] || {};
    const prompts = {
      plan:     `What's a fast-track recruitment plan for the ${u.count} urgent roles in "${u.label}"? Which steps are most critical?`,
      priority: `Which candidates or sourcing channels should we prioritize first for "${u.label}" given the tight deadline?`,
      risk:     `What's the business risk if we don't act on "${u.label}" within the next 14 days?`,
    };
    msg = prompts[action] || '';
  } else if (tab === 'trend') {
    const prompts = {
      driving:  `What factors are likely driving the volume trend we're seeing in the data? Is this seasonal, structural, or event-driven?`,
      forecast: `Based on the current trend, what should we expect in terms of job volume over the next 4 weeks?`,
      sectors:  `Which sectors are contributing most to the current volume movement, and which are bucking the trend?`,
    };
    msg = prompts[action] || '';
  }
  if (!msg) return;
  const cfg = _tabChats[tab];
  if (!cfg) return;
  const panel = document.getElementById(cfg.panelId);
  if (panel) panel.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  sendTabChat(tab, msg);
}

async function sendTabChat(tab, text) {
  const cfg = _tabChats[tab];
  if (!cfg || cfg.busy) return;
  const thread  = document.getElementById(cfg.threadId);
  const input   = document.getElementById(cfg.inputId);
  const sendBtn = document.getElementById(cfg.sendId);
  const msg = (text || (input && input.value) || '').trim();
  if (!msg) return;

  const empty = thread.querySelector('.opp-chat-empty');
  if (empty) empty.remove();

  thread.insertAdjacentHTML('beforeend',
    `<div class="opp-chat-msg user"><div class="opp-chat-bubble">${esc(msg)}</div></div>`);
  thread.scrollTop = thread.scrollHeight;

  if (input) input.value = '';
  cfg.busy = true;
  if (sendBtn) sendBtn.disabled = true;

  const typingId = 'tab-typing-' + Date.now();
  thread.insertAdjacentHTML('beforeend',
    `<div id="${typingId}" class="opp-chat-typing">Analysing…</div>`);
  thread.scrollTop = thread.scrollHeight;

  try {
    const briefing = (_radarData && _radarData.briefing) || {};
    const context = {
      totals:            (_radarData && _radarData.totals) || {},
      headline:          briefing.headline,
      top_opportunities: briefing.top_opportunities,
      underserved:       briefing.underserved,
      urgency_alerts:    briefing.urgency_alerts,
      recommendations:   briefing.recommendations,
      sectors:           ((_radarData && _radarData.sectors) || []).slice(0, 15),
    };
    const data = await api.post('/api/opportunity/chat', {message: msg, history: cfg.history, context});
    document.getElementById(typingId)?.remove();
    const answer = data.ok ? data.answer : (data.error || 'Something went wrong.');
    const _caIdx = _chatAnswers.push(answer) - 1;
    thread.insertAdjacentHTML('beforeend',
      `<div class="opp-chat-msg ai">
        <div class="opp-chat-bubble">${mdToHtml(answer)}</div>
        <button class="opp-chat-save-btn" data-action="add-to-summary-chat" data-idx="${_caIdx}">+ Save to Summary</button>
      </div>`);
    cfg.history.push({role: 'user',      content: msg});
    cfg.history.push({role: 'assistant', content: answer});
    if (cfg.history.length > 16) cfg.history = cfg.history.slice(-16);
  } catch(e) {
    document.getElementById(typingId)?.remove();
    thread.insertAdjacentHTML('beforeend',
      `<div class="opp-chat-msg ai"><div class="opp-chat-bubble" style="color:#ef4444">Error: ${esc(e.message)}</div></div>`);
  } finally {
    cfg.busy = false;
    if (sendBtn) sendBtn.disabled = false;
    thread.scrollTop = thread.scrollHeight;
  }
}

// Wire up tab chat send buttons + Enter key
Object.entries(_tabChats).forEach(([tab, cfg]) => {
  document.getElementById(cfg.sendId)?.addEventListener('click', () => sendTabChat(tab));
  document.getElementById(cfg.inputId)?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendTabChat(tab); }
  });
});

// ── Week-over-Week momentum chart ─────────────────────────────

function renderMomentumChart(trend) {
  const el = document.getElementById('radarMomentumChart');
  if (!el) return;
  if (!trend || trend.length < 2) {
    el.innerHTML = '<div class="radar-loading" style="color:#bbb;padding:20px">Need at least 2 weeks of data</div>';
    return;
  }
  const labels = [], vals = [];
  for (let i = 1; i < trend.length; i++) {
    const prev = trend[i-1].jobs_created || 0;
    const curr = trend[i].jobs_created   || 0;
    vals.push(prev > 0 ? Math.round((curr - prev) / prev * 100) : 0);
    labels.push(trend[i].week_start || String(trend[i].year_week));
  }
  const colors     = vals.map(v => v >= 0 ? '#16a34a' : '#ef4444');
  const textColors = vals.map(v => v >= 0 ? '#16a34a' : '#ef4444');
  Plotly.newPlot('radarMomentumChart', [{
    x: labels, y: vals, type: 'bar',
    marker: {color: colors},
    text: vals.map(v => (v >= 0 ? '+' : '') + v + '%'),
    textposition: 'outside',
    textfont: {size: 9, color: textColors},
    hovertemplate: '<b>%{x}</b><br>%{y:+.0f}% vs prior week<extra></extra>',
    name: 'WoW change',
  }], {
    margin: {t: 28, r: 10, b: 45, l: 48},
    plot_bgcolor: '#fff', paper_bgcolor: '#fff',
    font: {family: 'Segoe UI, Arial', size: 11, color: '#888'},
    xaxis: {tickangle: -30, tickfont: {size: 10}, gridcolor: '#f0efe8'},
    yaxis: {tickfont: {size: 10}, gridcolor: '#f0efe8', ticksuffix: '%',
            zeroline: true, zerolinecolor: '#ccc', zerolinewidth: 1.5},
    bargap: 0.3,
  }, {displayModeBar: false, responsive: true});
}

// ── Briefing follow-up chat ──────────────────────────────────

function triggerOppChat(idx, action) {
  const rec = _oppRecs[idx] || '';
  const prompts = {
    details: `Can you elaborate on recommendation ${idx+1}: "${rec}"? What specific steps should a recruiter take and what should they watch out for?`,
    trend:   `What underlying market trend or data pattern is driving recommendation ${idx+1}: "${rec}"?`,
    data:    `What are the specific numbers behind recommendation ${idx+1}: "${rec}"? Break down the key data points.`,
  };
  const msg = prompts[action] || rec;
  const panel = document.getElementById('oppChatPanel');
  if (panel) panel.scrollIntoView({behavior:'smooth', block:'nearest'});
  sendOppChat(msg);
}

async function sendOppChat(text) {
  if (_oppChatBusy) return;
  const input   = document.getElementById('oppChatInput');
  const thread  = document.getElementById('oppChatThread');
  const sendBtn = document.getElementById('oppChatSend');
  const msg = (text || (input && input.value) || '').trim();
  if (!msg) return;

  const empty = thread.querySelector('.opp-chat-empty');
  if (empty) empty.remove();

  thread.insertAdjacentHTML('beforeend',
    `<div class="opp-chat-msg user"><div class="opp-chat-bubble">${esc(msg)}</div></div>`);
  thread.scrollTop = thread.scrollHeight;

  if (input) input.value = '';
  _oppChatBusy = true;
  if (sendBtn) sendBtn.disabled = true;

  const typingId = 'opp-typing-' + Date.now();
  thread.insertAdjacentHTML('beforeend',
    `<div id="${typingId}" class="opp-chat-typing">Analysing…</div>`);
  thread.scrollTop = thread.scrollHeight;

  try {
    const briefing = _radarData && _radarData.briefing || {};
    const context = {
      totals:            (_radarData && _radarData.totals) || {},
      headline:          briefing.headline,
      top_opportunities: briefing.top_opportunities,
      underserved:       briefing.underserved,
      urgency_alerts:    briefing.urgency_alerts,
      recommendations:   briefing.recommendations,
      sectors:           ((_radarData && _radarData.sectors) || []).slice(0, 15),
    };

    const data = await api.post('/api/opportunity/chat', {message: msg, history: _oppChatHistory, context});
    document.getElementById(typingId)?.remove();

    const answer = data.ok ? data.answer : (data.error || 'Something went wrong.');
    const _caIdx = _chatAnswers.push(answer) - 1;
    thread.insertAdjacentHTML('beforeend',
      `<div class="opp-chat-msg ai">
        <div class="opp-chat-bubble">${mdToHtml(answer)}</div>
        <button class="opp-chat-save-btn" data-action="add-to-summary-chat" data-idx="${_caIdx}">+ Save to Summary</button>
      </div>`);

    _oppChatHistory.push({role: 'user',      content: msg});
    _oppChatHistory.push({role: 'assistant', content: answer});
    if (_oppChatHistory.length > 16) _oppChatHistory = _oppChatHistory.slice(-16);
  } catch(e) {
    document.getElementById(typingId)?.remove();
    thread.insertAdjacentHTML('beforeend',
      `<div class="opp-chat-msg ai"><div class="opp-chat-bubble" style="color:#ef4444">Error: ${esc(e.message)}</div></div>`);
  } finally {
    _oppChatBusy = false;
    if (sendBtn) sendBtn.disabled = false;
    thread.scrollTop = thread.scrollHeight;
  }
}

document.getElementById('oppChatSend')?.addEventListener('click', () => sendOppChat());
document.getElementById('oppChatInput')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendOppChat(); }
});

// ── Analytics Summary ─────────────────────────────────────────

const _TYPE_BADGE_CLASS = {
  recommendation: 'stb-recommendation',
  opportunity:    'stb-opportunity',
  underserved:    'stb-underserved',
  urgency:        'stb-urgency',
  trend:          'stb-trend',
  chat:           'stb-chat',
};
const _TYPE_LABEL = {
  recommendation: 'Recommendation',
  opportunity:    'Opportunity',
  underserved:    'Underserved',
  urgency:        'Urgency Alert',
  trend:          'Trend',
  chat:           'Chat Insight',
};

function addToSummaryCard(key, btnEl) {
  const d = _summaryCardData[key];
  if (d) addToSummary(d.type, d.label, d.content, btnEl);
}

function addToSummary(type, label, content, btnEl) {
  _summaryItems.push({ id: 'si-' + (++_summaryCounter), type, label, content });
  renderSummaryList();
  _updateSummaryBadge();
  if (btnEl) { btnEl.textContent = '✓ Added'; btnEl.classList.add('added'); btnEl.disabled = true; }
}

function removeFromSummary(id) {
  _summaryItems = _summaryItems.filter(s => s.id !== id);
  renderSummaryList();
  _updateSummaryBadge();
}

// Action registry for the radar/analytics dynamic markup — AI-filter chips
// (suggested + applied), opportunity/underserved/urgency cards, summary save
// buttons. (tab-chat + ai-filter-clear are registered in the radar block above.)
Object.assign(_ACTIONS, {
  'remove-ai-chip':      (el) => _removeAIChip(el.dataset.field, +el.dataset.i),
  'remove-ai-salary':    ()   => _removeAISalary(),
  'remove-applied-chip': (el) => _removeAppliedChip(el.dataset.field, +el.dataset.i),
  'trigger-opp-chat':    (el) => triggerOppChat(+el.dataset.i, el.dataset.act),
  'add-to-summary-card': (el) => addToSummaryCard(el.dataset.card, el),
  'add-to-summary-chat': (el) => addToSummary('chat', 'Chat Insight', _chatAnswers[+el.dataset.idx], el),
  'remove-from-summary': (el) => removeFromSummary(el.dataset.id),
});

function _updateSummaryBadge() {
  const badge = document.getElementById('summaryBadgeNav');
  const n = _summaryItems.length;
  if (badge) { badge.textContent = n; badge.style.display = n ? '' : 'none'; }
  ['summaryGenCompactBtn','summaryGenChartsBtn'].forEach(id => {
    const b = document.getElementById(id);
    if (b && !b.dataset.busy) b.disabled = n === 0;
  });
}

const _SECTION_ORDER = ['recommendation','opportunity','underserved','urgency','trend','chat'];
const _SECTION_NAMES = {
  recommendation: 'Recommendations',
  opportunity:    'Top Opportunities',
  underserved:    'Underserved Markets',
  urgency:        'Urgency Alerts',
  trend:          'Trend Insights',
  chat:           'Chat Insights',
};

function renderSummaryList() {
  const el = document.getElementById('summaryList');
  if (!el) return;
  if (!_summaryItems.length) {
    el.innerHTML = `<div class="summary-empty-state">
      <div class="summary-empty-state-icon">📋</div>
      <h3>No insights saved yet</h3>
      <p>Use the <strong>+ Add to Summary</strong> buttons in the Opportunities Radar to save findings here</p>
    </div>`;
    return;
  }

  // Group items by type, preserving insertion order within each group
  const groups = {};
  _summaryItems.forEach(s => {
    const t = s.type || 'chat';
    if (!groups[t]) groups[t] = [];
    groups[t].push(s);
  });

  const activeSections = _SECTION_ORDER.filter(t => groups[t] && groups[t].length);

  let globalNum = 0;
  const sectionsHtml = activeSections.map((t, secIdx) => {
    const items = groups[t];
    const secName = _SECTION_NAMES[t] || t;
    const secNum = secIdx + 1;
    const itemsHtml = items.map(s => {
      globalNum++;
      const preview = s.content.length > 220 ? s.content.slice(0, 220) + '…' : s.content;
      return `<div class="summary-item">
        <div class="summary-item-header">
          <span class="summary-item-num">#${globalNum}</span>
          <span class="summary-type-badge ${_TYPE_BADGE_CLASS[s.type] || 'stb-chat'}">${_TYPE_LABEL[s.type] || s.type}</span>
          <span class="summary-item-label" title="${esc(s.label)}">${esc(s.label)}</span>
          <button class="summary-item-remove" data-action="remove-from-summary" data-id="${s.id}" title="Remove">×</button>
        </div>
        <div class="summary-item-content">${esc(preview)}</div>
      </div>`;
    }).join('');
    return `<div class="summary-section-group">
      <div class="summary-section-header">
        <span class="summary-section-num">Section ${secNum}</span>
        <span class="summary-section-title">${secName}</span>
        <span class="summary-section-count">${items.length} ${items.length === 1 ? 'item' : 'items'}</span>
      </div>
      ${itemsHtml}
    </div>`;
  }).join('');

  el.innerHTML = `<div class="summary-list">${sectionsHtml}</div>`;
}

async function captureCharts() {
  const captures = [
    { id: 'radarTrendChart',    title: 'Weekly Job Creation' },
    { id: 'radarMomentumChart', title: 'Week-over-Week Volume Change' },
  ];
  const charts = [];
  for (const { id, title } of captures) {
    const el = document.getElementById(id);
    if (!el || !el.layout) continue;
    try {
      const dataUrl = await Plotly.toImage(el, { format: 'png', width: 780, height: 280 });
      charts.push({ title, data_url: dataUrl });
    } catch(e) { /* skip unavailable chart */ }
  }

  // Composition donut — item-type breakdown
  if (_summaryItems.length >= 2) {
    const counts = {};
    _summaryItems.forEach(s => { const t = s.type || 'chat'; counts[t] = (counts[t] || 0) + 1; });
    if (Object.keys(counts).length >= 2) {
      const typeColors = { recommendation:'#1a56c4', opportunity:'#16a34a', underserved:'#d97706', urgency:'#ea580c', trend:'#7c3aed', chat:'#6b7280' };
      const typeLabels = { recommendation:'Recommendations', opportunity:'Opportunities', underserved:'Underserved', urgency:'Urgency Alerts', trend:'Trend Insights', chat:'Chat Insights' };
      const tmpDiv = document.createElement('div');
      tmpDiv.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:480px;height:300px;';
      document.body.appendChild(tmpDiv);
      try {
        const keys = Object.keys(counts);
        await Plotly.newPlot(tmpDiv,
          [{ type:'pie', hole:0.45, labels: keys.map(k => typeLabels[k]||k), values: keys.map(k => counts[k]),
             marker:{ colors: keys.map(k => typeColors[k]||'#6b7280') },
             textinfo:'label+percent', textfont:{ size:11 } }],
          { margin:{t:20,b:10,l:10,r:10}, paper_bgcolor:'white', showlegend:false,
            font:{ family:'Segoe UI,Arial,sans-serif', size:11 } },
          { displayModeBar:false, staticPlot:true }
        );
        const dataUrl = await Plotly.toImage(tmpDiv, { format:'png', width:480, height:300 });
        charts.push({ title:'Summary Composition by Type', data_url: dataUrl });
      } catch(e) { /* skip */ }
      document.body.removeChild(tmpDiv);
    }
  }
  return charts;
}

async function generateReport(withCharts) {
  if (!_summaryItems.length) return;
  const btnId  = withCharts ? 'summaryGenChartsBtn' : 'summaryGenCompactBtn';
  const otherId = withCharts ? 'summaryGenCompactBtn' : 'summaryGenChartsBtn';
  const btn   = document.getElementById(btnId);
  const other = document.getElementById(otherId);
  const orig  = btn.innerHTML;
  btn.dataset.busy = '1'; btn.disabled = true;
  if (other) { other.dataset.busy = '1'; other.disabled = true; }

  const spinSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>';
  btn.innerHTML = spinSvg + ' Generating…';

  try {
    let charts = [];
    if (withCharts) {
      btn.innerHTML = spinSvg + ' Capturing charts…';
      charts = await captureCharts();
      btn.innerHTML = spinSvg + ' Building PDF…';
    }

    const briefing = (_radarData && _radarData.briefing) || {};
    const context  = {
      totals:            (_radarData && _radarData.totals) || {},
      headline:          briefing.headline,
      top_opportunities: briefing.top_opportunities,
      underserved:       briefing.underserved,
      urgency_alerts:    briefing.urgency_alerts,
      recommendations:   briefing.recommendations,
    };
    const res = await api.raw('/api/analytics/report', { method: 'POST', body: { items: _summaryItems, context, charts } });
    if (!res.ok) { const d = await res.json().catch(()=>{}); throw new Error((d && d.error) || res.statusText); }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    a.download = withCharts ? 'analytics-report-charts.pdf' : 'analytics-report.pdf';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch(e) {
    alert('Report generation failed: ' + e.message);
  } finally {
    btn.innerHTML = orig;
    delete btn.dataset.busy;
    if (other) delete other.dataset.busy;
    _updateSummaryBadge();
  }
}

// ── Analytics Summary chat ────────────────────────────────────
let _summaryChatHistory = [];
let _summaryChatBusy    = false;

function triggerSummaryChat(text) {
  const inp = document.getElementById('summaryChatInput');
  if (inp) inp.value = text;
  sendSummaryChat(text);
}

async function sendSummaryChat(overrideText) {
  if (_summaryChatBusy) return;
  const inp  = document.getElementById('summaryChatInput');
  const send = document.getElementById('summaryChatSend');
  const thread = document.getElementById('summaryChatThread');
  const text = (overrideText || (inp && inp.value.trim()) || '').trim();
  if (!text || !thread) return;

  if (inp) inp.value = '';
  _summaryChatBusy = true;
  if (send) send.disabled = true;

  // User bubble
  thread.innerHTML += `<div class="summary-chat-bubble-user">${esc(text)}</div>`;
  thread.innerHTML += `<div class="summary-chat-bubble-ai" id="summaryChatTyping" style="color:#aaa;font-style:italic">Thinking…</div>`;
  thread.scrollTop = thread.scrollHeight;

  _summaryChatHistory.push({ role: 'user', content: text });

  try {
    const data = await api.post('/api/analytics/chat', { history: _summaryChatHistory, items: _summaryItems });
    const answer = data.answer || '';
    _summaryChatHistory.push({ role: 'assistant', content: answer });

    const _scIdx = _chatAnswers.push(answer) - 1;
    const typing = document.getElementById('summaryChatTyping');
    if (typing) typing.outerHTML = `<div class="summary-chat-bubble-ai">
      ${mdToHtml(answer)}
      <button class="summary-chat-save-btn" data-action="add-to-summary-chat" data-idx="${_scIdx}">+ Save to Summary</button>
    </div>`;
  } catch(e) {
    const typing = document.getElementById('summaryChatTyping');
    if (typing) typing.outerHTML = `<div class="summary-chat-bubble-ai" style="color:#ef4444">Error: ${esc(e.message)}</div>`;
  } finally {
    _summaryChatBusy = false;
    if (send) send.disabled = false;
    thread.scrollTop = thread.scrollHeight;
  }
}

// ── Wire up tab ───────────────────────────────────────────────

