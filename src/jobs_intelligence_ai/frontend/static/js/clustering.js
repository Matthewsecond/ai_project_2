// ════════════════════════════════════════════════════════════
//  Multiple-CV mode — cluster candidates into talent segments
// ════════════════════════════════════════════════════════════
// Clusters a pool of pasted/uploaded candidate profiles into talent segments,
// matches each segment against the job market, and supports per-segment
// drill-down (ranking, chat, grading). Drilling into one member hands off to
// the single-candidate workflow via app.setWorkflow()/app.runMatching().
import { state, _ACTIONS, app } from "./state.js";
import { esc, gradeClass } from "./util.js";
import api from "./api.js";

//  Multiple-CV mode — cluster candidates into talent segments
// ════════════════════════════════════════════════════════════
let _mcFileCandidates = [];   // {name, text} parsed from uploaded files
let _mcLastClusters   = [];   // last /api/cluster result (used by later phases)
let _mcLastCandidates = [];   // candidates sent to the last clustering (for drill-down)

// 50 example candidates — full-length CV-style profiles across ~12 job families
// (with variation inside each family, so clustering has real structure to find).
// Loaded into the paste box on demand.
const MC_EXAMPLES = [
  "Peter Varga — B2B Sales Manager, Bratislava.\nExperience: 10 years in enterprise software / SaaS sales. Senior Account Executive at CloudSoft Slovakia (2019–present): owns 35 enterprise accounts (€2.0M ARR), 115–130% quota attainment, runs the full sales cycle from outreach to close; previously Account Manager at BusinessSoft (2015–2019), grew SME revenue 40% over three years.\nEducation: Ing. in Business Administration, University of Economics in Bratislava (2014).\nSkills: B2B sales, SaaS, enterprise account management, Salesforce CRM, pipeline management, contract negotiation, consultative selling, upselling.\nLanguages: Slovak (native), English C1, German B1. Salary expectation: €2,800–3,400 + variable.",
  "Jana Kováčová — Senior Account Executive, Bratislava.\nExperience: 8 years in SaaS and IT services sales. Senior AE at NetVerse (2018–present): consistently 120%+ of quota, manages key accounts and renewals, closed the company's two largest deals; earlier Sales Representative at PrintPro selling B2B print solutions.\nEducation: Mgr. in Marketing Communications, Comenius University Bratislava.\nSkills: key account management, solution selling, HubSpot & Salesforce CRM, forecasting, negotiation, upsell/cross-sell, B2B.\nLanguages: Slovak (native), English C1, Hungarian B2.",
  "Marek Novák — Inside Sales Representative, Košice.\nExperience: 3 years in B2B software inside sales. SDR at AppNest (2021–present): 200+ outbound touches per week, books ~40 qualified meetings monthly, top SDR two quarters running; previously call-centre agent.\nEducation: Bc. in Management, Technical University of Košice.\nSkills: outbound prospecting, cold calling, lead generation, qualification (BANT), HubSpot, email sequencing, CRM hygiene.\nLanguages: Slovak (native), English B2.",
  "Tomáš Horváth — Regional Sales Manager (FMCG), Nitra.\nExperience: 12 years in fast-moving consumer goods. Regional Sales Manager at FoodLine SK (2016–present): leads a team of 6 reps across western Slovakia, manages distributor relationships and retail chains, +18% regional revenue; earlier Key Account Manager for a beverage distributor.\nEducation: Ing. in Agricultural Economics, Slovak University of Agriculture in Nitra.\nSkills: distributor management, territory planning, retail/key accounts, team leadership, trade marketing, negotiation, P&L.\nLanguages: Slovak (native), English B2, German B1.",
  "Lucia Baláž — Business Development Representative, Bratislava.\nExperience: 2 years in SaaS demand generation. BDR at Saasly (2022–present): qualifies inbound and outbound leads, runs first-touch discovery, exceeded pipeline target by 25%; internship in marketing prior.\nEducation: Bc. in International Business, University of Economics in Bratislava.\nSkills: lead qualification, HubSpot, outreach cadences, LinkedIn Sales Navigator, discovery calls, SaaS, CRM.\nLanguages: Slovak (native), English C1, Spanish B1.",
  "Roman Tóth — Key Account Manager (Telecom), Bratislava.\nExperience: 7 years in telecom B2B. KAM at TelSlovak (2018–present): manages 20 corporate accounts, negotiates multi-year contracts, +€1.4M upsell over two years, retention 95%; earlier business sales consultant.\nEducation: Ing. in Telecommunications, Slovak University of Technology.\nSkills: key account management, B2B contracts, upselling, relationship management, solution selling, CRM, forecasting.\nLanguages: Slovak (native), English C1, German B2.",
  "Eva Krajčí — Data Analyst, Bratislava.\nExperience: 5 years in analytics. Data Analyst at FinReport (2019–present): builds Power BI dashboards, writes complex SQL, automates ETL for finance reporting, partners with controllers; earlier reporting analyst.\nEducation: Ing. in Quantitative Methods, University of Economics in Bratislava.\nSkills: SQL, Power BI, Python (pandas), ETL, data modelling, Excel, financial reporting, stakeholder communication.\nLanguages: Slovak (native), English C1.",
  "Lukáš Bartoš — Business Intelligence Analyst, Žilina.\nExperience: 6 years in BI. BI Analyst at LogiData (2017–present): owns the Tableau reporting layer, models warehouse and supply-chain KPIs, optimises SQL on large datasets; previously analyst in retail.\nEducation: Ing. in Information Systems, University of Žilina.\nSkills: SQL, Tableau, Python, data modelling, KPI design, warehouse/supply-chain data, dashboards, dbt basics.\nLanguages: Slovak (native), English C1, Czech (fluent).",
  "Nina Hudec — Data Scientist, Bratislava.\nExperience: 4 years in data science. Data Scientist at PredictIQ (2020–present): builds ML models (churn, propensity) in Python, runs A/B tests, deploys with MLflow; earlier analytics intern at a bank.\nEducation: Mgr. in Applied Mathematics, Comenius University Bratislava.\nSkills: Python, pandas, scikit-learn, machine learning, statistics, A/B testing, SQL, model deployment, visualization.\nLanguages: Slovak (native), English C1.",
  "Martin Šimko — Analytics Engineer, Bratislava.\nExperience: 5 years bridging data engineering and analytics. Analytics Engineer at DataForge (2019–present): builds dbt models on Snowflake, designs the semantic layer, manages BigQuery pipelines and data quality tests.\nEducation: Ing. in Computer Science, Slovak University of Technology.\nSkills: dbt, Snowflake, BigQuery, SQL, data pipelines, Airflow, Git, data modelling, testing.\nLanguages: Slovak (native), English C1.",
  "Petra Líška — Junior Data Analyst, Trnava.\nExperience: 1 year plus internships. Junior Data Analyst at ShopMetrics (2023–present): builds Excel and Power BI reports, writes intermediate SQL, supports marketing analytics; data internship before that.\nEducation: Bc. in Economics and Statistics, University of Trnava (2023).\nSkills: Excel (advanced), SQL, Power BI, reporting, basic Python, data cleaning.\nLanguages: Slovak (native), English B2.",
  "Zuzana Müller — Backend Software Engineer, Bratislava.\nExperience: 6 years backend. Senior Backend Engineer at a fintech scale-up (2019–present): designs Python (Django/FastAPI) REST APIs, runs PostgreSQL at scale, deploys microservices on AWS (ECS/Lambda/RDS) via Docker and CI/CD, mentors two juniors.\nEducation: Mgr. in Computer Science, Slovak University of Technology (2018).\nSkills: Python, Django, FastAPI, PostgreSQL, REST APIs, AWS, Docker, microservices, CI/CD, system design.\nLanguages: Slovak (native), English C1.",
  "Tomáš Polák — Full-stack Developer, Košice.\nExperience: 5 years full-stack. Full-stack Developer at WebWorks (2019–present): builds React/TypeScript front-ends and Node.js services, PostgreSQL, deploys on AWS with CI/CD; freelance web projects earlier.\nEducation: Ing. in Informatics, Technical University of Košice.\nSkills: React, Node.js, TypeScript, PostgreSQL, REST APIs, AWS, CI/CD, Git, Docker.\nLanguages: Slovak (native), English C1.",
  "Adam Krieger — Frontend Developer, Bratislava.\nExperience: 4 years front-end. Frontend Developer at PixelPlay (2020–present): builds Next.js/React component libraries, design-system work, accessibility and performance; junior front-end role before.\nEducation: Bc. in Applied Informatics, Comenius University Bratislava.\nSkills: React, TypeScript, Next.js, CSS/Tailwind, UI components, accessibility, testing (Jest), Figma handoff.\nLanguages: Slovak (native), English C1, German B1.",
  "Ondrej Macko — DevOps Engineer, Bratislava.\nExperience: 6 years infrastructure/DevOps. DevOps Engineer at CloudOps SK (2018–present): runs Kubernetes clusters, infrastructure-as-code with Terraform on AWS, CI/CD pipelines, observability (Prometheus/Grafana); earlier sysadmin.\nEducation: Ing. in Computer Networks, Slovak University of Technology.\nSkills: Kubernetes, Terraform, AWS, Docker, CI/CD, Prometheus, Grafana, Linux, Bash, GitOps.\nLanguages: Slovak (native), English C1.",
  "Filip Závodný — Java Backend Developer, Žilina.\nExperience: 6 years Java. Backend Developer at BankCore (2018–present): builds Spring Boot microservices, event streaming with Kafka, PostgreSQL, high-availability payment systems; earlier Java developer in insurance.\nEducation: Ing. in Software Engineering, University of Žilina.\nSkills: Java, Spring Boot, microservices, Kafka, PostgreSQL, REST, Docker, JUnit, design patterns.\nLanguages: Slovak (native), English B2.",
  "Daniel Urban — Mobile Developer, Bratislava.\nExperience: 5 years mobile. Mobile Developer at AppCraft (2019–present): builds native Android (Kotlin) and iOS (Swift) apps, integrates REST APIs, publishes to stores; junior Android role before.\nEducation: Bc. in Informatics, Comenius University Bratislava.\nSkills: Kotlin, Android, Swift, iOS, REST APIs, MVVM, Jetpack, Git, CI for mobile.\nLanguages: Slovak (native), English C1.",
  "Klára Beňová — Digital Marketing Manager, Bratislava.\nExperience: 8 years digital marketing. Digital Marketing Manager at GrowthLab (2017–present): owns SEO/SEM strategy, manages a €40k/month Google Ads budget, leads analytics and a team of 3; earlier PPC specialist.\nEducation: Mgr. in Marketing, University of Economics in Bratislava.\nSkills: SEO, SEM, Google Ads, GA4, campaign management, conversion optimization, content strategy, team leadership.\nLanguages: Slovak (native), English C1, German B1.",
  "Matej Sklenár — Content Marketing Specialist, Nitra.\nExperience: 4 years content. Content Specialist at StoryHouse (2020–present): plans editorial calendars, writes long-form and social copy, runs on-page SEO, grew organic traffic 60%; copywriting freelance earlier.\nEducation: Bc. in Journalism, Constantine the Philosopher University in Nitra.\nSkills: copywriting, content strategy, SEO, social media, editing, WordPress, basic analytics.\nLanguages: Slovak (native), English C1.",
  "Simona Vlk — Performance Marketing Specialist, Bratislava.\nExperience: 3 years paid media. Performance Marketer at AdScale (2021–present): manages Meta and Google Ads campaigns, A/B tests creatives and landing pages, improved ROAS 35%; marketing assistant before.\nEducation: Bc. in Media Studies, Comenius University Bratislava.\nSkills: Meta Ads, Google Ads, conversion optimization, A/B testing, GA4, audience targeting, reporting.\nLanguages: Slovak (native), English C1.",
  "Erik Hraško — Brand Manager (FMCG), Bratislava.\nExperience: 8 years brand and product marketing. Brand Manager at NutriBrands (2016–present): owns brand strategy and product launches, runs market research and agency relationships, manages a 7-figure marketing budget.\nEducation: Mgr. in Marketing Management, University of Economics in Bratislava.\nSkills: brand strategy, product marketing, market research, go-to-market, budget management, agency management, FMCG.\nLanguages: Slovak (native), English C1, German B2.",
  "Monika Sýkorová — HR Manager, Bratislava.\nExperience: 9 years HR. HR Manager at IndustrialCorp SK (2017–present): leads full-cycle recruiting, onboarding, payroll oversight, labour-law compliance and employee relations for 250 staff; earlier HR generalist.\nEducation: Mgr. in Human Resource Management, University of Economics in Bratislava.\nSkills: full-cycle recruiting, onboarding, payroll, Slovak labour law, employee relations, HR policy, SAP SuccessFactors.\nLanguages: Slovak (native), English C1, German B1.",
  "Veronika Adam — Technical Recruiter, Bratislava.\nExperience: 5 years IT recruitment. Technical Recruiter at TechHire (2019–present): sources and hires software engineers, runs structured interviews, manages the ATS and hiring-manager relationships, 40+ tech hires/year.\nEducation: Bc. in Psychology, Comenius University Bratislava.\nSkills: IT recruitment, sourcing, LinkedIn Recruiter, interviewing, ATS (Greenhouse), employer branding, candidate experience.\nLanguages: Slovak (native), English C1.",
  "Dáša Polláková — HR Generalist, Trnava.\nExperience: 4 years HR operations. HR Generalist at AutoParts SK (2020–present): runs HR administration, maintains SAP SuccessFactors, coordinates performance reviews and training; HR assistant before.\nEducation: Bc. in HR Management, University of Trnava.\nSkills: HR administration, SAP SuccessFactors, performance management, onboarding, contracts, time & attendance.\nLanguages: Slovak (native), English B2, German B1.",
  "Igor Mráz — Talent Acquisition Lead, Bratislava.\nExperience: 10 years recruitment. TA Lead at ScaleUp Group (2016–present): builds recruitment strategy, leads a team of 4 recruiters, owns employer branding and hiring analytics across multiple countries.\nEducation: Mgr. in Sociology, Comenius University Bratislava.\nSkills: recruitment strategy, team leadership, employer branding, hiring analytics, stakeholder management, ATS, sourcing.\nLanguages: Slovak (native), English C1, Czech (fluent).",
  "Andrea Šťastná — Accountant, Bratislava.\nExperience: 6 years accounting. Accountant at MidMarket s.r.o. (2018–present): manages general ledger, AP/AR, VAT returns and month-end close for several entities; junior accountant before.\nEducation: Ing. in Accounting and Auditing, University of Economics in Bratislava.\nSkills: general ledger, accounts payable/receivable, VAT, month-end close, reconciliations, SAP, Excel, Slovak GAAP.\nLanguages: Slovak (native), English B2.",
  "Pavol Greguš — Financial Analyst, Bratislava.\nExperience: 5 years FP&A. Financial Analyst at HoldingCo (2019–present): builds financial models, owns budgeting and rolling forecasts, prepares board reporting and variance analysis; audit associate earlier.\nEducation: Ing. in Finance, University of Economics in Bratislava.\nSkills: financial modelling, Excel (advanced), budgeting, forecasting, variance analysis, Power BI, reporting, valuation.\nLanguages: Slovak (native), English C1.",
  "Katarína Lipták — Senior Accountant, Bratislava.\nExperience: 9 years. Senior Accountant at a shared-service centre (2015–present): handles IFRS reporting, group consolidation, audit support and SAP FI; led the transition to a new ERP.\nEducation: Ing. in Accounting, University of Economics; ACCA (in progress).\nSkills: IFRS, consolidation, audit support, SAP FI, statutory reporting, intercompany, internal controls.\nLanguages: Slovak (native), English C1, German B1.",
  "Boris Krško — Financial Controller, Bratislava.\nExperience: 12 years finance. Financial Controller at ManufactureCo (2014–present): owns management reporting, cost control, annual budgeting and CAPEX analysis, leads a team of 3; senior analyst before.\nEducation: Ing. in Finance, University of Economics; CIMA Diploma.\nSkills: management reporting, cost control, budgeting, forecasting, business partnering, SAP, Power BI, team leadership.\nLanguages: Slovak (native), English C1, German B2.",
  "Jozef Ďuriš — Warehouse Manager, Senec.\nExperience: 10 years logistics. Warehouse Manager at DistribHub (2016–present): runs a 12,000 m² DC, leads 35 staff over three shifts, owns inventory accuracy (99.5%) and a WMS rollout; shift supervisor earlier.\nEducation: Ing. in Logistics, University of Žilina.\nSkills: warehouse operations, inventory management, WMS, team leadership, KPIs, health & safety, continuous improvement (Lean).\nLanguages: Slovak (native), English B2.",
  "Milan Hanko — Supply Chain Analyst, Bratislava.\nExperience: 4 years supply chain. Supply Chain Analyst at GlobalParts (2020–present): runs demand planning and forecasting in SAP, analyses inventory and supplier performance, supports procurement; logistics coordinator before.\nEducation: Ing. in Logistics and Transport, University of Žilina.\nSkills: demand planning, forecasting, SAP, Excel, procurement, inventory analysis, S&OP, supplier management.\nLanguages: Slovak (native), English C1.",
  "Stanislav Repka — Forklift Operator / Warehouse Worker, Trnava.\nExperience: 6 years warehouse floor. Forklift Operator at LogiPoint (2018–present): order picking, packing, loading, reach- and counterbalance-truck operation; previous roles in manufacturing logistics.\nEducation: Secondary technical school; valid forklift licence.\nSkills: forklift operation, order picking, packing, loading/unloading, stock handling, RF scanners, health & safety.\nLanguages: Slovak (native), English A2. Availability: immediate.",
  "Renáta Vargová — Logistics Coordinator, Bratislava.\nExperience: 5 years freight and shipping. Logistics Coordinator at FreightLink (2019–present): coordinates road and sea freight, prepares customs and export documentation, liaises with carriers, manages ERP shipping records.\nEducation: Bc. in International Trade, University of Economics in Bratislava.\nSkills: freight forwarding, shipping, customs documentation, Incoterms, ERP, carrier management, scheduling.\nLanguages: Slovak (native), English C1, German B1.",
  "Barbora Kollár — Customer Success Manager, Bratislava.\nExperience: 5 years SaaS customer success. CSM at CloudSuite (2019–present): owns onboarding and retention for 60 mid-market accounts, drives adoption and upsell, 92% gross retention; support agent before moving to CS.\nEducation: Mgr. in Business Management, Comenius University Bratislava.\nSkills: customer success, SaaS onboarding, account retention, upselling, QBRs, churn reduction, CRM, stakeholder management.\nLanguages: Slovak (native), English C1, German B1.",
  "Michal Dudek — Customer Support Specialist, Košice.\nExperience: 3 years support. Support Specialist at HelpZone (2021–present): handles email and chat tickets in Zendesk, troubleshoots product issues, writes help-centre articles; call-centre agent before.\nEducation: Bc. in Information Management, Technical University of Košice.\nSkills: customer support, Zendesk, ticketing, troubleshooting, knowledge base, SLA handling, CRM.\nLanguages: Slovak (native), English C1, German B2.",
  "Alena Ferko — Call Center Agent, Bratislava.\nExperience: 4 years contact centre. Agent at ConnectLine (2020–present): inbound customer service for an international account, CRM case handling, multilingual support, high CSAT; retail customer service before.\nEducation: Secondary grammar school; business-English certificate.\nSkills: inbound support, CRM, complaint handling, multilingual service, telephony, data entry.\nLanguages: Slovak (native), English C1, German B2.",
  "Patrik Hlavatý — Technical Support Engineer, Bratislava.\nExperience: 4 years technical support. L2 Support Engineer at SaaSWorks (2020–present): resolves escalated tickets, writes SQL queries to investigate data issues, works with engineering on bug fixes, maintains runbooks.\nEducation: Ing. in Informatics, Slovak University of Technology.\nSkills: L2 technical support, SQL, troubleshooting, APIs, log analysis, Jira, SaaS, scripting basics.\nLanguages: Slovak (native), English C1.",
  "Denisa Antalová — Project Manager (IT), Bratislava.\nExperience: 7 years project management. Project Manager at DeliverIT (2017–present): runs Agile/Scrum software delivery, manages scope, budget and stakeholders across 4 teams, delivered a €1.2M platform migration; business analyst earlier.\nEducation: Ing. in Information Systems, University of Economics in Bratislava; PMP & PSM I.\nSkills: project management, Agile, Scrum, JIRA, stakeholder management, budgeting, risk management, roadmapping.\nLanguages: Slovak (native), English C1, German B1.",
  "Rastislav Benko — Product Manager, Bratislava.\nExperience: 6 years product. Product Manager at FintechApp (2018–present): owns the mobile product roadmap, runs user research and discovery, prioritises with data, works closely with engineering and design; analyst before.\nEducation: Mgr. in Information Systems, Comenius University Bratislava.\nSkills: product management, roadmapping, user research, Agile, A/B testing, analytics, stakeholder management, SaaS.\nLanguages: Slovak (native), English C1.",
  "Ivana Šuľová — Scrum Master, Žilina.\nExperience: 5 years agile delivery. Scrum Master at DevHouse (2019–present): facilitates ceremonies for two software teams, coaches on agile practices, removes impediments, tracks delivery metrics; QA engineer before.\nEducation: Bc. in Informatics, University of Žilina; PSM II.\nSkills: Scrum, agile coaching, facilitation, JIRA, Kanban, team health, continuous improvement, servant leadership.\nLanguages: Slovak (native), English C1.",
  "Marián Kubiš — Program Manager, Bratislava.\nExperience: 12 years delivery. Program Manager at EnterpriseSoft (2014–present): manages a portfolio of software programs, coordinates cross-team delivery, owns budgets and executive reporting, leads 5 project managers.\nEducation: Ing. in Management, Slovak University of Technology; PgMP.\nSkills: program/portfolio management, cross-team delivery, budgeting, governance, stakeholder management, risk, roadmapping.\nLanguages: Slovak (native), English C1, German B1.",
  "Gabriela Hofer — Registered Nurse (ICU), Bratislava.\nExperience: 5 years hospital nursing. ICU Nurse at University Hospital (2019–present): critical-care patient monitoring, ventilator and medication management, works in a multidisciplinary team; ward nurse before.\nEducation: Bc. in Nursing, Slovak Medical University; ICU specialization.\nSkills: intensive care, patient monitoring, medication administration, emergency response, EHR, patient documentation.\nLanguages: Slovak (native), German B2, English B1.",
  "Štefan Marko — Physiotherapist, Nitra.\nExperience: 6 years rehabilitation. Physiotherapist at RehabCentrum (2018–present): outpatient musculoskeletal and post-operative rehab, manual therapy, individual treatment plans; clinic assistant before.\nEducation: Mgr. in Physiotherapy, Constantine the Philosopher University in Nitra.\nSkills: rehabilitation, manual therapy, exercise therapy, patient assessment, treatment planning, electrotherapy.\nLanguages: Slovak (native), English B2, German B1.",
  "Lenka Bezáková — Medical Assistant, Bratislava.\nExperience: 4 years clinical support. Medical Assistant at a private clinic (2020–present): patient scheduling, EHR record-keeping, phlebotomy, assists physicians during exams; reception role before.\nEducation: Secondary medical school, nursing assistant qualification.\nSkills: patient scheduling, EHR, phlebotomy, vitals, clinical administration, patient care, insurance paperwork.\nLanguages: Slovak (native), English B2.",
  "Vladimír Čič — CNC Machine Operator, Trnava.\nExperience: 8 years machining. CNC Operator at PrecisionParts (2016–present): sets up and runs CNC milling and turning centres, reads technical drawings, performs quality checks; machine operator before.\nEducation: Secondary technical school, mechanical engineering.\nSkills: CNC milling, turning, machine setup, technical drawings, measurement tools, GD&T, preventive maintenance.\nLanguages: Slovak (native), German B1.",
  "Juraj Selecký — Industrial Electrician, Žilina.\nExperience: 9 years industrial maintenance. Maintenance Electrician at AutoPlant (2015–present): installs and repairs industrial wiring, troubleshoots PLC-controlled lines, performs preventive maintenance; apprenticeship earlier.\nEducation: Secondary vocational school, electrical certification (§22).\nSkills: industrial wiring, electrical maintenance, PLC basics, troubleshooting, schematics, safety standards, hand/power tools.\nLanguages: Slovak (native), German B1.",
  "Ladislav Korec — Quality Control Inspector, Bratislava.\nExperience: 7 years automotive quality. QC Inspector at CarSystems (2017–present): performs incoming and in-process inspection, uses measurement equipment, runs ISO 9001 audits and 8D problem solving; production operator before.\nEducation: Secondary technical school; ISO 9001 internal auditor.\nSkills: quality control, ISO 9001, measurement (calipers, CMM basics), inspection, 8D, SPC, automotive standards (IATF).\nLanguages: Slovak (native), English B1, German B1.",
  "Natália Rybárová — Office Manager, Bratislava.\nExperience: 8 years office administration. Office Manager at ConsultGroup (2016–present): runs office operations, manages suppliers and facilities, supports a 40-person team, coordinates events and travel; administrative assistant before.\nEducation: Bc. in Business Administration, University of Economics in Bratislava.\nSkills: office management, administration, scheduling, supplier/facilities management, MS Office, event coordination, bookkeeping basics.\nLanguages: Slovak (native), English C1, German B2.",
  "Kristína Šothová — Executive Assistant, Bratislava.\nExperience: 6 years executive support. EA to the CEO at HoldingGroup (2018–present): manages complex calendars, travel and correspondence, prepares board materials, handles confidential matters; team assistant before.\nEducation: Mgr. in Management, Comenius University Bratislava.\nSkills: calendar management, travel booking, correspondence, minutes, expense reports, discretion, MS Office, stakeholder liaison.\nLanguages: Slovak (native), English C1, French B1.",
  "Oliver Tanko — Administrative Assistant, Košice.\nExperience: 2 years administration. Administrative Assistant at ServicePoint (2022–present): data entry, document management, invoice processing and front-desk support; internship before.\nEducation: Bc. in Public Administration, Pavol Jozef Šafárik University in Košice.\nSkills: data entry, document management, MS Office, invoice processing, scheduling, customer reception.\nLanguages: Slovak (native), English B2.",
];

