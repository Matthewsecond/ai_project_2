// ════════════════════════════════════════════════════════════
//  Job detail modal — header/meta, description toolbar, analysis panels,
//  quality assessment, job sub-chat, save-with-extras
// ════════════════════════════════════════════════════════════
// Everything driven by opening a job's detail modal: populating the header/meta/
// skills/description, the lazy salary/quality/candidate-strength analysis panels,
// the per-job chat, and the save (+ extras) footer. Calls into candidate.js
// (buildCandidateText/getCandidateName/clearCandidateProfile/company-panel/CV-
// preview), search.js (updateSavedBadge/doSaveWithExtras), saved.js (loadSaved/
// _miRefreshCurrent), clustering.js (closeSegmentModal) and interview.js (the
// scorecard controls + the two desc-toggle-* actions) via app.*.
import { state, _ACTIONS, app } from "./state.js";
import { esc, getStoredJob } from "./util.js";
import api from "./api.js";

// Job sub-chat session — only ever read/written from this module.
let jobChatSessionId   = null;
let _jobChatLastAnswer = '';

// ════════════════════════════════════════════════════════════
//  Job-detail-modal "save with extras" panel (awaiting modal.js extraction)
// ════════════════════════════════════════════════════════════
function toggleExtrasPanel() {
  const panel = document.getElementById('saveExtrasPanel');
  const btn   = document.getElementById('modalExtrasBtn');
  const open  = panel.style.display === 'none';
  panel.style.display = open ? '' : 'none';
  btn.classList.toggle('active', open);
  if (!open) return;
  // Enable checkboxes only for generated content
  const compact   = _descCompact_orig || _descCompact_trans;
  const questions = _descCvQuestions || app._ivHasAnswers();
  const outreach  = state.descOutreach;
  const strength  = _strengthData;
  const salaryStats = state.modalJob?._salaryStats;
  const qualityData = state.modalJob?.quality ? {
    grade: state.modalJob.quality, score: state.modalJob.quality_score,
    verdict: state.modalJob.quality_verdict, fit: state.modalJob.quality_fit,
    flags: state.modalJob.quality_flags,
  } : null;
  const set = (id, itemId, has) => {
    const chk  = document.getElementById(id);
    const item = document.getElementById(itemId);
    chk.disabled = !has;
    item.classList.toggle('dim', !has);
    if (has) chk.checked = true;
  };
  set('extrasChkSalary',    'extrasItemSalary',    !!salaryStats);
  set('extrasChkQuality',   'extrasItemQuality',   !!qualityData);
  set('extrasChkCompact',   'extrasItemCompact',   !!compact);
  set('extrasChkStrength',  'extrasItemStrength',  !!strength);
  set('extrasChkQuestions', 'extrasItemQuestions', !!questions);
  set('extrasChkOutreach',  'extrasItemOutreach',  !!outreach);
}

async function saveWithExtras() {
  if (!state.modalJob) return;
  const extras = {};
  if (document.getElementById('extrasChkSalary').checked && state.modalJob._salaryStats)
    extras.salary = state.modalJob._salaryStats;
  if (document.getElementById('extrasChkQuality').checked && state.modalJob.quality)
    extras.quality = {
      grade: state.modalJob.quality, score: state.modalJob.quality_score,
      verdict: state.modalJob.quality_verdict, fit: state.modalJob.quality_fit,
      flags: state.modalJob.quality_flags,
    };
  if (document.getElementById('extrasChkCompact').checked)
    extras.compact    = _descCompact_orig || _descCompact_trans || null;
  if (document.getElementById('extrasChkStrength').checked)
    extras.strength   = _strengthData || null;
  if (document.getElementById('extrasChkQuestions').checked) {
    if (_descCvQuestions) extras.cv_questions = _descCvQuestions;
    if (app._ivHasAnswers())  extras.interview   = state.interview;
  }
  if (document.getElementById('extrasChkOutreach').checked)
    extras.outreach   = state.descOutreach || null;

  const status = document.getElementById('modalStatusSel').value;
  try {
    const data = await api.post('/api/saved', { job: { ...state.modalJob, candidate_name: app.getCandidateName() }, status, extras, candidate_profile: state.currentCandidateProfile || null });
    if (data.ok) {
      state.savedJobs = data.jobs;
      app.updateSavedBadge();
      const saveBtn = document.getElementById('modalSaveBtn');
      saveBtn.textContent = '✓ Saved'; saveBtn.classList.add('saved');
      const extrasBtn = document.getElementById('modalExtrasBtn');
      extrasBtn.textContent = '✓ extras'; extrasBtn.disabled = true;
      document.getElementById('saveExtrasPanel').style.display = 'none';
      const tableBtn = document.getElementById(`save-${state.modalJob.job_id}`);
      if (tableBtn) { tableBtn.textContent = '✓ Saved'; tableBtn.classList.add('saved'); }
      app._miRefreshCurrent();
    }
  } catch(e) { alert('Save failed: ' + e.message); }
}

async function updateStatus(jobId, sel) {
  sel.className = `status-select s-${sel.value}`;
  await api.raw(`/api/saved/${jobId}`, { method: 'PATCH', body: { pipeline_status: sel.value } });
}
async function updateNotes(jobId, notes) {
  await api.raw(`/api/saved/${jobId}`, { method: 'PATCH', body: { notes } });
}
async function removeJob(jobId) {
  await api.raw(`/api/saved/${jobId}`, { method: 'DELETE' });
  document.getElementById(`srow-${jobId}`)?.remove();
  state.savedJobs = state.savedJobs.filter(j => j.job_id !== jobId);
  app.updateSavedBadge();
  app.loadSaved();
}


// ════════════════════════════════════════════════════════════
//  Job detail modal
// ════════════════════════════════════════════════════════════

