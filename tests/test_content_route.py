"""Content view in the canvas: route, breadcrumb bar, per-profile cards (static source checks)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "dashboard" / "app.js"
APP_CSS = ROOT / "dashboard" / "app.css"


def test_content_route_and_tabs():
    js = APP_JS.read_text(encoding="utf-8")
    assert r"/^\/content(?:\/(posts|calendar|briefs|voice))?$/" in js
    assert "async function renderContent(tab" in js
    assert 'data-f="ready"' in js or '["ready", "Ready"]' in js


def test_canvas_bar_shows_breadcrumb_not_sections_select():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'class="cn-crumb"' in js
    assert '<option value="">Sections…</option>' not in js   # moved into the More menu
    assert 'data-cn-more' in js


def test_focus_expands_card_beyond_page_size():
    js = APP_JS.read_text(encoding="utf-8")
    assert "focusId" in js and "PAGE_SIZE" in js
    assert 'card.querySelector(".pf-more")' in js or "limit: Infinity" in js


def test_workspace_switch_lands_on_content():
    js = APP_JS.read_text(encoding="utf-8")
    assert 'navigate(ws === "hq" ? "#/calendar" : "#/content")' in js


def test_content_view_has_empty_states():
    js = APP_JS.read_text(encoding="utf-8")
    assert "No profiles yet" in js
    assert "No posts yet" in js


def test_calendar_can_be_scoped_to_a_workspace():
    js = APP_JS.read_text(encoding="utf-8")
    assert "async function renderTimeline({ scope = null, head = null } = {})" in js
    assert "scope.has(r.entity_slug)" in js


def test_profile_cards_are_styled_with_sticky_headers():
    css = APP_CSS.read_text(encoding="utf-8")
    assert ".pf-head{" in css and "position:sticky" in css
    assert ".post-row.focused{" in css
    assert ".flash" not in css
