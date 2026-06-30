// ════════════════════════════════════════════════════════════
//  Boot — module wiring, tab routing, global delegated-action dispatch,
//  feedback widget, init
// ════════════════════════════════════════════════════════════
// The page entry point: imports every feature module (most register their own
// _ACTIONS/app entries as a load-time side effect), owns the top-level tab/
// mode-toggle routing, the central data-action dispatcher that all the other
// modules' _ACTIONS registrations are read by, and the feedback widget.
import { _ACTIONS, app } from "./state.js";
import api from "./api.js";
// Side-effect-only import: clustering.js has no page-script consumer of a bare
// binding (the search-tab Multiple-CV markup drives it entirely through
// _ACTIONS/app), so it must still be imported to run its top-level registration.
import "./clustering.js";
// Side-effect-only import: candidate.js registers its own _ACTIONS + app entries.
import "./candidate.js";
// Side-effect-only import: candidate-examples.js (bundled demo candidates +
// the Examples dropdown) registers its own _ACTIONS + builds the dropdown.
import "./candidate-examples.js";
// Side-effect-only import: guided.js registers its own _ACTIONS + app entries.
import "./guided.js";
// Side-effect-only import: assistant.js registers its own _ACTIONS + app entries.
import "./assistant.js";
// Side-effect-only import: search.js registers its own _ACTIONS + app entries.
import "./search.js";
// Side-effect-only import: saved.js registers its own _ACTIONS + app entries.
import "./saved.js";
// Side-effect-only import: modal.js registers its own _ACTIONS + app entries.
import "./modal.js";
// Side-effect-only import: interview.js registers its own _ACTIONS + app entries.
import "./interview.js";

// Cross-module exports — registered on app so candidate/saved/feedback can
// call into this module without a direct import (avoids circular references).
Object.assign(app, {
  getCandidateName, _activateTab,
  _feedbackContext,
});

// ════════════════════════════════════════════════════════════
//  State
// ════════════════════════════════════════════════════════════
// _ACTIONS (the delegated-action registry) is imported from state.js so feature
// modules can register their handlers next to their own code.
let currentCandidate = '';   // name entered in the candidate bar

function getCandidateName() {
  return document.getElementById('candidateName').value.trim() || 'Unassigned';
}
// The exact candidate text used for the last search — so the per-job chat can judge
// fit for the candidate you searched with, even if the input boxes change afterward.
// The candidate text the CURRENT scores were computed against — re-scoring a frozen
// set is only meaningful when this differs from the live candidate text.

// ════════════════════════════════════════════════════════════
//  Tab routing
// ════════════════════════════════════════════════════════════
function _activateTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('tab-' + id);
  const btn   = document.querySelector(`.tab-btn[data-tab="${id}"]`);
  if (panel) panel.classList.add('active');
  if (btn)   btn.classList.add('active');
  // Side effects
  if (id === 'saved') app.openSavedTab();
}

document.querySelectorAll('.tab-btn[data-mode-group]').forEach(btn =>
  btn.addEventListener('click', () => _activateTab(btn.dataset.tab)));

// ── Company link — delegated click handler ────────────────────
// All .company-link spans use data-company instead of inline onclick
// so we handle them here via event delegation (no quoting issues).
document.addEventListener('click', function(e) {
  const link = e.target.closest('.company-link');
  if (!link) return;
  e.stopPropagation();
  const name = link.getAttribute('data-company');
  if (name) app.openCompanyPanel(name);
});

// ── Action dispatch — delegated click handler (replaces inline onclick=) ──
// Elements carry data-action="name" (+ data-* params) instead of onclick="fn(args)".
// Each feature registers its handlers into _ACTIONS near its own code, so markup
// stops referencing global function names by name — the prerequisite for splitting
// the script into ES modules (2.6c). Registration runs at load, before any click.
// (`_ACTIONS` itself is declared up in the State section so the registration blocks
// scattered above this point aren't in its temporal dead zone.)
document.addEventListener('click', function(e) {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.action];
  if (handler) handler(el, e);
});
// Same registry, dispatched for the non-click inline handlers (oninput / onkeydown).
document.addEventListener('input', function(e) {
  const el = e.target.closest('[data-input-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.inputAction];
  if (handler) handler(el, e);
});
document.addEventListener('change', function(e) {
  const el = e.target.closest('[data-change-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.changeAction];
  if (handler) handler(el, e);
});
document.addEventListener('keydown', function(e) {
  const el = e.target.closest('[data-keydown-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.keydownAction];
  if (handler) handler(el, e);
});
// focusout (not blur — blur doesn't bubble, so it can't be delegated).
document.addEventListener('focusout', function(e) {
  const el = e.target.closest('[data-blur-action]');
  if (!el) return;
  const handler = _ACTIONS[el.dataset.blurAction];
  if (handler) handler(el, e);
});
// ════════════════════════════════════════════════════════════
//  Feedback widget
// ════════════════════════════════════════════════════════════
function _feedbackContext(){
  const p = document.querySelector('.tab-panel.active');
  return p && p.id ? p.id.replace('tab-','') : '';
}
function openFeedback(){
  document.getElementById('fbMsg').textContent = '';
  document.getElementById('fbText').value = '';
  document.getElementById('fbOverlay').classList.add('show');
  setTimeout(() => document.getElementById('fbText').focus(), 50);
}
function closeFeedback(){ document.getElementById('fbOverlay').classList.remove('show'); }
// Action registry for the feedback widget (markup lives after </script>).
Object.assign(_ACTIONS, {
  'open-feedback':     ()      => openFeedback(),
  'feedback-backdrop': (el, e) => { if (e.target === el) closeFeedback(); },
  'close-feedback':    ()      => closeFeedback(),
  'send-feedback':     ()      => sendFeedback(),
});
async function sendFeedback(){
  const ta  = document.getElementById('fbText');
  const msg = document.getElementById('fbMsg');
  const btn = document.getElementById('fbSend');
  const text = ta.value.trim();
  if (!text){ msg.style.color='#b91c1c'; msg.textContent='Please type something first.'; ta.focus(); return; }
  btn.disabled = true; msg.style.color='#6b7280'; msg.textContent='Sending…';
  try {
    const data = await api.post('/api/feedback', { message: text, context: app._feedbackContext() });
    msg.style.color='#1a7a2e'; msg.textContent='Thanks — feedback saved!';
    setTimeout(closeFeedback, 900);
  } catch(e){
    msg.style.color='#b91c1c'; msg.textContent='Could not send: ' + (e.message || e);
  } finally { btn.disabled = false; }
}

// ════════════════════════════════════════════════════════════
//  Init
// ════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => app.loadFilters());
