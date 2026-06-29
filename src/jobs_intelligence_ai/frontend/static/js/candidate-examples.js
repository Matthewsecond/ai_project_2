// ════════════════════════════════════════════════════════════
//  Candidate examples — bundled demo candidates + the "Examples" dropdown
// ════════════════════════════════════════════════════════════
// The one-click example candidates (Austrian + Slovak sets) and the dropdown that
// loads them into the CV zone. Split out of candidate.js (2.6f): pure example data
// plus their loaders, with no consumer other than the dropdown itself. Loads the
// chosen example by routing through the candidate module's app.* helpers
// (_activateCVMode / _setCvLoaded / _renderCandidateProfile).
import { state, _ACTIONS, app } from "./state.js";
import api from "./api.js";

// ── Example Candidate 1: Anna Bauer (text) ───────────────────
const _EXAMPLE_CANDIDATE = {
  name: 'Anna Bauer',
  text: `Logistics and Warehouse Supervisor with 8 years of experience in Vienna and Lower Austria.

Certified forklift operator (Staplerführerschein, valid until 2027). SAP Warehouse Management certified user (2020). Currently Senior Warehouse Supervisor at MegaLogistics GmbH Wien (2019–present): leading a team of 12 associates across two shifts, introduced SAP WM module reducing stock discrepancies by 23%, responsible for KPI reporting (fill rate, OTIF, pick accuracy). Previously Warehouse Coordinator at AustroPack AG, Niederösterreich (2016–2019): coordinated 2,000+ orders/day pick & pack, trained and onboarded 8 staff.

Key skills: SAP WM, forklift operation, inventory management, team leadership, lean logistics, FIFO/FEFO, MS Excel, KPI reporting.
Languages: German (native), English B2.
Salary expectation: €2,800–3,400 gross/month.
Availability: Immediately. Seeking full-time permanent role in Vienna or Niederösterreich.`,
};

const _EXAMPLE_PROFILE = {
  name: 'Anna Bauer',
  title: 'Logistics & Warehouse Supervisor',
  experience_years: '8 years',
  skills: ['Staplerführerschein','SAP WM','Team Leadership','Inventory Management','KPI Reporting','Lean Logistics','MS Excel','FIFO/FEFO'],
  location: 'Vienna / Niederösterreich',
  languages: 'German (native), English B2',
  salary_expectation: '€2,800–3,400/month',
  availability: 'Immediately',
  summary: 'Experienced logistics supervisor with 8 years in high-volume distribution, certified forklift operator with SAP WM expertise and a track record of reducing stock discrepancies.',
};

// ── Example Candidate 2: Max Weber (PDF) ─────────────────────
const _EXAMPLE_CANDIDATE_2 = {
  name: 'Max Weber',
  text: `Software Developer with 5 years of experience in backend and full-stack development, based in Vienna.

Currently Backend Developer at TechSolutions GmbH Vienna (2022–present): building REST APIs in Python/FastAPI, maintaining PostgreSQL databases, deploying services via Docker and CI/CD pipelines. Previously Junior Developer at WebFactory GmbH (2020–2022): developed React frontends and Node.js services, contributed to agile sprint planning and code reviews. IT Intern at Startup Hub Vienna (2019–2020): built internal tooling with Python and automated reporting workflows.

Education: FH Technikum Wien – BSc Computer Science (2019).
Key skills: Python, FastAPI, JavaScript/TypeScript, React, Node.js, PostgreSQL, Docker, Git, REST APIs, Linux, CI/CD.
Languages: German (native), English C1.
Salary expectation: €3,500–4,500 gross/month.
Availability: 3 months notice. Seeking full-time permanent role in Vienna.`,
};