function openJobModal(storeId) {
  const job = getStoredJob(storeId);
  if (!job) return;
  state.modalJob = job;

  const score = job.score != null ? (job.score <= 1 ? Math.round(job.score * 100) : Math.round(job.score)) : null;
  const g     = job.grade || (score == null ? 'C' : score >= 70 ? 'A' : score >= 50 ? 'B' : 'C');
  const gc    = g === 'A' ? 'grade-a' : g === 'B' ? 'grade-b' : 'grade-c';

  document.getElementById('modalGrade').textContent  = g;
  document.getElementById('modalGrade').className    = `grade ${gc}`;
  document.getElementById('modalScorePct').textContent = job.score_pct || (score != null ? score + '%' : '');
  document.getElementById('modalGradeLabel').textContent =
    g === 'A' ? '— Strong match' : g === 'B' ? '— Good match' : '— Weak match';
  document.getElementById('modalTitle').textContent   = job.title   || '—';
  document.getElementById('modalCompany').textContent = job.company || '';

  // Meta grid — only rows with real values
  const salaryDisplay = (() => {
    if (!job.salary) return null;
    const n = parseFloat(String(job.salary).replace(/[^\d.]/g, ''));
    const type = job.salary_type === 'monthly' ? '/mo' : job.salary_type === 'hourly' ? '/hr' : '';
    const wt   = job.work_time ? ` · ${job.work_time}` : '';
    return n > 100 ? `€${n.toLocaleString('de-AT')}${type}${wt}` : job.salary;
  })();

  const metaItems = [
    { key: 'Location',    val: [job.city, job.state].filter(Boolean).join(', ') },
    { key: 'Salary',      val: salaryDisplay, cls: 'salary' },
    { key: 'Portal',      val: job.portal },
    { key: 'Category',    val: job.occ_group },
    { key: 'Employment',  val: job.employment_relationship },
    { key: 'Start',       val: job.start_timeline },
    { key: 'Education',   val: job.education },
    { key: 'Deadline',    val: job.application_deadline ? String(job.application_deadline).substring(0,10) : null },
    { key: 'Posted',      val: job.posted ? String(job.posted).substring(0,10) : null },
    { key: 'Job ID',      val: job.job_id && !String(job.job_id).startsWith('chat-') ? job.job_id : null },
  ].filter(m => m.val && m.val !== 'null' && m.val !== 'undefined');

  document.getElementById('modalMetaGrid').innerHTML = metaItems.map(m =>
    `<div class="modal-meta-item">
       <span class="modal-meta-key">${m.key}</span>
       <span class="modal-meta-val${m.cls ? ' ' + m.cls : ''}">${esc(m.val)}</span>
     </div>`
  ).join('');

  // Original salary text (if present and different from parsed)
  const origSalEl = document.getElementById('modalOrigSalary');
  if (job.original_salary) {
    origSalEl.textContent = job.original_salary;
    origSalEl.style.display = '';
  } else {
    origSalEl.style.display = 'none';
  }

  // Contacts
  const contactsEl = document.getElementById('modalContacts');
  if (job.contacts) {
    document.getElementById('modalContactsText').textContent = job.contacts;
    contactsEl.style.display = '';
  } else {
    contactsEl.style.display = 'none';
  }

  // Skills
  const skillsWrap = document.getElementById('modalSkillsWrap');
  const rawSkills  = (job.skills_en || job.skills || '').replace(/^[\s,]+/, '');
  const skillList  = rawSkills.split(',').map(s => s.trim()).filter(s => s && s !== '-' && s.length > 1);
  if (skillList.length) {
    document.getElementById('modalSkills').innerHTML = skillList.map(s =>
      `<span class="skill-chip">${esc(s)}</span>`).join('');
    skillsWrap.style.display = '';
  } else {
    skillsWrap.style.display = 'none';
  }

  // Description
  const desc = job.description || job.description_snippet || '';
  const descWrap = document.getElementById('modalDescWrap');
  if (desc) {
    document.getElementById('modalDesc').textContent = desc;
    descWrap.style.display = '';
    _descReset(desc);
    // Nothing shown by default — user clicks Original / Compact / Interview.
    app._interviewReset();
    app._interviewRestore(job.job_id);
  } else {
    descWrap.style.display = 'none';
    _descReset('');
    app._interviewReset();
  }

  // Match reason
  const reasonEl = document.getElementById('modalReason');
  if (job.match_reason && job.match_reason !== desc) {
    reasonEl.textContent = 'Match reason: ' + job.match_reason;
    reasonEl.style.display = '';
  } else {
    reasonEl.style.display = 'none';
  }

  // Analysis panels — lazy, reset state
  _analysisBatchJobs = state.lastResults;
  _analysisLoaded = { salary: false, quality: false, strength: false };
  _analysisOpen   = { salary: false, quality: false, strength: false };
  _strengthData   = null;
  document.getElementById('saveExtrasPanel').style.display = 'none';
  document.getElementById('modalExtrasBtn').classList.remove('active');
  ['salary','quality','strength'].forEach(t => {
    document.getElementById('analysisPanel' + t[0].toUpperCase() + t.slice(1)).style.display = 'none';
    const btn = document.getElementById('analysisBtn' + t[0].toUpperCase() + t.slice(1));
    btn.classList.remove('active');
    btn.disabled = false;
  });

  // Job sub-chat — new session per job
  jobChatSessionId   = 'job-' + (job.job_id || Date.now());
  _jobChatLastAnswer = '';
  document.getElementById('jobChatThread').innerHTML = '';
  document.getElementById('jobChatInput').value = '';
  document.getElementById('jobChatAddBtn').style.display = 'none';

  // Link
  const linkBtn = document.getElementById('modalLinkBtn');
  if (job.url) {
    linkBtn.href = job.url;
    linkBtn.style.display = 'inline-flex';
  } else {
    linkBtn.style.display = 'none';
  }

  // Save button state
  const saveBtn = document.getElementById('modalSaveBtn');
  const alreadySaved = state.savedJobs.some(j => String(j.job_id) === String(job.job_id));
  saveBtn.textContent = alreadySaved ? '✓ Saved' : '+ Save to pipeline';
  saveBtn.classList.toggle('saved', alreadySaved);

  document.getElementById('jobModal').classList.remove('hidden');
  _renderJobModalLock();   // reflect the remembered lock state on the button
}

