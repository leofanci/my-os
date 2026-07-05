/** os-ids.js — ID runtime + nav chrome. Tab layout/labels from /api/schemas (setSchemas). */

const PROJECT_SECTIONS = [
  {key:"overview",  ico:"◇", label:"Overview"},
  {key:"validation",ico:"◎", label:"Problem & validation"},
  {key:"experiments",ico:"⚗", label:"Experiments"},
  {key:"pricing",   ico:"◧", label:"Positioning & pricing"},
  {key:"product",   ico:"▣", label:"Product"},
  {key:"technical", ico:"⚙", label:"Technical"},
];

let _apiSchemas = null;

/** Called from app.js ensureSchemas() after /api/schemas loads. */
function setSchemas(data) {
  _apiSchemas = data || null;
}

function sectionLayout(key) {
  return (_apiSchemas?.section_layout || {})[key] || {};
}

function sectionMemoTypes(key) {
  return sectionLayout(key).memo_types || [];
}

function sectionSkills(key) {
  const lay = sectionLayout(key);
  if (lay.skills?.length) return lay.skills;
  return lay.skill ? [lay.skill] : [];
}

function memoTypeLabel(type) {
  return (_apiSchemas?.memo_type_labels || {})[type] || type;
}

/** Runtime lookup — populated from /api/id-registry after tree load. */
const IdReg = {
  lookup: {},
  byId: {},
  load(data) {
    this.lookup = (data && data.lookup) || {};
    this.byId = {};
    for (const e of ((data && data.entries) || [])) this.byId[e.id] = e;
  },
  resolve(id) { return this.byId[id] || null; },
  get(key) { return this.lookup[key] || null; },
  proj(slug) { return this.get(`proj:${slug}`); },
  prof(slug) { return this.get(`prof:${slug}`); },
  prod(slug) { return this.get(`prod:${slug}`); },
  chan(slug) { return this.get(`chan:${slug}`); },
  tabProj(p, sec) { return this.get(`tab:proj:${p}:${sec}`); },
  tabProf(p, tab) { return this.get(`tab:prof:${p}:${tab}`); },
  tabChan(c, tab) { return this.get(`tab:chan:${c}:${tab}`); },
  post(id) { return this.get(`post:${id}`); },
  brief(postId) { return this.get(`brief:post:${postId}`); },
  slotFld(postId, field) { return this.get(`sl:post:${postId}:${field}`); },
  briefFld(postId, field) { return this.get(`fld:brief:${postId}:${field}`); },
  memo(project, type, ver) { return this.get(`memo:proj:${project}:${type}-v${ver}`); },
  doc(project, docKey) { return this.get(`doc:proj:${project}:${docKey}`); },
  docSubsection(project, docKey, title) {
    return this.get(`sub:proj:${project}:${docKey}:${this.slugKey(title)}`);
  },
  profBriefSpec(profile) { return this.get(`brief-spec:prof:${profile}`); },
  profVoice(profile) { return this.get(`voice:prof:${profile}`); },
  experiment(project, stem) { return this.get(`exp:proj:${project}:${stem}`); },
  feature(product, titleKey) { return this.get(`feat:prod:${product}:${titleKey}`); },
  feat(product, titleKey) { return this.feature(product, titleKey); },
  fld(scope, owner, field) { return this.get(`fld:${scope}:${owner}:${field}`); },
  btn(scope, owner, action) { return this.get(`btn:${scope}:${owner}:${action}`); },
  route(path) {
    const clean = String(path || "").replace(/^#\/?/, "") || "calendar";
    return this.get(`route:${clean}`);
  },
  view(key) { return this.get(`view:${key}`); },
  slugKey: text => (String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "untitled"),
};

/** Back-compat alias used throughout app.js */
const OSID = IdReg;