const _EXAMPLE_PROFILE_2 = {
  name: 'Max Weber',
  title: 'Backend & Full-Stack Developer',
  experience_years: '5 years',
  skills: ['Python','FastAPI','JavaScript/TypeScript','React','Node.js','PostgreSQL','Docker','Git','REST APIs','Linux','CI/CD'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,500–4,500/month',
  availability: '3 months notice',
  education: 'MSc Computer Science, TU Wien',
  summary: 'Full-stack developer with 5 years experience in Python backends and React frontends, comfortable with Docker deployments and agile teams.',
};

// ── Example Candidate 3: Thomas Gruber (finance director, text) ──
const _EXAMPLE_CANDIDATE_3 = {
  name: 'Thomas Gruber',
  text: `Director Group Finance with 15 years of experience in corporate finance, IFRS reporting and investor relations, based in Vorarlberg / Vienna.

Currently Head of Group Finance at Dornbirn Medtech AG (2019–present): responsible for consolidated IFRS financial statements, management reporting to the executive board and supervisory board, investor relations and earnings calls preparation, coordination of annual audit (Big 4). Previously Senior Finance Manager at Zumtobel Group AG, Dornbirn (2014–2019): led a team of 6 finance controllers, implemented SAP S/4HANA group-wide, reduced monthly close cycle from 12 to 7 days. Earlier positions: Finance Controller at Blum GmbH (2011–2014), Audit Senior at Deloitte Wien (2008–2011).

Education: WU Wien – MSc Finance & Accounting (2008). CPA Austria (Steuerberater, 2013).
Key skills: IFRS, Group consolidation, SAP S/4HANA, financial analysis, management reporting, investor relations, earnings calls, budgeting & forecasting, M&A due diligence, team leadership, Big 4 audit background.
Languages: German (native), English C1 (business fluent).
Salary expectation: €80,000–95,000 gross/year.
Availability: 3 months notice. Open to CFO or Director Group Finance roles in Vorarlberg, Vienna, or remote-hybrid.`,
};

const _EXAMPLE_PROFILE_3 = {
  name: 'Thomas Gruber',
  title: 'Director Group Finance',
  experience_years: '15 years',
  skills: ['IFRS','Group Consolidation','SAP S/4HANA','Financial Analysis','Management Reporting','Investor Relations','Budgeting & Forecasting','M&A Due Diligence','Team Leadership','CPA Austria'],
  location: 'Vorarlberg / Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€80,000–95,000/year',
  availability: '3 months notice',
  summary: 'Senior finance director with 15 years across Big 4 audit, controlling and group CFO functions; IFRS and SAP S/4HANA expert with investor relations and M&A experience.',
};

function loadExampleText() {
  app._activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = _EXAMPLE_CANDIDATE.text;
  app._setCvLoaded('Anna Bauer (example)');
  state.lastParsedText = _EXAMPLE_CANDIDATE.text;
  app._renderCandidateProfile(_EXAMPLE_PROFILE);
}

async function loadExamplePdf() {
  const tile = document.getElementById('exPdfTile');
  if (tile) { tile.style.opacity = '0.55'; tile.style.pointerEvents = 'none'; }
  try {
    const res = await api.raw('/api/candidate/example-pdf-2');
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();

    const fd = new FormData();
    fd.append('file', blob, 'Max_Weber_CV.pdf');
    let pdfText = _EXAMPLE_CANDIDATE_2.text;
    try {
      const pr = await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd });
      if (pr.ok) {
        const pj = await pr.json();
        if (pj.text && pj.text.trim().length > 20) pdfText = pj.text;
      }
    } catch(_) {}

    app._activateCVMode();
    const paste = document.getElementById('cvPasteText');
    if (paste) paste.value = pdfText;
    app._setCvLoaded('Max Weber CV (PDF)');
    state.lastParsedText = pdfText;
    app._renderCandidateProfile(_EXAMPLE_PROFILE_2);
  } catch(e) {
    alert('Could not load example CV: ' + e.message);
  } finally {
    if (tile) { tile.style.opacity = '1'; tile.style.pointerEvents = ''; }
  }
}

function loadExample3() {
  app._activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = _EXAMPLE_CANDIDATE_3.text;
  app._setCvLoaded('Thomas Gruber (example)');
  state.lastParsedText = _EXAMPLE_CANDIDATE_3.text;
  app._renderCandidateProfile(_EXAMPLE_PROFILE_3);
}