async function loadSalaryAnalysis(job, batchJobs) {
  try {
    const res  = await fetch(`/api/salary_stats?occ_group=${encodeURIComponent(job.occ_group)}`);
    const data = await res.json();

    const parseSal = v => { const n = parseFloat(String(v || '').replace(/[^0-9.]/g, '')); return n > 100 ? n : null; };
    const jobSalary = parseSal(job.salary);

    // Batch overlay — jobs from the same search/chat that have a salary
    const batchPoints = (batchJobs || [])
      .map(j => ({ sal: parseSal(j.salary), title: j.title || '—', grade: j.grade || 'C', job_id: j.job_id }))
      .filter(p => p.sal && String(p.job_id) !== String(job.job_id));

    const gradeColor = g => g === 'A' ? '#1a7a2e' : g === 'B' ? '#e8a800' : '#bbb';

    if (!data.ok || !data.count) {
      // No DB data — show batch-only chart if we have batch points
      if (batchPoints.length) {
        const rugY = 0;
        Plotly.react('modalAnalysisChart',
          [{ type:'scatter', mode:'markers',
             x: batchPoints.map(p => p.sal), y: batchPoints.map(() => rugY),
             text: batchPoints.map(p => p.title),
             marker:{ size:14, symbol:'line-ns', color: batchPoints.map(p => gradeColor(p.grade)),
                      line:{ width:2.5, color: batchPoints.map(p => gradeColor(p.grade)) } },
             hovertemplate:'<b>%{text}</b><br>€%{x}<extra></extra>' },
           ...(jobSalary ? [{ type:'scatter', mode:'markers',
             x:[jobSalary], y:[rugY], name:'This job',
             marker:{ size:16, symbol:'diamond', color:'#1a3864', line:{width:2,color:'#fff'} },
             hovertemplate:'<b>This job</b><br>€%{x}<extra></extra>' }] : [])],
          { margin:{t:16,r:14,b:40,l:14}, paper_bgcolor:'rgba(0,0,0,0)',
            plot_bgcolor:'#fafaf6', showlegend:false,
            xaxis:{ title:'EUR / month', showgrid:true, gridcolor:'#e8e7e0', zeroline:false },
            yaxis:{ visible:false, range:[-0.5, 1] } },
          { responsive:true, displayModeBar:false });
      } else {
        document.getElementById('modalAnalysisChart').innerHTML =
          '<div style="color:#bbb;font-size:12px;padding:20px 0;text-align:center">No salary data available for this category yet.</div>';
      }
      return;
    }

    // Reference lines
    const shapes = [
      { type:'line', xref:'x', yref:'paper', x0:data.mean,   x1:data.mean,   y0:0, y1:1,
        line:{ color:'#e8a800', width:2, dash:'dot' } },
      { type:'line', xref:'x', yref:'paper', x0:data.median, x1:data.median, y0:0, y1:1,
        line:{ color:'#a78bfa', width:2, dash:'dot' } },
    ];
    const annotations = [
      { xref:'x', yref:'paper', x:data.mean,   y:1.07, text:`Mean €${data.mean.toLocaleString()}`,
        showarrow:false, font:{ size:10, color:'#e8a800' }, xanchor:'center' },
      { xref:'x', yref:'paper', x:data.median, y:1.07, text:`Median €${data.median.toLocaleString()}`,
        showarrow:false, font:{ size:10, color:'#a78bfa' }, xanchor:'center' },
    ];
    if (jobSalary) {
      shapes.push({ type:'line', xref:'x', yref:'paper', x0:jobSalary, x1:jobSalary, y0:0, y1:1,
        line:{ color:'#1a3864', width:2.5 } });
      annotations.push({ xref:'x', yref:'paper', x:jobSalary, y:0.75,
        text:`This job<br>€${jobSalary.toLocaleString()}`,
        showarrow:true, arrowhead:2, arrowsize:0.8, arrowcolor:'#1a3864',
        font:{ size:10, color:'#fff' }, bgcolor:'#1a3864', borderpad:4,
        ax:0, ay:-38, xanchor:'center' });
    }

    // Three traces: DB histogram + batch rug (below x-axis) + this job diamond
    // Rug marks sit at y = RUG_Y (negative) so they don't overlap the histogram bars
    const RUG_Y = -1.5;
    const traces = [
      { type:'histogram', x:data.salaries, name:'Market',
        marker:{ color:'#dde8f4', line:{ color:'#99b8f0', width:0.5 } },
        opacity:0.75, hovertemplate:'%{y} jobs near €%{x}<extra></extra>' },
    ];
    if (batchPoints.length) {
      traces.push({
        type:'scatter', mode:'markers', name:'This search',
        x: batchPoints.map(p => p.sal),
        y: batchPoints.map(() => RUG_Y),
        text: batchPoints.map(p => `${p.title} (${p.grade})`),
        marker:{ size:14, symbol:'line-ns',
                 color: batchPoints.map(p => gradeColor(p.grade)),
                 line:{ width:2.5, color: batchPoints.map(p => gradeColor(p.grade)) } },
        hovertemplate:'<b>%{text}</b><br>€%{x}<extra></extra>',
      });
    }
    if (jobSalary) {
      traces.push({
        type:'scatter', mode:'markers', name:'This job',
        x:[jobSalary], y:[RUG_Y],
        marker:{ size:16, symbol:'diamond', color:'#1a3864', line:{ width:2, color:'#fff' } },
        hovertemplate:'<b>This job</b><br>€%{x}<extra></extra>',
      });
    }

    Plotly.react('modalAnalysisChart', traces, {
      margin:{ t:28, r:14, b:44, l:44 },
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'#fafaf6',
      font:{ family:"'Segoe UI',Arial,sans-serif", size:11, color:'#555' },
      xaxis:{ title:'EUR / month', showgrid:true, gridcolor:'#e8e7e0', zeroline:false },
      yaxis:{ title:'Job count', showgrid:true, gridcolor:'#e8e7e0',
              zeroline:true, zerolinecolor:'#c8c7c0', zerolinewidth:1.5,
              range:[RUG_Y * 2.5, null] },
      shapes, annotations, showlegend: batchPoints.length > 0,
      legend:{ orientation:'h', y:-0.32, font:{ size:10 } },
      bargap:0.05,
    }, { responsive:true, displayModeBar:false });

    // Stats row
    const pctBelow = jobSalary ? Math.round((data.salaries.filter(s => s < jobSalary).length / data.count) * 100) : null;
    const diffMean = jobSalary ? Math.round(jobSalary - data.mean) : null;
    // Store salary stats on the modal job so they can be saved as extras
    if (state.modalJob) {
      state.modalJob._salaryStats = {
        occ_group: job.occ_group || '',
        count: data.count,
        mean: Math.round(data.mean),
        median: Math.round(data.median),
        job_salary: jobSalary,
        pct_below: pctBelow,
        diff_mean: diffMean,
      };
    }
    document.getElementById('modalAnalysisStats').innerHTML = [
      `<div class="analysis-stat"><span class="analysis-stat-key">Market sample</span><span class="analysis-stat-val">${data.count} jobs</span></div>`,
      `<div class="analysis-stat"><span class="analysis-stat-key">Mean</span><span class="analysis-stat-val">€${data.mean.toLocaleString()}</span></div>`,
      `<div class="analysis-stat"><span class="analysis-stat-key">Median</span><span class="analysis-stat-val">€${data.median.toLocaleString()}</span></div>`,
      batchPoints.length ? `<div class="analysis-stat"><span class="analysis-stat-key">In this search</span><span class="analysis-stat-val">${batchPoints.length} with salary</span></div>` : '',
      jobSalary ? `<div class="analysis-stat"><span class="analysis-stat-key">This job</span><span class="analysis-stat-val ${diffMean >= 0 ? 'above' : 'below'}">€${jobSalary.toLocaleString()} · ${diffMean >= 0 ? '+' : ''}€${diffMean.toLocaleString()} vs mean · top ${100 - pctBelow}%</span></div>` : '',
    ].join('');

  } catch(e) {
    document.getElementById('modalAnalysisChart').innerHTML =
      `<div style="color:#e04040;font-size:12px;padding:12px 0">Could not load salary data: ${esc(e.message)}</div>`;
  }
}

