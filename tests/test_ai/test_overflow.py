"""Tests for context overflow detection, ported from overflow.test.ts.

Tests the is_context_overflow() function with various provider error messages
and usage-based overflow heuristics.
"""

from __future__ import annotations

import time

from harn_ai.types import AssistantMessage, Usage, UsageCost
from harn_ai.utils.overflow import is_context_overflow


def _make_usage(
    *,
    input: int = 0,
    output: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> Usage:
    return Usage(
        input=input,
        output=output,
        cacheRead=cache_read,
        cacheWrite=cache_write,
        totalTokens=input + output + cache_read + cache_write,
        cost=UsageCost(input=0, output=0, cacheRead=0, cacheWrite=0, total=0),
    )


def _create_error_message(error_message: str) -> AssistantMessage:
    """Create an AssistantMessage with stopReason 'error' and the given error message.

    Mirrors the createErrorMessage helper in the TS test.
    """
    return AssistantMessage(
        role="assistant",
        content=[],
        api="openai-completions",
        provider="ollama",
        model="qwen3.5:35b",
        usage=_make_usage(),
        stopReason="error",
        errorMessage=error_message,
        timestamp=int(time.time() * 1000),
    )


def _create_length_stop_message(
    input_tokens: int, cache_read: int, output_tokens: int
) -> AssistantMessage:
    """Create an AssistantMessage with stopReason 'length' for Xiaomi-style overflow.

    Mirrors the createLengthStopMessage helper in the TS test.
    """
    return AssistantMessage(
        role="assistant",
        content=[],
        api="openai-completions",
        provider="xiaomi",
        model="mimo-v2.5-pro",
        usage=_make_usage(input=input_tokens, cache_read=cache_read, output=output_tokens),
        stopReason="length",
        timestamp=int(time.time() * 1000),
    )


# ---------------------------------------------------------------------------
# Error-message-based overflow detection
# ---------------------------------------------------------------------------


class TestIsContextOverflow:
    """Tests ported from overflow.test.ts describe('isContextOverflow')."""

    def test_detects_explicit_ollama_prompt_too_long_errors(self) -> None:
        message = _create_error_message(
            "400 `prompt too long; exceeded max context length by 100918 tokens`"
        )
        assert is_context_overflow(message, 32768) is True

    def test_detects_together_ai_context_length_errors(self) -> None:
        message = _create_error_message(
            "400 The input (516368 tokens) is longer than the model's context length (262144 tokens)."
        )
        assert is_context_overflow(message, 262144) is True

    def test_detects_litellm_wrapped_openai_maximum_context_length_errors(self) -> None:
        message = _create_error_message(
            "Error: 503 litellm.ServiceUnavailableError: litellm.MidStreamFallbackError: "
            "litellm.APIConnectionError: APIConnectionError: OpenAIException - "
            "Requested token count exceeds the model's maximum context length of 131072 tokens."
        )
        assert is_context_overflow(message, 131072) is True

    def test_does_not_treat_generic_non_overflow_ollama_errors_as_overflow(self) -> None:
        message = _create_error_message("500 `model runner crashed unexpectedly`")
        assert is_context_overflow(message, 32768) is False

    def test_does_not_treat_bedrock_throttling_too_many_tokens_as_overflow(self) -> None:
        """Bedrock returns this for HTTP 429 rate limiting, NOT context overflow.

        formatBedrockError uses a human-readable prefix for ThrottlingException.
        """
        message = _create_error_message(
            "Throttling error: Too many tokens, please wait before trying again."
        )
        assert is_context_overflow(message, 200000) is False

    def test_does_not_treat_bedrock_service_unavailable_as_overflow(self) -> None:
        message = _create_error_message(
            "Service unavailable: The service is temporarily unavailable."
        )
        assert is_context_overflow(message, 200000) is False

    def test_does_not_treat_generic_rate_limit_errors_as_overflow(self) -> None:
        message = _create_error_message(
            "Rate limit exceeded, please retry after 30 seconds."
        )
        assert is_context_overflow(message, 200000) is False

    def test_does_not_treat_http_429_style_errors_as_overflow(self) -> None:
        message = _create_error_message("Too many requests. Please slow down.")
        assert is_context_overflow(message, 200000) is False

    # -----------------------------------------------------------------------
    # Xiaomi-style overflow: length stop with zero output and filled context
    # -----------------------------------------------------------------------

    def test_detects_xiaomi_style_overflow_length_stop_zero_output_filled_context(self) -> None:
        message = _create_length_stop_message(58, 1048512, 0)
        assert is_context_overflow(message, 1048576) is True

    def test_does_not_treat_normal_length_stops_with_output_as_overflow(self) -> None:
        message = _create_length_stop_message(1000, 0, 4096)
        assert is_context_overflow(message, 200000) is False

    def test_does_not_treat_length_stops_far_below_context_as_overflow(self) -> None:
        message = _create_length_stop_message(100, 0, 0)
        assert is_context_overflow(message, 200000) is False
