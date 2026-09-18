(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.PostCopy = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const SKIP_KEYS = new Set([
    "id", "channels", "slide",
    "platform", "format", "objective", "pillar", "status", "date", "version",
    "brief_id", "voice_id", "profile_slug", "post_id",
    "gen_prompts", "visual_brief", "structure", "notes_for_human",
  ]);

  function textBlock(value) {
    if (value == null) return "";
    if (typeof value === "string") return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return "";
  }

  function valueBlocks(value) {
    const direct = textBlock(value);
    if (direct) return [direct];
    if (Array.isArray(value)) return value.flatMap(valueBlocks);
    if (!value || typeof value !== "object") return [];
    const keys = Object.keys(value).filter(key => !key.startsWith("_"));
    if (typeof value.overlay === "string" && keys.every(key => key === "slide" || key === "overlay")) {
      return value.overlay.trim() ? [value.overlay.trim()] : [];
    }
    return Object.entries(value).flatMap(([key, nested]) => {
      if (key.startsWith("_") || SKIP_KEYS.has(key)) return [];
      return valueBlocks(nested);
    });
  }

  function formatPostContent(slot, brief) {
    if (brief && !brief._error) {
      return Object.entries(brief)
        .flatMap(([key, value]) => {
          if (key.startsWith("_") || SKIP_KEYS.has(key)) return [];
          return valueBlocks(value);
        })
        .filter(Boolean)
        .join("\n\n");
    }
    return [slot && slot.working_title, slot && slot.concept, slot && slot.notes]
      .map(textBlock)
      .filter(Boolean)
      .join("\n\n");
  }

  return { formatPostContent };
});
