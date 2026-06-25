// ════════════════════════════════════════════════════════════
//  Map tab — Leaflet map of the current result set
// ════════════════════════════════════════════════════════════
// First module extracted in the 2.6c split. `L` is the global from the Leaflet
// CDN <script> (resolves from module scope as a global-object property). The
// result set is passed in by the caller (handoff) rather than reaching into a
// shared global, so this module has no import back into the page script.

let leafletMap = null;
let mapMarkers = [];

export function updateMapStats(jobs) {
  const wienCount = jobs.filter(j =>
    (j.state || '').toLowerCase().includes('wien') ||
    (j.city  || '').toLowerCase().includes('wien')
  ).length;
  document.getElementById('statTotal').textContent = jobs.length || '—';
  document.getElementById('statWien').textContent  = jobs.length ? wienCount : '—';
  document.getElementById('statOther').textContent = jobs.length ? (jobs.length - wienCount) : '—';
}

export function initMap(results) {
  if (!leafletMap) {
    leafletMap = L.map('mapDiv').setView([47.5, 14.0], 7);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      {attribution: '© OpenStreetMap contributors', maxZoom: 18}).addTo(leafletMap);
  }
  mapMarkers.forEach(m => m.remove());
  mapMarkers = [];

  const withCoords = results.filter(j => j.lat && j.lon);
  const colors     = {A: '#1a7a2e', B: '#e8a800', C: '#a78bfa'};

  document.getElementById('mapInfoText').textContent = withCoords.length
    ? `Showing ${withCoords.length} of ${results.length} results with location data`
    : results.length ? 'No coordinate data for current results'
    : 'Run a search first to see jobs on the map';

  withCoords.forEach(job => {
    const m = L.circleMarker([job.lat, job.lon], {
      radius: 9, fillColor: colors[job.grade] || '#888',
      color: '#fff', weight: 2, fillOpacity: .85,
    }).bindPopup(`<strong>${job.title}</strong><br>${job.company}<br>
      <span style="color:${colors[job.grade]};font-weight:600">${job.grade} — ${job.score_pct}</span><br>
      ${[job.city, job.state].filter(Boolean).join(', ')}<br>
      ${job.url ? `<a href="${job.url}" target="_blank">View ↗</a>` : ''}`
    ).addTo(leafletMap);
    mapMarkers.push(m);
  });

  if (withCoords.length > 1)
    leafletMap.fitBounds(L.featureGroup(mapMarkers).getBounds().pad(.15));
  setTimeout(() => leafletMap.invalidateSize(), 80);
}
