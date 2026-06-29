"""Tests for seatrades/blocks.py — block code → human label decoder."""

import pytest

from seatrades.blocks import BLOCK_DECODER_CAPTION, block_label


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ("1a", "1st·AM"),
        ("1b", "1st·PM"),
        ("2a", "2nd·AM"),
        ("2b", "2nd·PM"),
    ],
)
def test_block_label_decodes_half_and_fleet(code, label):
    """First digit = half of week (1st/2nd); letter = fleet (a→AM, b→PM)."""
    assert block_label(code) == label


def test_decoder_caption_explains_both_axes():
    """The caption must explain both the half-of-week and the AM/PM fleet axes."""
    assert "half of week" in BLOCK_DECODER_CAPTION
    assert "morning/afternoon fleet" in BLOCK_DECODER_CAPTION