// ── Example Candidate 4: Sophie Wagner (Data Engineer) ───────
const _EXAMPLE_CANDIDATE_4 = {
  name: 'Sophie Wagner',
  text: `Data Engineer with 5 years of experience in data pipelines, analytics and BI, based in Vienna.

Currently Data Engineer at FinanzGroup Austria (2022–present): building and maintaining ETL pipelines with Apache Airflow and Spark on Azure Databricks, designing star-schema data warehouses in Azure Synapse, delivering Power BI dashboards for the finance and operations departments. Previously Data Analyst at MediaPlus GmbH (2020–2022): built SQL-based reporting in PostgreSQL, automated Excel reporting via Python scripts, introduced Power BI company-wide. Internship at Statistik Austria (2019–2020): assisted with official statistics data processing in R and SAS.

Education: WU Wien – BSc Business Informatics (2019).
Key skills: Python, SQL, Apache Spark, Airflow, Azure Databricks, Azure Synapse, Power BI, Tableau, dbt, PostgreSQL, Git, Docker, statistics.
Languages: German (native), English C1.
Salary expectation: €3,800–4,600 gross/month.
Availability: 2 months notice. Seeking Data Engineer or Senior Analyst roles in Vienna.`,
};
const _EXAMPLE_PROFILE_4 = {
  name: 'Sophie Wagner',
  title: 'Data Engineer',
  experience_years: '5 years',
  skills: ['Python','SQL','Apache Spark','Apache Airflow','Azure Databricks','Power BI','dbt','PostgreSQL','Docker','Statistics'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,800–4,600/month',
  availability: '2 months notice',
  summary: 'Data engineer with 5 years building production pipelines on Azure; strong in Spark, Airflow and Power BI with a business informatics background.',
};

// ── Example Candidate 5: Nina Fuchs (HR Manager) ─────────────
const _EXAMPLE_CANDIDATE_5 = {
  name: 'Nina Fuchs',
  text: `HR Manager with 7 years of experience in full-cycle recruiting, HR operations and people development, based in Vienna.

Currently HR Manager at RetailGroup Austria GmbH (2021–present): responsible for end-to-end recruiting (100+ hires/year across retail and corporate), manage SAP SuccessFactors HRIS, run onboarding and offboarding processes, coordinate annual performance review cycles, advise line managers on Austrian labor law (ABGB, AngG). Previously HR Generalist at BauService AG, Vienna (2019–2021): payroll processing in SAP HR, administering collective bargaining agreements (KV), welfare and health programs. HR Assistant at AMS Wien (2017–2019): candidate counselling, job placement, labor market analysis.

Education: Uni Wien – BSc Psychology (2017). WIFI HR-Fachkraft certificate (2018).
Key skills: Full-cycle recruiting, SAP SuccessFactors, SAP HR, Austrian labor law, onboarding, payroll, performance management, employee relations, KV administration.
Languages: German (native), English B2.
Salary expectation: €3,200–3,900 gross/month.
Availability: 1 month notice. Open to HR Manager or People Partner roles in Vienna.`,
};
const _EXAMPLE_PROFILE_5 = {
  name: 'Nina Fuchs',
  title: 'HR Manager',
  experience_years: '7 years',
  skills: ['Full-cycle Recruiting','SAP SuccessFactors','SAP HR','Austrian Labor Law','Onboarding','Payroll','Performance Management','Employee Relations','KV Administration'],
  location: 'Vienna',
  languages: 'German (native), English B2',
  salary_expectation: '€3,200–3,900/month',
  availability: '1 month notice',
  summary: 'Generalist HR manager with 7 years across retail and public sector; expert in SAP SuccessFactors, Austrian labor law and high-volume recruiting.',
};

// ── Example Candidate 6: Felix Kraus (PR & Marketing Manager) ─
const _EXAMPLE_CANDIDATE_6 = {
  name: 'Felix Kraus',
  text: `PR & Marketing Manager with 6 years of experience in corporate communications, content marketing and brand management, based in Vienna.

Currently PR & Marketing Manager at TravelPlus Austria GmbH (2021–present): managing all external communications (press releases, journalist relationships, crisis PR), running paid and organic social media across LinkedIn, Instagram and TikTok (combined reach 180k), coordinating content calendar and copywriting team of 3, responsible for brand guidelines and visual identity refresh (2023). Previously Content & Social Media Manager at AgencyOne Wien (2019–2021): produced content for 8 B2C clients, managed Google Ads and Meta campaigns (€20k/month budget), grew LinkedIn company pages by an average of 45%. Marketing Coordinator at Eventim Austria (2018–2019): copywriting, event communications, newsletter campaigns (Mailchimp).

Education: FH Wien – BA Media & Communications (2018).
Key skills: PR, content marketing, social media management (LinkedIn, Instagram, TikTok), copywriting, brand strategy, Google Ads, Meta Ads, SEO basics, Adobe Creative Suite, Mailchimp, crisis communications.
Languages: German (native), English C1.
Salary expectation: €3,000–3,800 gross/month.
Availability: Immediately. Seeking PR/Marketing Manager or Head of Communications roles in Vienna.`,
};
const _EXAMPLE_PROFILE_6 = {
  name: 'Felix Kraus',
  title: 'PR & Marketing Manager',
  experience_years: '6 years',
  skills: ['PR & Communications','Content Marketing','Social Media Management','Copywriting','Brand Strategy','Google Ads','Meta Ads','Adobe Creative Suite','SEO','Crisis Communications'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€3,000–3,800/month',
  availability: 'Immediately',
  summary: 'PR and marketing manager with 6 years in corporate comms and digital; managed 180k social reach and €20k/month ad budgets across B2B and B2C brands.',
};

// ── Example Candidate 7: Stefan Hofer (B2B Sales Manager) ─────
const _EXAMPLE_CANDIDATE_7 = {
  name: 'Stefan Hofer',
  text: `B2B Sales Manager with 10 years of experience in enterprise software and SaaS sales, based in Vienna.

Currently Senior Account Executive at CloudSoft GmbH Austria (2020–present): managing a portfolio of 35 enterprise accounts (€2.4M ARR), consistently exceeding quota 115–130% per year, running full sales cycle from cold outreach to contract close, coordinating with pre-sales and customer success. Previously Account Manager at BusinessSoft AG, Vienna (2016–2020): grew SME segment revenue by 40% over 3 years, introduced Salesforce CRM replacing spreadsheet-based tracking, mentored two junior sales reps. Inside Sales Rep at TeleSolutions Austria (2014–2016): 200+ cold calls/week, exceeded monthly quota 18 out of 24 months.

Education: FH Wiener Neustadt – BA Business Administration (2014).
Key skills: B2B sales, SaaS, enterprise account management, Salesforce CRM, cold calling, pipeline management, contract negotiation, consultative selling, upsell/cross-sell, CRM analytics.
Languages: German (native), English C1.
Salary expectation: €4,500–5,500 gross/month + variable.
Availability: 3 months notice. Open to Sales Manager or Head of Sales roles in Austria.`,
};
const _EXAMPLE_PROFILE_7 = {
  name: 'Stefan Hofer',
  title: 'B2B Sales Manager',
  experience_years: '10 years',
  skills: ['B2B Sales','SaaS','Enterprise Account Management','Salesforce CRM','Pipeline Management','Contract Negotiation','Consultative Selling','Cold Calling','Upsell/Cross-sell'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€4,500–5,500/month + variable',
  availability: '3 months notice',
  summary: 'Enterprise SaaS sales manager with 10 years; consistently 115–130% quota, €2.4M ARR portfolio, Salesforce power user and team mentor.',
};

// ── Example Candidate 8: Julia Reiter (IT Project Manager) ────
const _EXAMPLE_CANDIDATE_8 = {
  name: 'Julia Reiter',
  text: `IT Project Manager and Scrum Master with 8 years of experience managing software delivery and digital transformation projects, based in Vienna.

Currently Senior IT Project Manager at InsureTech Austria AG (2020–present): leading a portfolio of 4 simultaneous software projects (total budget €3.2M), acting as Scrum Master for two agile squads (8–10 devs each), coordinating with C-level stakeholders, managing vendors and third-party integrations, running steering committee meetings and risk registers. Previously IT Project Manager at ConsultCo Wien (2018–2020): delivered ERP implementation (SAP S/4HANA) on time and €120k under budget, managed cross-functional team of 15. Junior PM at Telekom Austria (2016–2018): tracked project milestones, maintained JIRA boards, facilitated retrospectives.

Education: TU Wien – MSc Software Engineering & Internet Computing (2016). PMP certified (2019). PSM I (Professional Scrum Master) certified (2020).
Key skills: IT project management, Scrum / Agile, PMP, PSM I, JIRA, Confluence, SAP S/4HANA delivery, stakeholder management, vendor management, risk management, budgeting, change management.
Languages: German (native), English C1.
Salary expectation: €4,500–5,500 gross/month.
Availability: 2 months notice. Open to IT PM or Programme Manager roles in Vienna.`,
};
const _EXAMPLE_PROFILE_8 = {
  name: 'Julia Reiter',
  title: 'IT Project Manager / Scrum Master',
  experience_years: '8 years',
  skills: ['IT Project Management','Scrum / Agile','PMP','JIRA','Confluence','SAP S/4HANA','Stakeholder Management','Vendor Management','Risk Management','Change Management'],
  location: 'Vienna',
  languages: 'German (native), English C1',
  salary_expectation: '€4,500–5,500/month',
  availability: '2 months notice',
  summary: 'Certified PMP & Scrum Master with 8 years delivering IT projects up to €3.2M; SAP S/4HANA experience and strong agile + stakeholder management track record.',
};

// ── Example Candidate 9: Roman Labuš (Python / data, text) ───
const _EXAMPLE_CANDIDATE_9 = {
  name: 'Roman Labuš',
  text: `Python Developer with ~4 years of experience in web scraping, ETL pipelines and LLM-based data enrichment, based in Bratislava.

Currently Programmer at Acme Recruitment, Bratislava (Aug 2022–present): built and maintained web-scraping solutions for internal competitive-intelligence products (real-estate market, lead research, jobs intelligence). Built automated scrapers in Python with Playwright and Selenium that collect high-value market data, directly generating €100k+ in yearly revenue. Developed ETL pipelines with Apache Airflow and Pandas to load large datasets into SQL databases, integrated Apify to replace manual data collection, and contributed to LLM-based data-enrichment workflows in close collaboration with analysts. Built internal IT tools, project-tracking dashboards and reporting that gave management real-time visibility. Research Intern – Discussion Toxicity Prediction at KInIT (Aug 2023–Jun 2024): trained multilingual models classifying toxic social-media content and built visualizations for end users. Earlier: Copywriter at WebSupport s.r.o. (2016–2022) and Vice President for PR at NGO BEST Bratislava (2021–2022).

Education: Slovak University of Technology, FIIT Bratislava – Information & Communication Technologies (2022–2024); University of Logistics (VŠLG) Bratislava – Informatics in Logistics (2025–present).
Key skills: Python, web scraping (Playwright, Selenium, Apify), ETL, Apache Airflow, Pandas, MySQL/SQL, LLM data enrichment, dashboards, Java (basic).
Languages: Slovak (native), English C1, German B2.
Driving licence: B. Interests: philosophy & business discussion clubs, improv theatre, writing a sci-fi novel ("Mission 77").`,
};
const _EXAMPLE_PROFILE_9 = {
  name: 'Roman Labuš',
  title: 'Python Developer (Web Scraping & Data)',
  experience_years: '4 years',
  skills: ['Python','Web Scraping','Playwright','Selenium','Apify','ETL','Apache Airflow','Pandas','MySQL','LLM Data Enrichment','Dashboards','Java (basic)'],
  location: 'Bratislava',
  languages: 'Slovak (native), English C1, German B2',
  education: 'ICT — FIIT STU Bratislava',
  summary: 'Python developer with ~4 years building production web-scraping and ETL pipelines (Playwright, Selenium, Apify, Airflow) plus LLM-based data enrichment; scrapers generated €100k+ in annual revenue.',
};

// ── Unified example catalogue (Austria) ──────────────────────
const _EXAMPLES_AT = [
  { area:'IT',        areaClass:'it',       name:'Roman Labuš',   desc:'Python · Web Scraping · Airflow · Apify · ETL · LLM', load: ()=>_loadExDirect(9) },
  { area:'IT',        areaClass:'it',       name:'Max Weber',     desc:'Python · FastAPI · React · PostgreSQL · Docker',    badge:'PDF',  load: ()=>loadExamplePdf() },
  { area:'IT',        areaClass:'it',       name:'Julia Reiter',  desc:'IT Project Mgmt · Scrum · PMP · JIRA · SAP S/4HANA', load: ()=>_loadExDirect(8) },
  { area:'Data',      areaClass:'data',     name:'Sophie Wagner', desc:'Python · Spark · Airflow · Azure · Power BI · dbt', load: ()=>_loadExDirect(4) },
  { area:'HR',        areaClass:'hr',       name:'Nina Fuchs',    desc:'Recruiting · SAP SuccessFactors · Labor Law · Payroll', load: ()=>_loadExDirect(5) },
  { area:'PR',        areaClass:'pr',       name:'Felix Kraus',   desc:'PR · Content Marketing · Social Media · Brand Strategy', load: ()=>_loadExDirect(6) },
  { area:'Sales',     areaClass:'sales',    name:'Stefan Hofer',  desc:'B2B Sales · SaaS · Salesforce · Enterprise Accounts', load: ()=>_loadExDirect(7) },
  { area:'Finance',   areaClass:'finance',  name:'Thomas Gruber', desc:'IFRS · Group Consolidation · SAP S/4HANA · M&A',    load: ()=>loadExample3() },
  { area:'Logistics', areaClass:'logistics',name:'Anna Bauer',    desc:'SAP WM · Forklift · Team Leadership · KPI Reporting', load: ()=>loadExampleText() },
];

// ── Slovak example candidates (shown when COUNTRY=sk) ─────────
// Self-contained: each item carries its own parsed text + profile, plus an
// optional PDF endpoint. Bratislava/Košice/Žilina, Slovak languages, Slovak
// market salaries — the SK counterpart to the Austrian set above.
const _SK_EXAMPLES_DATA = [
  { area:'IT', areaClass:'it', name:'Roman Labuš',
    desc:'Python · Web Scraping · Airflow · Apify · ETL · LLM',
    cand:{ name:'Roman Labuš', text:`Python Developer with ~4 years of experience in web scraping, ETL pipelines and LLM-based data enrichment, based in Bratislava.

Currently Programmer at Acme Recruitment, Bratislava (Aug 2022–present): built and maintained web-scraping solutions for internal competitive-intelligence products (real-estate market, lead research, jobs intelligence). Built automated scrapers in Python with Playwright and Selenium that collect high-value market data, directly generating €100k+ in yearly revenue. Developed ETL pipelines with Apache Airflow and Pandas to load large datasets into SQL databases, integrated Apify to replace manual data collection, and contributed to LLM-based data-enrichment workflows in close collaboration with analysts. Built internal IT tools, project-tracking dashboards and reporting that gave management real-time visibility. Research Intern – Discussion Toxicity Prediction at KInIT (Aug 2023–Jun 2024): trained multilingual models classifying toxic social-media content and built visualizations for end users. Earlier: Copywriter at WebSupport s.r.o. (2016–2022) and Vice President for PR at NGO BEST Bratislava (2021–2022).

Education: Slovak University of Technology, FIIT Bratislava – Information & Communication Technologies (2022–2024); University of Logistics (VŠLG) Bratislava – Informatics in Logistics (2025–present).
Key skills: Python, web scraping (Playwright, Selenium, Apify), ETL, Apache Airflow, Pandas, MySQL/SQL, LLM data enrichment, dashboards, Java (basic).
Languages: Slovak (native), English C1, German B2.
Driving licence: B. Interests: philosophy & business discussion clubs, improv theatre, writing a sci-fi novel ("Mission 77").` },
    prof:{ name:'Roman Labuš', title:'Python Developer (Web Scraping & Data)', experience_years:'4 years',
      skills:['Python','Web Scraping','Playwright','Selenium','Apify','ETL','Apache Airflow','Pandas','MySQL','LLM Data Enrichment','Dashboards','Java (basic)'],
      location:'Bratislava', languages:'Slovak (native), English C1, German B2',
      education:'ICT — FIIT STU Bratislava',
      summary:'Python developer with ~4 years building production web-scraping and ETL pipelines (Playwright, Selenium, Apify, Airflow) plus LLM-based data enrichment; scrapers generated €100k+ in annual revenue.' } },

  { area:'IT', areaClass:'it', name:'Marek Novák', badge:'PDF',
    pdf:'/api/candidate/example-pdf-sk', pdfFile:'Marek_Novak_CV.pdf',
    desc:'Python · FastAPI · React · PostgreSQL · Docker',
    cand:{ name:'Marek Novák', text:`Software Developer with 5 years of experience in backend and full-stack development, based in Bratislava.

Currently Backend Developer at TechSolutions s.r.o. Bratislava (2022–present): building REST APIs in Python/FastAPI, maintaining PostgreSQL databases, deploying services via Docker and CI/CD pipelines (GitLab CI). Previously Junior Developer at WebFactory s.r.o. (2020–2022): developed React frontends and Node.js services, contributed to agile sprint planning and code reviews. IT Intern at Startup Hub Bratislava (2019–2020): built internal tooling with Python.

Education: FIIT STU Bratislava – Ing. (MSc) Informatics (2019).
Key skills: Python, FastAPI, JavaScript/TypeScript, React, Node.js, PostgreSQL, Docker, Git, REST APIs, Linux, CI/CD.
Languages: Slovak (native), Czech (fluent), English C1.
Salary expectation: €2,800–3,600 gross/month.
Availability: 2 months notice. Seeking full-time permanent role in Bratislava.` },
    prof:{ name:'Marek Novák', title:'Backend & Full-Stack Developer', experience_years:'5 years',
      skills:['Python','FastAPI','JavaScript/TypeScript','React','Node.js','PostgreSQL','Docker','Git','REST APIs','Linux','CI/CD'],
      location:'Bratislava', languages:'Slovak (native), Czech, English C1',
      salary_expectation:'€2,800–3,600/month', availability:'2 months notice',
      education:'Ing. (MSc) Informatics, FIIT STU Bratislava',
      summary:'Full-stack developer with 5 years in Python backends and React frontends, comfortable with Docker deployments and agile teams.' } },

  { area:'IT', areaClass:'it', name:'Lucia Horváthová',
    desc:'IT Project Mgmt · Scrum · PMP · JIRA · ERP delivery',
    cand:{ name:'Lucia Horváthová', text:`IT Project Manager and Scrum Master with 8 years of experience managing software delivery projects, based in Bratislava.

Currently Senior IT Project Manager at InsureTech Slovakia a.s. (2020–present): leading 4 simultaneous software projects (total budget €2.4M), acting as Scrum Master for two agile squads (8–10 devs each), coordinating with C-level stakeholders and vendors. Previously IT Project Manager at ConsultCo Bratislava (2018–2020): delivered an ERP implementation on time and under budget, managed a cross-functional team of 15. Junior PM at Slovak Telekom (2016–2018): tracked milestones, maintained JIRA boards, facilitated retrospectives.

Education: FEI STU Bratislava – Ing. Software Engineering (2016). PMP certified (2019). PSM I certified (2020).
Key skills: IT project management, Scrum/Agile, PMP, PSM I, JIRA, Confluence, ERP delivery, stakeholder management, vendor management, risk management, budgeting.
Languages: Slovak (native), English C1, German B1.
Salary expectation: €3,000–3,800 gross/month.
Availability: 2 months notice. Open to IT PM or Programme Manager roles in Bratislava.` },
    prof:{ name:'Lucia Horváthová', title:'IT Project Manager / Scrum Master', experience_years:'8 years',
      skills:['IT Project Management','Scrum / Agile','PMP','JIRA','Confluence','ERP Delivery','Stakeholder Management','Vendor Management','Risk Management'],
      location:'Bratislava', languages:'Slovak (native), English C1, German B1',
      salary_expectation:'€3,000–3,800/month', availability:'2 months notice',
      summary:'Certified PMP & Scrum Master with 8 years delivering IT projects up to €2.4M; strong agile and stakeholder management track record.' } },

  { area:'Data', areaClass:'data', name:'Tomáš Kováč',
    desc:'Python · Spark · Airflow · Azure · Power BI · dbt',
    cand:{ name:'Tomáš Kováč', text:`Data Engineer with 5 years of experience in data pipelines, analytics and BI, based in Košice.

Currently Data Engineer at FinGroup Slovakia (2022–present): building ETL pipelines with Apache Airflow and Spark on Azure Databricks, designing star-schema data warehouses in Azure Synapse, delivering Power BI dashboards for finance and operations. Previously Data Analyst at MediaPlus s.r.o. (2020–2022): built SQL reporting in PostgreSQL, automated Excel reporting via Python, rolled out Power BI company-wide. Internship at the Statistical Office of the SR (2019–2020): data processing in R.

Education: TUKE Košice – Ing. Informatics (2019).
Key skills: Python, SQL, Apache Spark, Airflow, Azure Databricks, Azure Synapse, Power BI, dbt, PostgreSQL, Git, Docker, statistics.
Languages: Slovak (native), English C1.
Salary expectation: €2,600–3,400 gross/month.
Availability: 1 month notice. Seeking Data Engineer or Senior Analyst roles in Košice or remote.` },
    prof:{ name:'Tomáš Kováč', title:'Data Engineer', experience_years:'5 years',
      skills:['Python','SQL','Apache Spark','Apache Airflow','Azure Databricks','Power BI','dbt','PostgreSQL','Docker','Statistics'],
      location:'Košice', languages:'Slovak (native), English C1',
      salary_expectation:'€2,600–3,400/month', availability:'1 month notice',
      summary:'Data engineer with 5 years building production pipelines on Azure; strong in Spark, Airflow and Power BI.' } },

  { area:'HR', areaClass:'hr', name:'Zuzana Krajčíová',
    desc:'Recruiting · SuccessFactors · Labour Law · Payroll',
    cand:{ name:'Zuzana Krajčíová', text:`HR Manager with 7 years of experience in full-cycle recruiting, HR operations and people development, based in Bratislava.

Currently HR Manager at RetailGroup Slovakia s.r.o. (2021–present): end-to-end recruiting (100+ hires/year), managing SAP SuccessFactors HRIS, onboarding/offboarding, annual performance reviews, advising line managers on the Slovak Labour Code (Zákonník práce). Previously HR Generalist at BauService a.s. Bratislava (2019–2021): payroll processing, administering collective agreements. HR Assistant at ÚPSVR (labour office) Bratislava (2017–2019): candidate counselling, job placement.

Education: Comenius University Bratislava – Mgr. Psychology (2017).
Key skills: Full-cycle recruiting, SAP SuccessFactors, Slovak Labour Code, onboarding, payroll, performance management, employee relations.
Languages: Slovak (native), English B2.
Salary expectation: €2,200–2,900 gross/month.
Availability: 1 month notice. Open to HR Manager or People Partner roles in Bratislava.` },
    prof:{ name:'Zuzana Krajčíová', title:'HR Manager', experience_years:'7 years',
      skills:['Full-cycle Recruiting','SAP SuccessFactors','Slovak Labour Code','Onboarding','Payroll','Performance Management','Employee Relations'],
      location:'Bratislava', languages:'Slovak (native), English B2',
      salary_expectation:'€2,200–2,900/month', availability:'1 month notice',
      summary:'Generalist HR manager with 7 years across retail and public sector; expert in SAP SuccessFactors and the Slovak Labour Code.' } },

  { area:'PR', areaClass:'pr', name:'Martin Šimko',
    desc:'PR · Content Marketing · Social Media · Brand Strategy',
    cand:{ name:'Martin Šimko', text:`PR & Marketing Manager with 6 years of experience in corporate communications, content marketing and brand management, based in Bratislava.

Currently PR & Marketing Manager at TravelPlus Slovakia s.r.o. (2021–present): managing external communications and press relationships, running paid and organic social media across LinkedIn, Instagram and TikTok (combined reach 150k), coordinating a content team of 3, owning brand guidelines. Previously Content & Social Media Manager at AgencyOne Bratislava (2019–2021): content for 8 B2C clients, Google and Meta campaigns (€15k/month budget). Marketing Coordinator at Eventim Slovakia (2018–2019): copywriting, newsletter campaigns.

Education: Comenius University Bratislava – Mgr. Media & Communications (2018).
Key skills: PR, content marketing, social media (LinkedIn, Instagram, TikTok), copywriting, brand strategy, Google Ads, Meta Ads, SEO basics, Adobe Creative Suite.
Languages: Slovak (native), English C1.
Salary expectation: €1,800–2,400 gross/month.
Availability: Immediately. Seeking PR/Marketing Manager roles in Bratislava.` },
    prof:{ name:'Martin Šimko', title:'PR & Marketing Manager', experience_years:'6 years',
      skills:['PR & Communications','Content Marketing','Social Media Management','Copywriting','Brand Strategy','Google Ads','Meta Ads','Adobe Creative Suite','SEO'],
      location:'Bratislava', languages:'Slovak (native), English C1',
      salary_expectation:'€1,800–2,400/month', availability:'Immediately',
      summary:'PR and marketing manager with 6 years in corporate comms and digital; managed 150k social reach and €15k/month ad budgets.' } },

  { area:'Sales', areaClass:'sales', name:'Peter Varga',
    desc:'B2B Sales · SaaS · Salesforce · Enterprise Accounts',
    cand:{ name:'Peter Varga', text:`B2B Sales Manager with 10 years of experience in enterprise software and SaaS sales, based in Bratislava.

Currently Senior Account Executive at CloudSoft Slovakia s.r.o. (2020–present): managing 35 enterprise accounts (€2.0M ARR), consistently exceeding quota 115–130% per year, running the full sales cycle from outreach to close. Previously Account Manager at BusinessSoft a.s. Bratislava (2016–2020): grew SME revenue by 40% over 3 years, introduced Salesforce CRM, mentored two junior reps. Inside Sales Rep at TeleSolutions Slovakia (2014–2016): 200+ cold calls/week, exceeded quota 18 of 24 months.

Education: University of Economics in Bratislava – Ing. Business Administration (2014).
Key skills: B2B sales, SaaS, enterprise account management, Salesforce CRM, pipeline management, contract negotiation, consultative selling, upsell/cross-sell.
Languages: Slovak (native), English C1, Hungarian B2.
Salary expectation: €2,500–3,200 gross/month + variable.
Availability: 3 months notice. Open to Sales Manager or Head of Sales roles in Slovakia.` },
    prof:{ name:'Peter Varga', title:'B2B Sales Manager', experience_years:'10 years',
      skills:['B2B Sales','SaaS','Enterprise Account Management','Salesforce CRM','Pipeline Management','Contract Negotiation','Consultative Selling','Upsell/Cross-sell'],
      location:'Bratislava', languages:'Slovak (native), English C1, Hungarian B2',
      salary_expectation:'€2,500–3,200/month + variable', availability:'3 months notice',
      summary:'Enterprise SaaS sales manager with 10 years; consistently 115–130% quota, €2.0M ARR portfolio and Salesforce power user.' } },

  { area:'Finance', areaClass:'finance', name:'Eva Tóthová',
    desc:'IFRS · Group Consolidation · SAP S/4HANA · Audit',
    cand:{ name:'Eva Tóthová', text:`Director Group Finance with 15 years of experience in corporate finance, IFRS reporting and controlling, based in Bratislava.

Currently Head of Group Finance at Bratislava Medtech a.s. (2019–present): responsible for consolidated IFRS statements, management reporting to the board, coordination of the annual audit (Big 4). Previously Senior Finance Manager at Industrial Group Slovakia a.s. (2014–2019): led a team of 6 controllers, implemented SAP S/4HANA group-wide, reduced the monthly close from 12 to 7 days. Earlier: Finance Controller (2011–2014) and Audit Senior at Deloitte Bratislava (2008–2011).

Education: University of Economics in Bratislava – Ing. Finance & Accounting (2008). ACCA (2013).
Key skills: IFRS, group consolidation, SAP S/4HANA, financial analysis, management reporting, budgeting & forecasting, M&A due diligence, team leadership, Big 4 audit background.
Languages: Slovak (native), English C1.
Salary expectation: €4,500–6,000 gross/month.
Availability: 3 months notice. Open to CFO or Director Group Finance roles in Bratislava.` },
    prof:{ name:'Eva Tóthová', title:'Director Group Finance', experience_years:'15 years',
      skills:['IFRS','Group Consolidation','SAP S/4HANA','Financial Analysis','Management Reporting','Budgeting & Forecasting','M&A Due Diligence','Team Leadership','ACCA'],
      location:'Bratislava', languages:'Slovak (native), English C1',
      salary_expectation:'€4,500–6,000/month', availability:'3 months notice',
      summary:'Senior finance director with 15 years across Big 4 audit, controlling and group finance; IFRS and SAP S/4HANA expert.' } },

  { area:'Logistics', areaClass:'logistics', name:'Jana Kováčová',
    desc:'SAP WM · Forklift · Team Leadership · KPI Reporting',
    cand:{ name:'Jana Kováčová', text:`Logistics and Warehouse Supervisor with 8 years of experience in high-volume distribution, based in Žilina.

Certified forklift operator (vysokozdvižný vozík, valid until 2027). SAP Warehouse Management certified user (2020). Currently Senior Warehouse Supervisor at MegaLogistics s.r.o. Žilina (2019–present): leading a team of 12 across two shifts, introduced SAP WM reducing stock discrepancies by 23%, responsible for KPI reporting (fill rate, OTIF, pick accuracy). Previously Warehouse Coordinator at SlovPack a.s. (2016–2019): coordinated 2,000+ orders/day pick & pack, trained 8 staff.

Key skills: SAP WM, forklift operation, inventory management, team leadership, lean logistics, FIFO/FEFO, MS Excel, KPI reporting.
Languages: Slovak (native), English B2.
Salary expectation: €1,400–1,900 gross/month.
Availability: Immediately. Seeking full-time permanent role in Žilina region.` },
    prof:{ name:'Jana Kováčová', title:'Logistics & Warehouse Supervisor', experience_years:'8 years',
      skills:['Forklift Licence','SAP WM','Team Leadership','Inventory Management','KPI Reporting','Lean Logistics','MS Excel','FIFO/FEFO'],
      location:'Žilina', languages:'Slovak (native), English B2',
      salary_expectation:'€1,400–1,900/month', availability:'Immediately',
      summary:'Experienced logistics supervisor with 8 years in high-volume distribution; certified forklift operator with SAP WM expertise.' } },
];

// Generic loader for a Slovak example item (PDF download + parse when present,
// otherwise just the bundled text). Mirrors loadExamplePdf / loadExampleText.
async function _loadSkExample(item) {
  app._activateCVMode();
  let text = item.cand.text;
  if (item.pdf) {
    try {
      const res = await fetch(item.pdf);
      if (res.ok) {
        const blob = await res.blob();
        const fd = new FormData();
        fd.append('file', blob, item.pdfFile || 'CV.pdf');
        const pr = await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd });
        if (pr.ok) {
          const pj = await pr.json();
          if (pj.text && pj.text.trim().length > 20) text = pj.text;
        }
      }
    } catch(_) {}
  }
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = text;
  app._setCvLoaded(item.badge === 'PDF' ? `${item.name} CV (PDF)` : `${item.name} (example)`);
  state.lastParsedText = text;
  app._renderCandidateProfile(item.prof);
}

const _EXAMPLES_SK = _SK_EXAMPLES_DATA.map(item => ({
  area: item.area, areaClass: item.areaClass, name: item.name,
  desc: item.desc, badge: item.badge, load: () => _loadSkExample(item),
}));

// Active example set — Slovak when COUNTRY=sk, Austrian otherwise.
const _EXAMPLES = ("{{ country_code }}" === "sk") ? _EXAMPLES_SK : _EXAMPLES_AT;

function _loadExDirect(n) {
  const map = {
    4: [_EXAMPLE_CANDIDATE_4, _EXAMPLE_PROFILE_4, 'Sophie Wagner (example)'],
    5: [_EXAMPLE_CANDIDATE_5, _EXAMPLE_PROFILE_5, 'Nina Fuchs (example)'],
    6: [_EXAMPLE_CANDIDATE_6, _EXAMPLE_PROFILE_6, 'Felix Kraus (example)'],
    7: [_EXAMPLE_CANDIDATE_7, _EXAMPLE_PROFILE_7, 'Stefan Hofer (example)'],
    8: [_EXAMPLE_CANDIDATE_8, _EXAMPLE_PROFILE_8, 'Julia Reiter (example)'],
    9: [_EXAMPLE_CANDIDATE_9, _EXAMPLE_PROFILE_9, 'Roman Labuš (example)'],
  };
  const [cand, prof, label] = map[n];
  app._activateCVMode();
  const paste = document.getElementById('cvPasteText');
  if (paste) paste.value = cand.text;
  app._setCvLoaded(label);
  state.lastParsedText = cand.text;
  app._renderCandidateProfile(prof);
}

function _exToggle() {
  const dd = document.getElementById('exDropdown');
  dd.classList.toggle('open');
}

function _exClose() {
  document.getElementById('exDropdown')?.classList.remove('open');
}

// Build dropdown items once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const panel = document.getElementById('exDropdownPanel');
  if (!panel) return;
  _EXAMPLES.forEach((ex, i) => {
    const el = document.createElement('div');
    el.className = 'ex-dropdown-item';
    el.innerHTML = `<span class="ex-area ex-area--${ex.areaClass}">${ex.area}</span>
      <div class="ex-item-body">
        <div class="ex-item-name">${ex.name}${ex.badge ? `<span class="ex-item-badge">${ex.badge}</span>` : ''}</div>
        <div class="ex-item-desc">${ex.desc}</div>
      </div>`;
    el.addEventListener('click', () => { ex.load(); _exClose(); });
    panel.appendChild(el);
  });
  // Close on outside click
  document.addEventListener('click', e => {
    if (!document.getElementById('exDropdown')?.contains(e.target)) _exClose();
  });
});

// Action registry for the Examples dropdown toggle (markup lives in the search tab).
Object.assign(_ACTIONS, {
  'ex-toggle': () => _exToggle(),
});
