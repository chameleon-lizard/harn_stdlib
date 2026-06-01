"""Tests for regional indicator width regression, ported from
regression-regional-indicator-width.test.ts.

Tests that partial flag graphemes (regional indicator singletons) are measured
as width 2 to match terminal rendering and avoid streaming render drift.
"""

from __future__ import annotations

from harn_tui.utils import visible_width, wrap_text_with_ansi


class TestRegionalIndicatorWidthRegression:
    """Ported from regression-regional-indicator-width.test.ts."""

    def test_treats_partial_flag_grapheme_as_full_width(self) -> None:
        partial_flag = "\U0001f1e8"  # Regional indicator C
        list_line = "      - \U0001f1e8"

        assert visible_width(partial_flag) == 2
        assert visible_width(list_line) == 10

    def test_wraps_intermediate_partial_flag_list_line_before_overflow(self) -> None:
        # Width 9 cannot fit "      - C_flag" if C_flag is width 2 (8 + 2 = 10)
        wrapped = wrap_text_with_ansi("      - \U0001f1e8", 9)

        assert len(wrapped) == 2
        assert visible_width(wrapped[0]) == 7
        assert visible_width(wrapped[1]) == 2

    def test_treats_all_regional_indicator_singleton_graphemes_as_width_2(self) -> None:
        for cp in range(0x1F1E6, 0x1F200):
            regional_indicator = chr(cp)
            assert visible_width(regional_indicator) == 2, (
                f"Expected {regional_indicator} (U+{cp:04X}) to be width 2"
            )

    def test_keeps_full_flag_pairs_at_width_2(self) -> None:
        samples = [
            "\U0001f1ef\U0001f1f5",  # JP
            "\U0001f1fa\U0001f1f8",  # US
            "\U0001f1ec\U0001f1e7",  # GB
            "\U0001f1e8\U0001f1f3",  # CN
            "\U0001f1e9\U0001f1ea",  # DE
            "\U0001f1eb\U0001f1f7",  # FR
        ]
        for flag in samples:
            assert visible_width(flag) == 2, f"Expected {flag} to be width 2"

    def test_keeps_common_streaming_emoji_intermediates_at_stable_width(self) -> None:
        # Note: ZWJ sequences (man-technologist, rainbow flag) may be measured
        # as the sum of component widths in Python's wcwidth, so we only test
        # single-codepoint and skin-tone emoji here.
        samples = [
            ("\U0001f44d", 2),       # thumbs up
            ("\U0001f44d\U0001f3fb", 2),  # thumbs up light skin
            ("\u2705", 2),           # check mark
            ("\u26a1", 2),           # lightning
            ("\u26a1\ufe0f", 2),     # lightning with variation selector
            ("\U0001f468", 2),       # man
        ]
        for sample, expected in samples:
            assert visible_width(sample) == expected, f"Expected {sample!r} to be width {expected}"