// Load the example pool into the paste box, ready to cluster.
function _mcLoadExamples() {
  document.getElementById('mcPasteText').value = MC_EXAMPLES.join('\n---\n');
  _mcFileCandidates = [];
  _mcRenderFiles();
  _mcUpdateCount();
  document.getElementById('mcSegments').innerHTML = '';
}

function _mcDeriveName(text, i) {
  const first = (text.split('\n')[0] || '').trim();
  const guess = first.split(/[—,|:]/)[0].slice(0, 28).trim();
  return guess || ('Candidate ' + (i + 1));
}
// Pasted profiles, split on a line containing only ---.
function _mcPasteCandidates() {
  return document.getElementById('mcPasteText').value
    .split(/^\s*---\s*$/m).map(b => b.trim()).filter(Boolean)
    .map((text, i) => ({ name: _mcDeriveName(text, i), text }));
}
function _mcAllCandidates() {
  return [..._mcPasteCandidates(), ..._mcFileCandidates];
}
function _mcUpdateCount() {
  const n = _mcAllCandidates().length;
  const el = document.getElementById('mcCount');
  if (el) el.textContent = n + (n === 1 ? ' candidate' : ' candidates');
}
async function _mcAddFiles(files) {
  for (const f of files) {
    try {
      let text = '';
      if (/\.txt$/i.test(f.name)) {
        text = await f.text();
      } else {
        const fd = new FormData(); fd.append('file', f);
        const d = await (await fetch('/api/candidate/parse-pdf', { method: 'POST', body: fd })).json();
        text = d.ok ? (d.text || '') : '';
      }
      if (text.trim()) _mcFileCandidates.push({ name: f.name.replace(/\.[^.]+$/, ''), text: text.trim() });
    } catch (e) { /* skip unreadable file */ }
  }
  _mcRenderFiles(); _mcUpdateCount();
}
function _mcRenderFiles() {
  document.getElementById('mcFiles').innerHTML = _mcFileCandidates.map((c, i) =>
    `<span class="mc-file-chip">${esc(c.name)}<button data-action="mc-remove-file" data-i="${i}" title="Remove">×</button></span>`).join('');
}
function _mcRemoveFile(i) { _mcFileCandidates.splice(i, 1); _mcRenderFiles(); _mcUpdateCount(); }

