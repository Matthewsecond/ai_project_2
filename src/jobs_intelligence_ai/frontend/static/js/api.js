/*
 * api.js — the one thin client over the JSON API (Stage 2.6b).
 *
 * Owns the protocol that was previously copy-pasted across ~88 fetch() call sites:
 * JSON headers, the { ok, error, ... } envelope, and error throwing. Call sites
 * shrink from a ~6-line fetch boilerplate to `const d = await api.post(path, body)`.
 *
 * Three primitives cover every pattern in the app:
 *   api.get(path)          → parsed JSON envelope; throws Error(error) when ok is false
 *   api.post(path, body)   → same, POST with a JSON body
 *   api.patch(path, body)  → same, PATCH
 *   api.del(path)          → same, DELETE
 *   api.raw(path, opts)    → the raw Response (for blob downloads, SSE streams, and
 *                            fire-and-forget mutations where the caller ignores the body)
 *
 * Native ES module (RESTRUCTURE_PLAN §12). During the 2.6 transition a small inline
 * module bridge assigns this to `window.api` so the not-yet-modularized inline script
 * can use it; once the page JS is split into modules (2.6c) callers import it directly.
 */

function _opts(method, body) {
  const o = { method };
  if (body !== undefined && body !== null) {
    o.headers = { 'Content-Type': 'application/json' };
    o.body = JSON.stringify(body);
  }
  return o;
}

async function _envelope(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || 'Request failed');
  return data;
}

export const get = (path) => _envelope(path, _opts('GET'));
export const post = (path, body) => _envelope(path, _opts('POST', body));
export const patch = (path, body) => _envelope(path, _opts('PATCH', body));
export const del = (path) => _envelope(path, _opts('DELETE'));
export const raw = (path, opts = {}) => fetch(path, _opts(opts.method || 'GET', opts.body));

export const api = { get, post, patch, del, raw };
export default api;
