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
  filterOpts: { states: [], occ_groups: [], portals: [] },
};

// The delegated-action registry (data-action → handler). Lives here so any feature
// module can register its handlers via Object.assign(_ACTIONS, {…}) next to its own
// code, and the dispatcher (in the page module) can look them up. Imported bindings
// are initialised before any module body runs, so there's no temporal-dead-zone trap.
export const _ACTIONS = {};
