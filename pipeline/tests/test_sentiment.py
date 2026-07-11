"""Loughran-McDonald scoring contracts for compute_sentiment."""

import compute_sentiment as cs


def _sets():
    """A tiny stand-in for the LM category word-sets (words stored upper-case)."""
    return {
        "positive": {"STRONG", "GROWTH"},
        "negative": {"WEAK", "DECLINE"},
        "uncertainty": {"MAYBE"},
        "litigious": set(),
        "constraining": set(),
    }


def test_score_text_counts_categories_and_net():
    (pos, neg, unc, lit, con, lm_hits, total, net) = cs.score_text(
        "Strong growth but weak, maybe decline ahead", _sets()
    )
    assert (pos, neg, unc, lit, con) == (2, 2, 1, 0, 0)
    assert lm_hits == 5  # strong, growth, weak, maybe, decline
    assert total == 7  # every whitespace token counts toward total_words
    assert net == (pos - neg) / total


def test_score_text_net_is_signed_by_the_balance():
    _, _, _, _, _, _, total, net = cs.score_text("strong strong weak", _sets())
    assert total == 3
    assert net == (2 - 1) / 3


def test_score_text_empty_is_all_zero():
    assert cs.score_text("", _sets()) == (0, 0, 0, 0, 0, 0, 0, 0.0)
