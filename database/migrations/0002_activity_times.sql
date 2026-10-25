-- Timed activities: the CEO has one calendar across every workspace, so an
-- activity may carry a start/end time (HH:MM, same day) and bots may not book
-- overlapping times (fileops.find_overlaps).
ALTER TABLE activities ADD COLUMN time TEXT;
ALTER TABLE activities ADD COLUMN time_end TEXT;

DROP VIEW timeline;
CREATE VIEW timeline AS
  SELECT x.started_on AS date, NULL AS date_end, x.entity_slug AS entity_slug,
         'experiment' AS kind, x.assumption AS title, x.status AS status,
         e.priority AS priority, e.hours_per_week AS hours_per_week,
         NULL AS ref_id, NULL AS time, NULL AS time_end
  FROM experiments x LEFT JOIN entities e ON e.slug = x.entity_slug
  UNION ALL
  SELECT p.date, NULL, p.profile_slug, 'post',
         COALESCE(p.working_title, p.pillar, ''), p.status, e.priority, e.hours_per_week, p.id, NULL, NULL
  FROM posts p LEFT JOIN entities e ON e.slug = p.profile_slug
  UNION ALL
  SELECT COALESCE(f.shipped_date, f.target_date), NULL, f.product_slug, 'feature',
         f.title, f.status, COALESCE(f.priority, e.priority), e.hours_per_week, NULL, NULL, NULL
  FROM features f LEFT JOIN entities e ON e.slug = f.product_slug
  UNION ALL
  SELECT a.date, a.date_end, a.entity_slug, 'activity', a.title, a.status,
         COALESCE(a.priority, e.priority), e.hours_per_week, NULL, a.time, a.time_end
  FROM activities a LEFT JOIN entities e ON e.slug = a.entity_slug
  UNION ALL
  SELECT m.date, m.date_end, m.entity_slug, 'milestone', m.title, NULL,
         COALESCE(m.priority, e.priority), e.hours_per_week, m.id, NULL, NULL
  FROM milestones m LEFT JOIN entities e ON e.slug = m.entity_slug;
