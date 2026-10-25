// Post pipeline rules shared by the Content view, the profile page and post
// detail: which filter bucket a status belongs to, what the next step is, and
// how posts group under their profiles. Pure functions, no DOM.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ContentView = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  // Filter bucket per stored status. Ready is its own bucket, not a kind of draft.
  const STAGE_GROUP = {
    planned: "ideas", approved_slot: "ideas", briefed: "drafts",
    approved: "ready", published: "published", rejected: "archived",
  };
  // Pill class per status, shared with the calendar.
  const STATUS_PILL = {
    planned: "idea", approved_slot: "idea", briefed: "draft",
    approved: "ready", published: "published", rejected: "archived",
  };
  const STATUS_LABEL = {
    planned: "Idea", approved_slot: "Idea", briefed: "Draft",
    approved: "Ready", published: "Published", rejected: "Archived",
  };
  const BUCKETS = ["ideas", "drafts", "ready", "published", "archived"];
  const PAGE_SIZE = 5;

  const statusLabel = status => STATUS_LABEL[status] || status;

  // The one step that moves a post forward. Approving a draft is never a
  // one-click row action: "Review" opens the post, where Approve lives.
  function nextActionFor(post) {
    switch (post && post.status) {
      case "planned":
      case "approved_slot": return { label: "Write draft", kind: "brief" };
      case "briefed": return { label: "Review", kind: "review" };
      case "approved": return post.date ? { label: "Publish", kind: "publish" } : { label: "Schedule", kind: "schedule" };
      case "rejected": return { label: "Restore", kind: "restore" };
      default: return null;
    }
  }

  // Undated first (they need a date), then newest first. Returns a new array.
  function sortPosts(posts) {
    return posts
      .map((post, i) => [post, i])
      .sort(([a, i], [b, j]) => {
        if (!a.date !== !b.date) return a.date ? 1 : -1;
        if (a.date !== b.date && a.date && b.date) return a.date < b.date ? 1 : -1;
        return i - j;
      })
      .map(([post]) => post);
  }

  // One group per profile, every profile kept even when it has no posts.
  // Profiles with drafts waiting for review come first.
  function groupByProfile(posts, profiles) {
    const groups = profiles.map((profile, order) => {
      const own = sortPosts(posts.filter(p => p.profile_slug === profile.slug));
      const counts = { all: own.length };
      BUCKETS.forEach(b => { counts[b] = 0; });
      own.forEach(p => { const b = STAGE_GROUP[p.status]; if (b) counts[b] += 1; });
      return { profile, posts: own, counts, needsYou: own.filter(p => p.status === "briefed").length, order };
    });
    return groups
      .sort((a, b) => b.needsYou - a.needsYou || a.order - b.order)
      .map(({ order, ...group }) => group);
  }

  return { STAGE_GROUP, STATUS_PILL, PAGE_SIZE, statusLabel, nextActionFor, sortPosts, groupByProfile };
});
