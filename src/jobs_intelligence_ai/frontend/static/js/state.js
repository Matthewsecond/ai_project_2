// ════════════════════════════════════════════════════════════
//  Shared cross-module state
// ════════════════════════════════════════════════════════════
// The genuinely cross-cutting singletons that several feature modules read/write.
// Exported as object properties (not bare `let`s) so other modules can mutate them
// — ES modules forbid reassigning an imported binding, but mutating a property of
// an imported object is fine. Feature-local state stays private to its own module.

// Filter dropdown options (states / occ_groups / portals), loaded once from the
// API and read by the search filters, the guided builder, and the radar AI filter.
export const state = {
  // Filter dropdown options (states / occ_groups / portals), loaded once from the
  // API and read by the search filters, the guided builder, and the radar AI filter.
  filterOpts: { states: [], occ_groups: [], portals: [] },
  // The current search result set — produced by search, read by map/export/sort/
  // candidate-assistant. (search owns it; others read via state.)
  lastResults: [],
  // The saved pipeline (jobs saved against candidates) — saved panel + export + modal.
  savedJobs: [],
  // The active candidate's parsed profile — set by candidate input, read by search /
  // modal / guided / saved when saving or scoring.
  currentCandidateProfile: null,
  // Current input mode ('cv' | 'linkedin' | 'guided' | 'multiple') — mode/tab switching.
  activeMode: 'cv',
  // The job currently open in the detail modal — modal + quality/analysis/interview + saved.
  modalJob: null,

  // ── Search result-set bookkeeping (search; read by candidate/assistant) ──
  pinnedJobIds: new Set(),        // jobs frozen individually (kept across re-runs)
  dismissedJobIds: new Set(),     // jobs removed from view (won't resurface on re-run)
  resultsFrozen: false,           // whole set frozen — re-score in place, don't re-search
  sortCol: 'score',
  sortAsc: false,
  // Text the current results were matched/scored against — search + per-job fit chat.
  lastMatchText: '',
  scoredAgainstText: '',
  lastParsedText: '',             // last parsed CV text (candidate; read by search/modal/interview)

  // ── Candidate-assistant highlight overlay (assistant; read by search/candidate) ──
  highlightedJobIds: new Set(),
  highlightCriterion: '',

  // Page-wide AI chat language (job chat / guided / interview / modal).
  jobChatLang: 'en',
  // Per-page session id for the candidate-assistant chat (assistant + modal).
  SESSION_ID: Math.random().toString(36).slice(2) + Date.now().toString(36),
  // Drilled from a multi-CV segment into the single-candidate workflow — clustering
  // sets it on drill-down, candidate's clearCandidateProfile/setWorkflow clear it.
  mcDrilledFrom: false,
  // Guided-builder draft fields — owned/written by guided.js, read by candidate's
  // buildCandidateText() when the active input mode is 'guided'.
  gbDraft: { name:'', sector:[], roles:[], skills:[], levels:[], states:[], languages:[], certs:[], salary:'', availability:'', notes:'' },
  // CV-style lines the candidate assistant added → folded into the matching text by
  // candidate's buildCandidateText()/_withAsstNotes(); owned/written by assistant.js.
  candAsstNotes: [],
  // Saved-tab view ('table' | 'dash') — owned by saved.js, set from candidate.js's
  // _gotoSavedLocal() when jumping to the Saved → Local list after a LinkedIn import.
  savedView: 'table',
  // Job-detail-modal description state read/written from both modal.js (the
  // translate/compact toolbar) and interview.js (descToggleOutreach reads the
  // source text + lang; descToggleCvQuestions toggles the questions-shown flag).
  descOriginal: '',
  modalLang: 'de',
  descOutreach: null,
  descOutreachShown: false,
  descCvQuestionsShown: false,
};

// The delegated-action registry (data-action → handler). Lives here so any feature
// module can register its handlers via Object.assign(_ACTIONS, {…}) next to its own
// code, and the dispatcher (in the page module) can look them up. Imported bindings
// are initialised before any module body runs, so there's no temporal-dead-zone trap.
export const _ACTIONS = {};

// Cross-module function registry (late binding). Feature modules that genuinely call
// into one another register their public functions here on load
// (Object.assign(app, { fn, … })) and callers invoke app.fn(…). This decouples the
// core cluster — no module needs to import a sibling — so each can be extracted
// independently. Calls fire at runtime (after every module has loaded + registered),
// the same guarantee that makes _ACTIONS safe.
export const app = {};
