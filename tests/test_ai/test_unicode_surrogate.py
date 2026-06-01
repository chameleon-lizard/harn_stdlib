"""Tests for Unicode surrogate sanitization, ported from unicode-surrogate.test.ts.

The TS test is E2E (sends emoji through live provider APIs). The Python port
tests the sanitize_surrogates() utility directly to ensure it correctly handles
emoji, unpaired surrogates, and various Unicode content that would be sent to
provider APIs.
"""

from __future__ import annotations

from harn_ai.utils.sanitize_unicode import sanitize_surrogates


class TestSanitizeSurrogates:
    """Unit tests for the sanitize_surrogates helper that underpins
    provider-safe JSON serialization of Unicode content."""

    def test_preserves_normal_ascii_text(self) -> None:
        assert sanitize_surrogates("Hello World") == "Hello World"

    def test_preserves_well_formed_emoji(self) -> None:
        """Emoji like U+1F648 (see-no-evil monkey) are valid and should pass through."""
        assert sanitize_surrogates("Hello \U0001f648 World") == "Hello \U0001f648 World"

    def test_preserves_multiple_emoji(self) -> None:
        """Test with the same emoji set used in the TS unicode-surrogate.test.ts."""
        text = (
            "Test with emoji \U0001f648 and other characters:\n"
            "- Monkey emoji: \U0001f648\n"
            "- Thumbs up: \U0001f44d\n"
            "- Rocket: \U0001f680\n"
            "- Thinking face: \U0001f914"
        )
        assert sanitize_surrogates(text) == text

    def test_preserves_cjk_and_mathematical_symbols(self) -> None:
        """Japanese, Chinese, and math symbols from the TS test."""
        text = "Japanese: \u3053\u3093\u306b\u3061\u306f Chinese: \u4f60\u597d Math: \u2211\u222b\u2202\u221a"
        assert sanitize_surrogates(text) == text

    def test_preserves_german_umlauts_with_emoji(self) -> None:
        """Real-world test case from the TS unicode-surrogate.test.ts (LinkedIn data)."""
        text = "Mario Zechner wann? Wo? Bin grad \u00e4u\u00dfersr eventuninformiert \U0001f648"
        assert sanitize_surrogates(text) == text

    def test_strips_unpaired_high_surrogate(self) -> None:
        """An unpaired high surrogate (0xD83D) without its low counterpart should be removed.

        This mirrors the testUnpairedHighSurrogate scenario from the TS test.
        In Python, surrogates can appear in strings created via chr() or
        surrogateescape handling.
        """
        # Construct a string with an intentionally unpaired high surrogate
        unpaired = chr(0xD83D)  # High surrogate without low surrogate
        text = f"Text with unpaired surrogate: {unpaired} <- should be sanitized"
        result = sanitize_surrogates(text)
        assert chr(0xD83D) not in result
        assert "Text with unpaired surrogate:" in result
        assert "<- should be sanitized" in result

    def test_strips_unpaired_low_surrogate(self) -> None:
        """An unpaired low surrogate (0xDE48) should also be removed."""
        unpaired = chr(0xDE48)
        text = f"Before {unpaired} after"
        result = sanitize_surrogates(text)
        assert chr(0xDE48) not in result
        assert "Before" in result
        assert "after" in result

    def test_preserves_properly_paired_surrogates(self) -> None:
        """A proper surrogate pair (high + low) should be preserved."""
        # U+1F648 = D83D DE48 as surrogate pair
        paired = chr(0xD83D) + chr(0xDE48)
        text = f"Pair {paired} ok"
        result = sanitize_surrogates(text)
        assert result == f"Pair {paired} ok"

    def test_empty_string(self) -> None:
        assert sanitize_surrogates("") == ""

    def test_curly_quotes_and_special_punctuation(self) -> None:
        """Special quotes from the TS test: 'curly' "quotes"."""
        text = "\u201ccurly\u201d \u2018quotes\u2019"
        assert sanitize_surrogates(text) == text
