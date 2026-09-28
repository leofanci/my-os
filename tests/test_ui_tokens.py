from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


def test_ui_tokens_load_before_component_css():
    html = (DASHBOARD / "app.html").read_text(encoding="utf-8")
    assert html.index('/ui-tokens.css') < html.index('/app.css')


def test_ui_tokens_are_canonical_source():
    tokens = (DASHBOARD / "ui-tokens.css").read_text(encoding="utf-8")
    app_css = (DASHBOARD / "app.css").read_text(encoding="utf-8")

    required = (
        "--ui-color-canvas:",
        "--ui-type-body:",
        "--ui-space-2:",
        "--ui-radius-card:",
        "--ui-control-default:",
        "--ui-shell-nav:",
        "--ui-shell-assistant-default:",
        "--ui-header-height:",
        "--ui-motion-fast:",
    )
    assert all(token in tokens for token in required)
    assert ":root" not in app_css
    assert ".app{--chat-w:" not in app_css
    assert "grid-template-columns:250px" not in app_css


def test_all_css_custom_properties_resolve():
    styles = "\n".join(
        (DASHBOARD / name).read_text(encoding="utf-8")
        for name in ("ui-tokens.css", "app.css")
    )
    definitions = set(re.findall(r"(--[\w-]+)\s*:", styles))
    uses = set(re.findall(r"var\((--[\w-]+)", styles))
    assert uses <= definitions


def test_layout_javascript_reads_css_tokens():
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    for token in (
        "--ui-shell-assistant-min",
        "--ui-shell-assistant-max",
        "--ui-shell-assistant-default",
        "--ui-shell-assistant-height-min",
        "--ui-shell-assistant-height-max",
        "--ui-shell-assistant-height-default",
    ):
        assert token in app_js


def test_server_serves_token_asset():
    server = (DASHBOARD / "server.py").read_text(encoding="utf-8")
    assert '"ui-tokens.css"' in server
    assert '"/ui-tokens.css"' in server


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_functional_text_colors_meet_wcag_aa():
    tokens = (DASHBOARD / "ui-tokens.css").read_text(encoding="utf-8")

    def value(name: str) -> str:
        match = re.search(rf"{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", tokens)
        assert match, name
        return match.group(1)

    for name in (
        "--ui-color-text",
        "--ui-color-text-secondary",
        "--ui-color-accent",
        "--ui-color-danger",
    ):
        assert _contrast_ratio(value(name), "#FFFFFF") >= 4.5
    assert _contrast_ratio(value("--ui-color-text-muted"), value("--ui-color-canvas")) >= 4.5


def test_semantic_colors_meet_wcag_aa_on_tinted_backgrounds():
    tokens = (DASHBOARD / "ui-tokens.css").read_text(encoding="utf-8")

    def hex_value(name: str) -> str:
        match = re.search(rf"{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", tokens)
        assert match, name
        return match.group(1)

    def composited_soft(name: str) -> str:
        match = re.search(rf"{re.escape(name)}:\s*rgba\((\d+),\s*(\d+),\s*(\d+),\s*([.\d]+)\)", tokens)
        assert match, name
        red, green, blue = (int(match.group(index)) for index in (1, 2, 3))
        alpha = float(match.group(4))
        mixed = [round(channel * alpha + 255 * (1 - alpha)) for channel in (red, green, blue)]
        return "#" + "".join(f"{channel:02X}" for channel in mixed)

    pairs = (
        ("--ui-color-warning", "--ui-color-warning-soft"),
        ("--ui-color-success", "--ui-color-success-soft"),
        ("--ui-kind-activity", "--ui-kind-activity-soft"),
        ("--ui-kind-experiment", "--ui-kind-experiment-soft"),
        ("--ui-kind-milestone", "--ui-kind-milestone-soft"),
        ("--ui-kind-feature", "--ui-kind-feature-soft"),
    )
    for foreground, background in pairs:
        assert _contrast_ratio(hex_value(foreground), composited_soft(background)) >= 4.5


def test_assistant_becomes_overlay_before_workspace_is_cramped():
    tokens = (DASHBOARD / "ui-tokens.css").read_text(encoding="utf-8")
    app_css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert "--ui-breakpoint-assistant-overlay: 1440px" in tokens
    assert "@media (max-width:1440px)" in app_css
    assert '#chat-dock{position:fixed' in app_css
    assert 'grid-template-areas:"nav center"' in app_css
    assert '.app.chat-bl{grid-template-rows:minmax(0,1fr)}' in app_css
    assert 'cssPx("--ui-breakpoint-assistant-overlay", 1440)' in app_js


def test_calendar_events_have_non_color_and_keyboard_cues():
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    assert 'role="button" tabindex="0"' in app_js
    assert 'aria-label="${esc(label)}"' in app_js
    assert 'class="ev-mark"' in app_js
    assert 'e.key==="Enter"||e.key===" "' in app_js


def test_project_edit_action_reveals_on_actual_row_hover():
    app_css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    assert "[data-toggle-project]:hover .rail-edit" in app_css
    assert "[data-toggle-project]:focus-within .rail-edit" in app_css


def test_terminal_theme_reads_canonical_tokens():
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    app_css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    assert 'cssValue("--ui-font-mono"' in app_js
    assert 'cssPx("--ui-terminal-font-size"' in app_js
    assert 'cssValue("--ui-color-terminal"' in app_js
    assert "background:#1e1e28" not in app_css
    assert "background:#241F1B" not in app_css


def test_filter_chips_use_pointer_appropriate_targets():
    app_css = (DASHBOARD / "app.css").read_text(encoding="utf-8")
    assert ".chip,.kchip{min-height:var(--ui-control-dense)" in app_css
    assert ".kid a,.rail-edit,.chip,.kchip{min-width:var(--ui-control-touch);min-height:var(--ui-control-touch)}" in app_css


def test_kernel_logo_is_wired_into_dashboard_shell():
    logo = DASHBOARD / "logo.svg"
    html = (DASHBOARD / "app.html").read_text(encoding="utf-8")
    app_js = (DASHBOARD / "app.js").read_text(encoding="utf-8")
    server = (DASHBOARD / "server.py").read_text(encoding="utf-8")

    assert logo.read_text(encoding="utf-8").startswith("<svg")
    assert '<link rel="icon" href="/logo.svg" type="image/svg+xml">' in html
    assert '<img class="mark" src="/logo.svg" alt="">' in app_js
    assert '"/logo.svg"' in server
    assert '"image/svg+xml"' in server