// ════════════════════════════════════════════════════════════
//  Quality assessment — modal
// ════════════════════════════════════════════════════════════

async function loadQualityAssessment(job) {
  const contentEl = document.getElementById('modalQualityContent');
  try {
    const payload = {
      jobs: [job],
      occ_group: job.occ_group || '',
      state: job.state || null,
    };
    const data = await api.post('/api/quality', payload);
    if (!data.jobs?.length) throw new Error(data.error || 'No result');

    const enriched    = data.jobs[0];
    const groupStats  = data.group_stats || {};

    // Persist quality onto the stored job so re-opening is instant
    const storedJob = state.modalJob;
    if (storedJob) Object.assign(storedJob, {
      quality: enriched.quality, quality_score: enriched.quality_score,
      quality_verdict: enriched.quality_verdict, quality_fit: enriched.quality_fit,
      quality_flags: enriched.quality_flags,
    });

    contentEl.innerHTML = renderQualitySection(enriched, groupStats);
  } catch(e) {
    contentEl.innerHTML = `<div class="quality-loading" style="color:#e44">Could not load quality assessment.</div>`;
  }
}

function renderQualitySection(job, groupStats) {
  const q     = job.quality || 'mid';
  const score = job.quality_score != null ? Math.round(job.quality_score * 100) : null;
  const fit   = job.quality_fit   || 'unknown';
  const flags = job.quality_flags || [];
  const verdict = job.quality_verdict || '';

  const badgeCls = {high:'quality-high', mid:'quality-mid', low:'quality-low'}[q] || 'quality-mid';
  const badgeTxt = {high:'🟢 High quality', mid:'🟡 Mid quality', low:'🔴 Low quality'}[q] || q;
  const fitLabel = {fair:'Fair compensation', overpaying:'Above-market pay',
                    underpaying:'Below-market pay', unknown:'Salary unknown'}[fit] || fit;

  // Salary position bar
  let salBarHTML = '';
  const sal = parseFloat(job.salary || 0);
  if (sal > 0 && groupStats.count > 0) {
    const pos = _salaryBarPos(sal, groupStats);
    const fmtK = v => v >= 1000 ? `€${(v/1000).toFixed(1)}k` : `€${Math.round(v)}`;
    salBarHTML = `
      <div class="quality-sal-wrap">
        <div class="quality-sal-label">Salary position in <b>${esc(groupStats.occ_group||'')}</b>
          (n=${groupStats.count} jobs)</div>
        <div class="quality-sal-track">
          <div class="quality-sal-dot" style="left:${pos}%"></div>
          <div class="quality-sal-tick" style="left:25%">${fmtK(groupStats.p25)}<br>p25</div>
          <div class="quality-sal-tick" style="left:50%">${fmtK(groupStats.median)}<br>med</div>
          <div class="quality-sal-tick" style="left:75%">${fmtK(groupStats.p75)}<br>p75</div>
        </div>
      </div>`;
  }

  // Flags
  const flagsHTML = flags.length ? `<div class="quality-flags">${
    flags.map(f => {
      const neg = /no |not |below|expired|vague|missing|low|poor|underpay/i.test(f);
      return `<span class="qflag ${neg ? 'qflag-neg' : 'qflag-pos'}">${esc(f)}</span>`;
    }).join('')
  }</div>` : '';

  return `
    <div>
      <div class="quality-header">
        <span class="quality-badge ${badgeCls}">${badgeTxt}</span>
        <span class="quality-fit">${fitLabel}</span>
        ${score != null ? `<span class="quality-score-val">${score}/100</span>` : ''}
      </div>
      ${verdict ? `<div class="quality-verdict">"${esc(verdict)}"</div>` : ''}
      ${salBarHTML}
      ${flagsHTML}
    </div>`;
}

