const $ = s => document.querySelector(s);
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const EMPTY = "n/a";
function normalizeDashes(s){ return String(s==null?"":s).replace(/\s*—\s*/g,", "); }

function formatInlineMd(s){
  let t=esc(normalizeDashes(s));
  t=t.replace(/\*\*(.+?)\*\*/g,"<strong>$1</strong>");
  t=t.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g,"<em>$1</em>");
  t=t.replace(/_([^_\n]+)_/g,"<em>$1</em>");
  return t;
}

function formatBlocks(raw){
  if(raw==null||raw==="") return "";
  const text=normalizeDashes(raw).replace(/\r\n/g,"\n");
  const blocks=text.split(/\n\s*\n/);
  let html="";
  for(const block of blocks){
    const lines=block.split("\n").map(l=>l.trim()).filter(Boolean);
    if(!lines.length) continue;
    const bullet=lines.every(l=>/^[-*•]\s+/.test(l));
    const numbered=lines.every(l=>/^\d+[.)]\s+/.test(l));
    if(bullet&&lines.length){
      html+=`<ul class="memo-list">${lines.map(l=>`<li>${formatInlineMd(l.replace(/^[-*•]\s+/,""))}</li>`).join("")}</ul>`;
    } else if(numbered&&lines.length){
      html+=`<ol class="memo-list">${lines.map(l=>`<li>${formatInlineMd(l.replace(/^\d+[.)]\s+/,""))}</li>`).join("")}</ol>`;
    } else {
      html+=`<p>${formatInlineMd(lines.join(" "))}</p>`;
    }
  }
  return html;
}

function formatMdDoc(raw, opts={}){
  if(raw==null||String(raw).trim()==="") return `<p class="memo-empty">Empty — fill via chat or your editor.</p>`;
  const lines=String(raw).replace(/\r\n/g,"\n").split("\n");
  let html="", para=[], list=null;
  const flushPara=()=>{ if(para.length){ html+=`<p>${formatInlineMd(para.join(" "))}</p>`; para=[]; } };
  const closeList=()=>{ if(list){ html+=`</${list.tag}>`; list=null; } };
  const pushListItem=(tag,line)=>{
    if(!list||list.tag!==tag){ flushPara(); closeList(); html+=`<${tag} class="memo-list">`; list={tag}; }
    const item=tag==="ul"?line.replace(/^[-*•]\s+/,""):line.replace(/^\d+[.)]\s+/,"");
    html+=`<li>${formatInlineMd(item)}</li>`;
  };
  for(const line of lines){
    const t=line.trim();
    if(!t){ flushPara(); closeList(); continue; }
    if(/^#{1,3}\s+/.test(t)){
      flushPara(); closeList();
      const lvl=(t.match(/^#+/)||["#"])[0].length;
      if (opts.dropH1 && lvl === 1) continue;
      const txt=t.replace(/^#+\s+/,"");
      html+=lvl<=1?`<h3 class="md-h">${esc(txt)}</h3>`:`<h4 class="md-h">${esc(txt)}</h4>`;
    } else if(/^[-*•]\s+/.test(t)) pushListItem("ul",t);
    else if(/^\d+[.)]\s+/.test(t)) pushListItem("ol",t);
    else { closeList(); para.push(t); }
  }
  flushPara(); closeList();
  return html||`<p class="memo-empty">Empty — fill via chat or your editor.</p>`;
}

function memoField(label,value){
  const body=formatBlocks(value);
  return body?`<div class="memo-field">${label?`<b>${esc(label)}</b>`:""}${body}</div>`:"";
}

const MEMO_BODY_META=new Set(["status","date","version"]);
/** Fallback until /api/schemas loads — keep in sync with core/project_schemas.py */
const MEMO_FIELD_LABELS_FALLBACK={
  problem_statement:"Problem", who_has_it:"Who", current_workaround:"Workaround",
  cheapest_next_test:"Next test", willingness_to_pay_signal:"WTP signal",
  pace_recommendation:"Pace", riskiest_assumption:"Riskiest assumption",
  recommendation:"Call", summary:null, evidence:"Evidence",
};
const MEMO_FIELD_ORDER_FALLBACK={
  "problem-validation":["problem_statement","who_has_it","_status","current_workaround","willingness_to_pay_signal","cheapest_next_test","evidence","recommendation"],
  assessment:["pace_recommendation","riskiest_assumption","recommendation"],
  _default:["summary","recommendation"],
};

function memoFieldOrder(type){
  const o = _SCHEMAS?.memo_render_order?.[type];
  if (o && o.length) return o;
  return MEMO_FIELD_ORDER_FALLBACK[type] || MEMO_FIELD_ORDER_FALLBACK._default;
}
function memoFieldLabel(key){
  const fromApi = _SCHEMAS?.memo_field_labels?.[key];
  if (fromApi != null) return fromApi;
  if (key in MEMO_FIELD_LABELS_FALLBACK) return MEMO_FIELD_LABELS_FALLBACK[key];
  return humanizeKey(key);
}

function renderMemoEvidence(list){
  if(!Array.isArray(list)||!list.length) return "";
  const items=list.map(e=>{
    if(e&&typeof e==="object"){
      const sig=e.signal||e.text||e.note||"";
      const tag=e.strength||e.kind||"signal";
      const src=e.source?` <span class="memo-src">(${esc(e.source)})</span>`:"";
      return `<li><b>${esc(tag)}</b> ${formatInlineMd(sig)}${src}</li>`;
    }
    return `<li>${formatInlineMd(e)}</li>`;
  }).join("");
  return `<div class="memo-field"><b>Evidence</b><ul class="memo-list">${items}</ul></div>`;
}

function renderMemoValue(key,val){
  if(val==null||val==="") return "";
  if(key==="evidence"&&Array.isArray(val)) return renderMemoEvidence(val);
  if(Array.isArray(val)){
    if(!val.length) return "";
    const items=val.map(v=>`<li>${typeof v==="object"?esc(JSON.stringify(v)):formatInlineMd(v)}</li>`).join("");
    const label=memoFieldLabel(key);
    return `<div class="memo-field"><b>${esc(label)}</b><ul class="memo-list">${items}</ul></div>`;
  }
  const label=memoFieldLabel(key);
  if(label===null) return `<div class="memo-field">${formatBlocks(val)}</div>`;
  return memoField(label, val);
}

function renderMemoBody(b,type){
  const order=memoFieldOrder(type);
  const seen=new Set();
  let html="";
  for(const key of order){
    if(key==="_status"&&type==="problem-validation"){
      html+=`<div class="memo-field"><b>Status</b><p>${esc(b.validation_status||"?")} · severity ${esc(b.severity||"?")} · ${esc(b.frequency||EMPTY)}</p></div>`;
      seen.add("validation_status"); seen.add("severity"); seen.add("frequency");
      continue;
    }
    if(seen.has(key)||!(key in b)) continue;
    seen.add(key);
    html+=renderMemoValue(key,b[key]);
  }
  for(const [key,val] of Object.entries(b||{})){
    if(MEMO_BODY_META.has(key)||seen.has(key)) continue;
    if(val==null||val===""||(Array.isArray(val)&&!val.length)) continue;
    html+=renderMemoValue(key,val);
  }
  return html;
}

function formatChatText(raw){
  return formatBlocks(raw);
}
const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
function toast(m,sticky){const t=$("#toast");t.textContent=m;t.style.opacity=1;clearTimeout(t._timer);if(!sticky)t._timer=setTimeout(()=>t.style.opacity=0,2400);}
async function api(p,o){const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j;}
function jpost(p,body){return api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});}
function postUrl(id, profileSlug, suffix=""){
  const base = `/api/post/${id}${suffix}`;
  return profileSlug ? `${base}?profile=${encodeURIComponent(profileSlug)}` : base;
}

