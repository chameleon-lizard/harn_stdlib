"""Tests for syntax highlight renderer, ported from syntax-highlight.test.ts.

Tests the HTML-based syntax highlight renderer that converts highlighted
spans with a provided theme, and the Pygments-based code highlighter.
"""

from __future__ import annotations

from harn_coding_agent.utils.syntax_highlight import (
    highlight,
    render_highlighted_html,
    supports_language,
)


class TestSyntaxHighlightRenderer:
    """Ported from syntax-highlight.test.ts."""

    def test_renders_highlighted_spans_with_provided_theme(self) -> None:
        rendered = render_highlighted_html(
            '<span class="hljs-keyword">const</span> value',
            {"keyword": lambda text: f"[keyword:{text}]"},
        )
        assert rendered == "[keyword:const] value"

    def test_decodes_html_entities_emitted_by_highlight_js(self) -> None:
        rendered = render_highlighted_html(
            '&lt;tag attr=&quot;value&quot;&gt;&amp;#x41;&#65;&lt;/tag&gt;'
        )
        assert rendered == '<tag attr="value">&#x41;A</tag>'

    def test_inherits_parent_formatting_for_unmapped_nested_scopes(self) -> None:
        interpolation = "${x}"
        rendered = render_highlighted_html(
            f'<span class="hljs-string">a<span class="hljs-subst">{interpolation}</span>b</span>',
            {"string": lambda text: f"[string:{text}]"},
        )
        assert rendered == f"[string:a][string:{interpolation}][string:b]"

    def test_keeps_parent_formatting_across_unscoped_nested_spans(self) -> None:
        rendered = render_highlighted_html(
            '<span class="hljs-string">a<span class="language-xml">b</span>c</span>',
            {"string": lambda text: f"[string:{text}]"},
        )
        assert rendered == "[string:a][string:b][string:c]"

    def test_highlights_code_through_pygments(self) -> None:
        assert supports_language("typescript") is True
        rendered = highlight("const value = 1", {
            "language": "typescript",
            "ignoreIllegals": True,
            "theme": {
                "keyword": lambda text: f"[keyword:{text}]",
                "number": lambda text: f"[number:{text}]",
            },
        })
        assert "[keyword:const]" in rendered
        assert "[number:1]" in rendered

    def test_supports_language_detection(self) -> None:
        assert supports_language("python") is True
        assert supports_language("javascript") is True
        assert supports_language("nonexistent-fake-language") is False
