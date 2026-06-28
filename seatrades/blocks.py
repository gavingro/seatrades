"""Pure decoder from block codes to Scheduling-Captain-friendly labels.

A block code (e.g. ``1a``) encodes two things:
- the half of the week: ``1`` = first half, ``2`` = second half
- the fleet: ``a`` = Fleet 1 (morning / AM), ``b`` = Fleet 2 (afternoon / PM)

No Streamlit, no side effects — safe to import anywhere (charts, notebooks, API).
"""

BLOCK_LABELS = {
    "1a": "1st·AM",
    "1b": "1st·PM",
    "2a": "2nd·AM",
    "2b": "2nd·PM",
}

BLOCK_DECODER_CAPTION = "1st/2nd = half of week · AM/PM = morning/afternoon fleet"


def block_label(code: str) -> str:
    """Return the compact human label for a block ``code`` (e.g. ``1a`` → ``1st·AM``)."""
    return BLOCK_LABELS[code]