// ── router ───────────────────────────────────────────────────────────────────
let _NAV_EXTRAS = {};
function navigate(hash, extras){
  _NAV_EXTRAS = extras || {};
  if(location.hash===hash) parseRoute(hash);
  else location.hash = hash;
}
const ROUTES = [
  [/^\/calendar$/,                              ()       => { setState("calendar"); renderTimeline(); }],
  [/^\/operations$/,                            ()       => { setState("operations"); renderOperations(); }],
  [/^\/needs$/,                                 ()       => { setState("needs"); renderNeeds(); }],
  [/^\/project\/new$/,                          ()       => renderNewProject()],
  [/^\/project\/([^/]+)\/edit$/,                ([s])    => renderEditProject(s)],
  [/^\/project\/([^/]+)\/delete$/,              ([s])    => renderConfirmDeleteProject(s)],
  [/^\/project\/([^/]+)\/profile\/new$/,        ([s])    => renderNewProfile(s)],
  [/^\/project\/([^/]+)\/intake\/new$/,          ([s])    => renderNewIntake(s)],
  [/^\/project\/([^/]+)\/technical\/new$/,       ([s])    => renderNewTechnical(s)],
  [/^\/project\/([^/]+)\/technical\/subsection\/new$/, ([s]) => renderNewDocSubsection(s, "technical")],
  [/^\/project\/([^/]+)\/technical\/subsection\/edit\/([^/]+)$/, ([s,k]) => renderEditDocSubsection(s, "technical", k, _NAV_EXTRAS)],
  [/^\/project\/([^/]+)\/memo\/new\/([^/]+)$/,   ([s,t])  => renderNewMemo(s,t)],
  [/^\/project\/([^/]+)\/experiment\/new$/,     ([s])    => renderNewExperiment(s)],
  [/^\/project\/([^/]+)\/product\/new$/,          ([s])    => renderNewProduct(s)],
  [/^\/product\/([^/]+)\/feature\/new$/,         ([ps])   => renderNewFeature(ps, _NAV_EXTRAS.projectSlug)],
  [/^\/project\/([^/]+)\/([^/]+)$/,             ([s,k])  => { setState("section",{project:s,section:k}); OPEN.projects.add(s); saveOpen(); renderProjectSection(s,k); }],
  [/^\/profile\/([^/]+)\/setup$/,               ([s])    => { setState("profileSetup",{profile:s}); _expandProfile(s); renderProfileSetup(s); }],
  [/^\/profile\/([^/]+)\/delete$/,              ([s])    => renderConfirmDeleteProfile(s)],
  [/^\/profile\/([^/]+)\/add$/,                 ([s])    => renderAddIdea(s)],
  [/^\/profile\/([^/]+)\/generate$/,            ([s])    => renderGenerateIdeas(s)],
  [/^\/profile\/([^/]+)\/channel\/new$/,        ([s])    => renderNewChannel(s)],
  [/^\/profile\/([^/]+)$/,                      ([s])    => { setState("profile",{profile:s}); _expandProfile(s); renderProfile(s, _NAV_EXTRAS.chanFilter||null); }],
  [/^\/channel\/([^/]+)\/setup$/,               ([s])    => renderChannelSetup(s, _NAV_EXTRAS.profileSlug||"")],
  [/^\/channel\/([^/]+)\/delete$/,              ([s])    => renderConfirmDeleteChannel(s, _NAV_EXTRAS.profileSlug||"")],
  [/^\/post\/([^/]+)\/revise$/,                 ([id])   => renderRevise(id)],
  [/^\/post\/([^/]+)\/edit$/,                   ([id])   => renderEditPost(id, _NAV_EXTRAS.profileSlug||"")],
  [/^\/post\/([^/]+)\/delete$/,                 ([id])   => renderConfirmDelete(id, _NAV_EXTRAS.profileSlug||"")],
  [/^\/post\/([^/]+)$/,                         ([id])   => renderPostDetail(id, _NAV_EXTRAS.profileSlug||"")],
  [/^\/posts\/delete$/,                         ()       => renderConfirmBulkDelete(_NAV_EXTRAS.ids||[], _NAV_EXTRAS.profileSlug||"")],
  [/^\/activity\/new$/,                         ()       => renderNewActivity(_NAV_EXTRAS)],
  [/^\/milestone\/new$/,                        ()       => renderNewMilestone(_NAV_EXTRAS)],
  [/^\/milestone\/([^/]+)\/edit$/,              ([id])   => renderEditMilestone(id, _NAV_EXTRAS)],
];
function parseRoute(hash){
  const path = (hash||"#/calendar").replace(/^#/,"").replace(/\?.*$/,"");
  CURRENT_POST = null;
  CURRENT_PROFILE_SLUG = null;
  const ex = _NAV_EXTRAS; _NAV_EXTRAS = {};
  for(const [re, fn] of ROUTES){
    const m = path.match(re);
    if(m){
      _NAV_EXTRAS = ex;
      const out = fn(m.length>1?m.slice(1):[]);
      if (out && typeof out.then === "function") void out;
      _NAV_EXTRAS={}; highlight(); return;
    }
  }
  navigate("#/calendar");
}
function setState(view, extra={}){
  STATE={view, project:extra.project||null, section:extra.section||null,
         profile:extra.profile||null, channelGuidelines:extra.channelGuidelines||null};
}
function _expandProfile(slug){
  const pp=_TREE.find(p=>p.profiles.some(pr=>pr.slug===slug));
  if(pp){ OPEN.projects.add(pp.slug); saveOpen(); }
}
window.addEventListener("hashchange", ()=>parseRoute(location.hash));

// ── form helpers ─────────────────────────────────────────────────────────────
const flabel = (t, osId=null) => {
  const chip = osId ? ` <span class="label-id">${sectionIdChip(osId)}</span>` : "";
  return `<label class="flabel">${esc(t)}${chip}</label>`;
};
const finput = (name,val='',extra='',osId=null) => `<input name="${name}"${osId?` data-os-id="${esc(osId)}"`:""} value="${esc(val)}" ${extra}>`;
const fsel = (name,opts,val,osId=null) => `<select name="${name}"${osId?` data-os-id="${esc(osId)}"`:""}>`+opts.map(([v,l])=>`<option value="${esc(v)}"${v===val?" selected":""}>${esc(l)}</option>`).join("")+`</select>`;
const fta = (name,val='',rows=5,extra='',osId=null) => `<textarea name="${name}" rows="${rows}"${osId?` data-os-id="${esc(osId)}"`:""} ${extra}>${esc(val)}</textarea>`;
const mentionBare = c => {
  if (c.osId && c.osId.includes(".")) return c.osId.split(".").pop();
  if (c.osId && c.osId.includes(":")) return c.osId.split(":").pop();
  return c.slug;
};
function formVals(root){ const d={}; root.querySelectorAll("[name]").forEach(i=>d[i.name]=i.value); return d; }
function pageHeader(title, crumb, btns='', pageId=null){
  const idBar = pageId ? `<div class="sec-meta" style="margin-top:5px">${sectionIdChip(pageId, {dropTabSuffix:true})}</div>` : "";
  return `<div class="topbar"><div><div class="crumbs"><a class="bk" style="cursor:pointer;color:var(--navy)">← ${esc(crumb)}</a></div><h1 class="title">${esc(title)}</h1>${idBar}</div><div style="margin-left:auto;display:flex;gap:8px">${btns}</div></div>`;
}
document.addEventListener("click", e=>{ if(e.target.classList.contains("bk")) history.back(); });

// ── undo toast (for small reversible deletes) ────────────────────────────────
function undoToast(msg, undoFn){
  const t=$("#toast");
  t.innerHTML=`${esc(msg)} <button>Undo</button>`;
  t.style.opacity=1; clearTimeout(t._timer);
  t.querySelector("button").onclick=async()=>{ t.style.opacity=0; try{await undoFn();}catch(e){toast("✗ "+e.message);} };
  t._timer=setTimeout(()=>t.style.opacity=0, 8000);
}

const SECTIONS = PROJECT_SECTIONS;
let STATE = {view:"calendar", project:null, section:null, profile:null, channelGuidelines:null};
let _TREE = [];
let _POSTS = [];   // flat post index for @-mentions, refreshed in renderRail
let _SKILLS = [];  // [{name, description}] for the manual skill picker (/ and ⊕)
// Post open in detail view. Full slot+brief inlined only when the turn needs it
// (content keywords, @mention) — otherwise a compact pointer saves tokens.
// Set in renderPostDetail, cleared on every navigation in parseRoute.
let CURRENT_POST = null;
// Profile slug for the current main view — lean pointer by default; voice/spec
// only when the turn is content-related or user @mentions the profile.
let CURRENT_PROFILE_SLUG = null;

// Rail fold state — which projects/profiles are expanded. Persisted so folds
// survive the full renderRail() that fires after every chat action / refresh.
const OPEN = loadOpen();
function loadOpen(){
  try{ const o = JSON.parse(localStorage.getItem("gtmos.rail.open") || "{}");
    return { projects:new Set(o.projects||[]), profiles:new Set(o.profiles||[]) }; }
  catch{ return { projects:new Set(), profiles:new Set() }; }
}
function saveOpen(){
  localStorage.setItem("gtmos.rail.open",
    JSON.stringify({ projects:[...OPEN.projects], profiles:[...OPEN.profiles] }));
}
// A node is open if it's in the OPEN set (persisted). Navigate actions below
// auto-add the parent to OPEN so navigating to a child keeps it visible,
// but the user can still manually collapse the parent afterwards.
function isOpen(kind, slug){
  if(kind === "projects") return OPEN.projects.has(slug);
  if(kind === "profiles") return OPEN.profiles.has(slug);
  return false;
}
function toggleOpen(kind, slug){
  const set = OPEN[kind];
  set.has(slug) ? set.delete(slug) : set.add(slug);
  saveOpen(); renderRail();
}

async function boot(){ await ensureSchemas(); await renderRail(); parseRoute(location.hash||"#/calendar"); }

async function ensureIdRegistry(force=false){
  if (!force && Object.keys(IdReg.lookup || {}).length) return;
  try { IdReg.load(await api("/api/id-registry")); }
  catch { IdReg.load({}); }
}

async function refreshIdRegistry(){
  try { IdReg.load(await api("/api/id-registry")); }
  catch { IdReg.load({}); }
}

let _SCHEMAS = null;
async function ensureSchemas(force=false){
  if (!force && _SCHEMAS) return _SCHEMAS;
  try { _SCHEMAS = await api("/api/schemas"); }
  catch { _SCHEMAS = { memos: {}, experiment: [], feature: [] }; }
  setSchemas(_SCHEMAS);
  return _SCHEMAS;
}

function renderSchemaField(spec){
  const key = spec.key;
  const label = spec.label || humanizeKey(key);
  const req = spec.required ? " required" : "";
  const ph = spec.placeholder ? ` placeholder="${esc(spec.placeholder)}"` : "";
  if (spec.type === "textarea" || spec.type === "evidence") {
    const hint = spec.type === "evidence" ? ' placeholder="One signal per line"' : ph;
    return `${flabel(label)}${fta(key, "", spec.rows || 3, hint + req)}`;
  }
  if (spec.type === "select") {
    const opts = (spec.options || []).map(o => [o, o === "" ? "—" : (o.charAt(0).toUpperCase() + o.slice(1))]);
    return `${flabel(label)}${fsel(key, opts, spec.default || opts[0]?.[0] || "")}`;
  }
  return `${flabel(label)}${finput(key, "", ph + req)}`;
}

function schemaFields(kind, memoType=null){
  const s = _SCHEMAS || {};
  if (kind === "memo") return (s.memos && s.memos[memoType]) || [];
  if (kind === "experiment") return s.experiment || [];
  if (kind === "feature") return s.feature || [];
  return [];
}

async function renderRail(){
  const skillsP = _SKILLS.length ? Promise.resolve(_SKILLS) : api("/api/skills-index").catch(() => []);
  const regP = api("/api/id-registry").then(d => { IdReg.load(d); }).catch(() => IdReg.load({}));
  const schP = ensureSchemas();
  [_TREE, _POSTS, _SKILLS] = await Promise.all([api("/api/tree"), api("/api/posts-index").catch(() => []), skillsP, regP, schP]);
  await ensureIdRegistry();
  const projects = _TREE.map(p=>{
    const totalFeatures = p.products.reduce((n,prod)=>n+prod.features,0);
    const profileRows = p.profiles.length ? p.profiles.map(prof=>{
      const hasCh = prof.channels.length > 0;
      const profOpen = !hasCh || isOpen("profiles", prof.slug);
      const wedge = hasCh ? (profOpen ? "▾" : "▸") : "·";
      const channelsBlock = prof.channels.length ? `<div class="kid" style="margin-top:1px;margin-bottom:2px">
        ${prof.channels.map(ch=>`<a data-profile="${esc(prof.slug)}" data-chan-filter="${esc(ch.slug)}" style="display:flex;align-items:center;gap:6px;cursor:pointer;flex-wrap:wrap"><span style="opacity:.5">${PLATFORM_ICON[ch.platform]||"⌗"}</span>${esc(ch.name||ch.platform)}</a>`).join("")}
        <a data-new-channel="${esc(prof.slug)}" style="color:var(--navy)!important;font-weight:normal!important">＋ Channel</a>
      </div>` : ``;
      return `<a data-profile="${esc(prof.slug)}" style="display:flex;align-items:center;gap:6px;padding:4px 9px;border-radius:10px;text-decoration:none;cursor:pointer;flex-wrap:wrap">
        <span data-toggle-profile="${esc(prof.slug)}" style="opacity:.45;font-size:9px;width:9px;text-align:center;cursor:pointer;flex-shrink:0">${wedge}</span>
        ${esc(prof.name)}<span class="c">${prof.posts}</span>
      </a>
      ${hasCh && profOpen ? channelsBlock : ""}`;
    }).join("") : `<a style="color:var(--dim);font-size:12px;padding:4px 9px">No profiles yet</a>`;
    const pOpen = isOpen("projects", p.slug);
    return `
    <div style="margin-top:6px">
      <div data-toggle-project="${esc(p.slug)}" style="display:flex;align-items:center;gap:7px;font:700 13px/1 var(--disp);padding:4px 9px;border-radius:10px;cursor:pointer;color:var(--ink2);flex-wrap:wrap">
        <span style="opacity:.45;font-size:10px;width:9px;display:inline-block">${pOpen?"▾":"▸"}</span>${esc(p.name)}
        <span style="margin-left:auto;font:600 9px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--navy);background:var(--sky-soft);padding:2px 6px;border-radius:20px">${esc(p.kind||p.type)}</span>
        <button class="rail-edit" data-edit-project="${esc(p.slug)}" data-os-id="${esc(OSID.route(`project/${p.slug}/edit`))}" title="Edit project">✎</button></div>
      ${pOpen ? `<nav class="sec">
        ${SECTIONS.map(s=>`<a data-project="${esc(p.slug)}" data-section="${s.key}" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><span class="ico">${s.ico}</span> ${esc(s.label)}${
          s.key==="experiments"&&p.experiments?`<span class="c">${p.experiments}</span>`:
          s.key==="product"&&totalFeatures?`<span class="c">${totalFeatures}</span>`:""}</a>`).join("")}
        <div class="grp" style="display:flex;align-items:center">Profiles
          <button class="add-btn" data-new-profile="${esc(p.slug)}" data-os-id="${esc(OSID.btn("proj",p.slug,"new-profile"))}" style="margin-left:auto" title="Add profile">＋</button></div>
        ${profileRows}
      </nav>` : ""}
    </div>`;
  }).join("");
  $("#rail").innerHTML = `
    <div class="brand" id="brand-btn"><span class="mark"></span><b>GTM&nbsp;OS</b>
      <div class="brand-menu" id="brand-menu"><a id="quit-btn">Quit GTM OS</a></div>
    </div>
    <nav class="nav">
      <a data-view="needs"><span class="ico">◉</span> Needs you</a>
      <a data-view="calendar"><span class="ico">▦</span> Calendar</a>
      <a data-view="operations"><span class="ico">✓</span> Operations</a>
    </nav>
    <div class="rail-hdr"><span class="label">Projects</span>
      <button class="add-btn" id="new-project-btn" data-os-id="btn:global:new-project" title="New project">＋</button></div>
    ${projects || '<div style="padding:8px 12px;color:var(--dim);font-size:12px">No projects yet — click ＋ to create one</div>'}
    `;
  $("#rail").querySelectorAll("[data-view]").forEach(a=>a.onclick=()=>selectGlobal(a.dataset.view));
  $("#rail").querySelectorAll("[data-section]").forEach(a=>a.onclick=()=>selectSection(a.dataset.project,a.dataset.section));
  $("#rail").querySelectorAll("[data-profile]").forEach(a=>a.onclick=e=>{ e.stopPropagation(); selectProfile(a.dataset.profile, a.dataset.chanFilter||null); });
  $("#rail").querySelectorAll("[data-new-profile]").forEach(b=>b.onclick=e=>{ e.stopPropagation(); openNewProfile(b.dataset.newProfile); });
  $("#rail").querySelectorAll("[data-new-channel]").forEach(b=>b.onclick=e=>{ e.stopPropagation(); openNewChannel(b.dataset.newChannel); });
  $("#rail").querySelectorAll("[data-edit-project]").forEach(b=>b.onclick=e=>{ e.stopPropagation(); openEditProject(b.dataset.editProject); });
  $("#rail").querySelectorAll("[data-toggle-project]").forEach(el=>el.onclick=e=>{ e.stopPropagation(); toggleOpen("projects", el.dataset.toggleProject); });
  $("#rail").querySelectorAll("[data-toggle-profile]").forEach(el=>el.onclick=e=>{ e.stopPropagation(); toggleOpen("profiles", el.dataset.toggleProfile); });
  $("#new-project-btn").onclick=e=>{ e.stopPropagation(); openNewProject(); };
  const brandMenu = $("#brand-menu");
  $("#brand-btn").onclick = e => { e.stopPropagation(); brandMenu.classList.toggle("open"); };
  document.addEventListener("click", () => brandMenu.classList.remove("open"));
  $("#quit-btn").onclick = () => { fetch("/quit").catch(()=>{}); setTimeout(()=>window.close(), 350); };
  highlight();
}

function openNewProject(){ navigate("#/project/new"); }
function openEditProject(slug){ navigate(`#/project/${slug}/edit`); }
function openNewProfile(projectSlug){ navigate(`#/project/${projectSlug}/profile/new`); }
function openNewChannel(profileSlug){ navigate(`#/profile/${profileSlug}/channel/new`); }
function highlight(){
  document.querySelectorAll("#rail [data-view]").forEach(a=>a.classList.toggle("active",STATE.view===a.dataset.view&&!STATE.project&&!STATE.profile&&!STATE.channelGuidelines));
  document.querySelectorAll("#rail [data-section]").forEach(a=>a.classList.toggle("active",STATE.view==="section"&&STATE.project===a.dataset.project&&STATE.section===a.dataset.section));
  document.querySelectorAll("#rail [data-profile]").forEach(a=>a.classList.toggle("active",(STATE.view==="profile"||STATE.view==="profileSetup")&&STATE.profile===a.dataset.profile));
  document.querySelectorAll("#rail [data-chan-guidelines]").forEach(a=>a.classList.toggle("active",STATE.view==="channelGuidelines"&&STATE.channelGuidelines===a.dataset.chanGuidelines));
}
function selectGlobal(v){ navigate(`#/${v}`); }
function selectSection(project,section){ OPEN.projects.add(project); saveOpen(); navigate(`#/project/${project}/${section}`); }
function selectProfile(slug, chanFilter){ navigate(`#/profile/${slug}`, chanFilter?{chanFilter}:{}); }
function selectChannelGuidelines(slug){
  const parentProf=_TREE.flatMap(p=>p.profiles).find(pr=>pr.channels.some(c=>c.slug===slug));
  const parentProj=_TREE.find(p=>p.profiles.some(pr=>pr.channels.some(c=>c.slug===slug)));
  if(parentProf){OPEN.profiles.add(parentProf.slug);} if(parentProj){OPEN.projects.add(parentProj.slug);}
  if(parentProf||parentProj) saveOpen();
  STATE={view:"channelGuidelines",project:null,section:null,profile:null,channelGuidelines:slug}; highlight(); renderChannelGuidelines(slug); }

// Re-render the rail + the current center view (used after the chat agent
// mutates entities via osctl, so new/changed items appear without a reload).
async function refreshViews(){
  await renderRail();
  const v = STATE.view;
  if (v === "calendar") return renderTimeline();
  if (v === "operations") return renderOperations();
  if (v === "section") return renderProjectSection(STATE.project, STATE.section);
  if (v === "profile") return renderProfile(STATE.profile);
  if (v === "profileSetup") return renderProfileSetup(STATE.profile);
  if (v === "channelGuidelines") return renderChannelGuidelines(STATE.channelGuidelines);
  return renderNeeds();
}

async function renderNeeds(){ $("#main").innerHTML=`<div class="topbar"><div><div class="crumbs">Across everything</div><h1 class="title">Needs you</h1></div></div><div class="scroll"><div style="padding:24px 4px;color:var(--dim)">Your prioritized to-act list arrives in a later phase. For now, open a project section or a profile.</div></div>`; }

async function renderOperations(){
  const all = await api("/api/timeline");
  const items = all.filter(r=>r.kind==="activity");
  const statuses=["planned","running","blocked","done"];
  let FILT="active";
  function draw(){
    const list = FILT==="active" ? items.filter(r=>r.status!=="done") : FILT==="done" ? items.filter(r=>r.status==="done") : items;
    const projectOpts = _TREE.map(p=>`<option value="${esc(p.slug)}">${esc(p.name)}</option>`).join("");
    const rows = list.length ? list.map(r=>{
      const done=r.status==="done";
      return `<div class="post" style="${done?"opacity:.5":""}">
        <span class="stp ${done?"sched":"idea"}">${esc(r.status||"planned")}</span>
        <div class="t">${esc(r.title)}<small>${[r.entity_name||r.entity_slug, r.date].filter(Boolean).join(" · ")}</small></div>
        ${!done?`<button class="go" data-done-title="${esc(r.title)}" data-done-entity="${esc(r.entity_slug||"")}">Done ✓</button>`:""}
        <button class="more" data-ev='${JSON.stringify({...r,title:(r.title||"").slice(0,80)}).replace(/'/g,"&#39;")}'>Edit</button>
      </div>`;
    }).join("") : `<div style="padding:24px 4px;color:var(--dim)">Nothing here.</div>`;
    const active=items.filter(r=>r.status!=="done").length;
    $("#ops-list").innerHTML=`
      <div class="filters" style="margin-bottom:14px">
        <span class="chip${FILT==="active"?" on":""}" data-of="active">Active <span class="n">${active}</span></span>
        <span class="chip${FILT==="all"?" on":""}" data-of="all">All <span class="n">${items.length}</span></span>
        <span class="chip${FILT==="done"?" on":""}" data-of="done">Done <span class="n">${items.filter(r=>r.status==="done").length}</span></span>
      </div>
      <div class="rowc">${rows}</div>`;
    $("#ops-list").querySelectorAll(".chip").forEach(c=>c.onclick=()=>{ FILT=c.dataset.of; draw(); });
    $("#ops-list").querySelectorAll("[data-done-title]").forEach(b=>b.onclick=async()=>{
      try{ await jpost("/api/activity/done",{title:b.dataset.doneTitle,entity:b.dataset.doneEntity}); toast("Done ✓"); renderOperations(); }
      catch(e){ toast("✗ "+e.message); }
    });
    $("#ops-list").querySelectorAll("[data-ev]").forEach(el=>el.onclick=e=>{ e.stopPropagation(); try{toggleEvDetail(el,JSON.parse(el.dataset.ev));}catch(_){} });
  }
  $("#main").innerHTML=`
    <div class="topbar"><div><div class="crumbs">Across everything</div><h1 class="title">Operations</h1></div>
      <div style="margin-left:auto"><button class="btn primary" id="newOpBtn">＋ Activity</button></div></div>
    <div class="scroll"><div id="ops-list"></div></div>`;
  draw();
  $("#newOpBtn").onclick=()=>navigate("#/activity/new");
}
function plainStatus(s){ return ({planned:"Idea",approved_slot:"Idea",briefed:"Draft",approved:"Ready",published:"Published",rejected:"Archived"})[s]||s; }

function latestMemo(project, type){
  return (project.memos || []).filter(m => m.type === type).sort((a, b) => b.version - a.version)[0] || null;
}

// Profile/channel tab ids (…pf1.sec00, …ch1.sec00) add no discrimination when the
// entity is already named in nav — drop only that suffix, never shared-prefix stripping.
const PROFILE_TAB_ID_RE = /^((?:pr\d+\.)+pf\d+)\.sec\d{2}$/;
const CHANNEL_TAB_ID_RE = /^((?:pr\d+\.)+pf\d+\.ch\d+)\.sec\d{2}$/;

function entityId(id){
  if (!id) return "";
  let m = id.match(PROFILE_TAB_ID_RE);
  if (m) return m[1];
  m = id.match(CHANNEL_TAB_ID_RE);
  if (m) return m[1];
  return id;
}

function idDisplay(id, opts={}){
  if (!id) return "";
  let s = opts.dropTabSuffix ? entityId(id) : id;
  // Tab subsections: show pr2.sec06.ss1 not pr2.sec06.doc1.ss1 (doc = file layer, redundant in UI).
  if (/\.doc\d+\.ss\d+/i.test(s)) s = s.replace(/\.doc\d+(\.ss\d+)/i, "$1");
  return s;
}

function sectionIdChip(id, opts=null){
  if (!id) return "";
  const o = (opts && typeof opts === "object") ? opts : {};
  const shown = idDisplay(id, o);
  if (!shown) return "";
  return `<span class="sec-id" role="button" tabindex="0" data-os-id="${esc(id)}" title="Copy @mention">${esc(shown)}</span>`;
}

function renderArtifactHead(title, id, trailing=""){
  const chip = sectionIdChip(id);
  if (!chip && !trailing) return `<h4>${esc(title)}</h4>`;
  return `<div class="sec-artifact-head"><h4>${esc(title)}</h4><div class="artifact-head-end">${chip}${trailing}</div></div>`;
}

function metaPlain(label, value){
  if(value==null||value==="") return "";
  return `<span class="meta-plain" style="font-size:11px;color:var(--dim)"><b style="color:var(--ink2)">${esc(label)}:</b> ${esc(value)}</span>`;
}

function titledWithId(title, id=null, opts={}){
  const label = esc(title);
  if (!id) return label;
  const chip = sectionIdChip(id, {dropTabSuffix:true, ...opts});
  if (!chip) return label;
  return `${label} <span class="titled-id">${chip}</span>`;
}

function fallbackCopyText(text){
  const ta = document.createElement("textarea");
  ta.value = text; ta.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(ta); ta.focus(); ta.select();
  try { document.execCommand("copy"); } catch { /* ignore */ }
  document.body.removeChild(ta);
}

function copyMentionId(id){
  const token = "@" + id;
  const done = () => toast("Copied " + token);
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(token).then(done, () => { fallbackCopyText(token); done(); });
  } else { fallbackCopyText(token); done(); }
}

function wireIdChips(){
  /* delegated — see boot() */
}

document.addEventListener("click", e => {
  const el = e.target.closest(".sec-id[data-os-id]");
  if (!el) return;
  e.preventDefault(); e.stopPropagation();
  copyMentionId(el.dataset.osId);
});
document.addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const el = e.target.closest(".sec-id[data-os-id]");
  if (!el) return;
  e.preventDefault();
  copyMentionId(el.dataset.osId);
});

function sectionEmptyState(sectionKey){
  const hints = sectionSkills(sectionKey).map(s => `/${s}`);
  const hint = hints.length
    ? `<p class="sec-hint">Fill via chat: ${hints.map(h => `<code>${esc(h)}</code>`).join(" ")}</p>`
    : "";
  return `<div class="sec-empty"><p>Nothing here yet.</p>${hint}</div>`;
}

/** Composed IDs only (pr2.sec04.mm1) — never show lookup keys (memo:proj:…) in UI. */
function composedIdOnly(...candidates){
  for (const id of candidates) {
    if (id && /^pr\d+\./.test(String(id))) return id;
  }
  return "";
}

function renderSecGroup(label, inner, id=null, actions=""){
  const chip = sectionIdChip(composedIdOnly(id));
  const act = actions ? `<div class="sec-group-actions">${actions}</div>` : "";
  const head = chip || act
    ? `<div class="sec-group-head"><h3>${esc(label)}</h3><div class="sec-group-end">${chip}${act}</div></div>`
    : `<h3>${esc(label)}</h3>`;
  return `<div class="sec-group">${head}${inner}</div>`;
}