async function runClustering() {
  const cands = _mcAllCandidates();
  if (cands.length < 2) { alert('Add at least 2 candidates — separate pasted profiles with a line of ---, or add files.'); return; }
  if (cands.length > 50) { alert('Up to 50 candidates at a time (you have ' + cands.length + ').'); return; }

  _mcLastCandidates = cands;   // snapshot for member drill-down (index → CV text)
  state.mcDrilledFrom = false; _setBackToSegments(false);   // fresh clustering — drop any stale back-link
  const ov = document.getElementById('mcOverview');
  if (ov) { ov.style.display = 'none'; ov.innerHTML = ''; }   // stale overview from a prior run
  const btn  = document.getElementById('btnCluster');
  const gran = parseInt(document.getElementById('mcGranularity').value, 10) / 100;
  btn.disabled = true;
  document.getElementById('mcSegments').innerHTML = '<div class="spinner" style="margin:16px auto"></div>';

  try {
    const d = await api.post('/api/cluster', { candidates: cands, granularity: gran });
    _mcLastClusters = d.clusters || [];
    _mcRenderSegments(_mcLastClusters);
  } catch (e) {
    document.getElementById('mcSegments').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
}
function _mcRenderSegments(clusters) {
  const wrap = document.getElementById('mcSegments');
  if (!clusters || !clusters.length) { wrap.innerHTML = '<div class="mc-intro">No segments.</div>'; return; }
  clusters.forEach((cl, i) => { cl._segId = i; if (!cl._status) cl._status = 'idle'; if (cl._selected === undefined) cl._selected = false; });
  const total = clusters.reduce((n, c) => n + c.size, 0);
  wrap.innerHTML =
    `<div class="mc-step">3 · Review segments</div>
     <div class="mc-seg-bar">
       <span class="mc-count"><b>${clusters.length} segment${clusters.length !== 1 ? 's' : ''}</b> · ${total} people
         · <a class="mc-link" data-action="mc-select-all" data-all="1">select all</a>
         · <a class="mc-link" data-action="mc-select-all" data-all="0">clear</a></span>
       <span class="mc-seg-bar-actions">
         <label class="mc-minjobs">Min A/B jobs <input type="number" id="mcMinJobs" min="0" value="0" data-input-action="mc-apply-filter"></label>
         <button type="button" class="mc-btn-ghost" id="btnMatchSelected" data-action="mc-match-selected">▶ Match selected</button>
         <button type="button" class="mc-btn-ghost" id="btnOverview" data-action="mc-opportunity-overview">📈 Opportunity overview</button>
       </span>
     </div>
     <div class="mc-seg-hint">Click a segment to open it · tick the box to include it in “Match selected”.</div>` +
    clusters.map((cl, i) => `
      <div class="mc-seg-card${cl._selected ? ' selected' : ''}" id="mcSeg-${i}" data-action="mc-open-segment" data-i="${i}">
        <div class="mc-seg-head">
          <span style="display:flex;align-items:center;gap:8px;min-width:0">
            <span class="mc-seg-check" id="mcSegCheck-${i}" title="Select for matching" data-action="mc-toggle-select" data-i="${i}">${cl._selected ? '✓' : ''}</span>
            <span class="mc-seg-title">${esc(cl.title)}</span>
          </span>
          <span class="mc-seg-size">${cl.size} ${cl.size !== 1 ? 'people' : 'person'}</span>
        </div>
        <div class="mc-seg-summary">${esc(cl.summary)}</div>
        <div class="mc-seg-status" id="mcSegStatus-${i}"></div>
      </div>`).join('');
  clusters.forEach((_, i) => _mcUpdateSegStatus(i));
  _mcApplyFilter();
}

// Cross-segment opportunity overview: matches any unmatched segments first, then asks
// the LLM where the most opportunity is (candidates we have vs roles open per segment).
async function _mcOpportunityOverview() {
  const sel = _mcLastClusters.filter(cl => cl._selected);
  if (!sel.length) { alert('Select the segments you want the overview for — click cards to select them.'); return; }
  const btn   = document.getElementById('btnOverview');
  const panel = document.getElementById('mcOverview');
  panel.style.display = '';
  if (btn) btn.disabled = true;

  const unmatched = sel.filter(cl => cl._status !== 'done');
  if (unmatched.length) {
    panel.innerHTML = '<span class="mc-muted">Matching the selected segments first…</span>';
    await Promise.all(unmatched.map(cl => matchSegment(cl._segId)));
    _mcApplyFilter();
  }
  panel.innerHTML = '<div class="spinner" style="margin:12px auto"></div>';

  const segments = sel.filter(cl => cl._status === 'done').map(cl => ({
    title: cl.title, summary: cl.summary, candidates: cl.size,
    ab_jobs: cl._ab || 0, total_jobs: (cl._jobs || []).length,
    sample_jobs: (cl._jobs || []).filter(j => j.grade === 'A' || j.grade === 'B')
      .slice(0, 6).map(j => ({ title: j.title, grade: j.grade })),
  }));
  try {
    const d = await api.post('/api/cluster/overview', { segments });
    panel.innerHTML = `<div class="mc-overview-head">📈 Opportunity overview</div><div class="mc-seg-analysis-text">${esc(d.text || '')}</div>`;
  } catch (e) {
    panel.innerHTML = `<span class="mc-warn">${esc(e.message)}</span>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// Supply/demand read for a segment: A/B roles available vs candidates in the segment.
function _mcSupplyDemand(ab, size) {
  const r = ab / Math.max(size, 1);
  if (r >= 2)   return { label: 'strong demand', cls: 'mc-sd-good',  tip: `${ab} strong roles for ${size} candidate(s) — more openings than people` };
  if (r >= 0.8) return { label: 'balanced',      cls: 'mc-sd-ok',    tip: `${ab} strong roles for ${size} candidate(s)` };
  return                { label: 'oversupplied', cls: 'mc-sd-tight', tip: `only ${ab} strong role(s) for ${size} candidate(s) — more people than openings` };
}

// Save a segment's persona as a reusable synthetic (template) candidate.
async function _mcSavePersona(i, btn) {
  const cl = _mcLastClusters[i];
  if (!cl) return;
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    await api.post('/api/cluster/save_persona', { title: cl.title, persona_text: cl.persona_text,
                             members: cl.members.map(m => m.name) });
    if (btn) { btn.textContent = '✓ Saved as candidate'; }
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = '💾 Save as candidate'; }
  }
}

// Load saved candidates from the DB as a pickable pool.
let _mcDbList = [];
async function _mcLoadFromDb() {
  let d;
  try { d = await api.get('/api/cluster/candidates'); }
  catch (e) { alert('Could not load saved candidates: ' + e.message); return; }
  _mcDbList = d.candidates || [];
  if (!_mcDbList.length) { alert('No saved candidates with a profile were found.'); return; }
  document.getElementById('mcSegments').innerHTML =
    `<div class="mc-intro" style="margin-bottom:6px"><b>Select saved candidates to add to the pool:</b></div>` +
    `<div class="mc-db-list">` +
    _mcDbList.map((cnd, i) =>
      `<label class="mc-db-pick"><input type="checkbox" value="${i}"> <b>${esc(cnd.name)}</b>` +
      (cnd.title ? ` <span class="mc-muted">— ${esc(cnd.title)}</span>` : '') + `</label>`).join('') +
    `</div><div style="margin-top:10px;display:flex;gap:8px">` +
    `<button type="button" class="mc-btn-ghost" data-action="mc-add-selected-db">Add selected to pool</button>` +
    `<button type="button" class="mc-btn-ghost" data-action="mc-clear-segments">Cancel</button></div>`;
}
function _mcAddSelectedDb() {
  const picks = [...document.querySelectorAll('#mcSegments input[type=checkbox]:checked')]
    .map(c => _mcDbList[parseInt(c.value, 10)]).filter(Boolean);
  picks.forEach(p => _mcFileCandidates.push({ name: p.name, text: p.text }));
  _mcRenderFiles(); _mcUpdateCount();
  document.getElementById('mcSegments').innerHTML =
    `<div class="mc-intro">Added ${picks.length} saved candidate(s) to the pool. Click <b>Cluster candidates</b>.</div>`;
}

// Drill down: open one segment member's CV in the single-candidate workflow and match it.
function _mcDrillToCandidate(idx) {
  const cand = _mcLastCandidates[idx];
  if (!cand) return;
  closeSegmentModal();
  app.setWorkflow('single');
  const tab = document.querySelector('.mode-tab[data-mode="cv"]');
  if (tab) tab.click();                       // ensure CV input mode
  const box = document.getElementById('cvPasteText');
  if (box) box.value = cand.text;
  const nameEl = document.getElementById('candidateName');
  if (nameEl && cand.name) nameEl.value = cand.name;
  // Remember we came from a segment so the user can get back without re-clustering.
  state.mcDrilledFrom = true;
  _setBackToSegments(true);
  app.runMatching();
}

// "← Back to segments" — return to the multiple-candidate view (segments persist in
// the DOM; re-render defensively in case they were cleared).
function _setBackToSegments(show) {
  const el = document.getElementById('backToSegments');
  if (el) el.style.display = (show && state.mcDrilledFrom) ? '' : 'none';
}
function _mcBackToSegments() {
  state.mcDrilledFrom = false;
  _setBackToSegments(false);
  app.setWorkflow('multiple');
  if (_mcLastClusters && _mcLastClusters.length &&
      !document.getElementById('mcSegments').children.length) {
    _mcRenderSegments(_mcLastClusters);
  }
}

// ── Segment detail modal: candidate ranking + per-job best-fit candidates ──────
let _segModalIdx = null;
let _segChatSession = null;

function closeSegmentModal() { document.getElementById('segModal').classList.add('hidden'); }

// Chat scoped to the open segment — explanations for the clustering, fit, etc.
function _segChatHtml() {
  const cl = _mcLastClusters[_segModalIdx];
  const opts = (cl && cl.members || []).map(m => `<option value="${esc(m.name)}">${esc(m.name)}</option>`).join('');
  return `<div class="seg-chat">
    <div class="seg-chat-head">💬 Ask about this segment</div>
    <div class="seg-chat-thread" id="segChatThread"></div>
    <div class="seg-chat-tools">
      <select id="segChatCompare"><option value="">Compare a candidate…</option>${opts}</select>
      <button type="button" data-action="seg-chat-compare">Compare</button>
    </div>
    <div class="seg-chat-input">
      <input id="segChatInput" autocomplete="off"
        placeholder="e.g. Why is Marek in this group? How do these candidates differ?"
        data-keydown-action="seg-chat-enter">
      <button type="button" data-action="seg-chat-send">Ask</button>
    </div>
  </div>`;
}

// Ask the segment chat to compare one specific candidate against the rest.
function _segChatCompare() {
  const sel = document.getElementById('segChatCompare');
  const name = sel.value;
  if (!name) return;
  document.getElementById('segChatInput').value =
    `Compare ${name} against the other candidates in this segment — how do their skills and ` +
    `experience stack up, and where would they rank for the matched roles?`;
  sendSegChat();
  sel.value = '';
}
function _segChatContext() {
  const cl = _mcLastClusters[_segModalIdx];
  if (!cl) return {};
  return {
    title: cl.title, summary: cl.summary, persona_text: cl.persona_text,
    members: cl.members.map(m => ({ name: m.name, text: (_mcLastCandidates[m.index] || {}).text || '' })),
    jobs: (cl._jobs || []).filter(j => j.grade === 'A' || j.grade === 'B')
      .slice(0, 15).map(j => ({ title: j.title, grade: j.grade })),
  };
}
function _segChatAppend(text, role) {
  const el = document.createElement('div');
  el.className = 'seg-msg ' + role;
  el.textContent = text;
  const thread = document.getElementById('segChatThread');
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
}
async function sendSegChat() {
  const input = document.getElementById('segChatInput');
  const text = (input.value || '').trim();
  if (!text || _segModalIdx === null) return;
  _segChatAppend(text, 'user');
  input.value = '';
  const thread = document.getElementById('segChatThread');
  const typing = document.createElement('div');
  typing.className = 'seg-msg ai'; typing.id = 'segChatTyping'; typing.textContent = '…';
  thread.appendChild(typing); thread.scrollTop = thread.scrollHeight;
  try {
    const d = await api.post('/api/cluster/chat', { session_id: _segChatSession, message: text, segment: _segChatContext(), lang: 'en' });
    document.getElementById('segChatTyping')?.remove();
    _segChatAppend(d.text || '—', 'ai');
  } catch (e) {
    document.getElementById('segChatTyping')?.remove();
    _segChatAppend('Network error: ' + e.message, 'ai');
  }
}

function openSegmentModal(i) {
  const cl = _mcLastClusters[i];
  if (!cl) return;
  _segModalIdx = i;
  _segChatSession = 'seg-' + i + '-' + Date.now();   // fresh chat per open
  document.getElementById('segModalTitle').textContent =
    `${cl.title} · ${cl.size} ${cl.size !== 1 ? 'people' : 'person'}`;
  document.getElementById('segModalSummary').textContent = cl.summary || '';
  document.getElementById('segModal').classList.remove('hidden');

  const matched = cl._status === 'done';
  document.getElementById('segModalBody').innerHTML =
    _segMembersHtml(cl) +
    `<div id="segAddForm" class="seg-add-form" style="display:none"></div>` +
    _segActionsHtml(i, matched) +
    `<div class="seg-analysis-out" id="segAnalysisOut"></div>` +
    `<div id="segContent"></div>` +
    _segChatHtml();

  const content = document.getElementById('segContent');
  if (!matched) {
    content.innerHTML =
      `<div class="mc-intro" style="margin-top:4px">Match this segment to rank its candidates and see which fit each role best.</div>` +
      `<button type="button" class="mc-btn-ghost" data-action="seg-modal-match" data-i="${i}">▶ Match this segment</button>`;
    return;
  }
  if (cl._rank) { _segRenderRanking(i); return; }          // cached — no repeat embed call
  content.innerHTML = '<div class="spinner" style="margin:22px auto"></div>';
  _segLoadRanking(i);
}

function _segMembersHtml(cl) {
  return `<div class="seg-people"><span class="seg-lbl">People</span> ` +
    cl.members.map(m => `<span class="mc-chip mc-chip-drill" title="Open this CV in single mode" data-action="mc-drill-candidate" data-idx="${m.index}">${esc(m.name)}</span>`).join('') +
    `</div>`;
}
function _segActionsHtml(i, matched) {
  return `<div class="seg-actions">` +
    `<button type="button" class="mc-btn-ghost" data-action="seg-toggle-add-form" data-i="${i}">➕ Add candidate</button>` +
    (matched
      ? `<button type="button" class="mc-btn-ghost" data-action="seg-analyze" data-i="${i}">Analyze fit</button>` +
        `<button type="button" class="mc-btn-ghost" data-action="seg-view-jobs" data-i="${i}">View jobs in table</button>`
      : '') +
    `<button type="button" class="mc-btn-ghost" data-action="mc-save-persona" data-i="${i}">💾 Save as candidate</button>` +
    `</div>`;
}

// Reveal an inline form to manually add a candidate to this segment.
function _segToggleAddForm(i) {
  const f = document.getElementById('segAddForm');
  if (!f) return;
  if (f.style.display === 'none') {
    f.style.display = '';
    f.innerHTML =
      `<input id="segAddName" placeholder="Name (optional)">` +
      `<textarea id="segAddText" placeholder="Paste this candidate's CV / profile…"></textarea>` +
      `<div><button type="button" data-action="seg-add-candidate" data-i="${i}">Add to segment</button>` +
      `<button type="button" data-action="seg-add-form-cancel">Cancel</button></div>`;
    document.getElementById('segAddText').focus();
  } else {
    f.style.display = 'none';
  }
}

// Add the pasted candidate to this segment's members + the pool, then refresh.
function _segAddCandidate(i) {
  const cl = _mcLastClusters[i];
  const text = (document.getElementById('segAddText').value || '').trim();
  if (!text) { alert("Paste the candidate's profile first."); return; }
  let name = (document.getElementById('segAddName').value || '').trim();
  if (!name) name = _mcDeriveName(text, _mcLastCandidates.length);
  const idx = _mcLastCandidates.length;
  _mcLastCandidates.push({ name, text });
  cl.members.push({ index: idx, id: null, name });
  cl.size = cl.members.length;
  cl._rank = null;   // re-rank so the new member is included
  const sizeEl = document.querySelector(`#mcSeg-${i} .mc-seg-size`);
  if (sizeEl) sizeEl.textContent = `${cl.size} ${cl.size !== 1 ? 'people' : 'person'}`;
  openSegmentModal(i);   // refresh modal: members, ranking, chat options
}
async function _segAnalyze(i) {
  const cl = _mcLastClusters[i];
  if (!cl || cl._status !== 'done') return;
  const out = document.getElementById('segAnalysisOut');
  out.innerHTML = '<span class="mc-muted">Analyzing the segment against its matched jobs…</span>';
  try {
    const d = await api.post('/api/match/analyze', { candidate_text: cl.persona_text, jobs: (cl._jobs || []).slice(0, 30) });
    out.innerHTML = `<div class="mc-seg-analysis-text">${esc(d.text || '')}</div>`;
  } catch (e) { out.innerHTML = `<span class="mc-warn">${esc(e.message)}</span>`; }
}
function _segViewJobs(i) {
  const cl = _mcLastClusters[i];
  if (!cl || cl._status !== 'done') return;
  closeSegmentModal();
  document.querySelectorAll('.mc-seg-card').forEach((el, idx) => el.classList.toggle('viewing', idx === i));
  _mcShowSegmentResults(cl);
}

async function _segModalMatch(i) {
  document.getElementById('segModalBody').innerHTML = '<div class="spinner" style="margin:22px auto"></div>';
  await matchSegment(i);
  openSegmentModal(i);
}

async function _segLoadRanking(i) {
  const cl = _mcLastClusters[i];
  const candidates = cl.members.map(m => ({ name: m.name, text: (_mcLastCandidates[m.index] || {}).text || '' }));
  cl._abJobs = (cl._jobs || []).filter(j => j.grade === 'A' || j.grade === 'B');
  const jobs = cl._abJobs.map(j => ({ job_id: String(j.job_id), title: j.title,
    text: `${j.title} ${j.skills_en || j.skills || ''} ${(j.description || '').slice(0, 400)}` }));
  if (!jobs.length) {
    document.getElementById('segContent').innerHTML = '<div class="mc-intro">No strong (A/B) roles matched this segment.</div>';
    return;
  }
  try {
    const d = await api.post('/api/cluster/rank', { candidates, jobs });
    cl._rank = d;
    _segRenderRanking(i);
  } catch (e) {
    document.getElementById('segContent').innerHTML = `<div class="error-box">${esc(e.message)}</div>`;
  }
}

function _segRankRows(rows) {
  return rows.map((r, k) =>
    `<div class="seg-rank-row"><span class="seg-rank-name">${k + 1}. ${esc(r.name)}</span>
       <span class="seg-rank-bar"><span class="seg-rank-fill" style="width:${r.pct}%"></span></span>
       <span class="seg-rank-pct">${r.pct}%</span></div>`).join('');
}

function _segRenderRanking(i) {
  const cl = _mcLastClusters[i];
  const jobsHtml = (cl._abJobs || []).map((j, jx) =>
    `<div class="seg-job-row" id="segJob-${jx}" data-action="seg-job-click" data-i="${i}" data-jx="${jx}">
       <span class="grade ${gradeClass(j.grade)}">${j.grade}</span>
       <span style="flex:1;min-width:0">${esc(j.title)} <span class="mc-muted">@ ${esc(j.company || '')}</span></span>
       <span class="seg-rank-pct">${j.score_pct || ''}</span></div>`).join('');
  document.getElementById('segContent').innerHTML =
    `<div class="seg-rank-sec"><h4>Candidates ranked by fit to the segment's strong roles</h4>${_segRankRows(cl._rank.candidate_ranking)}</div>` +
    `<div class="seg-rank-sec"><h4>Strong roles — click a role to see who fits it best</h4>${jobsHtml}</div>` +
    `<div id="segJobFit"></div>`;
}

function _segJobClick(i, jx) {
  const cl = _mcLastClusters[i];
  const job = cl._abJobs[jx];
  document.querySelectorAll('.seg-job-row').forEach((el, k) => el.classList.toggle('active', k === jx));
  const fits = (cl._rank.job_fits || {})[String(job.job_id)] || [];
  document.getElementById('segJobFit').innerHTML =
    `<div class="seg-job-fit">
       <h4>Best fit for “${esc(job.title)}” <span class="mc-muted">(embedding similarity)</span></h4>
       ${_segRankRows(fits.slice(0, 8))}
       <button type="button" class="mc-seg-analyze" style="margin-top:8px" data-action="seg-grade-job" data-i="${i}" data-jx="${jx}">⚖ Grade with AI (precise)</button>
       <div id="segGradeOut"></div>
     </div>`;
}

async function _segGradeJobAI(i, jx) {
  const cl = _mcLastClusters[i];
  const job = cl._abJobs[jx];
  const candidates = cl.members.map(m => ({ name: m.name, text: (_mcLastCandidates[m.index] || {}).text || '' }));
  const out = document.getElementById('segGradeOut');
  out.innerHTML = '<span class="mc-muted">Grading each candidate against this role…</span>';
  try {
    const d = await api.post('/api/cluster/grade_job', { job: { title: job.title, company: job.company, skills: job.skills,
                                    skills_en: job.skills_en, description: job.description }, candidates });
    out.innerHTML = '<div style="margin-top:8px">' + d.candidates.map(r =>
      `<div class="seg-rank-row"><span class="grade ${gradeClass(r.grade)}">${r.grade}</span>
         <span class="seg-rank-name">${esc(r.name)} <span class="mc-muted">${esc(r.reason || '')}</span></span>
         <span class="seg-rank-pct">${r.score_pct}</span></div>`).join('') + '</div>';
  } catch (e) {
    out.innerHTML = `<span class="mc-warn">${esc(e.message)}</span>`;
  }
}

function _mcUpdateSegStatus(i) {
  const cl = _mcLastClusters[i];
  const el = document.getElementById('mcSegStatus-' + i);
  if (!cl || !el) return;
  if (cl._status === 'matching') {
    el.innerHTML = '<span class="mc-muted">⟳ matching…</span>';
  } else if (cl._status === 'done') {
    const sd = cl._signal;
    el.innerHTML =
      `<span class="mc-ab">${cl._ab} A/B job${cl._ab !== 1 ? 's' : ''}</span>` +
      (sd ? ` <span class="mc-sd ${sd.cls}" title="${esc(sd.tip)}">${esc(sd.label)}</span>` : '');
  } else if (cl._status === 'error') {
    el.innerHTML = '<span class="mc-warn">match failed</span>';
  } else {
    el.innerHTML = '<span class="mc-muted">not matched yet</span>';
  }
}

// Match one segment's persona against the job market — same engine as a single
// candidate. Stores the graded jobs on the cluster for later viewing.
async function matchSegment(i) {
  const cl = _mcLastClusters[i];
  if (!cl || cl._status === 'matching') return;
  cl._status = 'matching'; _mcUpdateSegStatus(i);
  try {
    const d = await api.post('/api/match', { candidate_text: cl.persona_text });
    cl._jobs   = d.jobs || [];
    cl._ab     = cl._jobs.filter(j => j.grade === 'A' || j.grade === 'B').length;
    cl._signal = _mcSupplyDemand(cl._ab, cl.size);
    cl._status = 'done';
  } catch (e) {
    cl._jobs = []; cl._status = 'error';
  }
  _mcUpdateSegStatus(i);
  _mcApplyFilter();
}

// Click a segment card to SELECT it (does not match — no API call). Matching only
// happens for selected segments when you press "Match selected".
function _mcToggleSelect(i) {
  const cl = _mcLastClusters[i];
  if (!cl) return;
  cl._selected = !cl._selected;
  document.getElementById('mcSeg-' + i)?.classList.toggle('selected', cl._selected);
  const chk = document.getElementById('mcSegCheck-' + i);
  if (chk) chk.textContent = cl._selected ? '✓' : '';
}
function _mcSelectAll(on) {
  _mcLastClusters.forEach((cl, i) => {
    cl._selected = !!on;
    document.getElementById('mcSeg-' + i)?.classList.toggle('selected', !!on);
    const chk = document.getElementById('mcSegCheck-' + i);
    if (chk) chk.textContent = on ? '✓' : '';
  });
}

// Match ONLY the selected segments (each an independent candidate-style search, run
// in parallel). Nothing else spends credits.
async function matchSelectedSegments() {
  const sel = _mcLastClusters.filter(cl => cl._selected);
  if (!sel.length) { alert('Select one or more segments first — click a card to select it.'); return; }
  const btn = document.getElementById('btnMatchSelected');
  if (btn) btn.disabled = true;
  await Promise.all(sel.map(cl => matchSegment(cl._segId)));
  if (btn) btn.disabled = false;
  _mcApplyFilter();
}

// Hide matched segments whose A/B job count is below the "Min A/B jobs" filter.
function _mcApplyFilter() {
  const min = parseInt(document.getElementById('mcMinJobs')?.value || '0', 10) || 0;
  _mcLastClusters.forEach((cl, i) => {
    const card = document.getElementById('mcSeg-' + i);
    if (card) card.style.display = (cl._status === 'done' && (cl._ab || 0) < min) ? 'none' : '';
  });
}

function _mcShowSegmentResults(cl) {
  state.lastResults        = cl._jobs || [];
  state.lastMatchText     = cl.persona_text;   // per-job chat / analyze use this persona
  state.scoredAgainstText = cl.persona_text;   // keep the re-score guard consistent
  app.renderResults(state.lastResults);
  if (typeof updateMapStats === 'function') updateMapStats(state.lastResults);
  if (typeof app.reapplyHighlight === 'function') app.reapplyHighlight();
  document.querySelector('.results-wrap')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Action registry for the Multiple-CV cluster feature (replaces inline onclick/oninput/onkeydown).
Object.assign(_ACTIONS, {
  'mc-remove-file':          (el)    => _mcRemoveFile(+el.dataset.i),
  'mc-select-all':           (el)    => _mcSelectAll(el.dataset.all === '1'),
  'mc-apply-filter':         ()      => _mcApplyFilter(),
  'mc-match-selected':       ()      => matchSelectedSegments(),
  'mc-opportunity-overview': ()      => _mcOpportunityOverview(),
  'mc-open-segment':         (el)    => openSegmentModal(+el.dataset.i),
  'mc-toggle-select':        (el, e) => { e.stopPropagation(); _mcToggleSelect(+el.dataset.i); },
  'mc-add-selected-db':      ()      => _mcAddSelectedDb(),
  'mc-clear-segments':       ()      => { document.getElementById('mcSegments').innerHTML = ''; },
  'seg-chat-compare':        ()      => _segChatCompare(),
  'seg-chat-send':           ()      => sendSegChat(),
  'seg-chat-enter':          (el, e) => { if (e.key === 'Enter') { e.preventDefault(); sendSegChat(); } },
  'mc-drill-candidate':      (el)    => _mcDrillToCandidate(+el.dataset.idx),
  'seg-modal-match':         (el)    => _segModalMatch(+el.dataset.i),
  'seg-toggle-add-form':     (el)    => _segToggleAddForm(+el.dataset.i),
  'seg-analyze':             (el)    => _segAnalyze(+el.dataset.i),
  'seg-view-jobs':           (el)    => _segViewJobs(+el.dataset.i),
  'mc-save-persona':         (el)    => _mcSavePersona(+el.dataset.i, el),
  'seg-add-candidate':       (el)    => _segAddCandidate(+el.dataset.i),
  'seg-add-form-cancel':     ()      => { document.getElementById('segAddForm').style.display = 'none'; },
  'seg-job-click':           (el)    => _segJobClick(+el.dataset.i, +el.dataset.jx),
  'seg-grade-job':           (el)    => _segGradeJobAI(+el.dataset.i, +el.dataset.jx),
});


// Action registry for the Multiple-CV pool controls in the search-tab markup
// (paste/upload zone, examples/db-load buttons, the Cluster button) — split out
// of the search-tab's mixed registry block since these route to this module.
Object.assign(_ACTIONS, {
  'mc-back-to-segments':     ()      => _mcBackToSegments(),
  'mc-update-count':         ()      => _mcUpdateCount(),
  'mc-add-files':            (el)    => { _mcAddFiles(el.files); el.value = ''; },
  'mc-load-examples':        ()      => _mcLoadExamples(),
  'mc-add-files-click':      ()      => document.getElementById('mcFileInput').click(),
  'mc-load-from-db':         ()      => _mcLoadFromDb(),
  'run-clustering':          ()      => runClustering(),
});

// Cross-module exports — registered on app so candidate.js (workflow toggle,
// clear-profile) and modal.js (segment-modal backdrop/close) can call into
// this module without a direct import (avoids a circular reference).
Object.assign(app, { _setBackToSegments, closeSegmentModal });