function _salaryBarPos(salary, stats) {
  // Map salary to 0-100 position using piecewise linear interpolation
  const { min=0, p25, median: med, p75, max=p75*1.5 } = stats;
  const clamp = (v,lo,hi) => Math.max(lo, Math.min(hi, v));
  if (salary <= min)  return 0;
  if (salary >= max)  return 100;
  if (salary <= p25)  return clamp((salary - min)  / (p25 - min)  * 25,       0, 25);
  if (salary <= med)  return clamp(25 + (salary - p25) / (med - p25) * 25,   25, 50);
  if (salary <= p75)  return clamp(50 + (salary - med) / (p75 - med) * 25,   50, 75);
  return clamp(75 + (salary - p75) / (max  - p75) * 25,  75, 100);
}

function closeJobModal() {
  document.getElementById('jobModal').classList.add('hidden');
  state.modalJob = null;
  if (jobChatSessionId) {
    api.raw('/api/job_chat/reset', { method: 'POST', body: { session_id: jobChatSessionId } });
    jobChatSessionId   = null;
    _jobChatLastAnswer = '';
  }
  document.getElementById('jobChatThread').innerHTML = '';
  document.getElementById('jobChatAddBtn').style.display = 'none';
}

// ════════════════════════════════════════════════════════════
//  Job sub-chat
// ════════════════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.activeElement === document.getElementById('jobChatInput'))
    sendJobChat();
});