function stripLeadingDocTitle(raw){
  const lines = String(raw || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i++;
  if (i < lines.length && /^#\s+/.test(lines[i].trim())) {
    i++;
    while (i < lines.length && !lines[i].trim()) i++;
  }
  return lines.slice(i).join("\n");
}

function docArtifactId(projectSlug, artifact){
  const p = artifact?.path || "";
  let key = "";
  if (p.endsWith("strategy/intake.md")) key = "intake";
  else if (p.endsWith("technical.md")) key = "technical";
  else if (p.endsWith("project.md")) key = "project";
  return composedIdOnly(artifact?.id, key ? OSID.doc(projectSlug, key) : "");
}

function parseMdSections(text){
  if (!text) return [];
  const sections = [];
  let cur = null;
  for (const line of String(text).split("\n")) {
    if (line.startsWith("## ")) {
      if (cur) sections.push(cur);
      cur = { title: line.slice(3).trim(), body: "" };
    } else if (cur) {
      cur.body += (cur.body ? "\n" : "") + line;
    }
  }
  if (cur) sections.push(cur);
  return sections;
}

function projectDocSubsections(p, docKey){
  const fromProj = p?.subsections?.docs?.[docKey];
  if (fromProj && fromProj.length) return fromProj;
  const fromMeta = _SCHEMAS?.subsections?.docs?.[docKey]?.default_subsections;
  if (fromMeta && fromMeta.length) return fromMeta;
  const fromApi = _SCHEMAS?.[docKey]?.default_subsections || _SCHEMAS?.[docKey]?.sections;
  if (fromApi && fromApi.length) return fromApi;
  if (docKey === "intake") return ["What it is", "Stage & evidence", "Market", "Resources", "Goals", "Evidence log"];
  if (docKey === "technical") return ["Stack", "Architecture", "Infrastructure", "APIs & integrations", "Data & storage", "Deployment", "Open questions"];
  return ["Now", "Next", "Later / Ideas", "Shipped"];
}

function validationTabSubsections(p){
  const fromProj = p?.subsections?.validation_tab;
  if (fromProj && fromProj.length) return fromProj;
  const fromMeta = _SCHEMAS?.subsections?.validation_tab_default;
  if (fromMeta && fromMeta.length) return fromMeta;
  const fromApi = _SCHEMAS?.intake?.validation_tab_sections;
  if (fromApi && fromApi.length) return fromApi;
  return ["Stage & evidence", "Market", "Resources", "Goals", "Evidence log"];
}

function roadmapSectionOrder(p){
  const titles = p ? projectDocSubsections(p, "roadmap") : [];
  const order = titles.length
    ? titles.map(title => [roadmapSectionKey(title), title])
    : ROADMAP_SECTION_ORDER_FALLBACK;
  return order;
}

function docSubsectionId(projectSlug, p, docKey, title){
  const fromApi = p?.subsection_ids?.[docKey]?.[title];
  if (fromApi && /^pr\d+\./i.test(String(fromApi))) return String(fromApi).toLowerCase();
  return composedIdOnly(OSID.docSubsection(projectSlug, docKey, title));
}

function renderMdSubsections(projectSlug, p, docKey, text, opts = {}){
  const order = projectDocSubsections(p, docKey);
  const parsed = Object.fromEntries(parseMdSections(text || "").map(s => [s.title, s.body]));
  let html = "";
  order.forEach(title => {
    const body = (parsed[title] || "").trim();
    const inner = body ? formatMdDoc(body) : `<p class="memo-empty">Empty — click Edit to add content.</p>`;
    const subId = docSubsectionId(projectSlug, p, docKey, title);
    const titleKey = OSID.slugKey(title);
    const editBtn = opts.editable
      ? `<button type="button" class="btn" data-edit-doc-sub="${esc(docKey)}" data-sub-title="${esc(title)}" data-sub-key="${esc(titleKey)}" style="padding:4px 10px;font-size:11px">✎ Edit</button>`
      : "";
    html += renderSecGroup(title, `<div class="pcard"><div class="sec-body memo-body">${inner}</div></div>`, subId, editBtn);
  });
  return html;
}

function wireDocSubsectionEditButtons(projectSlug){
  $("#main").querySelectorAll("[data-edit-doc-sub]").forEach(btn => {
    btn.onclick = () => navigate(
      `#/project/${projectSlug}/${btn.dataset.editDocSub}/subsection/edit/${btn.dataset.subKey}`,
      { subTitle: btn.dataset.subTitle },
    );
  });
}

function filterIntakeSections(text, allowedTitles){
  const allow = new Set(allowedTitles);
  return parseMdSections(text)
    .filter(s => allow.has(s.title) && s.body.trim())
    .map(s => `## ${s.title}\n\n${s.body.trim()}`)
    .join("\n\n");
}

function memoArtifactId(projectSlug, memo){
  return composedIdOnly(memo.id, OSID.memo(projectSlug, memo.type, memo.version));
}

const ROADMAP_SECTION_ORDER_FALLBACK = [
  ["now", "Now"],
  ["next", "Next"],
  ["later", "Later / Ideas"],
  ["shipped", "Shipped"],
];
function roadmapSectionKey(sec){
  const s = String(sec || "").toLowerCase();
  if (s.includes("now") || s.includes("building")) return "now";
  if (s.includes("next") || s.includes("planned")) return "next";
  if (s.includes("later") || s.includes("ideas")) return "later";
  if (s.includes("shipped")) return "shipped";
  return "other";
}

function featureStatusPill(status){
  const k = ({ shipped: "sched", building: "draft", planned: "idea", idea: "idea" })[status] || "draft";
  return `<span class="stp ${k}">${esc(status || "idea")}</span>`;
}

function renderMemoCard(projectSlug, memo, opts = {}){
  const b = memo.body || {};
  const title = opts.title || `${memoTypeLabel(memo.type)} v${memo.version}`;
  const id = memoArtifactId(projectSlug, memo);
  let body = renderMemoBody(b, memo.type || "");
  if (!body) body = `<p>${esc(memo.status || EMPTY)}</p>`;
  if (opts.headless) {
    return `<div class="pcard"><div class="sec-body memo-body">${body}</div></div>`;
  }
  return `<div class="pcard">${renderArtifactHead(title, id)}<div class="sec-body memo-body">${body}</div></div>`;
}

function fileCardTitle(artifact){
  const p=artifact.path||"";
  if(p.endsWith("intake.md")) return "Venture intake";
  if(p.endsWith("technical.md")) return "Technical";
  if(p.endsWith("project.md")) return "Project";
  return (artifact.label||"").split("/").pop()||"File";
}

function renderFileCard(artifact, projectSlug, opts = {}){
  const title = fileCardTitle(artifact);
  let raw = artifact.text;
  if (opts.headless && raw != null) raw = stripLeadingDocTitle(raw);
  const mdOpts = opts.headless ? { dropH1: true } : {};
  const content = raw != null ? formatMdDoc(raw, mdOpts) : `<p class="memo-empty">Could not load file.</p>`;
  const id = docArtifactId(projectSlug, artifact);
  if (opts.headless) {
    return `<div class="pcard"><div class="sec-body memo-body">${content}</div></div>`;
  }
  return `<div class="pcard">${renderArtifactHead(title, id)}<div class="sec-body memo-body">${content}</div></div>`;
}

function renderOverviewSection(slug, p, sec){
  const e = p.entity || {};
  const pv = latestMemo(p, "problem-validation");
  const as = latestMemo(p, "assessment");
  const vb = pv && pv.body || {};
  const ab = as && as.body || {};
  const kv = (k, v) => `<div class="kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
  let html = "";
  html += renderSecGroup("Project snapshot", `<div class="grid2">
    ${kv("Stage", e.status || "—")}${kv("Priority", e.priority || "—")}${kv("Hours/week", e.hours_per_week ?? "—")}
    ${kv("Validation", vb.validation_status || "—")}${kv("Pace", ab.pace_recommendation || "—")}
    ${kv("Profiles", (p.profiles || []).map(c => c.name).join(", ") || "—")}</div>`);
  html += renderSecGroup("GTM assessment",
    (as && ab.riskiest_assumption) ? renderMemoCard(slug, as, { title: "GTM assessment", headless: true })
      : `<div class="sec-missing">No assessment memo · <span class="sec-hint"><code>/gtm-assessment</code></span></div>`,
    (as && ab.riskiest_assumption) ? memoArtifactId(slug, as) : null);
  return html;
}

function renderValidationSection(slug, p, sec){
  const intake = (sec.artifacts || []).find(a => a.kind === "file" && (a.path || "").endsWith("strategy/intake.md"));
  const pv = latestMemo(p, "problem-validation");
  let html = "";
  const intakeFiltered = intake ? filterIntakeSections(intake.text, validationTabSubsections(p)) : "";
  html += renderSecGroup("Venture intake",
    intakeFiltered
      ? renderFileCard({ ...intake, text: intakeFiltered }, slug, { headless: true })
      : `<div class="sec-missing">No validation intake yet · <span class="sec-hint"><code>/venture-intake</code></span></div>`,
    docArtifactId(slug, intake));
  html += renderSecGroup("Problem validation",
    pv ? renderMemoCard(slug, pv, { headless: true }) : `<div class="sec-missing">No memo yet · <span class="sec-hint"><code>/problem-validation</code></span></div>`,
    pv ? memoArtifactId(slug, pv) : null);
  return html;
}

function renderTechnicalSection(slug, p, sec){
  const tech = (sec.artifacts || []).find(a => a.kind === "file" && (a.path || "").endsWith("technical.md"));
  if (!tech) return sectionEmptyState("technical");
  return `<div class="sec-subsections">${renderMdSubsections(slug, p, "technical", tech.text, { editable: true })}</div>`;
}

function renderExperimentCard(slug, x){
  const stem = x.stem || (x.file_path || "").split("/").pop().replace(/\.json$/, "") || x.id;
  const id = composedIdOnly(x.id, OSID.experiment(slug, stem));
  const b = x.body || {};
  let body = `<div><b>Status</b> · ${esc(x.status || "?")}`;
  if (x.decision) body += ` · decision <b>${esc(x.decision)}</b>`;
  if (x.duration_days) body += ` · ${esc(x.duration_days)}d`;
  if (x.started_on) body += ` · started ${esc(x.started_on)}`;
  body += `</div>`;
  if (x.result) body += `<div><b>Result</b> · ${esc(x.result)}</div>`;
  if (b.success_criteria) body += `<div><b>Success</b> · ${esc(b.success_criteria)}</div>`;
  if (b.kill_criteria) body += `<div><b>Kill</b> · ${esc(b.kill_criteria)}</div>`;
  return `<div class="pcard">${renderArtifactHead(x.assumption || stem, id)}<div class="sec-body">${body}</div></div>`;
}

function renderExperimentsSection(slug, p, sec){
  const exps = p.experiments || [];
  if (!exps.length) return sectionEmptyState("experiments");
  const cards = exps.map(x => renderExperimentCard(slug, x)).join("");
  return renderSecGroup("Experiments", cards);
}

const PRICING_SKILL_HINT = {
  positioning: "positioning",
  pricing: "pricing-strategy",
  competitors: "competitor-scan",
  icp: "icp-research",
  channels: "channel-strategy",
};

function renderPricingSection(slug, p){
  const types = sectionMemoTypes("pricing");
  let html = "";
  types.forEach(type => {
    const m = latestMemo(p, type);
    const label = memoTypeLabel(type);
    const skill = PRICING_SKILL_HINT[type] || type;
    const inner = m
      ? renderMemoCard(slug, m, { headless: true })
      : `<div class="sec-missing">No ${esc(label.toLowerCase())} memo yet · <span class="sec-hint"><code>/${esc(skill)}</code></span></div>`;
    html += renderSecGroup(label, inner, m ? memoArtifactId(slug, m) : null);
  });
  return html;
}

function renderFeatureCard(prod, f){
  const fid = composedIdOnly(f.id, OSID.feat(prod.slug, OSID.slugKey(f.title)));
  const badges = `<div class="artifact-badges">${featureStatusPill(f.status)}${
    f.priority ? `<span class="prio-tag">${esc(f.priority)}</span>` : ""}${
    f.target_date ? `<span class="prio-tag">${esc(f.target_date)}</span>` : ""}</div>`;
  const body = f.why
    ? `<div class="sec-body">${esc(f.why)}</div>`
    : `<div class="sec-body memo-empty">No description — add after title in roadmap: <code>Title — one-line why</code></div>`;
  return `<div class="pcard">${renderArtifactHead(f.title, fid)}${badges}${body}</div>`;
}

function renderProductSection(slug, p){
  let html = "";
  const products = p.products || [];
  if (!products.length) return html + sectionEmptyState("product");
  products.forEach(prod => {
    const feats = (p.features || []).filter(f => f.product_slug === prod.slug);
    const prodId = composedIdOnly(OSID.prod(prod.slug));
    const addBtn = `<button class="btn" type="button" data-add-feat="${esc(prod.slug)}" style="padding:6px 10px;font-size:11px">＋ Feature</button>`;
    const sectionOrder = roadmapSectionOrder(p);
    const buckets = Object.fromEntries(sectionOrder.map(([k]) => [k, []]));
    buckets.other = [];
    feats.forEach(f => {
      const k = roadmapSectionKey(f.roadmap_section);
      (buckets[k] || buckets.other).push(f);
    });
    let inner = `<p style="font-size:12px;color:var(--dim);margin:0 0 12px">${feats.length} feature${feats.length !== 1 ? "s" : ""} in roadmap</p>`;
    sectionOrder.forEach(([key, label]) => {
      const group = buckets[key] || [];
      if (!group.length) return;
      inner += renderSecGroup(label, `<div class="rowc">${group.map(f => renderFeatureCard(prod, f)).join("")}</div>`);
    });
    if (buckets.other.length) {
      inner += renderSecGroup("Roadmap", `<div class="rowc">${buckets.other.map(f => renderFeatureCard(prod, f)).join("")}</div>`);
    }
    if (!feats.length) inner += `<div class="sec-missing">No features yet.</div>`;
    html += `<div class="pcard" style="margin-bottom:14px">${renderArtifactHead(prod.name, prodId, addBtn)}${inner}</div>`;
  });
  return html;
}

function wireProductFeatureButtons(slug){
  $("#main").querySelectorAll("[data-add-feat]").forEach(btn => {
    btn.onclick = () => navigate(`#/product/${btn.dataset.addFeat}/feature/new`, { projectSlug: slug });
  });
}

function hasProjectIntake(p){
  return ((p.sections || {}).validation?.artifacts || []).some(
    a => a.kind === "file" && (a.path || "").endsWith("strategy/intake.md"));
}

function hasProjectTechnical(p){
  return ((p.sections || {}).technical?.artifacts || []).some(
    a => a.kind === "file" && (a.path || "").endsWith("technical.md"));
}

function sectionAddButtons(slug, section, p){
  const out = [];
  if (section === "validation") {
    if (!hasProjectIntake(p)) out.push({ label: "＋ Intake", route: `#/project/${slug}/intake/new` });
    out.push({ label: "＋ Memo", route: `#/project/${slug}/memo/new/problem-validation` });
  } else if (section === "experiments") {
    out.push({ label: "＋ Experiment", route: `#/project/${slug}/experiment/new` });
  } else if (section === "pricing") {
    out.push({ label: "＋ Memo", route: `#/project/${slug}/memo/new/positioning`, pickType: true });
  } else if (section === "product") {
    out.push({ label: "＋ Product", route: `#/project/${slug}/product/new` });
    if ((p.products || []).length === 1)
      out.push({ label: "＋ Feature", route: `#/product/${p.products[0].slug}/feature/new`, projectSlug: slug });
    else if ((p.products || []).length > 1)
      out.push({ label: "＋ Feature", route: `#/project/${slug}/product`, pickProduct: true });
  } else if (section === "technical") {
    if (!hasProjectTechnical(p)) out.push({ label: "＋ Technical", route: `#/project/${slug}/technical/new` });
    else out.push({ label: "＋ Subsection", route: `#/project/${slug}/technical/subsection/new` });
  }
  return out;
}

async function renderProjectSection(slug, section){
  await refreshIdRegistry();
  const [p] = await Promise.all([api(`/api/project/${slug}`), ensureIdRegistry()]);
  const title = (SECTIONS.find(s => s.key === section) || {}).label || section;
  const sec = (p.sections || {})[section] || {};
  const renderers = {
    overview: () => renderOverviewSection(slug, p, sec),
    validation: () => renderValidationSection(slug, p, sec),
    experiments: () => renderExperimentsSection(slug, p, sec),
    pricing: () => renderPricingSection(slug, p),
    product: () => renderProductSection(slug, p),
    technical: () => renderTechnicalSection(slug, p, sec),
  };
  const body = (renderers[section] || (() => `<div style="padding:24px 4px;color:var(--dim)">Unknown section.</div>`))();
  const adds = sectionAddButtons(slug, section, p);
  const addHtml = adds.map((a, i) =>
    `<button class="btn${i === adds.length - 1 ? " primary" : ""}" data-sec-add="${i}">${esc(a.label)}</button>`
  ).join("");
  const tabId = composedIdOnly(OSID.tabProj(slug, section));
  $("#main").innerHTML = `<div class="topbar"><div><div class="crumbs">${esc(p.entity.name)} · <b>${esc(title)}</b></div>
      <div class="sec-meta" style="margin-top:6px"><h1 class="title" style="margin:0">${esc(title)}</h1>${sectionIdChip(tabId)}</div></div>
    ${addHtml ? `<div style="margin-left:auto;display:flex;gap:8px">${addHtml}</div>` : ""}</div>
    <div class="scroll">${body}</div>`;
  adds.forEach((a, i) => {
    const btn = $("#main").querySelector(`[data-sec-add="${i}"]`);
    if (!btn) return;
    btn.onclick = () => {
      if (a.pickType) {
        const types = sectionMemoTypes("pricing");
        const pick = prompt(`Memo type:\n${types.map((t, n) => `${n + 1}. ${memoTypeLabel(t)}`).join("\n")}\n\nEnter number or type slug:`);
        if (!pick) return;
        const n = parseInt(pick, 10);
        const mtype = (!isNaN(n) && n >= 1 && n <= types.length) ? types[n - 1] : pick.trim();
        if (!types.includes(mtype)) return toast("Unknown memo type");
        navigate(`#/project/${slug}/memo/new/${mtype}`);
        return;
      }
      if (a.pickProduct) {
        const prods = p.products || [];
        const pick = prompt(prods.map((pr, n) => `${n + 1}. ${pr.name}`).join("\n") + "\n\nProduct number:");
        const n = parseInt(pick, 10);
        if (isNaN(n) || n < 1 || n > prods.length) return;
        navigate(`#/product/${prods[n - 1].slug}/feature/new`, { projectSlug: slug });
        return;
      }
      navigate(a.route, a.projectSlug ? { projectSlug: a.projectSlug } : {});
    };
  });
  if (section === "product") wireProductFeatureButtons(slug);
  if (section === "technical") wireDocSubsectionEditButtons(slug);
  wireIdChips($("#main"));
}

let CAL = (function(){ const d=new Date(); return {y:d.getFullYear(), m:d.getMonth(), filter:"all"}; })();
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
function calShift(delta){ let m=CAL.m+delta,y=CAL.y; if(m<0){m=11;y--;} if(m>11){m=0;y++;} CAL={...CAL,y,m}; renderTimeline(); }
function calToday(){ const d=new Date(); CAL={...CAL,y:d.getFullYear(),m:d.getMonth()}; renderTimeline(); }

function evDone(r){
  return (r.kind==="post"&&r.status==="published")||(r.kind==="activity"&&r.status==="done");
}

function evDetail(r){
  // Returns an .ev-detail element for inline expansion in calendar cells and ops list.
  const d=document.createElement("div"); d.className="ev-detail"; d.dataset.forEv=JSON.stringify(r);
  const meta=[r.kind, r.entity_name||r.entity_slug, r.date, r.status].filter(Boolean).join(" · ");
  let acts="";
  if(r.kind==="activity"&&r.status!=="done")
    acts+=`<button class="btn primary" data-ev-done>Mark done ✓</button>`;
  if(r.kind==="post")
    acts+=`<button class="btn primary" data-ev-go>Open post →</button>`;
  if(r.kind==="activity")
    acts+=`<button class="btn danger-btn" data-ev-del>Delete</button>`;
  if(r.kind==="milestone"&&r.ref_id){
    acts+=`<button class="btn primary" data-ev-edit>Edit</button>`;
    acts+=`<button class="btn danger-btn" data-ev-del>Delete</button>`;
  }
  d.innerHTML=`<div class="ev-meta">${esc(meta)}</div><div class="ev-acts">${acts}</div>`;
  const doneBtn=d.querySelector("[data-ev-done]");
  if(doneBtn) doneBtn.onclick=async()=>{
    try{ await jpost("/api/activity/done",{title:r.title,entity:r.entity_slug}); toast("Marked done ✓"); refreshViews(); }
    catch(e){ toast("✗ "+e.message); }
  };
  const goBtn=d.querySelector("[data-ev-go]");
  if(goBtn) goBtn.onclick=()=>selectProfile(r.entity_slug);
  const delBtn=d.querySelector("[data-ev-del]");
  if(delBtn) delBtn.onclick=async()=>{
    d.remove();
    if(r.kind==="activity"){
      try{
        await jpost("/api/activity/delete",{title:r.title});
        undoToast(`Activity "${r.title}" deleted`, async()=>{
          await jpost("/api/activity/new",{title:r.title,entity:r.entity_slug,date:r.date,type:r.type||"task"});
          refreshViews();
        });
        refreshViews();
      }catch(e){ toast("✗ "+e.message); }
    } else if(r.kind==="milestone"&&r.ref_id){
      try{
        await jpost(`/api/milestone/${r.ref_id}/delete`,{});
        undoToast(`Milestone "${r.title}" deleted`, async()=>{
          await jpost("/api/milestone/new",{title:r.title,date:r.date,entity:r.entity_slug,notes:r.notes||""});
          refreshViews();
        });
        refreshViews();
      }catch(e){ toast("✗ "+e.message); }
    }
  };
  const editBtn=d.querySelector("[data-ev-edit]");
  if(editBtn) editBtn.onclick=()=>navigate(`#/milestone/${r.ref_id}/edit`,{title:r.title,date:r.date,date_end:r.date_end||""});
  return d;
}
function toggleEvDetail(el, r){
  const existing=el.parentNode.querySelector(".ev-detail");
  if(existing&&existing.dataset.forEv===JSON.stringify(r)){ existing.remove(); return; }
  if(existing) existing.remove();
  el.parentNode.insertBefore(evDetail(r), el.nextSibling);
}

