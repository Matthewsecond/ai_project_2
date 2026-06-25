// ════════════════════════════════════════════════════════════
//  Export — CSV (matching results) + XLSX (saved pipeline) + PDF report
// ════════════════════════════════════════════════════════════
// `XLSX` is the global from the SheetJS CDN <script>. The data to export is
// passed in by the caller (handoff) rather than read from a shared global.

import api from "./api.js";

export function exportResults(results) {
  if (!results.length) { alert('Run matching first.'); return; }
  const cols = ['job_id','title','company','state','city','salary','grade','score_pct','portal','posted','url'];
  csvDownload(results, cols, 'jobs_matching_results.csv');
}

export function exportSaved(savedJobs) {
  if (!savedJobs.length) { alert('No saved jobs.'); return; }

  const wb = XLSX.utils.book_new();

  // ── Sheet 1: Pipeline (all jobs) ───────────────────────────
  const pipelineCols = [
    ['job_id','Job ID'], ['candidate_name','Candidate'], ['title','Title'],
    ['company','Company'], ['state','State'], ['city','City'],
    ['salary','Salary'], ['grade','Grade'], ['score_pct','Score %'],
    ['pipeline_status','Status'], ['notes','Notes'], ['url','URL'],
  ];
  const pipelineRows = [pipelineCols.map(c => c[1])];
  savedJobs.forEach(j => pipelineRows.push(pipelineCols.map(([k]) => j[k] || '')));
  const ws1 = XLSX.utils.aoa_to_sheet(pipelineRows);
  ws1['!cols'] = [8,18,30,24,14,14,14,7,8,12,30,40].map(w => ({ wch: w }));
  XLSX.utils.book_append_sheet(wb, ws1, 'Pipeline');

  // ── Sheet 2: Salary Analysis ───────────────────────────────
  const salRows = savedJobs.filter(j => j.extras?.salary);
  if (salRows.length) {
    const salHeader = ['Job ID','Candidate','Title','Company','Occ. Group',
      'Job Salary (€)','Market Mean (€)','Market Median (€)',
      'vs. Mean (€)','Percentile','Sample Size'];
    const salData = [salHeader, ...salRows.map(j => {
      const s = j.extras.salary;
      return [
        j.job_id, j.candidate_name||'', j.title||'', j.company||'',
        s.occ_group||'',
        s.job_salary ?? '', s.mean ?? '', s.median ?? '',
        s.diff_mean ?? '', s.pct_below != null ? `Top ${100-s.pct_below}%` : '',
        s.count ?? '',
      ];
    })];
    const ws2 = XLSX.utils.aoa_to_sheet(salData);
    ws2['!cols'] = [10,18,30,24,20,14,14,14,12,12,10].map(w => ({ wch: w }));
    XLSX.utils.book_append_sheet(wb, ws2, 'Salary Analysis');
  }

  // ── Sheet 3: Candidate Strength ────────────────────────────
  const strRows = savedJobs.filter(j => j.extras?.strength?.axes?.length);
  if (strRows.length) {
    const strHeader = ['Job ID','Candidate','Title','Company','Dimension','Score /10','Reason','Overall'];
    const strData   = [strHeader];
    strRows.forEach(j => {
      const st = j.extras.strength;
      st.axes.forEach((ax, i) => {
        strData.push([
          j.job_id, j.candidate_name||'', j.title||'', j.company||'',
          ax, st.scores[i] ?? '',
          (st.reasons||[])[i] || '',
          i === 0 ? (st.overall || '') : '',   // overall only on first row per job
        ]);
      });
    });
    const ws3 = XLSX.utils.aoa_to_sheet(strData);
    ws3['!cols'] = [10,18,30,24,20,8,45,40].map(w => ({ wch: w }));
    XLSX.utils.book_append_sheet(wb, ws3, 'Candidate Strength');
  }

  // ── Sheet 4: Descriptions ──────────────────────────────────
  const descRows = savedJobs.filter(j => j.extras?.compact);
  if (descRows.length) {
    const descHeader = ['Job ID','Candidate','Title','Company','Compact Description'];
    const descData   = [descHeader, ...descRows.map(j => [
      j.job_id, j.candidate_name||'', j.title||'', j.company||'',
      j.extras.compact||'',
    ])];
    const ws4 = XLSX.utils.aoa_to_sheet(descData);
    ws4['!cols'] = [10,18,30,24,80].map(w => ({ wch: w }));
    XLSX.utils.book_append_sheet(wb, ws4, 'Descriptions');
  }

  // ── Sheet 5: Interviews ────────────────────────────────────
  // One row per answered question, plus the overall read, for any saved job
  // that carries an interview scorecard in extras.interview.
  const ivRows = savedJobs.filter(j => j.extras?.interview?.questions?.length);
  if (ivRows.length) {
    const ivHeader = ['Job ID','Candidate','Title','Question','Answer','Score','Verdict','Strengths','Concerns','Signals','Overall','Assessment'];
    const ivData = [ivHeader];
    ivRows.forEach(j => {
      const iv = j.extras.interview;
      const ov = iv.overall ? `${iv.overall.score ?? ''}% ${iv.overall.recommendation || ''} — ${iv.overall.summary || ''}`.trim() : '';
      const asp = (iv.aspects || []).map(a => `${a.aspect}: ${a.score != null ? a.score + '%' : '—'} (${a.status})`).join(' | ')
                  + (iv.aspectsSummary ? `\n${iv.aspectsSummary}` : '');
      (iv.questions || []).forEach((q, i) => {
        const a = (iv.answers || {})[q.id] || {};
        if (!(a.answer || '').trim()) return;
        ivData.push([
          j.job_id, j.candidate_name||'', j.title||'',
          q.question||'', a.answer||'',
          a.score != null ? a.score + '%' : '', a.verdict||'',
          (a.strengths||[]).join('; '), (a.concerns||[]).join('; '),
          (a.signals||[]).join('; '),
          i === 0 ? ov : '',
          i === 0 ? asp.trim() : '',
        ]);
      });
    });
    if (ivData.length > 1) {
      const ws5 = XLSX.utils.aoa_to_sheet(ivData);
      ws5['!cols'] = [10,18,26,40,50,8,40,30,30,24,50,55].map(w => ({ wch: w }));
      XLSX.utils.book_append_sheet(wb, ws5, 'Interviews');
    }
  }

  XLSX.writeFile(wb, 'jobs_pipeline.xlsx');
}

export async function generateSavedReport(cand) {
  if (!cand) { alert('No candidate selected.'); return; }
  const btn   = document.getElementById('csPdf');
  const label = document.getElementById('csPdfLabel');
  const orig  = label ? label.textContent : '';
  if (label) label.textContent = 'Generating…';
  if (btn) btn.disabled = true;
  try {
    const res = await api.raw('/api/saved/report', { method: 'POST', body: { candidate: cand.name } });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const filename = `${cand.name.trim().replace(/\s+/g, '_')}_MatchInsights.pdf`;
    const a = Object.assign(document.createElement('a'), { href: url, download: filename });
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 800);
  } catch(e) {
    alert('Report generation failed: ' + e.message);
  } finally {
    if (label) label.textContent = orig;
    if (btn) btn.disabled = false;
  }
}

function csvDownload(rows, cols, filename) {
  const csv = [cols.join(','), ...rows.map(r =>
    cols.map(c => `"${(r[c] || '').toString().replace(/"/g, '""')}"`).join(',')
  )].join('\n');
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob(['﻿' + csv], {type: 'text/csv'})),
    download: filename,
  });
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}
