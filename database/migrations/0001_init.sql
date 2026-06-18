-- schema.sql — consolidated DDL for os.db (the DERIVED, DISPOSABLE index).
-- Source of truth is always the authored files; index.py wipes and rebuilds this.
-- Hierarchy: project > {profile > channel, product}. Posts are profile-level and
-- target one or more channels via post_channels.
PRAGMA foreign_keys = ON;

CREATE TABLE entities (
  slug           TEXT PRIMARY KEY,
  type           TEXT NOT NULL CHECK (type IN ('project','profile','channel','product','external')),
  subtype        TEXT,
  name           TEXT NOT NULL,
  priority       TEXT CHECK (priority IN ('primary','secondary','experiment')),
  status         TEXT NOT NULL DEFAULT 'active',
  hours_per_week INTEGER,
  file_path      TEXT,
  updated_at     TEXT NOT NULL
);

CREATE TABLE relationships (
  from_slug TEXT NOT NULL REFERENCES entities(slug),
  to_slug   TEXT NOT NULL REFERENCES entities(slug),
  kind      TEXT NOT NULL CHECK (kind IN ('belongs_to','drives_to','depends_on')),
  PRIMARY KEY (from_slug, to_slug, kind)
);

CREATE TABLE memos (
  id          INTEGER PRIMARY KEY,
  entity_slug TEXT NOT NULL REFERENCES entities(slug),
  type        TEXT NOT NULL CHECK (type IN
                ('problem-validation','assessment','channels','icp',
                 'positioning','competitors','pricing','launch')),
  version     INTEGER NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('proposed','approved','superseded')),
  file_path   TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  UNIQUE (entity_slug, type, version)
);

CREATE TABLE experiments (
  id            INTEGER PRIMARY KEY,
  entity_slug   TEXT NOT NULL REFERENCES entities(slug),
  assumption    TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('planned','running','done')),
  duration_days INTEGER,
  started_on    TEXT,
  decision      TEXT CHECK (decision IN ('persist','pivot','kill')),
  result        TEXT,
  file_path     TEXT
);

CREATE TABLE posts (
  id           TEXT PRIMARY KEY,
  profile_slug TEXT NOT NULL REFERENCES entities(slug),
  date         TEXT,
  pillar       TEXT,
  status       TEXT NOT NULL CHECK (status IN
                 ('planned','approved_slot','briefed','approved',
                  'scheduled','published','rejected')),
  version      INTEGER NOT NULL DEFAULT 1,
  brief_path   TEXT
);
CREATE INDEX idx_posts_profile_date ON posts(profile_slug, date);

CREATE TABLE post_channels (
  post_id      TEXT NOT NULL REFERENCES posts(id),
  channel_slug TEXT NOT NULL REFERENCES entities(slug),
  PRIMARY KEY (post_id, channel_slug)
);

CREATE TABLE activities (
  id          INTEGER PRIMARY KEY,
  entity_slug TEXT REFERENCES entities(slug),
  title       TEXT NOT NULL,
  date        TEXT,
  date_end    TEXT,
  type        TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','running','blocked','done')),
  priority    TEXT CHECK (priority IN ('critical','high','normal','low'))
);

CREATE TABLE features (
  id           INTEGER PRIMARY KEY,
  product_slug TEXT NOT NULL REFERENCES entities(slug),
  title        TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('idea','planned','building','shipped')),
  priority     TEXT CHECK (priority IN ('critical','high','normal','low')),
  target_date  TEXT,
  shipped_date TEXT,
  release      TEXT
);
CREATE INDEX idx_features_product_status ON features(product_slug, status);

CREATE TABLE milestones (
  id          TEXT PRIMARY KEY,
  entity_slug TEXT REFERENCES entities(slug),
  entity_type TEXT,
  type        TEXT NOT NULL,
  title       TEXT NOT NULL,
  date        TEXT NOT NULL,
  date_end    TEXT,
  priority    TEXT CHECK (priority IN ('critical','high','normal','low')),
  notes       TEXT
);

CREATE VIEW timeline AS
  SELECT x.started_on AS date, NULL AS date_end, x.entity_slug AS entity_slug,
         'experiment' AS kind, x.assumption AS title, x.status AS status,
         e.priority AS priority, e.hours_per_week AS hours_per_week
  FROM experiments x LEFT JOIN entities e ON e.slug = x.entity_slug
  UNION ALL
  SELECT p.date, NULL, p.profile_slug, 'post',
         COALESCE(p.pillar, ''), p.status, e.priority, e.hours_per_week
  FROM posts p LEFT JOIN entities e ON e.slug = p.profile_slug
  UNION ALL
  SELECT COALESCE(f.shipped_date, f.target_date), NULL, f.product_slug, 'feature',
         f.title, f.status, COALESCE(f.priority, e.priority), e.hours_per_week
  FROM features f LEFT JOIN entities e ON e.slug = f.product_slug
  UNION ALL
  SELECT a.date, a.date_end, a.entity_slug, 'activity', a.title, a.status,
         COALESCE(a.priority, e.priority), e.hours_per_week
  FROM activities a LEFT JOIN entities e ON e.slug = a.entity_slug
  UNION ALL
  SELECT m.date, m.date_end, m.entity_slug, 'milestone', m.title, NULL,
         COALESCE(m.priority, e.priority), e.hours_per_week
  FROM milestones m LEFT JOIN entities e ON e.slug = m.entity_slug;
