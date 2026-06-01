"""Tests for UUIDv7 generation, ported from session-uuid.test.ts.

Tests that uuidv7() produces RFC 9562-compliant UUIDv7 values with
correct layout and monotonic ordering.
"""

from __future__ import annotations

import re

from harn_agent.harness.session.uuid import uuidv7

UUID_V7_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _parse_timestamp(uuid: str) -> int:
    return int(uuid.replace("-", "")[:12], 16)


class TestUuidv7:
    """Ported from session-uuid.test.ts."""

    def test_produces_valid_uuidv7_format(self) -> None:
        uuid = uuidv7()
        assert UUID_V7_RE.match(uuid), f"UUID {uuid} does not match UUIDv7 format"

    def test_multiple_uuids_are_unique(self) -> None:
        uuids = {uuidv7() for _ in range(100)}
        assert len(uuids) == 100

    def test_preserves_monotonic_order(self) -> None:
        uuids = [uuidv7() for _ in range(10)]
        for i in range(len(uuids) - 1):
            assert uuids[i] < uuids[i + 1], (
                f"UUIDs not monotonically ordered: {uuids[i]} >= {uuids[i + 1]}"
            )

    def test_version_nibble_is_7(self) -> None:
        uuid = uuidv7()
        # Version is bits 48-51 (7th character after removing dashes)
        raw = uuid.replace("-", "")
        version_nibble = int(raw[12], 16)
        assert version_nibble == 7

    def test_variant_bits_are_10xx(self) -> None:
        uuid = uuidv7()
        raw = uuid.replace("-", "")
        # Variant is bits 64-65 (17th character: 8,9,a,b)
        variant_nibble = int(raw[16], 16)
        assert variant_nibble in (8, 9, 0xA, 0xB)

    def test_timestamp_is_embedded(self) -> None:
        import time

        before = int(time.time() * 1000)
        uuid = uuidv7()
        after = int(time.time() * 1000)

        ts = _parse_timestamp(uuid)
        assert before <= ts <= after + 1
