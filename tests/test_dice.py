"""Cross-check the DP distribution against full brute-force path enumeration.

With small face counts every joint roll path can be enumerated, so the
"keep top K" dynamic program is tested exactly (same Fraction probabilities)
against an independent algorithm.
"""

from fractions import Fraction

import pytest

from itertools import combinations

from dice import (
    MAX_DICE,
    MAX_FACES,
    enumerate_distribution,
    expected_score,
    one_die_distribution,
    one_die_leaves,
    probability_at_least,
    top_k_distribution,
    validate_params,
)


def _subsets(values):
    """All subsets of a small list, each as a frozenset."""
    return [
        frozenset(c)
        for r in range(len(values) + 1)
        for c in combinations(values, r)
    ]


def test_leaves_form_a_partition():
    # Every single-die path tree is an exact partition of probability.
    for faces in range(2, 9):
        for reroll in _subsets(range(1, faces + 1)):
            leaves = one_die_leaves(faces, reroll)
            total = sum((p for _, p in leaves), Fraction(0))
            assert total == 1, (faces, reroll)


def test_face_value_f_is_impossible():
    # A final face of F always carries a bonus, so plain F has mass 0.
    for faces in range(2, 9):
        dist = one_die_distribution(faces, frozenset())
        assert dist.get(faces, 0) == 0
        assert all(1 <= value <= 2 * faces for value in dist)


def test_known_two_sided_all_reroll():
    # F=2, every face rerolled: the first roll is information-free, so the
    # distribution is the ordinary "roll d2, add d2 on a 2".
    # d2=1 -> 1 ; d2=2 -> 3 or 4, each with probability 1/4.
    dist = one_die_distribution(2, frozenset({1, 2}))
    assert dist == {1: Fraction(1, 2), 3: Fraction(1, 4), 4: Fraction(1, 4)}
    assert expected_score(dist) == Fraction(9, 4)


def test_known_two_dice_keep_one_two_sided():
    # Two d2 (no reroll), keep the highest:
    # values {1,3,4} with probs {1/2,1/4,1/4}.
    # P(max=1)=1/4, P(max=3)=P(no 4, some 3)= (3/4)^2-(1/2)^2=5/16,
    # P(max=4)=1-(3/4)^2=7/16.
    dist = top_k_distribution(2, 2, 1, frozenset())
    assert dist == {
        1: Fraction(1, 4),
        3: Fraction(5, 16),
        4: Fraction(7, 16),
    }
    assert sum(dist.values(), Fraction(0)) == 1


# F=2: enumerate all reroll subsets for every legal (n, k).
F2_CASES = [
    (n, 2, k, reroll)
    for n in range(1, 7)
    for k in range(1, n + 1)
    for reroll in _subsets([1, 2])
]

# F=3: every reroll subset, modest dice counts (8^? leaf product grows).
F3_CASES = [
    (n, 3, k, reroll)
    for n in range(1, 5)
    for k in range(1, n + 1)
    for reroll in _subsets([1, 2, 3])
]

# F=4: a representative spread of reroll sets, tiny dice counts.
F4_CASES = [
    (n, 4, k, reroll)
    for n in range(1, 4)
    for k in range(1, n + 1)
    for reroll in [
        frozenset(),
        frozenset({1}),
        frozenset({4}),
        frozenset({1, 4}),
        frozenset({2, 3}),
    ]
]

ALL_ENUM_CASES = F2_CASES + F3_CASES + F4_CASES


@pytest.mark.parametrize("n,faces,keep,reroll", ALL_ENUM_CASES)
def test_dp_matches_bruteforce_paths(n, faces, keep, reroll):
    fast = top_k_distribution(n, faces, keep, reroll)
    brute = enumerate_distribution(n, faces, keep, reroll)

    # Same support...
    assert set(fast) == set(brute), (n, faces, keep, reroll)
    # ...same exact reduced probability at every total.
    for score in fast:
        assert fast[score] == brute[score], (n, faces, keep, reroll, score)
    # And the partition property for both.
    assert sum(fast.values(), Fraction(0)) == 1
    assert sum(brute.values(), Fraction(0)) == 1


@pytest.mark.parametrize("faces", range(2, 9))
@pytest.mark.parametrize("n", range(1, 7))
@pytest.mark.parametrize("keep", range(1, 7))
def test_distribution_sums_to_one_over_full_grid(n, faces, keep):
    if keep > n:
        with pytest.raises(ValueError):
            validate_params(n, faces, keep, frozenset())
        return
    _, _, _, reroll = validate_params(n, faces, keep, frozenset({1, faces}))
    dist = top_k_distribution(n, faces, keep, reroll)
    assert sum(dist.values(), Fraction(0)) == 1

    # Score support is always within [keep, 2*faces*keep].
    assert min(dist) >= keep
    assert max(dist) <= 2 * faces * keep

    # Tail probabilities for extreme thresholds are 0 and 1.
    assert probability_at_least(dist, 2 * faces * keep + 1) == 0
    assert probability_at_least(dist, keep - 1) == 1
    assert probability_at_least(dist, keep) == 1


def test_expectation_consistency():
    # Expectation from the DP distribution vs. the brute-force oracle.
    for n, faces, keep, reroll in F2_CASES[::7]:
        fast = top_k_distribution(n, faces, keep, reroll)
        brute = enumerate_distribution(n, faces, keep, reroll)
        assert expected_score(fast) == expected_score(brute)


@pytest.mark.parametrize(
    "n,faces,keep,reroll",
    [
        (0, 6, 1, frozenset()),
        (7, 6, 1, frozenset()),
        (1, 1, 1, frozenset()),
        (1, 9, 1, frozenset()),
        (3, 6, 0, frozenset()),
        (3, 6, 4, frozenset()),
        (3, 6, 1, frozenset({0})),
        (3, 6, 1, frozenset({7})),
    ],
)
def test_invalid_params_rejected(n, faces, keep, reroll):
    with pytest.raises(ValueError):
        validate_params(n, faces, keep, reroll)


def test_reroll_deduplicated():
    _, _, _, reroll = validate_params(2, 6, 1, [1, 1, 6])
    assert reroll == frozenset({1, 6})
    assert MAX_DICE == 6 and MAX_FACES == 8