function setJobChatLang(lang) {
  state.jobChatLang = lang;
  document.querySelectorAll('.jc-lang-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.lang === lang));
}
_ACTIONS['job-chat-lang'] = (el) => setJobChatLang(el.dataset.lang);

async function sendJobChat() {
  if (!jobChatSessionId || !state.modalJob) return;
  const input = document.getElementById('jobChatInput');
  const text  = input.value.trim();
  if (!text) return;

  appendJobChatMsg(text, 'user');
  input.value = '';

  const btn = document.getElementById('jobChatSendBtn');
  btn.disabled = true;

  // Typing indicator
  const typing = document.createElement('div');
  typing.className = 'jcmsg ai';
  typing.id = 'jcTyping';
  typing.textContent = '…';
  typing.style.color = '#bbb';
  document.getElementById('jobChatThread').appendChild(typing);
  scrollJobChat();

  try {
    const data = await api.post('/api/job_chat', {
      session_id:     jobChatSessionId,
      message:        text,
      lang:           state.jobChatLang,
      candidate_text: state.lastMatchText || app.buildCandidateText(),   // the candidate you searched with (fallback: live input)
      job_context: {
        job_id:              state.modalJob.job_id,
        title:               state.modalJob.title,
        company:             state.modalJob.company,
        city:                state.modalJob.city,
        state:               state.modalJob.state,
        salary:              state.modalJob.salary,
        occ_group:           state.modalJob.occ_group,
        skills_en:           state.modalJob.skills_en,
        skills:              state.modalJob.skills,
        description:         state.modalJob.description,
        description_snippet: state.modalJob.description_snippet,
      },
    });
    document.getElementById('jcTyping')?.remove();
    const answer = data.ok ? (data.text || '—') : `Error: ${data.error}`;
    appendJobChatMsg(answer, 'ai');
    if (data.ok) {
      _jobChatLastAnswer = answer;
      document.getElementById('jobChatAddBtn').style.display = '';
    }
  } catch(e) {
    document.getElementById('jcTyping')?.remove();
    appendJobChatMsg(`Network error: ${e.message}`, 'ai');
  } finally {
    btn.disabled = false;
    input.focus();
  }
}

function appendJobChatMsg(text, role) {
  const el = document.createElement('div');
  el.className = `jcmsg ${role}`;
  el.textContent = text;
  document.getElementById('jobChatThread').appendChild(el);
  scrollJobChat();
}

function scrollJobChat() {
  const t = document.getElementById('jobChatThread');
  t.scrollTop = t.scrollHeight;
}

async function addLastAnswerToNotes() {
  if (!_jobChatLastAnswer || !state.modalJob) return;
  const jobId = state.modalJob.job_id;
  const existing = state.savedJobs.find(j => String(j.job_id) === String(jobId));
  const newNote = existing
    ? (existing.notes ? existing.notes + '\n' + _jobChatLastAnswer : _jobChatLastAnswer)
    : _jobChatLastAnswer;

  // Update in-memory and on server if already saved
  if (existing) {
    existing.notes = newNote;
    await api.raw(`/api/saved/${jobId}`, { method: 'PATCH', body: { notes: newNote } });
    const inp = document.getElementById(`srow-${jobId}`)?.querySelector('.notes-inp');
    if (inp) inp.value = newNote;
  }

  // Flash the button to confirm
  const btn = document.getElementById('jobChatAddBtn');
  btn.textContent = '✓ Added';
  btn.style.background = '#e6f4ea';
  setTimeout(() => {
    btn.textContent = '↓ Add last answer to notes';
    btn.style.background = '';
  }, 1800);
}

// Window lock — when on, an accidental click outside (or Esc) won't close the job
// modal; only the × does. The choice is remembered so it stays locked across opens.
let _jobModalLocked = false;
try { _jobModalLocked = localStorage.getItem('jobModalLocked') === '1'; } catch (_) {}

function _renderJobModalLock() {
  const b = document.getElementById('jobModalLockBtn');
  if (!b) return;
  b.textContent = _jobModalLocked ? '🔒' : '🔓';
  b.style.opacity = _jobModalLocked ? '1' : '.7';
  b.title = _jobModalLocked
    ? "Window locked — clicks outside (and Esc) won't close it. Click to unlock."
    : "Lock the window so an accidental click outside won't close it.";
}

function toggleJobModalLock() {
  _jobModalLocked = !_jobModalLocked;
  try { localStorage.setItem('jobModalLocked', _jobModalLocked ? '1' : '0'); } catch (_) {}
  _renderJobModalLock();
}

function _flashJobModalLock() {
  const b = document.getElementById('jobModalLockBtn');
  if (!b) return;
  b.style.transform = 'scale(1.4)';
  setTimeout(() => { b.style.transform = 'scale(1)'; }, 150);
}

function closeModalOnBackdrop(e) {
  if (e.target !== document.getElementById('jobModal')) return;
  if (_jobModalLocked) { _flashJobModalLock(); return; }   // locked — ignore stray clicks
  closeJobModal();
}

// Action registry for the job-detail modal markup (segment modal, job modal
// header/lang/lock/close, description toolbar, interview scorecard controls,
// analysis panels, job sub-chat, save/extras footer, CV preview, company panel).
// Backdrop closers re-check e.target === el themselves, since delegation routes
// clicks on any descendant up to the overlay's data-action.
Object.assign(_ACTIONS, {
  // segment + job modal shell
  'seg-modal-backdrop':    (el, e) => { if (e.target === el) app.closeSegmentModal(); },
  'close-segment-modal':   ()      => app.closeSegmentModal(),
  'job-modal-backdrop':    (el, e) => closeModalOnBackdrop(e),
  'set-modal-lang':        (el)    => setModalLang(el.dataset.lang),
  'toggle-job-modal-lock': ()      => toggleJobModalLock(),
  'close-job-modal':       ()      => closeJobModal(),
  // description toolbar
  'desc-toggle-translate': ()      => descToggleTranslate(),
  'desc-show-original':    ()      => descShowOriginal(),
  'desc-toggle-compact':   ()      => descToggleCompact(),
  'desc-toggle-cv-questions': ()   => app.descToggleCvQuestions(),
  'desc-toggle-outreach':  ()      => app.descToggleOutreach(),
  // interview scorecard controls
  'set-iv-perspective':    (el)    => app.setIvPerspective(el.dataset.persp),
  'toggle-freeze-interview': ()    => app.toggleFreezeInterview(),
  'regenerate-interview':  ()      => app.regenerateInterview(),
  'add-interview-question': ()     => app.addInterviewQuestion(),
  'interview-import-open': ()      => app.toggleInterviewImport(true),
  'interview-import-cancel': ()    => app.toggleInterviewImport(false),
  'analyze-all-interview': ()      => app.analyzeAllInterview(),
  'toggle-interview-context': ()   => app.toggleInterviewContext(),
  'iv-load-import-file':   (el)    => app._ivLoadImportFile(el),
  'import-interview-questions': () => app.importInterviewQuestions(),
  // analysis panels + job sub-chat
  'toggle-analysis-panel': (el)    => toggleAnalysisPanel(el.dataset.panel),
  'send-job-chat':         ()      => sendJobChat(),
  'add-last-answer-to-notes': ()   => addLastAnswerToNotes(),
  // save / extras footer
  'save-with-extras':      ()      => saveWithExtras(),
  'save-from-modal':       ()      => saveFromModal(),
  'toggle-extras-panel':   ()      => toggleExtrasPanel(),
  'do-save-with-extras':   ()      => app.doSaveWithExtras(),
  // CV preview drawer
  'cv-preview-backdrop':   (el, e) => { if (e.target === el || e.target.classList.contains('cv-preview-backdrop')) app.closeCvPreview(); },
  'cv-preview-remove':     ()      => { app.clearCandidateProfile(); app.closeCvPreview(); },
  'close-cv-preview':      ()      => app.closeCvPreview(),
  // company info modal
  'co-modal-backdrop':     (el, e) => { if (e.target === el) app.closeCompanyPanel(); },
  'close-company-panel':   ()      => app.closeCompanyPanel(),
});

async function saveFromModal() {
  const saveBtn = document.getElementById('modalSaveBtn');
  if (!state.modalJob || saveBtn.classList.contains('saved')) return;
  const status = document.getElementById('modalStatusSel').value;
  try {
    const data = await api.post('/api/saved', { job: { ...state.modalJob, candidate_name: app.getCandidateName() }, status, candidate_profile: state.currentCandidateProfile || null });
    if (data.ok) {
      saveBtn.textContent = '✓ Saved';
      saveBtn.classList.add('saved');
      state.savedJobs = data.jobs;
      app.updateSavedBadge();
      // Sync the results-table save button if present
      const tableBtn = document.getElementById(`save-${state.modalJob.job_id}`);
      if (tableBtn) { tableBtn.textContent = '✓ Saved'; tableBtn.classList.add('saved'); }
    }
  } catch(e) { alert('Save failed: ' + e.message); }
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    // Close panels in order: innermost first
    if (!document.getElementById('coModal').classList.contains('hidden')) {
      app.closeCompanyPanel(); return;
    }
    if (document.getElementById('cvPreviewOverlay').classList.contains('cvpo-open')) {
      app.closeCvPreview(); return;
    }
    // Respect the window lock — don't let Esc close a locked, open job modal.
    const jm = document.getElementById('jobModal');
    if (_jobModalLocked && jm && !jm.classList.contains('hidden')) { _flashJobModalLock(); return; }
    closeJobModal();
  }
});



// ════════════════════════════════════════════════════════════
//  Session id (candidate-assistant chat)
// ════════════════════════════════════════════════════════════

// (Radar / Analytics tab — moved to static/js/radar.js in 2.6c.)

// ════════════════════════════════════════════════════════════
//  Analysis panels — salary / quality / candidate strength
// ════════════════════════════════════════════════════════════

