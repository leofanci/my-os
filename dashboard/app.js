const $ = s => document.querySelector(s);
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const slugify = s => s.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/(^-|-$)/g,"");
function toast(m,sticky){const t=$("#toast");t.textContent=m;t.style.opacity=1;clearTimeout(t._timer);if(!sticky)t._timer=setTimeout(()=>t.style.opacity=0,2400);}
async function api(p,o){const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||r.status);return j;}
function jpost(p,body){return api(p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});}

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
  const ex = _NAV_EXTRAS; _NAV_EXTRAS = {};
  for(const [re, fn] of ROUTES){
    const m = path.match(re);
    if(m){ _NAV_EXTRAS = ex; fn(m.length>1?m.slice(1):[]); _NAV_EXTRAS={}; highlight(); return; }
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
const flabel = t => `<label class="flabel">${esc(t)}</label>`;
const finput = (name,val='',extra='') => `<input name="${name}" value="${esc(val)}" ${extra}>`;
const fsel = (name,opts,val) => `<select name="${name}">`+opts.map(([v,l])=>`<option value="${esc(v)}"${v===val?" selected":""}>${esc(l)}</option>`).join("")+`</select>`;
const fta = (name,val='',rows=5,extra='') => `<textarea name="${name}" rows="${rows}" ${extra}>${esc(val)}</textarea>`;
function formVals(root){ const d={}; root.querySelectorAll("[name]").forEach(i=>d[i.name]=i.value); return d; }
function pageHeader(title, crumb, btns=''){
  return `<div class="topbar"><div><div class="crumbs"><a class="bk" style="cursor:pointer;color:var(--sky)">← ${esc(crumb)}</a></div><h1 class="title">${esc(title)}</h1></div><div style="margin-left:auto;display:flex;gap:8px">${btns}</div></div>`;
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

const SECTIONS = [
  {key:"overview", ico:"◇", label:"Overview"},
  {key:"validation", ico:"◎", label:"Problem & validation"},
  {key:"experiments", ico:"⚗", label:"Experiments"},
  {key:"pricing", ico:"◧", label:"Positioning & pricing"},
  {key:"product", ico:"▣", label:"Product"},
];
let STATE = {view:"calendar", project:null, section:null, profile:null, channelGuidelines:null};
let _TREE = [];

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

async function boot(){ await renderRail(); parseRoute(location.hash||"#/calendar"); }

async function renderRail(){
  _TREE = await api("/api/tree");
  const projects = _TREE.map(p=>{
    const totalFeatures = p.products.reduce((n,prod)=>n+prod.features,0);
    const profileRows = p.profiles.length ? p.profiles.map(prof=>{
      const hasCh = prof.channels.length > 0;
      const profOpen = !hasCh || isOpen("profiles", prof.slug);
      const wedge = hasCh ? (profOpen ? "▾" : "▸") : "·";
      const channelsBlock = prof.channels.length ? `<div class="kid" style="margin-top:1px;margin-bottom:2px">
        ${prof.channels.map(ch=>`<a data-profile="${esc(prof.slug)}" data-chan-filter="${esc(ch.slug)}" style="display:flex;align-items:center;gap:6px;cursor:pointer"><span style="opacity:.5">${PLATFORM_ICON[ch.platform]||"⌗"}</span>${esc(ch.name||ch.platform)}</a>`).join("")}
        <a data-new-channel="${esc(prof.slug)}" style="color:var(--sky)!important;font-weight:normal!important">＋ Channel</a>
      </div>` : ``;
      return `<a data-profile="${esc(prof.slug)}" style="display:flex;align-items:center;gap:6px;padding:4px 9px;border-radius:10px;text-decoration:none;cursor:pointer">
        <span data-toggle-profile="${esc(prof.slug)}" style="opacity:.45;font-size:9px;width:9px;text-align:center;cursor:pointer;flex-shrink:0">${wedge}</span>
        ${esc(prof.name)}<span class="c">${prof.posts}</span>
      </a>
      ${hasCh && profOpen ? channelsBlock : ""}`;
    }).join("") : `<a style="color:var(--dim);font-size:12px;padding:4px 9px">No profiles yet</a>`;
    const pOpen = isOpen("projects", p.slug);
    return `
    <div style="margin-top:6px">
      <div data-toggle-project="${esc(p.slug)}" style="display:flex;align-items:center;gap:7px;font:700 13px/1 var(--disp);padding:4px 9px;border-radius:10px;cursor:pointer;color:var(--ink2)">
        <span style="opacity:.45;font-size:10px;width:9px;display:inline-block">${pOpen?"▾":"▸"}</span>${esc(p.name)}
        <span style="margin-left:auto;font:600 9px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--sky);background:var(--sky-soft);padding:2px 6px;border-radius:20px">${esc(p.kind||p.type)}</span>
        <button class="rail-edit" data-edit-project="${esc(p.slug)}" title="Edit project">✎</button></div>
      ${pOpen ? `<nav class="sec">
        ${SECTIONS.map(s=>`<a data-project="${esc(p.slug)}" data-section="${s.key}"><span class="ico">${s.ico}</span> ${esc(s.label)}${
          s.key==="experiments"&&p.experiments?`<span class="c">${p.experiments}</span>`:
          s.key==="product"&&totalFeatures?`<span class="c">${totalFeatures}</span>`:""}</a>`).join("")}
        <div class="grp" style="display:flex;align-items:center">Profiles
          <button class="add-btn" data-new-profile="${esc(p.slug)}" style="margin-left:auto" title="Add profile">＋</button></div>
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
      <button class="add-btn" id="new-project-btn" title="New project">＋</button></div>
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

async function renderProjectSection(slug, section){
  const p = await api(`/api/project/${slug}`);
  const title = (SECTIONS.find(s=>s.key===section)||{}).label || section;
  const memo = t => (p.memos.filter(m=>m.type===t).sort((a,b)=>b.version-a.version)[0]||null);
  const body = {
    overview: ()=>{
      const e=p.entity, pv=memo("problem-validation"), as=memo("assessment");
      const vb = pv&&pv.body||{}, ab = as&&as.body||{};
      return `<div class="grid2">
        ${kv("Stage", e.status)}${kv("Priority", e.priority)}${kv("Hours/week", e.hours_per_week??"—")}
        ${kv("Validation", vb.validation_status||"—")}${kv("Pace", ab.pace_recommendation||"—")}
        ${kv("Profiles", p.profiles.map(c=>c.name).join(", ")||"—")}</div>
        ${pv?card("Problem & validation", `Status: <b>${esc(vb.validation_status||"?")}</b> · ${esc(vb.recommendation||"")}`):""}
        ${ab.riskiest_assumption?card("Riskiest assumption", esc(ab.riskiest_assumption)):""}`;
    },
    validation: ()=>{ const m=memo("problem-validation"); if(!m) return empty("No problem-validation memo yet.");
      const b=m.body||{}; return card(`Problem-validation v${m.version}`,
        `Status: <b>${esc(b.validation_status||"?")}</b> · severity: ${esc(b.severity||"?")}<br>${esc(b.recommendation||"")}`); },
    pricing: ()=>{ const items=p.memos.filter(m=>["positioning","pricing","competitors","icp"].includes(m.type));
      return items.length? items.map(m=>card(`${m.type} v${m.version}`, esc((m.body&&(m.body.recommendation||m.body.summary))||m.status))).join("") : empty("No positioning/pricing memos yet."); },
    experiments: ()=> p.experiments.length? p.experiments.map(x=>card(esc(x.assumption),
        `Status: <b>${esc(x.status)}</b>${x.decision?` · decision: ${esc(x.decision)}`:""}`)).join("") : empty("No experiments yet."),
    product: ()=>{
      if(p.products&&p.products.length){
        const prodCards = p.products.map(prod=>{
          const feats = p.features.filter(f=>f.product_slug===prod.slug);
          return `<div class="pcard"><h4>${esc(prod.name)}</h4><div style="font-size:12px;color:var(--dim)">${feats.length} feature${feats.length!==1?"s":""} in roadmap</div>
            ${feats.length?`<div class="rowc" style="margin-top:10px">${feats.map(f=>`<div class="post" style="padding:9px 12px">
              <span class="stp draft">${esc(f.status)}</span>
              <div class="t" style="font-size:12px">${esc(f.title)}${f.target_date?`<small>${esc(f.target_date)}</small>`:""}</div></div>`).join("")}</div>`:""}</div>`;
        }).join("");
        return prodCards;
      }
      return p.features.length? listRows(p.features.map(f=>({pill:f.status, pillk:"draft", t:f.title, sub:[f.priority,f.target_date].filter(Boolean).join(" · ")}))) : empty("No products or roadmap features yet.");
    },
    operations: ()=> p.activities.length? listRows(p.activities.map(a=>({pill:a.status, pillk:a.status==="done"?"sched":"idea", t:a.title, sub:[a.type,a.date].filter(Boolean).join(" · ")}))) : empty("No operations/tasks for this project yet."),
  };
  $("#main").innerHTML = `<div class="topbar"><div><div class="crumbs">${esc(p.entity.name)} · <b>${esc(title)}</b></div><h1 class="title">${esc(title)}</h1></div></div>
    <div class="scroll">${(body[section]||(()=>empty("Nothing here yet.")))()}</div>`;

  function kv(k,v){ return `<div class="kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`; }
  function card(h,html){ return `<div class="pcard"><h4>${esc(h)}</h4><div>${html}</div></div>`; }
  function empty(m){ return `<div style="padding:24px 4px;color:var(--dim)">${esc(m)}</div>`; }
  function listRows(items){ return `<div class="rowc">${items.map(i=>`<div class="post">
      <span class="stp ${i.pillk}">${esc(plainStatus(i.pill))}</span>
      <div class="t">${esc(i.t)}${i.sub?`<small>${esc(i.sub)}</small>`:""}</div></div>`).join("")}</div>`; }
}

let CAL = (function(){ const d=new Date(); return {y:d.getFullYear(), m:d.getMonth(), filter:"all"}; })();
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
function calShift(delta){ let m=CAL.m+delta,y=CAL.y; if(m<0){m=11;y--;} if(m>11){m=0;y++;} CAL={...CAL,y,m}; renderTimeline(); }
function calToday(){ const d=new Date(); CAL={...CAL,y:d.getFullYear(),m:d.getMonth()}; renderTimeline(); }

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
    const evs=(byDay[k]||[]).map(r=>`<div class="ev ${esc(r.kind)}" data-ev='${JSON.stringify({...r,title:(r.title||"").slice(0,80)}).replace(/'/g,"&#39;")}'>${esc(r.title||r.kind)}</div>`).join("");
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
  const [posts, profData] = await Promise.all([
    api(`/api/profile/${slug}/posts`),
    api(`/api/profile/${slug}`),
  ]);
  const profNode = _TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===slug)||{channels:[]};
  const channels = profNode.channels||[];
  const count = g => posts.filter(p=>STAGE_GROUP[p.status]===g).length;
  let FILTER = "all";
  let CHAN_FILTER = initChanFilter||null;
  const SELECTED = new Set();  // post ids ticked for bulk actions
  const chanSection = `<div class="pcard" style="margin-bottom:14px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      ${channels.map(ch=>`<span class="chan-pill-wrap${CHAN_FILTER===ch.slug?" on":""}"><button class="chan-pill${CHAN_FILTER===ch.slug?" on":""}" data-cf="${esc(ch.slug)}">${PLATFORM_ICON[ch.platform]||"⌗"} ${esc(ch.name||ch.platform)}${ch.handle?` <span style="opacity:.6;font-size:10px">${esc(ch.handle)}</span>`:""}</button><button class="chan-gear" data-cg="${esc(ch.slug)}" title="Channel setup">⚙</button></span>`).join("")}
      <button class="btn" id="addChanBtn" style="font-size:12px;padding:5px 11px;border-radius:20px">＋ Add channel</button>
    </div>
    ${profData.topic?`<div style="margin-top:8px;font-size:12px;color:var(--dim)">${esc(profData.topic)}</div>`:""}
  </div>`;
  $("#main").innerHTML = `<div class="topbar"><div><div class="crumbs">Profiles · <b>${esc(profData.name||slug)}</b></div>
      <h1 class="title">${esc(profData.name||slug)}</h1><div class="titlemeta">${posts.length} posts</div></div>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn" id="setupBtn">⚙ Setup</button>
        <button class="btn" id="addIdea">＋ Add idea</button>
        <button class="btn" id="writeAll">✍ Write all ideas</button>
        <button class="btn primary" id="genIdeas">✦ Generate ideas</button>
      </div></div>
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
      const pillarTag = p.pillar && p.pillar!==title ? `<span class="chan-chip" style="background:var(--sky-soft);color:var(--sky)">${esc(p.pillar)}</span>` : "";
      const chanChips = ((pillarTag?1:0)||(p.channels&&p.channels.length))
        ? `<div class="chan-chips">${pillarTag}${(p.channels||[]).map(c=>`<span class="chan-chip">${esc(c)}</span>`).join("")}</div>` : "";
      return `<div class="post${SELECTED.has(p.id)?" sel":""}">
        <input type="checkbox" class="selbox" data-sel="${p.id}" ${SELECTED.has(p.id)?"checked":""} title="Select" style="margin:0 2px;width:16px;height:16px;flex:none;cursor:pointer">
        <span class="stp ${pk}">${esc(plainStatus(p.status))}</span>
        <div class="t" data-view="${p.id}" style="cursor:pointer">${esc(title)}<small>${[sub,p.date].filter(Boolean).map(esc).join(" · ")}</small>${chanChips}</div>
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
    try{ if(n.brief){ toast("Writing via claude -p… (a few seconds)"); await api(`/api/post/${id}/brief`,{method:"POST"}); toast("Draft ready ✓"); }
      else { await api(`/api/post/${id}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
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
      try{ await api(`/api/post/${next.id}/brief`,{method:"POST"}); }
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
  const profData = await api(`/api/profile/${slug}`);
  const profName = profData.name||slug;
  $("#main").innerHTML = `
    <div class="topbar">
      <div>
        <div class="crumbs"><a id="backToProfile" style="cursor:pointer;color:var(--sky)">← ${esc(profName)}</a> · <b>Setup</b></div>
        <h1 class="title">Profile setup</h1>
      </div>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn" id="delProfBtn" style="color:#c0392b">Delete profile</button>
        <button class="btn primary" id="saveProfBtn">Save</button>
      </div>
    </div>
    <div class="scroll">
      <div style="max-width:740px">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:22px">
          <div>
            <label style="display:block;font-size:11px;color:var(--dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Display name</label>
            <input id="ps-name" value="${esc(profName)}" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
          <div>
            <label style="display:block;font-size:11px;color:var(--dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Topic / niche</label>
            <input id="ps-topic" value="${esc(profData.topic||"")}" placeholder="e.g. Film reviews for movie lovers" style="width:100%;border:1px solid var(--hair);border-radius:10px;padding:10px 13px;font:inherit;background:rgba(255,255,255,.82)">
          </div>
        </div>
        <label style="display:block;font-size:11px;color:var(--dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Brand voice & tone</label>
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">Describe how this brand speaks — personality, tone, things to always or never say, example phrases. This context is injected into every AI generation for this profile.</p>
        <textarea id="ps-voice" style="width:100%;min-height:340px;border:1px solid var(--hair);border-radius:12px;padding:16px 18px;font:13.5px/1.75 var(--body);background:rgba(255,255,255,.82);resize:vertical">${esc(profData.voice||"")}</textarea>
        <label style="display:block;font-size:11px;color:var(--dim);margin:26px 0 6px;text-transform:uppercase;letter-spacing:.06em">Post brief spec</label>
        <p style="font-size:12px;color:var(--dim);margin:0 0 10px;line-height:1.5">What every post for this profile must produce — e.g. caption length, hashtag count, format leanings, overlay style. Injected as hard requirements into every "write it" brief generation.</p>
        <textarea id="ps-brief" placeholder="e.g. Captions 80–150 words, punchy first line. Max 8 hashtags. Prefer carousels (5–7 slides) with bold text overlays. Always end with a question CTA." style="width:100%;min-height:200px;border:1px solid var(--hair);border-radius:12px;padding:16px 18px;font:13.5px/1.75 var(--body);background:rgba(255,255,255,.82);resize:vertical">${esc(profData.brief_spec||"")}</textarea>
      </div>
    </div>`;
  $("#backToProfile").onclick = ()=>history.back();
  $("#saveProfBtn").onclick = async()=>{
    const data={name:$("#ps-name").value, topic:$("#ps-topic").value, voice:$("#ps-voice").value, brief_spec:$("#ps-brief").value};
    try{ await jpost(`/api/profile/${slug}/update`,data); toast("Saved ✓"); renderRail(); }
    catch(e){ toast("✗ "+e.message); }
  };
  $("#delProfBtn").onclick = ()=>navigate(`#/profile/${slug}/delete`);
}

async function renderChannelGuidelines(slug){
  $("#main").innerHTML = `<div class="topbar"><div><div class="crumbs">Channels · <b>${esc(slug)}</b></div>
      <h1 class="title">Channel guidelines</h1><div class="titlemeta">Injected into every generation for this channel</div></div>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn" id="refineBtn">✨ Refine with AI</button>
        <button class="btn primary" id="saveBtn">Save</button>
      </div></div>
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
function briefSect(h,b){ return `<div style="margin-top:16px"><div style="font:700 11px/1 var(--body);letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin-bottom:6px">${esc(h)}</div>${b}</div>`; }
function renderBriefBody(slot, brief, n){
  let body="";
  if(slot.concept) body+=briefSect("Concept",`<div style="font-size:13px;line-height:1.6">${esc(slot.concept)}</div>`);
  if(brief&&brief._error) body+=briefSect("Brief",`<div style="color:#c0392b;font-size:13px">${esc(brief._error)}</div>`);
  else if(brief){
    if(brief.hook) body+=briefSect("Hook",`<div style="font-size:14px;font-weight:600;line-height:1.5">${esc(brief.hook)}</div>`);
    if(Array.isArray(brief.structure)&&brief.structure.length) body+=briefSect("Structure",`<ol style="margin:0;padding-left:18px;font-size:13px;line-height:1.7">${brief.structure.map(s=>`<li>${esc(s)}</li>`).join("")}</ol>`);
    if(brief.caption) body+=briefSect("Caption",`<div style="font-size:13px;line-height:1.6;white-space:pre-wrap;background:rgba(0,0,0,.03);border-radius:10px;padding:11px 13px">${esc(brief.caption)}</div>`);
    if(brief.cta) body+=briefSect("CTA",`<div style="font-size:13px;line-height:1.5">${esc(brief.cta)}</div>`);
    if(Array.isArray(brief.hashtags)&&brief.hashtags.length) body+=briefSect("Hashtags",`<div style="font-size:12px;color:var(--sky)">${esc(brief.hashtags.map(h=>h.startsWith("#")?h:"#"+h).join(" "))}</div>`);
    const vb=brief.visual_brief;
    if(vb&&typeof vb==="object"){
      const rows=[["What it shows",vb.description],["Mood",vb.mood],["Format",vb.format_specs],
                  ["Overlays",Array.isArray(vb.text_overlays)?vb.text_overlays.join(" · "):vb.text_overlays],
                  ["Gen prompt",vb.genai_prompt_draft]]
        .filter(([,v])=>v).map(([k,v])=>`<div style="font-size:12.5px;line-height:1.55;margin-bottom:4px"><b style="color:var(--ink2)">${esc(k)}:</b> ${esc(v)}</div>`).join("");
      if(rows) body+=briefSect("Visual brief",rows);
    }
    if(brief.notes_for_human) body+=briefSect("⚑ For human",`<div style="font-size:12.5px;line-height:1.55;color:#b9770e">${esc(brief.notes_for_human)}</div>`);
  } else {
    body+=`<div style="margin-top:16px;color:var(--dim);font-size:13px">Not written yet${n&&n.brief?` — click <b>${esc(n.label)}</b> to generate.`:"."}</div>`;
  }
  return body;
}

// ── Post detail (replaces showDetail modal) ──────────────────────────────────
async function renderPostDetail(id, profileSlug){
  let detail; try{ detail=await api(`/api/post/${id}`); }catch(e){ return toast("✗ "+e.message); }
  const slot=detail.slot||{}, brief=detail.brief||null;
  const st=slot.status||"planned", n=NEXT[st];
  const title=slot.working_title||slot.pillar||id;
  const canRevise=["planned","approved_slot","briefed","approved"].includes(st);
  const meta=[["Status",plainStatus(st)],["Date",slot.date],["Pillar",slot.pillar],
              ["Objective",slot.objective],["Channels",(slot.channels||[]).join(", ")]]
    .filter(([,v])=>v).map(([k,v])=>`<span style="font-size:11px;color:var(--dim)"><b style="color:var(--ink2)">${esc(k)}:</b> ${esc(v)}</span>`).join("");
  const crumb=(_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{}).name||profileSlug||"Back";
  const btns=[
    `<button class="btn danger-btn" id="pd-del">Delete</button>`,
    n?`<button class="btn primary" id="pd-next">${esc(n.label)}</button>`:"",
    canRevise?`<button class="btn" id="pd-revise">✨ Revise</button>`:"",
    `<button class="btn" id="pd-edit">Edit</button>`,
  ].filter(Boolean).join("");
  $("#main").innerHTML=`${pageHeader(title,crumb,btns)}
    <div class="scroll" style="max-width:640px">
      <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px">${meta}</div>
      ${renderBriefBody(slot,brief,n)}</div>`;
  document.getElementById("pd-del").onclick=()=>navigate(`#/post/${id}/delete`,{profileSlug});
  document.getElementById("pd-edit").onclick=()=>navigate(`#/post/${id}/edit`,{profileSlug});
  const rdBtn=document.getElementById("pd-revise"); if(rdBtn) rdBtn.onclick=()=>navigate(`#/post/${id}/revise`,{profileSlug});
  const nb=document.getElementById("pd-next"); if(nb) nb.onclick=async()=>{
    nb.disabled=true;
    try{ if(n.brief){ toast("Writing via claude -p…",true); await api(`/api/post/${id}/brief`,{method:"POST"}); toast("Draft ready ✓"); }
      else{ await api(`/api/post/${id}/status`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({status:n.to})}); toast("✓ "+plainStatus(n.to)); }
      navigate(`#/post/${id}`,{profileSlug}); }
    catch(e){ nb.disabled=false; toast("✗ "+e.message); }
  };
}

// ── Edit post (replaces rowMenu modal) ───────────────────────────────────────
async function renderEditPost(id, profileSlug){
  let detail; try{ detail=await api(`/api/post/${id}`); }catch(e){ return toast("✗ "+e.message); }
  const slot=detail.slot||{};
  const profNode=_TREE.flatMap(p=>p.profiles).find(pr=>pr.slug===profileSlug)||{channels:[]};
  const chanHint=(profNode.channels||[]).map(c=>c.slug).join(", ")||"e.g. my-profile-tiktok";
  const crumb=profNode.name||profileSlug||"Back";
  $("#main").innerHTML=`${pageHeader("Edit post",crumb,`<button class="btn danger-btn" id="ep-del">Delete</button><button class="btn primary" id="ep-save">Save</button>`)}
    <div class="scroll"><div class="fpage">
      ${flabel("Title")}${finput("working_title",slot.working_title||"",'placeholder="short internal label"')}
      ${flabel("Concept")}${fta("concept",slot.concept||"",3,'placeholder="what this post does and why"')}
      ${flabel("Date")}${finput("date",slot.date||"",'type="date"')}
      ${flabel("Pillar")}${finput("pillar",slot.pillar||"")}
      ${flabel("Channels (slugs, comma-separated)")}${finput("channels",(slot.channels||[]).join(", "),`placeholder="${chanHint}"`)}
    </div></div>`;
  document.getElementById("ep-save").onclick=async()=>{
    const data=formVals($("#main"));
    try{ await api(`/api/post/${id}/update`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
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
  $("#main").innerHTML=`${pageHeader("✨ Revise with AI",title,`<button class="btn primary" id="rv-go">Revise</button>`)}
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
  $("#main").innerHTML=`${pageHeader("Edit project",e.name||slug,`<button class="btn danger-btn" id="ep2-del">Delete project</button><button class="btn primary" id="ep2-save">Save</button>`)}
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
  $("#main").innerHTML=`${pageHeader(`${PLATFORM_ICON[ch.platform]||"⌗"} ${ch.name||ch.platform||channelSlug} setup`,crumb,`<button class="btn danger-btn" id="cs-del">Delete channel</button><button class="btn primary" id="cs-save">Save</button>`)}
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
  $("#main").innerHTML=`<div class="topbar"><div><div class="crumbs"><a class="bk" style="cursor:pointer;color:var(--sky)">← Back</a></div><h1 class="title">${esc(title)}</h1></div></div>
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
  let title=id; try{ const d=await api(`/api/post/${id}`); title=(d.slot||{}).working_title||(d.slot||{}).pillar||id; }catch(_){}
  confirmPage("Delete post","Delete this post and its written content? This cannot be undone.",async()=>{
    try{ await api(`/api/post/${id}/delete`,{method:"POST"}); toast("Deleted ✓"); await renderRail(); navigate(`#/profile/${profileSlug}`); }
    catch(e){ toast("✗ "+e.message); }
  });
}

async function renderConfirmBulkDelete(ids, profileSlug){
  const n=ids.length;
  confirmPage("Delete posts",`Delete ${n} post${n!==1?"s":""} and their written content? This cannot be undone.`,async()=>{
    try{ const r=await api("/api/posts/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ids})});
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
  let chatPos = "right", chatHidden = false;
  try {
    chatPos = localStorage.getItem("chatPos") || "right";
    chatHidden = localStorage.getItem("chatHidden") === "1";
  } catch {}
  function applyChat(){
    appEl.classList.toggle("chat-bl", chatPos === "bl" && !chatHidden);
    appEl.classList.toggle("chat-hidden", chatHidden);
    const moveBtn = document.getElementById("chat-move");
    if (moveBtn){
      moveBtn.textContent = chatPos === "bl" ? "⇱" : "⇲";
      moveBtn.title = chatPos === "bl" ? "Move chat to the right" : "Move chat to bottom-left";
    }
    try {
      localStorage.setItem("chatPos", chatPos);
      localStorage.setItem("chatHidden", chatHidden ? "1" : "");
    } catch {}
  }
  document.getElementById("chat-move").onclick   = () => { chatPos = chatPos === "bl" ? "right" : "bl"; chatHidden = false; applyChat(); };
  document.getElementById("chat-hide").onclick   = () => { chatHidden = true; applyChat(); };
  document.getElementById("chat-reopen").onclick = () => { chatHidden = false; applyChat(); };
  document.getElementById("chat-clear").onclick  = () => {
    history.length = 0; stream.innerHTML = ""; statusEl.textContent = "Ready";
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
  applyChat();

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
      const t = await file.text();
      if (t.indexOf(String.fromCharCode(0)) !== -1) return `[binary: ${file.name}]`;  // NUL byte => not text
      return t;
    } catch { return `[binary: ${file.name}]`; }
  }
  async function addFiles(fileList){
    for (const file of fileList) {
      attachedFiles.push({ name: file.name, content: await readFile(file) });
    }
    renderAttachments();
  }

  attachBtn.onclick = () => fileInput.click();
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

  function mentionCandidates(){
    const out = [];
    for (const p of _TREE) {
      out.push({ type:"project", slug:p.slug, name:p.name, meta:(p.kind||p.type||"project") });
      for (const prof of (p.profiles||[])) {
        out.push({ type:"profile", slug:prof.slug, name:prof.name, meta:"profile" });
        for (const ch of (prof.channels||[]))
          out.push({ type:"channel", slug:ch.slug, name:(ch.name||ch.platform), meta:(ch.platform||"channel") });
      }
    }
    return out;
  }
  // the @-query immediately left of the caret, or null
  function activeQuery(){
    const pos = input.selectionStart;
    const before = input.value.slice(0, pos);
    const m = before.match(/(^|\s)@([\w-]*)$/);
    return m ? { q: m[2].toLowerCase(), start: pos - m[2].length - 1, end: pos } : null;
  }
  function closeMenu(){ menu.style.display = "none"; menuItems = []; menuIdx = 0; }
  function openMenu(){
    const aq = activeQuery();
    if (!aq) return closeMenu();
    menuItems = mentionCandidates()
      .filter(c => c.slug.toLowerCase().includes(aq.q) || c.name.toLowerCase().includes(aq.q))
      .slice(0, 8);
    if (!menuItems.length) return closeMenu();
    menuIdx = Math.min(menuIdx, menuItems.length - 1);
    const ICON = { project:"▣", profile:"◐", channel:"▶" };
    menu.innerHTML = menuItems.map((c, i) =>
      `<div class="mi${i===menuIdx?" sel":""}" data-i="${i}">
         <span class="mi-ic">${ICON[c.type]}</span><b>${esc(c.name)}</b>
         <span class="mi-meta">${esc(c.type)} · ${esc(c.meta)}</span></div>`
    ).join("");
    menu.querySelectorAll(".mi").forEach(el =>
      el.onmousedown = e => { e.preventDefault(); pickMention(+el.dataset.i); });
    menu.style.display = "block";
  }
  function pickMention(i){
    const c = menuItems[i]; if (!c) return;
    const aq = activeQuery(); if (!aq) return;
    const token = "@" + c.slug;
    input.value = input.value.slice(0, aq.start) + token + " " + input.value.slice(aq.end);
    const caret = aq.start + token.length + 1;
    input.setSelectionRange(caret, caret);
    if (!mentions.some(m => m.token === token))
      mentions.push({ token, type:c.type, slug:c.slug, name:c.name });
    closeMenu(); input.focus();
    input.dispatchEvent(new Event("input"));   // keep textarea autosize in sync
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

  function addMsg(role, text){
    const div = document.createElement("div");
    div.className = "msg " + (role === "user" ? "me" : "ai");
    div.innerHTML = `<div class="b"></div>`;
    div.querySelector(".b").textContent = text;
    stream.appendChild(div);
    stream.scrollTop = stream.scrollHeight;
    return div.querySelector(".b");
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

  function buildContext(text){
    const title = document.querySelector(".title");
    const crumbs = document.querySelector(".crumbs");
    let ctx = "";
    if (crumbs) ctx += "Current view: " + crumbs.textContent + "\n";
    if (title)  ctx += "Section: " + title.textContent + "\n";
    // resolve @-mentions still present in the message to exact entity slugs
    const refs = mentions.filter(m => text.includes(m.token));
    if (refs.length) {
      ctx += "\n## Referenced entities\n" + refs.map(m =>
        `- ${m.type} "${m.name}" (slug: ${m.slug})`
      ).join("\n") + "\n";
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
    input.style.height = "42px";
    statusEl.textContent = "thinking…";
    sendBtn.disabled = true;

    const fileNote = attachedFiles.length ? ` [+${attachedFiles.length} file${attachedFiles.length>1?"s":""}]` : "";
    history.push({ role: "user", content: text });
    addMsg("user", text + fileNote);

    const ctx = buildContext(text);
    attachedFiles = []; renderAttachments();
    mentions = [];

    const bubble = addMsg("assistant", ""); bubble.textContent = ""; let full = "";
    startTurnSteps(bubble.parentElement);   // steps line lives just above this answer
    let pendingBreak = false;

    try {
      const resp = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: text }], context: ctx })
      });

      if (!resp.ok) {
        const j = await resp.json().catch(() => ({}));
        bubble.textContent = "Error: " + (j.error || resp.status);
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
            if (obj.error) { bubble.textContent = "Error: " + obj.error; return; }
            if (obj.delta) {
              // A tool call ran between two narration segments — start the next
              // one on a fresh line so thoughts don't run together ("week.14").
              if (pendingBreak && full && !full.endsWith("\n")) full += "\n";
              pendingBreak = false;
              full += obj.delta; bubble.textContent = full; stream.scrollTop = stream.scrollHeight;
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
      statusEl.textContent = "Ready";
    } catch(e) {
      bubble.textContent = "Error: " + e.message;
      history.pop(); statusEl.textContent = "Error";
    } finally {
      finalizeSteps();                // turn the live steps line into a quiet summary
      busy = false; sendBtn.disabled = false; input.focus();
      refreshViews().catch(()=>{});   // act directly → show result
    }
  }

  sendBtn.onclick = send;
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  addMsg("assistant", "Hi — I run your GTM OS. Ask me to create or change things (projects, profiles, channels, posts, activities, milestones) and I'll do it directly and refresh the view. For power work, open the terminal with ⌃` .");
})();

boot();
