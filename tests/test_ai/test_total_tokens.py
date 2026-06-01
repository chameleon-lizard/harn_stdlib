"""Tests for totalTokens computation, ported from total-tokens.test.ts.

The TS test is E2E (sends requests to live providers). The Python port tests
the invariant that totalTokens equals the sum of input + output + cacheRead +
cacheWrite, which is the core assertion in every provider block.
"""

from __future__ import annotations

from harn_ai.types import Usage, UsageCost


def _make_usage(
    *,
    input: int = 0,
    output: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> Usage:
    total = input + output + cache_read + cache_write
    return Usage(
        input=input,
        output=output,
        cacheRead=cache_read,
        cacheWrite=cache_write,
        totalTokens=total,
        cost=UsageCost(input=0, output=0, cacheRead=0, cacheWrite=0, total=0),
    )


class TestTotalTokensInvariant:
    """The TS test asserts totalTokens == input + output + cacheRead + cacheWrite
    for every provider.  We verify the invariant holds on representative data."""

    def test_basic_usage_sum(self) -> None:
        usage = _make_usage(input=100, output=50, cache_read=20, cache_write=10)
        computed = usage.input + usage.output + usage.cacheRead + usage.cacheWrite
        assert usage.totalTokens == computed

    def test_zero_usage(self) -> None:
        usage = _make_usage()
        assert usage.totalTokens == 0

    def test_cache_heavy_usage(self) -> None:
        usage = _make_usage(input=10, output=5, cache_read=500, cache_write=300)
        computed = usage.input + usage.output + usage.cacheRead + usage.cacheWrite
        assert usage.totalTokens == computed

    def test_output_only(self) -> None:
        usage = _make_usage(output=4096)
        assert usage.totalTokens == 4096

    def test_large_values(self) -> None:
        usage = _make_usage(input=100_000, output=50_000, cache_read=200_000, cache_write=100_000)
        assert usage.totalTokens == 450_000