let _analysisBatchJobs = [];
let _analysisLoaded = { salary: false, quality: false, strength: false };
let _analysisOpen   = { salary: false, quality: false, strength: false };
let _strengthData   = null;

async function toggleAnalysisPanel(type) {
  const panelId = 'analysisPanel' + type[0].toUpperCase() + type.slice(1);
  const btnId   = 'analysisBtn'  + type[0].toUpperCase() + type.slice(1);
  const panel   = document.getElementById(panelId);
  const btn     = document.getElementById(btnId);

  if (_analysisOpen[type]) {
    _analysisOpen[type] = false;
    panel.style.display = 'none';
    btn.classList.remove('active');
    return;
  }

  _analysisOpen[type] = true;
  panel.style.display = '';
  btn.classList.add('active');

  if (_analysisLoaded[type]) return;
  _analysisLoaded[type] = true;

  if (type === 'salary') {
    document.getElementById('modalAnalysisGroup').textContent = state.modalJob.occ_group || '';
    document.getElementById('modalAnalysisChart').innerHTML =
      '<div style="color:#bbb;font-size:12px;padding:30px 0;text-align:center">Loading salary data…</div>';
    document.getElementById('modalAnalysisStats').innerHTML = '';
    if (state.modalJob.occ_group) {
      await loadSalaryAnalysis(state.modalJob, _analysisBatchJobs);
    } else {
      document.getElementById('modalAnalysisChart').innerHTML =
        '<div style="color:#bbb;font-size:12px;padding:30px 0;text-align:center">No occupational group — salary data unavailable.</div>';
    }

  } else if (type === 'quality') {
    document.getElementById('modalQualityContent').innerHTML =
      '<div class="quality-loading">Analysing responsibilities and compensation…</div>';
    await loadQualityAssessment(state.modalJob);

  } else if (type === 'strength') {
    if (!state.lastParsedText) {
      document.getElementById('modalStrengthChart').style.display = 'none';
      document.getElementById('modalStrengthDetails').innerHTML =
        '<div class="quality-loading" style="padding:16px 0">No CV loaded — upload or paste a CV to run candidate strength analysis.</div>';
      _analysisLoaded[type] = false;
      return;
    }
    document.getElementById('modalStrengthDetails').innerHTML =
      '<div class="quality-loading">Analysing candidate fit…</div>';
    await loadStrengthAnalysis(state.modalJob, state.lastParsedText);
  }
}

async function loadStrengthAnalysis(job, cvText) {
  const chartEl   = document.getElementById('modalStrengthChart');
  const detailsEl = document.getElementById('modalStrengthDetails');
  chartEl.style.display = '';
  try {
    const data = await api.post('/api/candidate_strength', {
      job: {
        title:       job.title,
        company:     job.company,
        skills:      job.skills_en || job.skills,
        description: (job.description || job.description_snippet || '').slice(0, 2000),
      },
      cv_text: cvText.slice(0, 2000),
      lang: state.modalLang,
    });

    const { axes, scores, reasons, overall } = data;
    _strengthData = { axes, scores, reasons, overall };

    // Radar chart
    Plotly.newPlot(chartEl, [{
      type: 'scatterpolar',
      r: [...scores, scores[0]],
      theta: [...axes, axes[0]],
      fill: 'toself',
      fillcolor: 'rgba(26,56,100,0.10)',
      line: { color: '#1a3864', width: 2 },
      hovertemplate: '<b>%{theta}</b><br>%{r}/10<extra></extra>',
    }], {
      polar: {
        radialaxis: { visible: true, range: [0, 10], tickvals: [2,4,6,8,10],
          tickfont: { size: 8, color: '#bbb' }, gridcolor: '#e8e7e0', linecolor: '#e8e7e0' },
        angularaxis: { tickfont: { size: 10, color: '#555' } },
        bgcolor: 'rgba(0,0,0,0)',
      },
      showlegend: false,
      margin: { t: 28, r: 48, b: 28, l: 48 },
      paper_bgcolor: 'rgba(0,0,0,0)',
    }, { responsive: true, displayModeBar: false });

    // Detail rows
    const rows = axes.map((ax, i) =>
      `<div class="strength-row">
         <span class="strength-axis">${esc(ax)}</span>
         <span class="strength-score">${scores[i]}/10</span>
         <span class="strength-reason">${esc(reasons[i] || '')}</span>
       </div>`
    ).join('');
    detailsEl.innerHTML =
      `<div class="strength-details">${rows}</div>` +
      (overall ? `<div class="strength-overall">${esc(overall)}</div>` : '');

  } catch(e) {
    chartEl.style.display = 'none';
    detailsEl.innerHTML = '<div class="quality-loading" style="color:#e44">Could not load strength analysis.</div>';
  }
}

// ════════════════════════════════════════════════════════════
//  Description — translate / compact
// ════════════════════════════════════════════════════════════

let _descTranslated = null;
let _descCompact_orig = null;
let _descCompact_trans = null;
let _descIsTranslated = false;
let _descBodyView = 'none';   // 'none' | 'original' | 'compact' — what the description body shows
let _descCvQuestions = null;