async function renderTimeline(){
  const all = await api("/api/timeline");
  const kinds=["post","activity","milestone","experiment","feature"];
  const filtered = CAL.filter==="all" ? all : all.filter(r=>r.kind===CAL.filter);
  const byDay={}; filtered.forEach(r=>{ if(r.date){ (byDay[r.date]=byDay[r.date]||[]).push(r); } });
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  const today=iso(new Date());
  const first=new Date(CAL.y,CAL.m,1), lead=(first.getDay()+6)%7, start=new Date(CAL.y,CAL.m,1-lead);
  let cells="";
  for(let i=0;i<42;i++){
    const d=new Date(start.getFullYear(),start.getMonth(),start.getDate()+i), k=iso(d), out=d.getMonth()!==CAL.m;
    const evs=(byDay[k]||[]).map(r=>{
      const done=evDone(r)?" done":"";
      return `<div class="ev ${esc(r.kind)}${done}" data-ev='${JSON.stringify({...r,title:(r.title||"").slice(0,80)}).replace(/'/g,"&#39;")}'>${esc(r.title||r.kind)}</div>`;
    }).join("");
    cells+=`<div class="day${out?" out":""}${k===today?" today":""}"><div class="n">${d.getDate()}</div>${evs}</div>`;
    if(i>=34&&d.getMonth()!==CAL.m&&(i+1)%7===0) break;
  }
  const counts=k=>all.filter(r=>r.kind===k).length;
  const chips=[["all","All",all.length],...kinds.map(k=>[k,k[0].toUpperCase()+k.slice(1)+"s",counts(k)])]
    .map(([k,l,n])=>`<span class="kchip k-${k}${CAL.filter===k?" on":""}" data-kf="${k}">${l} <span style="opacity:.6">${n}</span></span>`).join("");
  const dow=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(x=>`<div class="dow">${x}</div>`).join("");
  const projectOpts = _TREE.map(p=>`<option value="${esc(p.slug)}">${esc(p.name)}</option>`).join("");
  $("#main").innerHTML=`
    <div class="topbar"><div><div class="crumbs">Across everything</div><h1 class="title">Calendar</h1></div>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn" id="newActBtn">＋ Activity</button>
        <button class="btn" id="newMsBtn">＋ Milestone</button>
      </div></div>
    <div class="scroll">
      <div class="cal-filters">${chips}</div>
      <div class="cal-head"><span class="mlabel">${MONTHS[CAL.m]} ${CAL.y}</span>
        <div class="cal-nav"><button id="cprev">‹</button><button id="ctoday">Today</button><button id="cnext">›</button></div></div>
      <div class="cal">${dow}${cells}</div></div>`;
  $("#cprev").onclick=()=>calShift(-1); $("#cnext").onclick=()=>calShift(1); $("#ctoday").onclick=calToday;
  $("#main").querySelectorAll(".kchip").forEach(c=>c.onclick=()=>{ CAL.filter=c.dataset.kf; renderTimeline(); });
  $("#main").querySelectorAll("[data-ev]").forEach(el=>el.onclick=e=>{ e.stopPropagation(); try{toggleEvDetail(el,JSON.parse(el.dataset.ev));}catch(_){} });
  $("#newActBtn").onclick=()=>navigate("#/activity/new");
  $("#newMsBtn").onclick=()=>navigate("#/milestone/new");
}

const STAGE_GROUP = {planned:"ideas",approved_slot:"ideas",briefed:"drafts",approved:"drafts",published:"published",rejected:"archived"};
const NEXT = {
  planned:{label:"Write it →",brief:1}, approved_slot:{label:"Write it →",brief:1},
  briefed:{label:"Review →",to:"approved"}, approved:{label:"Publish →",to:"published"},
  published:null, rejected:{label:"Restore",to:"planned"},
};

const PLATFORM_ICON = {instagram:"📸",tiktok:"🎵",x:"𝕏",linkedin:"in",youtube:"▶",facebook:"f"};
async function renderProfile(slug, initChanFilter){
  CURRENT_PROFILE_SLUG = slug;
  const [posts, profData] = await Promise.all([
    api(`/api/profile/${slug}/posts`),
    api(`/api/profile/${slug}`),
    ensureIdRegistry(),
  ]);
  const profNode = _TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===slug)||{channels:[]};
  const channels = profNode.channels||[];
  const count = g => posts.filter(p=>STAGE_GROUP[p.status]===g).length;
  let FILTER = "all";
  let CHAN_FILTER = initChanFilter||null;
  const SELECTED = new Set();  // post ids ticked for bulk actions
  const chanSection = `<div class="pcard" style="margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      ${channels.map(ch=>`<span class="chan-pill-wrap${CHAN_FILTER===ch.slug?" on":""}"><button class="chan-pill${CHAN_FILTER===ch.slug?" on":""}" data-cf="${esc(ch.slug)}" style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">${PLATFORM_ICON[ch.platform]||"⌗"} ${titledWithId(ch.name||ch.platform)}${ch.handle?` <span style="opacity:.6;font-size:10px">${esc(ch.handle)}</span>`:""}</button><button class="chan-gear" data-cg="${esc(ch.slug)}" title="Channel setup">⚙</button></span>`).join("")}
      <button class="btn" id="addChanBtn" style="font-size:12px;padding:5px 11px;border-radius:20px">＋ Add channel</button>
    </div>
    ${profData.topic?`<div style="margin-top:8px;font-size:12px;color:var(--dim)">${esc(profData.topic)}</div>`:""}
  </div>`;
  const profBtns = `<button class="btn" id="setupBtn">⚙ Setup</button>`
    + `<button class="btn" id="addIdea">＋ Add idea</button>`
    + `<button class="btn" id="writeAll">✍ Write all ideas</button>`
    + `<button class="btn primary" id="genIdeas">✦ Generate ideas</button>`;
  $("#main").innerHTML = `${pageHeader(profData.name||slug, "Profiles", profBtns, OSID.prof(slug))}
    <div style="padding:0 24px 8px;font-size:12px;color:var(--dim)">${posts.length} posts</div>
    <div class="scroll">
      ${chanSection}
      <div class="filters">
        <span class="chip on" data-f="all">All <span class="n">${posts.length}</span></span>
        <span class="chip" data-f="ideas">💡 Ideas <span class="n">${count("ideas")}</span></span>
        <span class="chip" data-f="drafts">✍ Drafts <span class="n">${count("drafts")}</span></span>
        <span class="chip" data-f="published">✓ Published <span class="n">${count("published")}</span></span>
      </div>
      <div id="selbar"></div>
      <div class="rowc" id="list"></div></div>`;

  function drawSelBar(){
    const bar = $("#selbar"); if(!bar) return;
    const visible = posts.filter(p=>(FILTER==="all"||STAGE_GROUP[p.status]===FILTER)
      && (!CHAN_FILTER||(p.channels&&p.channels.includes(CHAN_FILTER))));
    // prune selections no longer visible so the count is honest
    [...SELECTED].forEach(id=>{ if(!visible.some(p=>p.id===id)) SELECTED.delete(id); });
    if(!SELECTED.size){ bar.innerHTML=""; return; }
    bar.innerHTML=`<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px;padding:9px 13px;background:rgba(192,57,43,.06);border:1px solid rgba(192,57,43,.25);border-radius:11px">
      <b style="font-size:13px">${SELECTED.size} selected</b>
      <button class="btn" id="selAll" style="font-size:12px;padding:4px 10px">Select all ${visible.length}</button>
      <button class="btn" id="selClear" style="font-size:12px;padding:4px 10px">Clear</button>
      <button class="btn danger-btn" id="selDel" style="margin-left:auto;color:#c0392b">🗑 Delete ${SELECTED.size}</button></div>`;
    $("#selAll").onclick=()=>{ visible.forEach(p=>SELECTED.add(p.id)); drawList(); };
    $("#selClear").onclick=()=>{ SELECTED.clear(); drawList(); };
    $("#selDel").onclick=()=>navigate("#/posts/delete",{ids:[...SELECTED],profileSlug:slug});
  }

  function drawList(){
    const list = posts.filter(p=>(FILTER==="all"||STAGE_GROUP[p.status]===FILTER)
      && (!CHAN_FILTER||(p.channels&&p.channels.includes(CHAN_FILTER))));
    const el = $("#list");
    drawSelBar();
    if(!list.length){ el.innerHTML=`<div style="padding:24px 4px;color:var(--dim)">Nothing here. Add an idea or generate a batch.</div>`; return; }
    el.innerHTML = list.map(p=>{
      const grp=STAGE_GROUP[p.status], pk=({ideas:"idea",drafts:"draft",published:"ready",archived:"idea"})[grp]||"idea";
      const n=NEXT[p.status];
      const title = p.working_title || p.pillar || p.id;
      const isIdea = p.status==="planned"||p.status==="approved_slot";
      const sub = isIdea ? (p.concept || "Just an idea — not written yet") : (p.brief_path?"Written — click to view":"");
      const pillarTag = p.pillar && p.pillar!==title ? `<span class="chan-chip" style="background:var(--sky-soft);color:var(--navy)">${esc(p.pillar)}</span>` : "";
      const chanChips = ((pillarTag?1:0)||(p.channels&&p.channels.length))
        ? `<div class="chan-chips">${pillarTag}${(p.channels||[]).map(c=>`<span class="chan-chip">${esc(c)}</span>`).join("")}</div>` : "";
      const postChip = sectionIdChip(OSID.post(p.id));
      return `<div class="post${SELECTED.has(p.id)?" sel":""}">
        <input type="checkbox" class="selbox" data-sel="${p.id}" ${SELECTED.has(p.id)?"checked":""} title="Select" style="margin:0 2px;width:16px;height:16px;flex:none;cursor:pointer">
        <span class="stp ${pk}">${esc(plainStatus(p.status))}</span>
        <div class="t" data-view="${p.id}" style="cursor:pointer;min-width:0">${postChip?`<div style="margin-bottom:4px">${postChip}</div>`:""}${esc(title)}<small>${[sub,p.date].filter(Boolean).map(esc).join(" · ")}</small>${chanChips}</div>
        ${n?`<button class="go" data-act="${p.id}">${n.label}</button>`:""}
        <button class="more" data-menu="${p.id}">Edit</button></div>`;
    }).join("");
    el.querySelectorAll("[data-sel]").forEach(b=>b.onclick=e=>{ e.stopPropagation();
      b.checked ? SELECTED.add(b.dataset.sel) : SELECTED.delete(b.dataset.sel);
      b.closest(".post")?.classList.toggle("sel",b.checked); drawSelBar(); });
    el.querySelectorAll("[data-act]").forEach(b=>b.onclick=()=>doNext(b.dataset.act));
    el.querySelectorAll("[data-menu]").forEach(b=>b.onclick=()=>navigate(`#/post/${b.dataset.menu}/edit`,{profileSlug:slug}));
    el.querySelectorAll("[data-view]").forEach(b=>b.onclick=()=>navigate(`#/post/${b.dataset.view}`,{profileSlug:slug}));
  }
  function byId(id){ return posts.find(p=>p.id===id)||{}; }
  async function doNext(id){ const p=byId(id), n=NEXT[p.status]; if(!n) return;
    try{ if(n.brief){ toast("Writing via claude -p… (a few seconds)"); await api(postUrl(id,slug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else { await api(postUrl(id,slug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
      renderProfile(slug); renderRail(); }catch(e){ toast("✗ "+e.message); } }

  $("#main").querySelectorAll(".chip").forEach(c=>c.onclick=()=>{ FILTER=c.dataset.f;
    $("#main").querySelectorAll(".chip").forEach(x=>x.classList.toggle("on",x===c)); drawList(); });
  $("#main").querySelectorAll(".chan-pill").forEach(p=>p.onclick=()=>{
    CHAN_FILTER = CHAN_FILTER===p.dataset.cf ? null : p.dataset.cf;
    $("#main").querySelectorAll(".chan-pill").forEach(x=>x.classList.toggle("on",x.dataset.cf===CHAN_FILTER));
    $("#main").querySelectorAll(".chan-pill-wrap").forEach(x=>x.classList.toggle("on",x.querySelector(".chan-pill")?.dataset.cf===CHAN_FILTER));
    drawList(); });
  $("#main").querySelectorAll(".chan-gear").forEach(btn=>btn.onclick=e=>{
    e.stopPropagation(); navigate(`#/channel/${btn.dataset.cg}/setup`,{profileSlug:slug});
  });
  $("#writeAll").onclick=()=>writeAllIdeas(slug);
  $("#addChanBtn").onclick=e=>{ e.stopPropagation(); openNewChannel(slug); };
  $("#setupBtn").onclick=()=>navigate(`#/profile/${slug}/setup`);
  $("#addIdea").onclick=()=>navigate(`#/profile/${slug}/add`);
  $("#genIdeas").onclick=()=>navigate(`#/profile/${slug}/generate`);
  drawList();
}

// Write every idea-stage post into a full brief, ONE AT A TIME, refreshing the
// list after each so drafts appear as they land (instead of all at the end).
// Each brief is a Sonnet `claude -p` job (~10-15s); the endpoint re-indexes per
// call, so a re-render reflects the new Draft immediately.
let _writingAll = false;
async function writeAllIdeas(slug){
  if(_writingAll) return;
  const isIdea = p => p.status==="planned" || p.status==="approved_slot";
  let done = 0;
  _writingAll = true;
  try{
    while(true){
      const posts = await api(`/api/profile/${slug}/posts`);
      const left = posts.filter(isIdea);
      const next = left[0];
      if(!next){ toast(done? `All ideas written ✓ (${done})` : "No ideas to write — generate some first"); break; }
      toast(`✍ Writing briefs… ${left.length} left (Sonnet, ~15s each)`, true);
      try{ await api(postUrl(next.id,slug,"/brief"),{method:"POST"}); }
      catch(e){ toast("✗ stopped: "+e.message); break; }
      done++;
      await renderProfile(slug);     // the just-written post now shows as a Draft
    }
  } finally {
    _writingAll = false;
    renderRail();
  }
}

function selectProfileSetup(slug){ navigate(`#/profile/${slug}/setup`); }

async function renderProfileSetup(slug){
  CURRENT_PROFILE_SLUG = slug;
  const [profData] = await Promise.all([api(`/api/profile/${slug}`), ensureIdRegistry()]);
  const profName = profData.name||slug;
  const setupTabId = composedIdOnly(OSID.tabProf(slug, "setup"));
  const voiceId = composedIdOnly(OSID.profVoice(slug));
  const briefSpecId = composedIdOnly(OSID.profBriefSpec(slug));
  $("#main").innerHTML = `${pageHeader("Profile setup", profName, `<button class="btn danger-btn" id="delProfBtn" style="color:#c0392b">Delete profile</button><button class="btn primary" id="saveProfBtn">Save</button>`, setupTabId || OSID.prof(slug))}
    <div class="scroll">
      <div style="max-width:740px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px">
          <div>
            ${flabel("Display name")}
            <input id="ps-name" value="${esc(profName)}" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
          <div>
            ${flabel("Topic / niche")}
            <input id="ps-topic" value="${esc(profData.topic||"")}" placeholder="e.g. Film reviews for movie lovers" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
        </div>
        ${flabel("Brand voice & tone", voiceId)}
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">Describe how this brand speaks — personality, tone, things to always or never say, example phrases. This context is injected into every AI generation for this profile.</p>
        <textarea id="ps-voice" style="width:100%;min-height:340px;border:1px solid var(--hair);border-radius:12px;padding:16px 18px;font:13.5px/1.75 var(--body);background:rgba(255,255,255,.82);resize:vertical">${esc(profData.voice||"")}</textarea>
        <div style="margin-top:26px">${flabel("Post brief spec", briefSpecId)}</div>
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">Per-profile output rules for new posts only. Changing this does not alter briefs already written. Other profiles have their own spec file.</p>
        <textarea id="ps-brief" placeholder="e.g. Captions 80–150 words, punchy first line. Max 8 hashtags. Prefer carousels (5–7 slides) with bold text overlays. Always end with a question CTA." style="width:100%;min-height:200px;border:1px solid var(--hair);border-radius:12px;padding:16px 18px;font:13.5px/1.75 var(--body);background:rgba(255,255,255,.82);resize:vertical">${esc(profData.brief_spec||"")}</textarea>
      </div>
    </div>`;
  wireIdChips($("#main"));
  $("#saveProfBtn").onclick = async()=>{
    const profile={name:$("#ps-name").value, topic:$("#ps-topic").value, voice:$("#ps-voice").value};
    const spec=$("#ps-brief").value;
    try{
      await jpost(`/api/profile/${slug}/update`, profile);
      await jpost(`/api/profile/${slug}/brief-spec`, {text: spec});
      toast("Saved ✓"); renderRail();
    }
    catch(e){ toast("✗ "+e.message); }
  };
  $("#delProfBtn").onclick = ()=>navigate(`#/profile/${slug}/delete`);
}

async function renderChannelGuidelines(slug){
  $("#main").innerHTML = `${pageHeader("Channel guidelines", slug, `<button class="btn" id="refineBtn">✨ Refine with AI</button><button class="btn primary" id="saveBtn">Save</button>`, OSID.chan(slug))}
    <div style="padding:0 24px 8px;font-size:12px;color:var(--dim)">Injected into every generation for this channel</div>
    <div class="scroll">
      <p style="color:var(--dim);font-size:12px;margin:0 0 12px">Use <code>## General</code> + per-platform sections. These guidelines are injected into every generation for this channel.</p>
      <textarea id="glText" rows="22" style="width:100%;border:1px solid var(--hair);border-radius:12px;padding:14px 16px;font:12px/1.6 ui-monospace,Menlo,monospace;background:rgba(255,255,255,.82);resize:vertical" placeholder="Add guidelines here…"></textarea>
    </div>`;
  try{
    const d = await api(`/api/channel/${slug}/guidelines`);
    const t = $("#glText"); if(t) t.value = d.text||"";
  }catch(e){ toast("Could not load guidelines: "+e.message); }
  $("#saveBtn").onclick = async()=>{
    const text = $("#glText").value;
    try{ await api(`/api/channel/${slug}/guidelines`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})}); toast("Guidelines saved ✓"); }
    catch(e){ toast("✗ "+e.message); }
  };
  $("#refineBtn").onclick = async()=>{
    const btn = $("#refineBtn"), t = $("#glText");
    btn.textContent = "refining…"; btn.disabled = true;
    try{
      const d = await api(`/api/channel/${slug}/guidelines/refine`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t.value})});
      t.value = d.refined;
      toast("Refined — review and Save when ready");
    }catch(e){ toast("✗ "+e.message); }
    finally{ btn.textContent = "✨ Refine with AI"; btn.disabled = false; }
  };
}

