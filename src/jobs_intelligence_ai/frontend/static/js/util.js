// ════════════════════════════════════════════════════════════
//  Shared utilities — used across feature modules
// ════════════════════════════════════════════════════════════
// Pure helpers (esc, mdToHtml) plus the job store — a tiny keyed cache that lets
// result rows / cluster cards hand a job object to the detail modal by id (so the
// id can travel through data-* attributes without serialising the whole job).

export function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export function mdToHtml(text) {
  let s = esc(text);
  // Bold then italic (order matters — do ** before *)
  s = s.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Bullet lists: lines starting with "- " or "• "
  s = s.replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>(\n|$))+/g, m => '<ul>' + m + '</ul>');
  // Paragraphs: double newline
  s = s.replace(/\n{2,}/g, '</p><p>');
  // Remaining single newlines
  s = s.replace(/\n/g, '<br>');
  return '<p>' + s + '</p>';
}

// ── Job store — lets cards/rows pass job data to the modal by id ──
const _jobStore = new Map();
let _jobStoreSeq = 0;

export function storeJob(job) {
  const id = 'jb' + (++_jobStoreSeq);
  _jobStore.set(id, job);
  return id;
}

export function getStoredJob(id) {
  return _jobStore.get(id);
}