function _descReset(text) {
  state.descOriginal = text;
  _descTranslated = null;
  _descCompact_orig = null;
  _descCompact_trans = null;
  _descIsTranslated = false;
  _descBodyView = 'none';
  _descCvQuestions = null;
  state.descCvQuestionsShown = false;
  state.descOutreach = null;
  state.descOutreachShown = false;
  state.modalLang = 'de';
  const tb = document.getElementById('descTranslateBtn');
  const orb = document.getElementById('descOriginalBtn');
  const cb = document.getElementById('descCompactBtn');
  const qb = document.getElementById('descCvQuestionsBtn');
  const ob = document.getElementById('descOutreachBtn');
  const de = document.getElementById('modalLangDE');
  const en = document.getElementById('modalLangEN');
  if (tb) { tb.textContent = 'Translate';    tb.classList.remove('active', 'applied'); tb.disabled = false; }
  if (orb){ orb.textContent = 'Original';    orb.classList.remove('active'); orb.disabled = false; }
  if (cb) { cb.textContent = 'Compact';      cb.classList.remove('active'); cb.disabled = false; }
  if (qb) { qb.textContent = 'Interview'; qb.classList.remove('active'); qb.disabled = false; }
  if (ob) { ob.textContent = 'Outreach';     ob.classList.remove('active'); ob.disabled = false; }
  if (de) { de.classList.add('active'); }
  if (en) { en.classList.remove('active'); }
  const cw = document.getElementById('modalDescCompactWrap');
  const qw = document.getElementById('modalDescCvQuestionsWrap');
  const ow = document.getElementById('modalDescOutreachWrap');
  const md = document.getElementById('modalDesc');
  if (cw) cw.style.display = 'none';
  if (qw) qw.style.display = 'none';
  if (ow) ow.style.display = 'none';
  if (md) md.style.display = 'none';
}

async function descToggleTranslate() {
  await setModalLang(state.modalLang === 'en' ? 'de' : 'en');
}

async function setModalLang(lang) {
  if (lang === state.modalLang) return;
  state.modalLang = lang;

  // Update flags
  document.getElementById('modalLangDE').classList.toggle('active', lang === 'de');
  document.getElementById('modalLangEN').classList.toggle('active', lang === 'en');

  // Update Translate button appearance
  const tb = document.getElementById('descTranslateBtn');
  if (tb) {
    tb.classList.remove('active', 'applied');
    if (lang === 'en') tb.classList.add('applied');
  }

  // Translate or revert description
  if (lang === 'en') {
    if (!_descTranslated) {
      if (tb) { tb.disabled = true; tb.textContent = '…'; }
      try {
        const data = await api.post('/api/desc_translate', { description: state.descOriginal });
        _descTranslated = data.text;
      } catch(e) {
        if (tb) { tb.disabled = false; tb.textContent = 'Translate'; }
        state.modalLang = 'de';
        document.getElementById('modalLangDE').classList.add('active');
        document.getElementById('modalLangEN').classList.remove('active');
        if (tb) tb.classList.remove('applied');
        return;
      }
      if (tb) { tb.disabled = false; tb.textContent = 'Translate'; }
    }
    _descIsTranslated = true;
    if (_descBodyView === 'compact') {
      await _fetchAndShowCompact(true);
    } else if (_descBodyView === 'original') {
      document.getElementById('modalDesc').textContent = _descTranslated;
    }
  } else {
    _descIsTranslated = false;
    if (_descBodyView === 'compact') {
      if (_descCompact_orig) {
        document.getElementById('modalDescCompactText').textContent = _descCompact_orig;
      } else {
        await _fetchAndShowCompact(false);
      }
    } else if (_descBodyView === 'original') {
      document.getElementById('modalDesc').textContent = state.descOriginal;
    }
  }

  // Clear language-dependent AI caches so next generation uses new lang.
  // The interview (recorded answers + scores) is candidate-driven, not a
  // re-translation of the description, so it is deliberately left untouched.
  state.descOutreach = null;

  if (state.descOutreachShown) {
    state.descOutreachShown = false;
    const ob = document.getElementById('descOutreachBtn');
    if (ob) { ob.textContent = 'Outreach'; ob.classList.remove('active'); }
    document.getElementById('modalDescOutreachWrap').style.display = 'none';
  }
}

async function _fetchAndShowCompact(useTranslated) {
  const cb = document.getElementById('descCompactBtn');
  const cached = useTranslated ? _descCompact_trans : _descCompact_orig;
  if (cached) {
    document.getElementById('modalDescCompactText').textContent = cached;
    return;
  }
  if (cb) { cb.disabled = true; }
  const source = useTranslated ? (_descTranslated || state.descOriginal) : state.descOriginal;
  try {
    const data = await api.post('/api/desc_compact', { description: source, lang: state.modalLang });
    if (useTranslated) _descCompact_trans = data.text;
    else               _descCompact_orig  = data.text;
    document.getElementById('modalDescCompactText').textContent = data.text;
  } catch(e) {}
  if (cb) { cb.disabled = false; }
}

// Highlight the Original / Compact buttons to match the active body view.
function _syncDescBodyButtons() {
  const orb = document.getElementById('descOriginalBtn');
  const cb  = document.getElementById('descCompactBtn');
  if (orb) orb.classList.toggle('active', _descBodyView === 'original');
  if (cb)  cb.classList.toggle('active', _descBodyView === 'compact');
}

// Show the full original (or translated) description. Click again to hide.
function descShowOriginal() {
  const md = document.getElementById('modalDesc');
  if (_descBodyView === 'original') {
    _descBodyView = 'none';
    md.style.display = 'none';
    _syncDescBodyButtons();
    return;
  }
  document.getElementById('modalDescCompactWrap').style.display = 'none';
  md.textContent = _descIsTranslated ? (_descTranslated || state.descOriginal) : state.descOriginal;
  md.style.display = '';
  _descBodyView = 'original';
  _syncDescBodyButtons();
}

async function descToggleCompact() {
  const btn = document.getElementById('descCompactBtn');
  if (!btn || btn.disabled) return;

  if (_descBodyView === 'compact') {
    _descBodyView = 'none';
    document.getElementById('modalDescCompactWrap').style.display = 'none';
    _syncDescBodyButtons();
    return;
  }

  btn.disabled = true;
  btn.textContent = '…';
  await _fetchAndShowCompact(_descIsTranslated);
  btn.disabled = false;
  btn.textContent = 'Compact';
  document.getElementById('modalDesc').style.display = 'none';
  document.getElementById('modalDescCompactWrap').style.display = '';
  _descBodyView = 'compact';
  _syncDescBodyButtons();
}


// Cross-module export — registered on app so search.js's row-click handler
// can open the modal without a direct import (avoids a circular reference).
Object.assign(app, { openJobModal });