// ── Brief content renderer (shared by post detail + revise pages) ───────────

// "cover_overlay" → "Cover overlay". Field labels come from the brief itself.
function humanizeKey(k){ return String(k).replace(/[_-]+/g," ").replace(/^\w/,c=>c.toUpperCase()); }

function sentenceCase(s){
  const t=String(s||"").trim();
  if(!t) return t;
  const words=t.split(/\s+/), first=words[0]||"";
  if(first.length>=2&&first.length<=4&&first===first.toUpperCase()&&/^[A-Z]+$/.test(first)){
    const rest=words.slice(1).join(" ").toLowerCase();
    return rest?first+" "+rest:first;
  }
  return t.charAt(0).toUpperCase()+t.slice(1).toLowerCase();
}

function isSlideOverlayItem(o){
  return o&&typeof o==="object"&&("overlay" in o||"slide" in o);
}

function renderSlideOverlayList(items, postId, opts = {}){
  const rows = items.map((o, i) => {
    const n = o.slide ?? (i + 1);
    const text = o.overlay ?? "";
    const fld = OSID.briefFld(postId, `slide-${n}`);
    return `<div style="display:flex;align-items:flex-start;gap:8px">`
      + `<span style="font:700 12px/1.5 var(--body);color:var(--dim);min-width:16px;text-align:right;padding-top:8px;flex-shrink:0">${esc(String(n))}</span>`
      + `<div style="flex:1">`
      + `<div style="margin-bottom:4px">${sectionIdChip(fld)}</div>`
      + `<div style="font-size:12.5px;line-height:1.5;background:rgba(0,0,0,.04);border-radius:8px;padding:6px 10px;white-space:pre-wrap">${esc(text)}</div>`
      + `</div></div>`;
  }).join("");
  const addBtn = opts.showAdd
    ? `<button type="button" class="btn" id="pd-add-slide" style="margin-top:8px;font-size:11.5px">＋ Slide</button>`
    : "";
  return `<div style="display:flex;flex-direction:column;gap:8px">${rows}${addBtn}</div>`;
}

function renderGenPromptList(prompts, postId){
  return `<div style="display:flex;flex-direction:column;gap:10px">` + prompts.map((text, i) => {
    const n = i + 1;
    const fld = `gen-prompt-${n}`;
    const chipId = OSID.briefFld(postId, fld);
    return `<div style="display:flex;gap:10px;align-items:flex-start">`
      + `<span style="font:700 12px/1.5 var(--body);color:var(--dim);min-width:20px;text-align:right;padding-top:8px;flex-shrink:0">${esc(String(n))}</span>`
      + `<div style="flex:1">`
      + `<div style="margin-bottom:4px">${sectionIdChip(chipId)}</div>`
      + `<div style="font-size:12.5px;line-height:1.55;background:rgba(0,0,0,.04);border-radius:8px;padding:8px 12px;white-space:pre-wrap;border:1px solid var(--hair)">${esc(text)}</div>`
      + `</div></div>`;
  }).join("") + `</div>`;
}

// Render ONE brief value by its shape — no hardcoded field names. This is what
// makes each profile's brief render its OWN output: whatever fields that
// profile's brief-spec produced get shown, in authored order, nothing assumed.
function renderBriefValue(v){
  if(v==null||v==="") return "";
  if(Array.isArray(v)){
    if(!v.length) return "";
    if(typeof v[0]==="object"&&v[0]!==null){
      if(v.every(isSlideOverlayItem)) return renderSlideOverlayList(v);
      return `<div style="display:flex;flex-direction:column;gap:6px">`+v.map(o=>
        `<div style="font-size:12.5px;line-height:1.5;background:rgba(0,0,0,.04);border-radius:8px;padding:6px 10px;white-space:pre-wrap">`
        +Object.entries(o).filter(([,val])=>val!=null&&val!=="")
          .map(([kk,val])=>`<b style="color:var(--ink2)">${esc(humanizeKey(kk))}:</b> ${esc(Array.isArray(val)?val.join(" · "):val)}`).join("&nbsp; · &nbsp;")
        +`</div>`).join("")+`</div>`;
    }
    return `<div style="font-size:12.5px;line-height:1.6;color:var(--navy)">${v.map(esc).join(" · ")}</div>`;
  }
  if(typeof v==="object"){                              // nested object, e.g. visual_brief
    return Object.entries(v).filter(([,val])=>val!=null&&val!=="").map(([kk,val])=>
      `<div style="font-size:12.5px;line-height:1.55;margin-bottom:4px"><b style="color:var(--ink2)">${esc(humanizeKey(kk))}:</b> ${renderBriefValue(val)}</div>`
    ).join("");
  }
  return `<div style="font-size:13px;line-height:1.6;white-space:pre-wrap;background:rgba(0,0,0,.03);border-radius:10px;padding:10px 12px">${esc(v)}</div>`;
}

// Identity fields stored on the brief JSON but shown elsewhere in the post UI.
const BRIEF_UI_SKIP = new Set(["id", "channels"]);

function briefSect(h, b, fldId){
  const chip = fldId ? sectionIdChip(fldId) : "";
  return `<div style="margin-top:16px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
      <div style="font:700 11px/1 var(--body);letter-spacing:.07em;text-transform:uppercase;color:var(--dim)">${esc(h)}</div>${chip}
    </div>${b}</div>`;
}

function renderBriefEditField(key, value, postId){
  const label = humanizeKey(key);
  const fldId = OSID.briefFld(postId, key);
  if (key === "slide_overlays" && Array.isArray(value) && value.every(isSlideOverlayItem)) {
    return value.map((o, i) => {
      const n = o.slide ?? (i + 1);
      return `${flabel(`${label} ${n}`)}${fta(
        `brief.slide.${i}`, o.overlay || "", 4,
        `data-brief-field="slide_overlays" data-brief-idx="${i}"`,
        OSID.briefFld(postId, `slide-${n}`),
      )}`;
    }).join("");
  }
  if (key === "gen_prompts" && Array.isArray(value) && value.length && typeof value[0] === "string") {
    return value.map((text, i) => `${flabel(`${label} ${i + 1}`)}${fta(
      `brief.gen.${i}`, text, 5,
      `data-brief-field="gen_prompts" data-brief-idx="${i}"`,
      OSID.briefFld(postId, `gen-prompt-${i + 1}`),
    )}`).join("");
  }
  if (typeof value === "string" || value == null || typeof value === "number") {
    const text = value == null ? "" : String(value);
    const rows = text.length > 140 ? 6 : text.includes("\n") ? 5 : 3;
    return `${flabel(label)}${fta(`brief.${key}`, text, rows, `data-brief-field="${esc(key)}"`, fldId)}`;
  }
  if (Array.isArray(value) && value.every(v => typeof v === "string")) {
    return `${flabel(label)}${fta(
      `brief.${key}`, value.join("\n"), Math.max(3, value.length + 1),
      `data-brief-field="${esc(key)}" data-brief-type="lines"`, fldId,
    )}`;
  }
  return `${flabel(label)}${fta(
    `brief.${key}`, JSON.stringify(value, null, 2), 8,
    `data-brief-field="${esc(key)}" data-brief-type="json"`, fldId,
  )}`;
}

function renderBriefEditSection(brief, postId){
  if (!brief || brief._error) return "";
  const fields = Object.entries(brief)
    .filter(([k]) => !k.startsWith("_") && !BRIEF_UI_SKIP.has(k))
    .map(([k, v]) => renderBriefEditField(k, v, postId))
    .join("");
  if (!fields) return "";
  const brId = sectionIdChip(OSID.brief(postId));
  return `<div style="margin-top:28px;padding-top:22px;border-top:1px solid var(--hair)">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <div style="font:700 11px/1 var(--body);letter-spacing:.07em;text-transform:uppercase;color:var(--dim)">Brief</div>${brId}
    </div>${fields}</div>`;
}

function briefFromEditForm(root, originalBrief){
  const out = JSON.parse(JSON.stringify(originalBrief || {}));
  root.querySelectorAll("[data-brief-field]:not([data-brief-idx])").forEach(el => {
    const key = el.dataset.briefField;
    const type = el.dataset.briefType;
    if (type === "json") {
      const raw = el.value.trim();
      if (!raw) { delete out[key]; return; }
      try { out[key] = JSON.parse(raw); }
      catch { throw new Error(`Invalid JSON in ${humanizeKey(key)}`); }
      return;
    }
    if (type === "lines") {
      const lines = el.value.split("\n").map(s => s.trim()).filter(Boolean);
      if (lines.length) out[key] = lines;
      else delete out[key];
      return;
    }
    const v = el.value.trim();
    if (v) out[key] = v;
    else delete out[key];
  });
  if (Array.isArray(out.slide_overlays)) {
    const slides = out.slide_overlays.map((item, i) => ({ ...item }));
    root.querySelectorAll('[data-brief-field="slide_overlays"]').forEach(el => {
      const i = +el.dataset.briefIdx;
      if (!slides[i] || typeof slides[i] !== "object") return;
      slides[i] = { ...slides[i], overlay: el.value };
    });
    out.slide_overlays = slides;
  }
  if (Array.isArray(out.gen_prompts)) {
    const prompts = [...out.gen_prompts];
    root.querySelectorAll('[data-brief-field="gen_prompts"]').forEach(el => {
      const i = +el.dataset.briefIdx;
      if (i < 0 || i >= prompts.length) return;
      prompts[i] = el.value;
    });
    out.gen_prompts = prompts;
  }
  return out;
}

// Schema-agnostic: render exactly the fields the profile's brief contains.
function renderBriefBody(slot, brief, n, postId){
  let body="";
  if(slot.concept&&!brief) body+=briefSect("Concept",`<div style="font-size:13px;line-height:1.6">${esc(slot.concept)}</div>`);
  if(slot.working_title&&!brief) body+=briefSect("Working title",`<div style="font-size:13px;line-height:1.6">${esc(slot.working_title)}</div>`);
  if(brief&&brief._error) body+=briefSect("Brief",`<div style="color:#c0392b;font-size:13px">${esc(brief._error)}</div>`);
  else if(brief){
    const brId = postId ? OSID.brief(postId) : null;
    if(brId) body+=`<div style="display:flex;align-items:center;gap:8px;margin-top:16px;margin-bottom:8px;flex-wrap:wrap">
      <div style="font:700 11px/1 var(--body);letter-spacing:.07em;text-transform:uppercase;color:var(--dim)">Brief</div>${sectionIdChip(brId)}</div>`;
    for(const [k,v] of Object.entries(brief)){
      if(k.startsWith("_")||BRIEF_UI_SKIP.has(k)) continue;
      const shown=k==="cover_overlay"?sentenceCase(v):v;
      let html;
      if(k==="slide_overlays"&&Array.isArray(shown)&&shown.every(isSlideOverlayItem))
        html=renderSlideOverlayList(shown, postId, { showAdd: true });
      else if(k==="gen_prompts"&&Array.isArray(shown)&&shown.length&&typeof shown[0]==="string")
        html=renderGenPromptList(shown, postId);
      else html=renderBriefValue(shown);
      const fldId = postId ? OSID.briefFld(postId, k) : null;
      if(html) body+=briefSect(humanizeKey(k), html, fldId);
    }
  } else {
    body+=`<div style="margin-top:16px;color:var(--dim);font-size:13px">Not written yet${n&&n.brief?` — click <b>${esc(n.label)}</b> to generate.`:"."}</div>`;
  }
  return body;
}

