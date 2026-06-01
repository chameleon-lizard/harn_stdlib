"""Tests for truncateToWidth and visibleWidth, ported from truncate-to-width.test.ts.

Tests the Unicode-aware text truncation and visible width measurement
utilities used for terminal rendering.
"""

from __future__ import annotations

from harn_tui.utils import normalize_terminal_output, truncate_to_width, visible_width


class TestTruncateToWidth:
    """Ported from truncate-to-width.test.ts."""

    def test_keeps_output_within_width_for_very_large_unicode_input(self) -> None:
        text = "\U0001f642\u754c" * 100_000
        truncated = truncate_to_width(text, 40, "\u2026")
        assert visible_width(truncated) <= 40
        assert truncated.endswith("\u2026\x1b[0m")

    def test_preserves_ansi_styling_for_kept_text_and_resets_around_ellipsis(self) -> None:
        text = f"\x1b[31m{'hello ' * 1000}\x1b[0m"
        truncated = truncate_to_width(text, 20, "\u2026")
        assert visible_width(truncated) <= 20
        assert "\x1b[31m" in truncated
        assert truncated.endswith("\x1b[0m\u2026\x1b[0m")

    def test_handles_malformed_ansi_escape_prefixes_without_hanging(self) -> None:
        text = f"abc\x1bnot-ansi {'\U0001f642' * 1000}"
        truncated = truncate_to_width(text, 20, "\u2026")
        assert visible_width(truncated) <= 20

    def test_clips_wide_ellipsis_safely_and_brackets_with_resets(self) -> None:
        assert truncate_to_width("abcdef", 1, "\U0001f642") == ""
        assert truncate_to_width("abcdef", 2, "\U0001f642") == "\x1b[0m\U0001f642\x1b[0m"
        assert visible_width(truncate_to_width("abcdef", 2, "\U0001f642")) <= 2

    def test_returns_original_text_when_it_already_fits_even_if_ellipsis_too_wide(self) -> None:
        assert truncate_to_width("a", 2, "\U0001f642") == "a"
        assert truncate_to_width("\u754c", 2, "\U0001f642") == "\u754c"

    def test_pads_truncated_output_to_requested_width(self) -> None:
        truncated = truncate_to_width("\U0001f642\u754c\U0001f642\u754c\U0001f642\u754c", 8, "\u2026", pad=True)
        assert visible_width(truncated) == 8

    def test_adds_trailing_reset_when_truncating_without_ellipsis(self) -> None:
        truncated = truncate_to_width(f"\x1b[31m{'hello' * 100}", 10, "")
        assert visible_width(truncated) <= 10
        assert truncated.endswith("\x1b[0m")

    def test_keeps_contiguous_prefix(self) -> None:
        truncated = truncate_to_width("\U0001f642\t\u754c \x1b_abc\x07", 7, "\u2026", pad=True)
        assert truncated == "\U0001f642\t\x1b[0m\u2026\x1b[0m "


class TestVisibleWidth:
    """Ported from truncate-to-width.test.ts: visibleWidth section."""

    def test_counts_tabs_inline_and_skips_ansi_inline(self) -> None:
        assert visible_width("\t\x1b[31m\u754c\x1b[0m") == 5

    def test_keeps_thai_and_lao_am_clusters_at_normal_cell_width(self) -> None:
        assert visible_width("\u0e33") == 1
        assert visible_width("\u0eb3") == 1
        assert visible_width("\u0e01\u0e33") == 2
        assert visible_width("\u0e81\u0eb3") == 2

    def test_normalizes_thai_and_lao_am_vowels_for_terminal_output(self) -> None:
        assert normalize_terminal_output("\u0e33") == "\u0e4d\u0e32"
        assert normalize_terminal_output("\u0eb3") == "\u0ecd\u0eb2"
        assert visible_width(normalize_terminal_output("\u0e33abc")) == visible_width("\u0e33abc")
        assert visible_width(normalize_terminal_output("\u0eb3abc")) == visible_width("\u0eb3abc")
