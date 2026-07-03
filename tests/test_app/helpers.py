"""Shared AppTest widget lookups for the app-integration tests."""


def find_slider(at, label_substring):
    """Return the first slider whose label contains ``label_substring`` (case-insensitive)."""
    return next(s for s in at.slider if label_substring.lower() in s.label.lower())


def find_button(at, label_substring):
    """Return the first button whose label contains ``label_substring`` (case-insensitive)."""
    return next(b for b in at.button if label_substring.lower() in b.label.lower())