// ── Post detail (replaces showDetail modal) ──────────────────────────────────
async function renderPostDetail(id, profileSlug){
  let detail;
  try{
    [detail] = await Promise.all([api(postUrl(id,profileSlug)), ensureIdRegistry()]);
  }catch(e){ return toast("✗ "+e.message); }
  const slot=detail.slot||{}, brief=detail.brief||null;
  CURRENT_PROFILE_SLUG = profileSlug || detail.profile_slug || null;
  CURRENT_POST = { id, slot, brief };
  const st=slot.status||"planned", n=NEXT[st];
  const title=slot.working_title||slot.pillar||id;
  const canRevise=["planned","approved_slot","briefed","approved"].includes(st);
  const meta=[["Date",slot.date],["Format",slot.format],["Pillar",slot.pillar],
              ["Objective",slot.objective]]
    .filter(([,v])=>v!=null&&v!=="").map(([k,v])=>metaPlain(k,v)).join("");
  const chanSlugs=(slot.channels||[]).filter(Boolean);
  const chanMeta=chanSlugs.length
    ? `<span class="meta-plain" style="font-size:11px;color:var(--dim)"><b style="color:var(--ink2)">Channels:</b> ${chanSlugs.map(esc).join(", ")}</span>`
    : "";
  const crumb=(_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{}).name||profileSlug||"Back";
  const btns=[
    `<button class="btn danger-btn" id="pd-del">Delete</button>`,
    n?`<button class="btn primary" id="pd-next">${esc(n.label)}</button>`:"",
    canRevise?`<button class="btn" id="pd-revise">✨ Revise</button>`:"",
    `<button class="btn" id="pd-edit">Edit</button>`,
  ].filter(Boolean).join("");
  $("#main").innerHTML=`${pageHeader(title,crumb,btns, OSID.post(id))}
    <div class="scroll" style="max-width:640px">
      <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">${meta}${chanMeta}</div>
      ${renderBriefBody(slot,brief,n,id)}</div>`;
  wireIdChips($("#main"));
  const addSlide=document.getElementById("pd-add-slide");
  if(addSlide) addSlide.onclick=async()=>{
    const overlay=prompt("Slide overlay (3 lines: show name / season+year / one-line description):");
    if(!overlay||!overlay.trim()) return;
    try{
      const out=await jpost(postUrl(id,profileSlug,"/slide/new"),{overlay:overlay.trim()});
      toast(`Slide ${out.slide} added · ${out.field_id||""}`);
      navigate(`#/post/${id}`,{profileSlug});
    }catch(e){ toast("✗ "+e.message); }
  };
  document.getElementById("pd-del").onclick=()=>navigate(`#/post/${id}/delete`,{profileSlug});
  document.getElementById("pd-edit").onclick=()=>navigate(`#/post/${id}/edit`,{profileSlug});
  const rdBtn=document.getElementById("pd-revise"); if(rdBtn) rdBtn.onclick=()=>navigate(`#/post/${id}/revise`,{profileSlug});
  const nb=document.getElementById("pd-next"); if(nb) nb.onclick=async()=>{
    nb.disabled=true;
    try{ if(n.brief){ toast("Writing via claude -p…",true); await api(postUrl(id,profileSlug,"/brief"),{method:"POST"}); toast("Draft ready ✓"); }
      else{ await api(postUrl(id,profileSlug,"/status"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
      navigate(`#/post/${id}`,{profileSlug}); }
    catch(e){ nb.disabled=false; toast("✗ "+e.message); }
  };
}

// ── Edit post (replaces rowMenu modal) ───────────────────────────────────────
async function renderEditPost(id, profileSlug){
  let detail; try{ detail=await api(postUrl(id,profileSlug)); }catch(e){ return toast("✗ "+e.message); }
  const slot=detail.slot||{}, brief=detail.brief||null;
  CURRENT_PROFILE_SLUG = profileSlug || detail.profile_slug || null;
  CURRENT_POST = { id, slot, brief };
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{channels:[]};
  const chanHint=(profNode.channels||[]).map(c=>c.slug).join(", ")||"e.g. my-profile-tiktok";
  const crumb=profNode.name||profileSlug||"Back";
  const briefSection = brief && !brief._error ? renderBriefEditSection(brief, id) : "";
  $("#main").innerHTML=`${pageHeader("Edit post",crumb,`<button class="btn danger-btn" id="ep-del">Delete</button><button class="btn primary" id="ep-save">Save</button>`, OSID.post(id))}
    <div class="scroll"><div class="fpage">
      <div style="font:700 11px/1 var(--body);letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin-bottom:14px">Slot</div>
      ${flabel("Title")}${finput("working_title",slot.working_title||"",'placeholder="short internal label"')}
      ${flabel("Concept")}${fta("concept",slot.concept||"",3,'placeholder="what this post does and why"')}
      ${flabel("Date")}${finput("date",slot.date||"",'type="date"')}
      ${flabel("Format")}${finput("format",slot.format||"carousel",'placeholder="carousel | reel | short"')}
      ${flabel("Pillar")}${finput("pillar",slot.pillar||"")}
      ${flabel("Objective")}${finput("objective",slot.objective||"")}
      ${flabel("Channels (slugs, comma-separated)")}${finput("channels",(slot.channels||[]).join(", "),`placeholder="${chanHint}"`)}
      ${briefSection}
    </div></div>`;
  wireIdChips($("#main"));
  document.getElementById("ep-save").onclick=async()=>{
    const data=formVals($("#main"));
    const payload={...data};
    if (brief && !brief._error) {
      try{ payload.brief=briefFromEditForm($("#main"), brief); }
      catch(e){ return toast("✗ "+e.message); }
    }
    try{ await api(postUrl(id,profileSlug,"/update"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      toast("Saved ✓"); navigate(`#/post/${id}`,{profileSlug}); }catch(e){ toast("✗ "+e.message); }
  };
  document.getElementById("ep-del").onclick=()=>navigate(`#/post/${id}/delete`,{profileSlug});
}

// ── Revise with AI ───────────────────────────────────────────────────────────
async function renderRevise(id){
  let detail; try{ detail=await api(`/api/post/${id}`); }catch(e){ return toast("✗ "+e.message); }
  const slot=detail.slot||{}, brief=detail.brief||null;
  const kind=brief?"draft":"idea", title=slot.working_title||slot.pillar||id;
  const profileSlug=detail.profile_slug||"";
  CURRENT_PROFILE_SLUG = profileSlug || null;
  CURRENT_POST = { id, slot, brief };
  $("#main").innerHTML=`${pageHeader("✨ Revise with AI",title,`<button class="btn primary" id="rv-go">Revise</button>`, OSID.post(id))}
    <div class="scroll"><div class="fpage">
      <p style="font-size:13px;color:var(--dim);margin:0 0 16px;line-height:1.55">
        Describe what should change in this ${kind}. The AI will apply your instruction and preserve everything else.
      </p>
      ${flabel("Instruction")}${fta("instruction","",4,'placeholder="e.g. punchier hook, caption under 200 chars, focus on 90s thrillers" required')}
    </div></div>`;
  document.getElementById("rv-go").onclick=async()=>{
    const btn=document.getElementById("rv-go"), instruction=$("#main textarea[name=instruction]").value.trim();
    if(!instruction) return toast("Enter an instruction first");
    btn.disabled=true; btn.textContent="Revising…"; toast("✨ Revising via claude -p…",true);
    try{ await jpost(`/api/post/${id}/revise`,{instruction}); toast("Revised ✓");
      navigate(`#/post/${id}`,{profileSlug}); }
    catch(e){ btn.disabled=false; btn.textContent="Revise"; toast("✗ "+e.message); }
  };
}

// ── New / edit project ───────────────────────────────────────────────────────
function renderNewProject(){
  $("#main").innerHTML=`${pageHeader("New project","Projects",`<button class="btn primary" id="np-save">Create project</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Name")}${finput("name","",'placeholder="My Venture" required')}
      ${flabel("Slug (auto-filled, editable)")}${finput("slug","",'placeholder="my-venture" required')}
      ${flabel("Kind")}${fsel("kind",[["venture","Venture"],["brand","Brand"]],"venture")}
      ${flabel("Priority")}${fsel("priority",[["primary","Primary"],["secondary","Secondary"],["experiment","Experiment"]],"primary")}
      ${flabel("Status")}${fsel("status",[["idea","Idea"],["prototype","Prototype"],["live","Live"],["revenue","Revenue"]],"idea")}
    </div></div>`;
  const n=$("#main input[name=name]"), s=$("#main input[name=slug]");
  n.oninput=()=>{ if(!s.dataset.manual) s.value=slugify(n.value); };
  s.oninput=()=>{ s.dataset.manual=s.value?"1":""; };
  document.getElementById("np-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost("/api/project/new",data); if(data.slug){OPEN.projects.add(data.slug);saveOpen();} toast("Project created ✓"); await renderRail(); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
}

async function renderEditProject(slug){
  let e={}; try{ e=(await api(`/api/project/${slug}`)).entity||{}; }catch(_){}
  $("#main").innerHTML=`${pageHeader("Edit project",e.name||slug,`<button class="btn danger-btn" id="ep2-del">Delete project</button><button class="btn primary" id="ep2-save">Save</button>`, OSID.proj(slug))}
    <div class="scroll"><div class="fpage">
      ${flabel("Name")}${finput("name",e.name||"",'required')}
      ${flabel("Kind")}${fsel("kind",[["venture","Venture"],["brand","Brand"]],e.subtype||"venture")}
      ${flabel("Priority")}${fsel("priority",[["primary","Primary"],["secondary","Secondary"],["experiment","Experiment"]],e.priority||"primary")}
      ${flabel("Status")}${fsel("status",[["idea","Idea"],["prototype","Prototype"],["live","Live"],["revenue","Revenue"]],e.status||"idea")}
      ${flabel("Hours / week")}${finput("hours_per_week",String(e.hours_per_week??0),'type="number" min="0"')}
      <p style="margin-top:12px;font-size:11.5px;color:var(--dim)">Slug <b>${esc(slug)}</b> is fixed — it's the identity used across files.</p>
    </div></div>`;
  document.getElementById("ep2-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost(`/api/project/${slug}/update`,data); toast("Project updated ✓"); await renderRail(); refreshViews(); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
  document.getElementById("ep2-del").onclick=()=>navigate(`#/project/${slug}/delete`);
}

// ── Project section artifacts (files → reindex → IDs stay in sync) ───────────
function renderNewIntake(projectSlug){
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  $("#main").innerHTML = `${pageHeader("New intake", projName, `<button class="btn primary" id="ni-save">Create intake</button>`)}
    <div class="scroll"><div class="fpage">
      <p style="font-size:13px;color:var(--dim);margin:0 0 12px;line-height:1.55">
        Creates <code>strategy/intake.md</code> with starter headings. Edit in chat or your editor; IDs update on save via reindex.
      </p>
    </div></div>`;
  document.getElementById("ni-save").onclick = async () => {
    try {
      const out = await jpost(`/api/project/${projectSlug}/intake/new`, {});
      toast(`Intake created · ${out.path || ""}`);
      await renderRail(); navigate(`#/project/${projectSlug}/validation`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

function renderNewTechnical(projectSlug){
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  $("#main").innerHTML = `${pageHeader("New technical", projName, `<button class="btn primary" id="nt-save">Create technical</button>`)}
    <div class="scroll"><div class="fpage">
      <p style="font-size:13px;color:var(--dim);margin:0 0 12px;line-height:1.55">
        Creates <code>technical.md</code> with starter sections. Edit each with ✎ on the Technical tab.
      </p>
    </div></div>`;
  document.getElementById("nt-save").onclick = async () => {
    try {
      const out = await jpost(`/api/project/${projectSlug}/technical/new`, {});
      toast(`Technical created · ${out.path || ""}`);
      await renderRail(); navigate(`#/project/${projectSlug}/technical`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderNewDocSubsection(projectSlug, docKey){
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const tab = docKey === "technical" ? "technical" : docKey;
  $("#main").innerHTML = `${pageHeader("New subsection", projName, `<button class="btn primary" id="ns-save">Add subsection</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Section title")}${finput("title", "", 'placeholder="e.g. Security" required')}
      <p style="font-size:12px;color:var(--dim);margin:12px 0 0">Adds a heading to this project&apos;s ${esc(docKey)} list and <code>${esc(docKey)}.md</code>.</p>
    </div></div>`;
  document.getElementById("ns-save").onclick = async () => {
    const title = ($("#main input[name=title]").value || "").trim();
    if (!title) return toast("Title required");
    try {
      await jpost(`/api/project/${projectSlug}/subsections/add`, { doc: docKey, title });
      toast(`Subsection added · ${title}`);
      await renderRail(); navigate(`#/project/${projectSlug}/${tab}`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderEditDocSubsection(projectSlug, docKey, titleKey, extras = {}){
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const tab = docKey === "technical" ? "technical" : docKey;
  const p = await api(`/api/project/${projectSlug}`);
  const order = projectDocSubsections(p, docKey);
  const title = extras.subTitle
    || order.find(t => OSID.slugKey(t) === titleKey)
    || order.find(t => t.toLowerCase() === String(titleKey || "").replace(/-/g, " "));
  if (!title) {
    $("#main").innerHTML = `<div class="scroll"><p class="memo-empty">Subsection not found.</p></div>`;
    return;
  }
  const sec = (p.sections || {})[tab] || {};
  const art = (sec.artifacts || []).find(a => {
    if (a.kind !== "file") return false;
    const p = a.path || "";
    if (docKey === "intake") return p.endsWith("strategy/intake.md");
    return p.endsWith(`${docKey}.md`);
  });
  const parsed = Object.fromEntries(parseMdSections(art?.text || "").map(s => [s.title, s.body]));
  const body = (parsed[title] || "").trim();
  const subId = docSubsectionId(projectSlug, p, docKey, title);
  $("#main").innerHTML = `${pageHeader(`Edit · ${title}`, projName, `<button class="btn primary" id="es-save">Save</button>`, subId)}
    <div class="scroll"><div class="fpage">
      <p style="font-size:12px;color:var(--dim);margin:0 0 10px">Markdown for <b>${esc(title)}</b> only.</p>
      <textarea id="es-body" style="width:100%;min-height:320px;border:1px solid var(--hair);border-radius:12px;padding:14px 16px;font:13.5px/1.65 var(--body);resize:vertical">${esc(body)}</textarea>
    </div></div>`;
  document.getElementById("es-save").onclick = async () => {
    try {
      await jpost(`/api/project/${projectSlug}/doc/${docKey}/section`, { title, body: $("#es-body").value });
      toast(`Saved · ${title}`);
      await renderRail(); navigate(`#/project/${projectSlug}/${tab}`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderNewMemo(projectSlug, memoType){
  await ensureSchemas();
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const label = memoTypeLabel(memoType);
  const fields = schemaFields("memo", memoType);
  const formHtml = fields.map(renderSchemaField).join("");
  $("#main").innerHTML = `${pageHeader("New memo", `${projName} · ${label}`, `<button class="btn primary" id="nm-save">Create memo</button>`)}
    <div class="scroll"><div class="fpage">
      <p style="font-size:12px;color:var(--dim);margin:0 0 14px">Next version: <code>${esc(memoType)}-vN.json</code> — same schema as chat/osctl writes.</p>
      ${formHtml}
    </div></div>`;
  document.getElementById("nm-save").onclick = async () => {
    const data = { ...formVals($("#main")), type: memoType };
    try {
      const out = await jpost(`/api/project/${projectSlug}/memo/new`, data);
      toast(`Memo created · ${out.id || ""}`);
      await renderRail();
      const back = memoType === "problem-validation" ? "validation"
        : memoType === "assessment" ? "overview" : "pricing";
      navigate(`#/project/${projectSlug}/${back}`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderNewExperiment(projectSlug){
  await ensureSchemas();
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const formHtml = schemaFields("experiment").map(renderSchemaField).join("");
  $("#main").innerHTML = `${pageHeader("New experiment", projName, `<button class="btn primary" id="ne-save">Create experiment</button>`)}
    <div class="scroll"><div class="fpage">${formHtml}</div></div>`;
  document.getElementById("ne-save").onclick = async () => {
    const data = formVals($("#main"));
    if (!data.assumption?.trim()) return toast("Assumption is required");
    try {
      const out = await jpost(`/api/project/${projectSlug}/experiment/new`, data);
      toast(`Experiment created · ${out.id || ""}`);
      await renderRail(); navigate(`#/project/${projectSlug}/experiments`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

function renderNewProduct(projectSlug){
  const projName = (_TREE.find(p => p.slug === projectSlug) || {}).name || projectSlug;
  const typeOpts = [["app","App"],["physical","Physical"],["service","Service"]];
  $("#main").innerHTML = `${pageHeader("New product", projName, `<button class="btn primary" id="npd-save">Create product</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Name")}${finput("name","",'placeholder="Acme App" required')}
      ${flabel("Slug")}${finput("slug","",'placeholder="acme-app" required')}
      ${flabel("Type")}${fsel("type",typeOpts,"app")}
    </div></div>`;
  const n = $("#main input[name=name]"), s = $("#main input[name=slug]");
  n.oninput = () => { if (!s.dataset.manual) s.value = slugify(n.value); };
  s.oninput = () => { s.dataset.manual = s.value ? "1" : ""; };
  document.getElementById("npd-save").onclick = async () => {
    const data = formVals($("#main"));
    try {
      const out = await jpost(`/api/project/${projectSlug}/product/new`, data);
      toast(`Product created · ${out.id || ""}`);
      await renderRail(); navigate(`#/project/${projectSlug}/product`);
    } catch (e) { toast("✗ " + e.message); }
  };
}

async function renderNewFeature(productSlug, projectSlug){
  await ensureSchemas();
  const back = projectSlug ? `#/project/${projectSlug}/product` : "#/calendar";
  let fields = schemaFields("feature");
  if (projectSlug) {
    try {
      const proj = await api(`/api/project/${projectSlug}`);
      if (proj.feature?.length) fields = proj.feature;
    } catch (_) { /* global schema defaults */ }
  }
  const formHtml = fields.map(renderSchemaField).join("");
  $("#main").innerHTML = `${pageHeader("New feature", productSlug, `<button class="btn primary" id="nf-save">Add feature</button>`)}
    <div class="scroll"><div class="fpage">${formHtml}</div></div>`;
  document.getElementById("nf-save").onclick = async () => {
    const data = formVals($("#main"));
    if (!data.title?.trim()) return toast("Title is required");
    try {
      const out = await jpost(`/api/product/${productSlug}/feature/new`, data);
      toast(`Feature added · ${out.id || ""}`);
      await renderRail(); navigate(back);
    } catch (e) { toast("✗ " + e.message); }
  };
}

// ── New profile ──────────────────────────────────────────────────────────────
function renderNewProfile(projectSlug){
  const projName=(_TREE.find(p=>p.slug===projectSlug)||{}).name||projectSlug;
  $("#main").innerHTML=`${pageHeader("New profile",projName,`<button class="btn primary" id="nr-save">Create profile</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Name")}${finput("name","",'placeholder="My Brand" required')}
      ${flabel("Slug (auto-filled)")}${finput("slug","",'placeholder="my-brand" required')}
      ${flabel("Topic / niche")}${finput("topic","",'placeholder="e.g. sustainable fashion for Gen-Z"')}
    </div></div>`;
  const n=$("#main input[name=name]"), s=$("#main input[name=slug]");
  n.oninput=()=>{ if(!s.dataset.manual) s.value=slugify(n.value); };
  s.oninput=()=>{ s.dataset.manual=s.value?"1":""; };
  document.getElementById("nr-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost(`/api/project/${projectSlug}/profile/new`,data);
      OPEN.projects.add(projectSlug); if(data.slug) OPEN.profiles.add(data.slug); saveOpen();
      toast("Profile created ✓"); await renderRail(); navigate(`#/profile/${data.slug}`); }
    catch(e){ toast("✗ "+e.message); }
  };
}

// ── New channel ──────────────────────────────────────────────────────────────
function renderNewChannel(profileSlug){
  const profName=(_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{}).name||profileSlug;
  const platOpts=[["instagram","Instagram"],["tiktok","TikTok"],["x","X / Twitter"],["linkedin","LinkedIn"],["youtube","YouTube"],["facebook","Facebook"]];
  $("#main").innerHTML=`${pageHeader("New channel",profName,`<button class="btn primary" id="nc-save">Add channel</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Platform")}${fsel("platform",platOpts,"instagram")}
      ${flabel("Handle (optional)")}${finput("handle","",'placeholder="@handle"')}
    </div></div>`;
  document.getElementById("nc-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost(`/api/profile/${profileSlug}/channel/new`,data);
      OPEN.profiles.add(profileSlug); saveOpen(); toast("Channel created ✓"); await renderRail(); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
}

// ── Channel setup (replaces gear modal) ─────────────────────────────────────
async function renderChannelSetup(channelSlug, profileSlug){
  let ch={}, gl={text:""};
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{channels:[]};
  ch=(profNode.channels||[]).find(c=>c.slug===channelSlug)||{};
  try{ gl=await api(`/api/channel/${channelSlug}/guidelines`); }catch(_){}
  const platOpts=[["instagram","Instagram"],["tiktok","TikTok"],["x","X / Twitter"],["linkedin","LinkedIn"],["youtube","YouTube"],["facebook","Facebook"]];
  const crumb=profNode.name||profileSlug||"Back";
  $("#main").innerHTML=`${pageHeader(`${PLATFORM_ICON[ch.platform]||"⌗"} ${ch.name||ch.platform||channelSlug} setup`,crumb,`<button class="btn danger-btn" id="cs-del">Delete channel</button><button class="btn primary" id="cs-save">Save</button>`, OSID.chan(channelSlug))}
    <div class="scroll"><div class="fpage">
      ${flabel("Platform")}${fsel("platform",platOpts,ch.platform||"instagram")}
      ${flabel("Handle (optional)")}${finput("handle",ch.handle||"",'placeholder="@handle"')}
      ${flabel("Voice & guidelines")}
      <p style="font-size:12px;color:var(--dim);margin:0 0 8px;line-height:1.5">Injected into every generation for this channel.</p>
      ${fta("text",gl.text||"",10,'style="font-family:ui-monospace,Menlo,monospace;font-size:12px"')}
    </div></div>`;
  document.getElementById("cs-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost(`/api/channel/${channelSlug}/update`,{platform:data.platform,handle:data.handle});
      await jpost(`/api/channel/${channelSlug}/guidelines`,{text:data.text});
      toast("Saved ✓"); await renderRail(); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
  document.getElementById("cs-del").onclick=()=>navigate(`#/channel/${channelSlug}/delete`,{profileSlug});
}

// ── Add idea ─────────────────────────────────────────────────────────────────
async function renderAddIdea(slug){
  CURRENT_PROFILE_SLUG = slug;
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===slug)||{channels:[]};
  const chanHint=(profNode.channels||[]).map(c=>c.slug).join(", ")||"e.g. my-profile-tiktok";
  const crumb=profNode.name||slug;
  $("#main").innerHTML=`${pageHeader("Add idea",crumb,`<button class="btn primary" id="ai-save">Add idea</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("working_title","",'placeholder="short internal label"')}
      ${flabel("Concept")}${fta("concept","",3,'placeholder="what this post does and why"')}
      ${flabel("Date")}${finput("date","",'type="date"')}
      ${flabel("Pillar")}${finput("pillar","",'placeholder="e.g. Story Craft"')}
      ${flabel("Channels (slugs, comma-separated)")}${finput("channels",``,`placeholder="${chanHint}"`)}
    </div></div>`;
  document.getElementById("ai-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await api(`/api/profile/${slug}/posts`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
      toast("Idea added ✓"); await renderRail(); navigate(`#/profile/${slug}`); }
    catch(e){ toast("✗ "+e.message); }
  };
}

// ── Generate ideas ───────────────────────────────────────────────────────────
async function renderGenerateIdeas(slug){
  CURRENT_PROFILE_SLUG = slug;
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===slug)||{channels:[]};
  const channels=profNode.channels||[];
  const crumb=profNode.name||slug;
  const isoDay=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  const start=new Date(), end=new Date(Date.now()+14*864e5);
  $("#main").innerHTML=`${pageHeader("Generate ideas",crumb,`<button class="btn primary" id="gi-save">Generate ✦</button>`)}
    <div class="scroll"><div class="fpage">
      <p style="font-size:13px;color:var(--dim);margin:0 0 16px;line-height:1.55">
        Claude will generate a batch of content ideas for this profile. Takes ~15–30s.
      </p>
      ${flabel("Period start")}${finput("period_start",isoDay(start),'type="date" required')}
      ${flabel("Period end")}${finput("period_end",isoDay(end),'type="date" required')}
      ${flabel("Platforms")}${finput("platforms",channels.map(c=>c.platform).join(","),'placeholder="tiktok,instagram"')}
      ${flabel("Cadence (posts per platform / week)")}${finput("cadence","",'placeholder="3"')}
      ${flabel("Focus (optional)")}${finput("focus","",'placeholder="push the launch"')}
    </div></div>`;
  document.getElementById("gi-save").onclick=async()=>{
    const btn=document.getElementById("gi-save"), data=formVals($("#main"));
    btn.disabled=true; btn.textContent="Generating…";
    const payload={period:`${data.period_start} to ${data.period_end}`,platforms:data.platforms,cadence:data.cadence,focus:data.focus};
    toast("⏳ Generating ideas via claude -p… (10–30s)",true);
    navigate(`#/profile/${slug}`);  // navigate away immediately; job runs in background
    try{ await api(`/api/profile/${slug}/plan`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      toast("Ideas generated ✓"); await renderRail(); await renderProfile(slug); }
    catch(e){ toast("✗ "+e.message); }
  };
}

// ── New activity / milestone / edit milestone ────────────────────────────────
async function renderNewActivity(extras={}){
  const projectOpts=_TREE.map(p=>`<option value="${esc(p.slug)}"${extras.entity===p.slug?" selected":""}>${esc(p.name)}</option>`).join("");
  const typeOpts=["task","meeting","call","review","launch"].map(t=>`<option>${t}</option>`).join("");
  $("#main").innerHTML=`${pageHeader("New activity","Operations",`<button class="btn primary" id="na-save">Add activity</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("title","",'placeholder="e.g. Record intro video" required')}
      ${flabel("Project")}<select name="entity">${projectOpts}</select>
      ${flabel("Date")}${finput("date",extras.date||"",'type="date"')}
      ${flabel("Type")}<select name="type">${typeOpts}</select>
    </div></div>`;
  document.getElementById("na-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost("/api/activity/new",data); toast("Activity added ✓"); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
}

async function renderNewMilestone(extras={}){
  const projectOpts=_TREE.map(p=>`<option value="${esc(p.slug)}"${extras.entity===p.slug?" selected":""}>${esc(p.name)}</option>`).join("");
  $("#main").innerHTML=`${pageHeader("New milestone","Calendar",`<button class="btn primary" id="nm-save">Add milestone</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("title","",'placeholder="e.g. Launch v1" required')}
      ${flabel("Date")}${finput("date",extras.date||"",'type="date" required')}
      ${flabel("Project")}<select name="entity">${projectOpts}</select>
      ${flabel("Notes")}${finput("notes",extras.notes||"",'placeholder="optional"')}
    </div></div>`;
  document.getElementById("nm-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost("/api/milestone/new",data); toast("Milestone added ✓"); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
}

async function renderEditMilestone(ref_id, extras={}){
  $("#main").innerHTML=`${pageHeader("Edit milestone","Calendar",`<button class="btn primary" id="em-save">Save</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("title",extras.title||"",'required')}
      ${flabel("Date")}${finput("date",extras.date||"",'type="date"')}
      ${flabel("End date (optional)")}${finput("date_end",extras.date_end||"",'type="date"')}
    </div></div>`;
  document.getElementById("em-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await jpost(`/api/milestone/${ref_id}/update`,data); toast("Milestone updated ✓"); history.back(); }
    catch(e){ toast("✗ "+e.message); }
  };
}

// ── Confirm / delete pages ───────────────────────────────────────────────────
function confirmPage(title, msg, deleteFn){
  $("#main").innerHTML=`<div class="topbar"><div><div class="crumbs"><a class="bk" style="cursor:pointer;color:var(--navy)">← Back</a></div><h1 class="title">${esc(title)}</h1></div></div>
    <div class="scroll"><div class="confirm-box">
      <h2>${esc(title)}</h2>
      <p>${esc(msg)}</p>
      <div class="acts">
        <button class="btn" id="cd-cancel">Cancel</button>
        <button class="btn danger-btn" id="cd-del" style="font-weight:600">Delete</button>
      </div></div></div>`;
  document.getElementById("cd-cancel").onclick=()=>history.back();
  document.getElementById("cd-del").onclick=deleteFn;
}

async function renderConfirmDelete(id, profileSlug){
  let title=id; try{ const d=await api(postUrl(id,profileSlug)); title=(d.slot||{}).working_title||(d.slot||{}).pillar||id; }catch(_){}
  confirmPage("Delete post","Delete this post and its written content? This cannot be undone.",async()=>{
    try{ await api(postUrl(id,profileSlug,"/delete"),{method:"POST"}); toast("Deleted ✓"); await renderRail(); navigate(`#/profile/${profileSlug}`); }
    catch(e){ toast("✗ "+e.message); }
  });
}

async function renderConfirmBulkDelete(ids, profileSlug){
  const n=ids.length;
  confirmPage("Delete posts",`Delete ${n} post${n!==1?"s":""} and their written content? This cannot be undone.`,async()=>{
    try{ const r=await api("/api/posts/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids,profile:profileSlug||undefined})});
      toast(`Deleted ✓ (${r.count})`); await renderRail(); navigate(`#/profile/${profileSlug}`); }
    catch(e){ toast("✗ "+e.message); }
  });
}

async function renderConfirmDeleteProject(slug){
  let name=slug; try{ name=((await api(`/api/project/${slug}`)).entity||{}).name||slug; }catch(_){}
  confirmPage("Delete project",`Delete project "${name}" and all its files? This cannot be undone.`,async()=>{
    try{ await jpost(`/api/project/${slug}/delete`,{}); OPEN.projects.delete(slug); saveOpen();
      toast("Project deleted ✓"); await renderRail(); navigate("#/calendar"); }
    catch(e){ toast("✗ "+e.message); }
  });
}

async function renderConfirmDeleteProfile(slug){
  let name=slug; try{ name=(await api(`/api/profile/${slug}`)).name||slug; }catch(_){}
  confirmPage("Delete profile",`Delete "${name}" and all its posts? This cannot be undone.`,async()=>{
    try{ await jpost(`/api/profile/${slug}/delete`,{}); toast("Profile deleted ✓"); await renderRail(); navigate("#/calendar"); }
    catch(e){ toast("✗ "+e.message); }
  });
}

async function renderConfirmDeleteChannel(channelSlug, profileSlug){
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{channels:[]};
  const ch=(profNode.channels||[]).find(c=>c.slug===channelSlug)||{};
  const name=ch.name||ch.platform||channelSlug;
  confirmPage("Delete channel",`Delete the ${name} channel? Guidelines will be lost.`,async()=>{
    try{ await jpost(`/api/channel/${channelSlug}/delete`,{}); toast("Channel deleted ✓"); await renderRail(); navigate(`#/profile/${profileSlug}`); }
    catch(e){ toast("✗ "+e.message); }
  });
}

// ── AI Consultant (bottom terminal) ────────────────────────────────────────
(function(){
  const stream    = document.getElementById("chat-stream");
  const input     = document.getElementById("chat-input");
  const sendBtn   = document.getElementById("chat-send");
  const statusEl  = document.getElementById("chat-status");
  const attachBtn = document.getElementById("attach-btn");
  const fileInput = document.getElementById("file-input");
  const attachEl  = document.getElementById("attachments");
  const appEl     = document.getElementById("app");

  // ── chat placement: right dock ⟷ bottom-left ⟷ hidden (persisted) ────────
  const CHAT_W_MIN = 320, CHAT_W_MAX = 960;
  const CHAT_H_MIN = 220, CHAT_H_MAX = 720;
  let chatPos = "right", chatHidden = false;
  let chatW = 480, chatH = 380;
  try {
    chatPos = localStorage.getItem("chatPos") || "right";
    chatHidden = localStorage.getItem("chatHidden") === "1";
    chatW = Math.min(CHAT_W_MAX, Math.max(CHAT_W_MIN, parseInt(localStorage.getItem("chatW"), 10) || 480));
    chatH = Math.min(CHAT_H_MAX, Math.max(CHAT_H_MIN, parseInt(localStorage.getItem("chatH"), 10) || 380));
  } catch {}
  function applyChatSize(){
    appEl.style.setProperty("--chat-w", chatW + "px");
    appEl.style.setProperty("--chat-h", chatH + "px");
  }
  function applyChat(){
    appEl.classList.toggle("chat-bl", chatPos === "bl" && !chatHidden);
    appEl.classList.toggle("chat-hidden", chatHidden);
    applyChatSize();
    const moveBtn = document.getElementById("chat-move");
    if (moveBtn){
      moveBtn.textContent = chatPos === "bl" ? "⇱" : "⇲";
      moveBtn.title = chatPos === "bl" ? "Move chat to the right" : "Move chat to bottom-left";
    }
    try {
      localStorage.setItem("chatPos", chatPos);
      localStorage.setItem("chatHidden", chatHidden ? "1" : "");
      localStorage.setItem("chatW", String(chatW));
      localStorage.setItem("chatH", String(chatH));
    } catch {}
  }
  (function bindChatResize(){
    const handle = document.getElementById("chat-resize");
    if (!handle) return;
    let dragging = false, axis = "x", start = 0, startSize = 0;
    const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
    const onMove = e => {
      if (!dragging) return;
      const pt = e.touches ? e.touches[0] : e;
      if (axis === "x") chatW = clamp(startSize + (start - pt.clientX), CHAT_W_MIN, CHAT_W_MAX);
      else chatH = clamp(startSize + (start - pt.clientY), CHAT_H_MIN, CHAT_H_MAX);
      applyChatSize();
      e.preventDefault();
    };
    const onEnd = () => {
      if (!dragging) return;
      dragging = false;
      handle.classList.remove("active");
      document.body.classList.remove("chat-resizing", "chat-resize-v");
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onEnd);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
      try {
        localStorage.setItem("chatW", String(chatW));
        localStorage.setItem("chatH", String(chatH));
      } catch {}
    };
    const onStart = e => {
      if (chatHidden) return;
      axis = chatPos === "bl" ? "y" : "x";
      const pt = e.touches ? e.touches[0] : e;
      dragging = true;
      start = axis === "x" ? pt.clientX : pt.clientY;
      startSize = axis === "x" ? chatW : chatH;
      handle.classList.add("active");
      document.body.classList.add("chat-resizing");
      if (axis === "y") document.body.classList.add("chat-resize-v");
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onEnd);
      window.addEventListener("touchmove", onMove, { passive: false });
      window.addEventListener("touchend", onEnd);
      e.preventDefault();
    };
    handle.addEventListener("mousedown", onStart);
    handle.addEventListener("touchstart", onStart, { passive: false });
  })();
  applyChat();
  document.getElementById("chat-move").onclick   = () => { chatPos = chatPos === "bl" ? "right" : "bl"; chatHidden = false; applyChat(); };
  document.getElementById("chat-hide").onclick   = () => { chatHidden = true; applyChat(); };
  document.getElementById("chat-reopen").onclick = () => { chatHidden = false; applyChat(); };
  document.getElementById("chat-clear").onclick  = () => {
    history.length = 0; stream.innerHTML = ""; refreshChatStatus("Ready");
    try { localStorage.removeItem("chatHistory"); localStorage.removeItem("chatSessionId"); } catch {}
    fetch("/api/chat-reset", { method: "POST" }).catch(() => {});
  };

  // ── session sync: restore history if server session matches, else wipe ───
  function saveHistory() {
    try { localStorage.setItem("chatHistory", JSON.stringify(history)); } catch {}
  }
  fetch("/api/chat-session").then(r => r.json()).then(({ session_id }) => {
    if (!session_id) return; // no session yet — nothing to restore
    try {
      const storedId  = localStorage.getItem("chatSessionId");
      const storedLog = localStorage.getItem("chatHistory");
      if (storedId === session_id && storedLog) {
        const msgs = JSON.parse(storedLog);
        msgs.forEach(m => { history.push(m); addMsg(m.role, m.content); });
      } else {
        // server session changed (restart) — clear stale UI history
        localStorage.removeItem("chatHistory");
        localStorage.removeItem("chatSessionId");
      }
      localStorage.setItem("chatSessionId", session_id);
    } catch {}
  }).catch(() => {});

  // ── integrated terminal (lazy WS connect + PTY spawn on first open) ───────
  let term, termSock, termFit;
  function initTerminal(){
    term = new Terminal({ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                          fontSize: 12, theme: { background: "#1e1e28" } });
    termFit = new FitAddon.FitAddon();
    term.loadAddon(termFit);
    term.open(document.getElementById("term"));
    termFit.fit();
    termSock = new WebSocket(`ws://${location.host}/ws/terminal`);
    termSock.binaryType = "arraybuffer";
    termSock.onopen = () => sendResize();
    termSock.onmessage = e => term.write(new Uint8Array(e.data));
    termSock.onclose = () => { if (term) term.write("\r\n[session ended — toggle the terminal to reconnect]\r\n"); };
    term.onData(d => { if (termSock && termSock.readyState === 1) termSock.send(d); });
    window.addEventListener("resize", () => { if (termFit) { termFit.fit(); sendResize(); } });
    term.attachCustomKeyEventHandler(e => {
      if (e.type !== "keydown" || !e.metaKey || e.key !== "v") return true;
      (async () => {
        try {
          const items = await navigator.clipboard.read();
          const imgItem = items.find(i => i.types.some(t => t.startsWith("image/")));
          if (imgItem) {
            const imgType = imgItem.types.find(t => t.startsWith("image/"));
            const blob = await imgItem.getType(imgType);
            const b64 = await new Promise(res => {
              const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(blob);
            });
            const ext = imgType.split("/")[1] || "png";
            const { path } = await jpost("/api/upload-temp", { data: b64, ext });
            if (termSock && termSock.readyState === 1) termSock.send(path);
            return;
          }
        } catch {}
        const text = await navigator.clipboard.readText().catch(() => "");
        if (text && termSock && termSock.readyState === 1) termSock.send(text);
      })();
      return false;
    });
  }
  function sendResize(){
    if (termSock && termSock.readyState === 1 && term)
      termSock.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
  }
  function toggleTerminal(){
    const panel = document.getElementById("term-panel");
    const opening = panel.classList.toggle("open");
    document.getElementById("term-chevron").textContent = opening ? "▾" : "▸";
    document.getElementById("term-close").textContent = opening ? "close" : "open ⌃`";
    if (opening && !term) initTerminal();
    // fit after the height transition settles, else xterm sizes to 0 rows
    if (opening) setTimeout(() => { if (termFit) { termFit.fit(); sendResize(); } }, 160);
  }
  document.getElementById("term-tab").onclick   = e => { if (!e.target.closest("#term-close")) toggleTerminal(); };
  document.getElementById("term-close").onclick = e => { e.stopPropagation(); toggleTerminal(); };
  // Cursor-style toggle: Ctrl+`
  document.addEventListener("keydown", e => {
    if (e.ctrlKey && e.key === "`") { e.preventDefault(); toggleTerminal(); }
  });

  // ── file attachments (button · paste · drag-drop) ─────────────────────────
  let attachedFiles = [];

  async function readFile(file){
    if (file.type.startsWith("image/")) return `[image: ${file.name} — not sent to the model, referenced by name]`;
    try {
      let t = await file.text();
      if (t.indexOf(String.fromCharCode(0)) !== -1) return `[binary: ${file.name}]`;  // NUL byte => not text
      if (t.length > CTX_ATTACH_CAP) {
        t = t.slice(0, CTX_ATTACH_CAP)
            + `\n[…truncated ${t.length - CTX_ATTACH_CAP} chars — use osctl read-file for full doc]`;
      }
      return t;
    } catch { return `[binary: ${file.name}]`; }
  }

  async function refreshChatStatus(base){
    try {
      const { turn_count, max_turns } = await fetch("/api/chat-session").then(r => r.json());
      const n = turn_count || 0, max = max_turns || 6;
      const warn = n >= max - 1 ? " · ⌫ clears model memory" : "";
      statusEl.textContent = (base || "Ready") + ` · turn ${n}/${max}${warn}`;
    } catch {
      if (base) statusEl.textContent = base;
    }
  }
  async function addFiles(fileList){
    for (const file of fileList) {
      attachedFiles.push({ name: file.name, content: await readFile(file) });
    }
    renderAttachments();
  }

  // ⊕ opens the manual picker (skills · web search · attach file); file attach
  // is reachable from inside it, plus paste & drag-drop still work directly.
  attachBtn.onclick = () => openPicker();
  fileInput.onchange = async e => { await addFiles(e.target.files); fileInput.value = ""; };

  // Cmd+V of a file/image lands in clipboardData.files; plain text falls through.
  input.addEventListener("paste", e => {
    const files = e.clipboardData && e.clipboardData.files;
    if (files && files.length) { e.preventDefault(); addFiles(files); }
  });

  // Drag a file anywhere onto the composer to attach it.
  const composeEl = attachBtn.closest(".compose");
  composeEl.addEventListener("dragover", e => { e.preventDefault(); composeEl.classList.add("drag"); });
  composeEl.addEventListener("dragleave", e => { if (e.target === composeEl) composeEl.classList.remove("drag"); });
  composeEl.addEventListener("drop", e => {
    e.preventDefault(); composeEl.classList.remove("drag");
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });

  function renderAttachments(){
    attachEl.innerHTML = attachedFiles.map((f, i) =>
      `<span class="att-chip">${esc(f.name)}<button data-ai="${i}" title="Remove">✕</button></span>`
    ).join("");
    attachEl.querySelectorAll("[data-ai]").forEach(b =>
      b.onclick = () => { attachedFiles.splice(+b.dataset.ai, 1); renderAttachments(); }
    );
  }

  // ── @-mention autocomplete (references real entities from _TREE) ───────────
  let mentions = [];                       // {token, type, slug, name}
  let menuItems = [], menuIdx = 0;
  const menu = document.createElement("div");
  menu.className = "mention-menu"; menu.style.display = "none";
  composeEl.appendChild(menu);

  // @  → entities (project/profile/channel/post) — their content is inlined.
  // /  → skills + tools (web search, attach file) — routing tokens, not inlined.
  function mentionCandidates(trigger){
    const out = [];
    if (trigger === "/") {
      out.push({ type:"action", slug:"__attach", name:"Attach file…", meta:"upload a document" });
      out.push({ type:"tool",   slug:"web",      name:"Web search",   meta:"let the OS research online this turn" });
      for (const s of _SKILLS)
        out.push({ type:"skill", slug:s.name, name:s.name, meta:(s.description||"").slice(0, 90) });
      return out;
    }
    for (const p of _TREE) {
      out.push({ type:"project", slug:p.slug, osId:OSID.proj(p.slug), name:p.name, meta:(p.kind||p.type||"project") });
      for (const s of PROJECT_SECTIONS)
        out.push({
          type:"section",
          slug:`${p.slug}/${s.key}`,
          osId:OSID.tabProj(p.slug, s.key),
          name:`${p.name} · ${s.label}`,
          meta:"section",
        });
      for (const prof of (p.profiles||[])) {
        out.push({ type:"profile", slug:prof.slug, osId:OSID.prof(prof.slug), name:prof.name, meta:"profile" });
        for (const ch of (prof.channels||[]))
          out.push({ type:"channel", slug:ch.slug, osId:OSID.chan(ch.slug), name:(ch.name||ch.platform), meta:(ch.platform||"channel") });
      }
    }
    for (const post of _POSTS) {
      out.push({
        type:"post",
        slug:post.id,
        osId:OSID.post(post.id),
        name:(post.working_title || post.pillar || post.id),
        meta:`${post.profile_name||post.profile_slug} · ${post.status||""}`.trim(),
      });
    }
    return out;
  }
  // the @- or /-query immediately left of the caret, or null
  function activeQuery(){
    const pos = input.selectionStart;
    const before = input.value.slice(0, pos);
    const m = before.match(/(^|\s)([@/])([\w.-]*)$/);
    return m ? { q: m[3].toLowerCase(), trigger: m[2], start: pos - m[3].length - 1, end: pos } : null;
  }
  function closeMenu(){ menu.style.display = "none"; menuItems = []; menuIdx = 0; }
  function openMenu(){
    const aq = activeQuery();
    if (!aq) return closeMenu();
    menuItems = mentionCandidates(aq.trigger)
      .filter(c => c.slug.toLowerCase().includes(aq.q) || c.name.toLowerCase().includes(aq.q)
        || (c.osId||"").toLowerCase().includes(aq.q))
      .slice(0, 8);
    if (!menuItems.length) return closeMenu();
    menuIdx = Math.min(menuIdx, menuItems.length - 1);
    const ICON = { project:"▣", profile:"◐", channel:"▶", post:"✎", section:"◎", skill:"✦", tool:"🌐", action:"📎" };
    menu.innerHTML = menuItems.map((c, i) =>
      `<div class="mi${i===menuIdx?" sel":""}" data-i="${i}">
         <span class="mi-ic">${ICON[c.type]||"·"}</span><b>${esc(c.name)}</b>
         <span class="mi-meta">${esc(c.type)} · ${esc(c.meta)}</span></div>`
    ).join("");
    menu.querySelectorAll(".mi").forEach(el =>
      el.onmousedown = e => { e.preventDefault(); pickMention(+el.dataset.i); });
    menu.style.display = "block";
  }
  function pickMention(i){
    const c = menuItems[i]; if (!c) return;
    const aq = activeQuery(); if (!aq) return;
    // "Attach file" action: drop the typed "/" and open the file picker.
    if (c.type === "action" && c.slug === "__attach") {
      input.value = input.value.slice(0, aq.start) + input.value.slice(aq.end);
      input.setSelectionRange(aq.start, aq.start);
      closeMenu(); fileInput.click(); input.dispatchEvent(new Event("input"));
      return;
    }
    // Skills/tools are routing tokens (/slug) read server-side — never inlined,
    // so they are NOT tracked in mentions[]. Entities use @slug and ARE tracked.
    const sigil = (c.type === "skill" || c.type === "tool") ? "/" : "@";
    const token = sigil + (c.osId || c.slug);
    input.value = input.value.slice(0, aq.start) + token + " " + input.value.slice(aq.end);
    const caret = aq.start + token.length + 1;
    input.setSelectionRange(caret, caret);
    if (sigil === "@" && !mentions.some(m => m.token === token))
      mentions.push({ token, type:c.type, slug:mentionBare(c), osId:c.osId||null, name:c.name });
    closeMenu(); input.focus();
    input.dispatchEvent(new Event("input"));   // keep textarea autosize in sync
  }
  // ⊕ button = manual picker: insert "/" at the caret and open the skill/tool menu.
  function openPicker(){
    const pos = input.selectionStart;
    const before = input.value.slice(0, pos);
    const sep = (pos === 0 || /\s$/.test(before)) ? "" : " ";
    input.value = before + sep + "/" + input.value.slice(pos);
    const caret = pos + sep.length + 1;
    input.setSelectionRange(caret, caret);
    input.focus(); openMenu();
  }
  // Runs before the send handler below; swallows nav keys while the menu is open.
  input.addEventListener("keydown", e => {
    if (menu.style.display === "none") return;
    if (e.key === "ArrowDown") { menuIdx = (menuIdx + 1) % menuItems.length; openMenu(); e.preventDefault(); e.stopImmediatePropagation(); }
    else if (e.key === "ArrowUp") { menuIdx = (menuIdx - 1 + menuItems.length) % menuItems.length; openMenu(); e.preventDefault(); e.stopImmediatePropagation(); }
    else if (e.key === "Enter" || e.key === "Tab") { pickMention(menuIdx); e.preventDefault(); e.stopImmediatePropagation(); }
    else if (e.key === "Escape") { closeMenu(); e.preventDefault(); e.stopImmediatePropagation(); }
  });
  input.addEventListener("input", openMenu);
  input.addEventListener("blur", () => setTimeout(closeMenu, 120));

  // ── chat ─────────────────────────────────────────────────────────────────
  const history = [];
  let busy = false;
  let chatAbort = null;   // AbortController for the in-flight /api/ask stream

  // ESC stops the current turn: abort the SSE stream client-side AND tell the
  // server to kill the claude subprocess (otherwise it keeps burning tokens).
  function stopChat(){
    if (!busy) return false;
    if (chatAbort) chatAbort.abort();
    fetch("/api/chat-stop", { method: "POST" }).catch(() => {});
    return true;
  }

  function setMsgContent(el, role, text){
    if (role === "user" || role === "assistant") el.innerHTML = formatChatText(text);
    else el.textContent = text;
  }

  function addMsg(role, text){
    const div = document.createElement("div");
    const uiRole = role === "user" ? "me" : "ai";
    div.className = "msg " + uiRole;
    div.innerHTML = `<div class="b"></div>`;
    const bubble = div.querySelector(".b");
    setMsgContent(bubble, role, text);
    stream.appendChild(div);
    stream.scrollTop = stream.scrollHeight;
    return bubble;
  }

  // Tool activity for the in-flight turn collapses into ONE quiet line that
  // sits ABOVE the answer (never a trailing stack of Bash/Read cards). It ticks
  // live while working, then becomes a click-to-expand "N steps" summary.
  let stepLabels = [], stepEl = null, stepAnchor = null;

  function startTurnSteps(anchor){ stepLabels = []; stepEl = null; stepAnchor = anchor; }

  function addStep(text){
    stepLabels.push(text);
    if (!stepEl){
      stepEl = document.createElement("div");
      stepEl.className = "tool-chip tool-summary";
      stream.insertBefore(stepEl, stepAnchor);   // keep it above the free-text answer
    }
    const n = stepLabels.length;
    stepEl.textContent = `⚙ working… ${n} step${n > 1 ? "s" : ""}`;
    stream.scrollTop = stream.scrollHeight;
  }

  function finalizeSteps(){
    if (!stepEl) return;
    const labels = stepLabels.slice();
    let detail = null;
    const paint = () => stepEl.textContent = detail
      ? "⚙ hide steps"
      : `⚙ ${labels.length} step${labels.length > 1 ? "s" : ""}`;
    stepEl.onclick = () => {
      if (detail) { detail.remove(); detail = null; }
      else {
        detail = document.createElement("div");
        detail.className = "tool-detail";
        detail.textContent = labels.join("  ·  ");
        stepEl.after(detail);
      }
      paint();
    };
    paint();
  }

  // Token-lean context: inject heavy profile/post bodies only when the turn
  // needs them. State snapshot + osctl cover everything else.
  const CTX_VOICE_FULL = 1200, CTX_SPEC_FULL = 1500;
  const CTX_ATTACH_CAP = 12000;
  const SKILL_TAG_RE = /(?:^|\s)\/([a-z][a-z0-9-]+)/;
  const WRITE_HINT_RE = /\b(save|commit|write|create|update|fill|populate|add|generate|draft|validate|assess|design|plan|build|launch|revise|brief|memo|intake|roadmap|experiment)\b/i;
  const CONTINUATION_RE = /\b(yes|yep|yeah|ok|okay|sure|go ahead|save|commit|do it|approved|looks good|next tab|proceed|continue|save all)\b/i;
  const CTX_PORTFOLIO_KW = /\b(all posts|other posts|how many posts|list posts|what posts|calendar|timeline|projects?|profiles?|portfolio)\b/i;

  function hasExplicitSkillTag(text) {
    const tags = text.match(/(?:^|\s)\/([a-z][a-z0-9-]+)/g) || [];
    return tags.some(t => _SKILLS.some(s => s.name === t.slice(1)));
  }

  function needsFullProfile(text, refs) {
    if (refs.some(m => m.type === "profile")) return true;
    if (STATE.view === "profileSetup") return true;
    return /(?:^|\s)\/content-brief\b/.test(text);
  }

  function needsFullOpenPost(text, refs) {
    if (!CURRENT_POST) return false;
    if (CTX_PORTFOLIO_KW.test(text)) return false;
    if (!/(?:^|\s)\/content-brief\b/.test(text)) return false;
    if (refs.some(m => m.type === "post")) return true;
    const openId = CURRENT_POST.id;
    if (text.includes("@" + openId) || text.includes(OSID.post(openId))) return true;
    return true;
  }

  async function profileContextBlock(slug, label, full){
    const d = await api("/api/profile/" + slug);
    const oid = OSID.prof(slug);
    const vCap = CTX_VOICE_FULL;
    const sCap = CTX_SPEC_FULL;
    let body = `id: ${oid}\ntopic: ${d.topic || "—"}`;
    if (full) {
      body += `\nvoice:\n${(d.voice || "").slice(0, vCap)}`;
      body += `\nbrief-spec.md:\n`
           + (d.brief_spec ? String(d.brief_spec).slice(0, sCap) : "(empty)");
    } else {
      body += `\n(voice/spec omitted — @mention profile or ask about content to inline; else osctl get-brief-spec / read-file)`;
    }
    return `\n## ${label} "${d.name || slug}" (${oid})\n${body}\n`;
  }

  function compactOpenPostBlock() {
    const slot = CURRENT_POST.slot || {};
    const oid = OSID.post(CURRENT_POST.id);
    return `\n## Post in view (${oid})\n`
         + `status: ${slot.status || "—"} · date: ${slot.date || "—"}\n`
         + `title: ${slot.working_title || slot.pillar || CURRENT_POST.id}\n`
         + `(full slot/brief omitted — ask about this post or @mention it; else osctl read-file)\n`;
  }

  function pastedCanonicalIds(text){
    const re = /@([a-z]{2,3}\d{1,3}(?:\.[a-z]{2,3}\d{1,3})*)/g;
    const out = [];
    let m;
    while ((m = re.exec(text)) !== null) out.push(m[1]);
    return [...new Set(out)];
  }

  async function buildContext(text){
    const title = document.querySelector(".title");
    const crumbs = document.querySelector(".crumbs");
    let ctx = "";
    if (crumbs) ctx += "Current view: " + crumbs.textContent + "\n";
    if (title)  ctx += "Section: " + title.textContent + "\n";
    const refs = mentions.filter(m => text.includes(m.token));
    const ECAP = 3;
    const entSeen = new Set();
    const entRefs = [];
    for (const m of refs) {
      if (m.type === "post") continue;
      const key = m.osId || (m.type + ":" + m.slug);
      if (entSeen.has(key)) continue;
      entSeen.add(key); entRefs.push(m);
    }
    const profileSlugs = new Set();
    const autoProfile = CURRENT_PROFILE_SLUG || STATE.profile;
    const wantFullProfile = needsFullProfile(text, refs);
    if (autoProfile) {
      try {
        ctx += await profileContextBlock(autoProfile, "Active profile", wantFullProfile);
        profileSlugs.add(autoProfile);
      } catch { /* optional */ }
    }
    for (const m of entRefs.slice(0, ECAP)) {
      let body = "";
      try {
        if (m.type === "profile") {
          if (profileSlugs.has(m.slug)) continue;
          ctx += await profileContextBlock(m.slug, "Referenced profile", true);
          profileSlugs.add(m.slug);
          continue;
        } else if (m.type === "channel") {
          const d = await api("/api/channel/" + m.slug + "/guidelines");
          body = `guidelines:\n${(d.text || "(none)").slice(0, 2000)}`;
        } else if (m.type === "project") {
          const d = await api("/api/project/" + m.slug);
          const e = d.entity || {};
          const memos = (d.memos || []).map(x => `${x.type}-v${x.version} [${x.status}]`).join(", ") || "none";
          const secs = Object.entries(d.sections || {}).map(([k, s]) =>
            `${k} id=${s.id} [${s.empty ? "empty" : (s.artifacts || []).length + " artifacts"}]`
          ).join("\n") || "none";
          body = `kind: ${e.subtype || e.type || ""} · priority: ${e.priority || "—"} · status: ${e.status || "—"}\nmemos: ${memos}\nsections:\n${secs}`;
        } else if (m.type === "section") {
          const ent = IdReg.resolve(m.osId || "");
          const projSlug = ent?.ref?.project || (m.slug || "").split("/")[0];
          const secKey = ent?.ref?.section || (m.slug || "").split("/")[1];
          const d = await api("/api/project/" + projSlug);
          const sec = (d.sections || {})[secKey];
          if (sec) {
            const arts = (sec.artifacts || []).map(a =>
              `- ${a.id || a.kind}: ${a.label}${a.path ? ` (${a.path})` : ""}`
            ).join("\n") || "(none)";
            const hint = sec.skill ? `skill:${sec.skill}` : (sec.skills || []).map(s => `skill:${s}`).join(", ");
            body = `id: ${sec.id}\nlabel: ${sec.label}\nempty: ${sec.empty}\nartifacts:\n${arts}${hint ? `\nhints: ${hint}` : ""}`;
          } else {
            body = `(section not found: ${m.osId})`;
          }
        }
      } catch { body = "(could not load content)"; }
      ctx += `\n## Referenced ${m.type} "${m.name}" (slug: ${m.slug})\n${body}\n`;
    }
    for (const m of entRefs.slice(ECAP)) {
      ctx += `\n## Referenced ${m.type} "${m.name}" (slug: ${m.slug})\n`;
    }
    // post mentions: inline full slot+brief. Dedupe (incl. the open post) and cap.
    const seen = new Set(CURRENT_POST ? [CURRENT_POST.id] : []);
    const postRefs = [];
    for (const m of refs) {
      if (m.type !== "post" || seen.has(m.slug)) continue;
      seen.add(m.slug); postRefs.push(m);
    }
    const CAP = 5;
    for (const m of postRefs.slice(0, CAP)) {
      let body;
      try {
        const d = await api("/api/post/" + m.slug);
        body = "Full content:\n```json\n"
             + JSON.stringify({ slot: d.slot, brief: d.brief }, null, 2)
             + "\n```\n";
      } catch {
        body = "(could not load content)\n";
      }
      ctx += `\n## Referenced post (id: ${m.slug})\n` + body;
    }
    for (const m of postRefs.slice(CAP)) {
      ctx += `\n## Referenced post (id: ${m.slug})\n${m.name}\n`;
    }
    const pasted = pastedCanonicalIds(text).filter(id => !refs.some(m => (m.osId || m.token.slice(1)) === id));
    for (const id of pasted.slice(0, 8)) {
      const ent = IdReg.resolve(id);
      const ref = ent?.ref || {};
      if (ent?.kind === "brief" && ref.post) {
        const pid = ref.post;
        if (seen.has(pid)) continue;
        seen.add(pid);
        try {
          const d = await api("/api/post/" + pid);
          ctx += `\n## Pasted ${id} (brief)\n\`\`\`json\n`
               + JSON.stringify({ brief: d.brief }, null, 2) + "\n\`\`\`\n";
        } catch { ctx += `\n## Pasted ${id}\n(could not load)\n`; }
      } else if (ref.post && !ref.field) {
        const pid = ref.post;
        if (seen.has(pid)) continue;
        seen.add(pid);
        try {
          const d = await api("/api/post/" + pid);
          ctx += `\n## Pasted ${id}\n\`\`\`json\n`
               + JSON.stringify({ slot: d.slot, brief: d.brief }, null, 2) + "\n\`\`\`\n";
        } catch { ctx += `\n## Pasted ${id}\n(could not load)\n`; }
      } else if (ref.post && ref.field) {
        const pid = ref.post, field = ref.field;
        try {
          const d = await api("/api/post/" + pid);
          const brief = d.brief || {};
          let val = brief[field];
          if (field.startsWith("slide-")) {
            const n = parseInt(field.split("-")[1], 10);
            const slide = (brief.slide_overlays || []).find(s => (s.slide ?? 0) === n);
            val = slide ? slide.overlay : null;
          } else if (field.startsWith("gen-prompt-")) {
            const n = parseInt(field.split("-")[2], 10);
            val = (brief.gen_prompts || [])[n - 1];
          }
          ctx += `\n## Pasted ${id}\npost: ${pid}\nfield: ${field}\nvalue:\n${val != null ? String(val) : "(empty)"}\n`;
        } catch { ctx += `\n## Pasted ${id}\n(could not load)\n`; }
      } else if (ref.project && ref.section) {
        try {
          const d = await api("/api/project/" + ref.project);
          const sec = (d.sections || {})[ref.section];
          if (sec) {
            const arts = (sec.artifacts || []).map(a =>
              `- ${a.id || a.kind}: ${a.label}${a.path ? ` (${a.path})` : ""}`
            ).join("\n") || "(none)";
            ctx += `\n## Pasted ${id}\n${arts}\n`;
          }
        } catch { /* skip */ }
      }
    }
    if (CURRENT_POST) {
      if (needsFullOpenPost(text, refs)) {
        ctx += `\n## Post currently open (${OSID.post(CURRENT_POST.id)})\n`
             + "Brief edits: `update-brief --id " + CURRENT_POST.id + "`. Slot fields: `update-post`. Full content:\n```json\n"
             + JSON.stringify({ slot: CURRENT_POST.slot, brief: CURRENT_POST.brief }, null, 2)
             + "\n```\n";
      } else {
        ctx += compactOpenPostBlock();
      }
    }
    if (attachedFiles.length) {
      ctx += "\n## Attached files\n" + attachedFiles.map(f =>
        `### ${f.name}\n\`\`\`\n${f.content}\n\`\`\``
      ).join("\n\n");
    }
    return ctx;
  }

  async function send(){
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    input.value = "";
    input.style.height = "56px";
    statusEl.textContent = "thinking…";
    sendBtn.disabled = true;

    const fileNote = attachedFiles.length ? ` [+${attachedFiles.length} file${attachedFiles.length>1?"s":""}]` : "";
    history.push({ role: "user", content: text });
    addMsg("user", text + fileNote);

    const ctx = await buildContext(text);
    attachedFiles = []; renderAttachments();
    mentions = [];

    const bubble = addMsg("assistant", ""); bubble.innerHTML = ""; let full = "";
    startTurnSteps(bubble.parentElement);   // steps line lives just above this answer
    let pendingBreak = false;

    chatAbort = new AbortController();
    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: text }], context: ctx }),
        signal: chatAbort.signal
      });

      if (!resp.ok) {
        const j = await resp.json().catch(() => ({}));
        bubble.innerHTML = formatChatText("Error: " + (j.error || resp.status));
        history.pop(); return;
      }

      const reader = resp.body.getReader();
      const dec = new TextDecoder(); let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n"); buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const obj = JSON.parse(raw);
            if (obj.error) { bubble.innerHTML = formatChatText("Error: " + obj.error); return; }
            if (obj.delta) {
              // A tool call ran between two narration segments — start the next
              // one on a fresh line so thoughts don't run together ("week.14").
              if (pendingBreak && full && !full.endsWith("\n")) full += "\n";
              pendingBreak = false;
              full += obj.delta; bubble.innerHTML = formatChatText(full); stream.scrollTop = stream.scrollHeight;
            }
            if (obj.tool)  { addStep("⚙ " + obj.tool); pendingBreak = true; }
          } catch {}
        }
      }

      if (full) {
        history.push({ role: "assistant", content: full });
        // Persist session ID on first completed turn (session created by /api/ask)
        fetch("/api/chat-session").then(r => r.json()).then(({ session_id }) => {
          if (session_id) try { localStorage.setItem("chatSessionId", session_id); } catch {}
        }).catch(() => {});
        saveHistory();
      }
      await refreshChatStatus("Ready");
    } catch(e) {
      if (e.name === "AbortError") {
        bubble.innerHTML = formatChatText(full ? full + "  ⏹ stopped" : "⏹ stopped");
        if (full) { history.push({ role: "assistant", content: full }); saveHistory(); }
        statusEl.textContent = "Stopped";
      } else {
        bubble.innerHTML = formatChatText("Error: " + e.message);
        history.pop(); statusEl.textContent = "Error";
      }
    } finally {
      chatAbort = null;
      finalizeSteps();                // turn the live steps line into a quiet summary
      busy = false; sendBtn.disabled = false; input.focus();
      refreshViews().catch(()=>{});   // act directly → show result
    }
  }

  sendBtn.onclick = send;
  input.addEventListener("keydown", e => {
    if (e.key === "Escape" && busy) { e.preventDefault(); e.stopPropagation(); stopChat(); return; }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  // Global ESC also stops a streaming turn (when focus isn't in the textarea).
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && busy) stopChat();
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  });

  addMsg("assistant", "Hi. I run your GTM OS. Ask me to create or change things (projects, profiles, channels, posts, activities, milestones) and I'll do it directly and refresh the view. For power work, open the terminal with ⌃` .");
})();

boot();
